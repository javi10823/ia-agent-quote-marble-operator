"""Context analyzer — construye el resumen de contexto que se muestra al
operador ANTES del despiece.

Principio del operador D'Angelo: Valentina nunca avanza al despiece (ni
menos al Paso 2) con datos faltantes o asunciones sin confirmar. Este
módulo arma una card de 3 secciones:

1. **Datos conocidos**: cosas que sabemos del brief o de la quote saved.
   Source: "brief" | "quote" | "catalog_match". Estos son hechos.

2. **Asunciones aplicadas**: defaults de regla de negocio o del config
   que arrancamos usando. Source: "rule" | "config_default". Estos
   requieren validación del operador.

3. **Preguntas bloqueantes**: lo que pending_questions.py detectó. Sin
   respuesta a estas, no se avanza al despiece.

Output va en un chunk `context_analysis` que el frontend renderea como
card nueva (ContextAnalysis.tsx). Cuando el operador confirma con
[CONTEXT_CONFIRMED], recién ahí se emite el `dual_read_result`.
"""
from __future__ import annotations

import re
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Helpers: extractores del brief
# ─────────────────────────────────────────────────────────────────────────────

_MATERIAL_BRIEF_KEYWORDS = (
    "silestone", "dekton", "neolith", "puraprima", "pura prima",
    "purastone", "laminatto", "granito", "mármol", "marmol",
    "negro brasil", "blanco norte", "onix", "quartz",
)


def _extract_material_from_brief(brief: str) -> str | None:
    if not brief:
        return None
    low = brief.lower()
    for k in _MATERIAL_BRIEF_KEYWORDS:
        if k in low:
            # Devuelve una slice corta alrededor del match (primeros 60 chars)
            idx = low.index(k)
            snippet = brief[idx : idx + 60].strip()
            return snippet
    return None


_LOCALIDAD_KEYWORDS = re.compile(
    r"\b(rosario|echesortu|funes|rold[aá]n|puerto\s+san\s+mart[ií]n|"
    r"granadero\s+baigorria|pueblo\s+esther|capit[aá]n\s+bermudez|"
    r"villa\s+gobernador\s+g[aá]lvez|arroyo\s+seco|san\s+lorenzo|"
    r"san\s+nicol[aá]s|pergamino|rafaela|fisherton)\b",
    re.IGNORECASE,
)


def _extract_localidad_from_brief(brief: str) -> str | None:
    if not brief:
        return None
    m = _LOCALIDAD_KEYWORDS.search(brief)
    return m.group(0) if m else None


_ZOCALO_YES = re.compile(
    r"\b(con\s+z[oó]c|lleva(n)?\s+z[oó]c|z[oó]calos?\s*s[ií])",
    re.IGNORECASE,
)
_COLOC_YES = re.compile(r"\b(con\s+colocaci[oó]n|incluye\s+colocaci[oó]n)", re.IGNORECASE)
_COLOC_NO = re.compile(r"\b(sin\s+colocaci[oó]n|no\s+(incluye\s+)?colocaci[oó]n)", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# Section builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_data_known(brief: str, quote: dict | None) -> list[dict]:
    """Datos que sabemos con certeza (del brief o del quote guardado)."""
    known: list[dict] = []

    # Cliente
    client = (quote or {}).get("client_name")
    if client:
        known.append({"field": "Cliente", "value": client, "source": "quote"})
    else:
        # Intentar extraer del brief
        m = re.search(r"cliente\s*[:=]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ\s]{1,40})", brief or "", re.IGNORECASE)
        if m:
            known.append({"field": "Cliente", "value": m.group(1).strip(), "source": "brief"})

    # Proyecto
    project = (quote or {}).get("project")
    if project:
        known.append({"field": "Proyecto", "value": project, "source": "quote"})

    # Material
    mat = (quote or {}).get("material") or _extract_material_from_brief(brief)
    if mat:
        known.append({
            "field": "Material",
            "value": mat,
            "source": "quote" if (quote or {}).get("material") else "brief",
        })

    # Localidad
    loc = (quote or {}).get("localidad") or _extract_localidad_from_brief(brief)
    if loc:
        known.append({
            "field": "Localidad",
            "value": loc,
            "source": "quote" if (quote or {}).get("localidad") else "brief",
        })

    return known


def _build_assumptions(
    brief: str,
    quote: dict | None,
    dual_result: dict,
    config_defaults: dict,
) -> list[dict]:
    """Asunciones: reglas de negocio + defaults del config. El operador
    debe confirmar (o corregir)."""
    assumptions: list[dict] = []

    # Regla D'Angelo: pileta en cocina SIEMPRE empotrada.
    has_cocina = any(
        (s.get("tipo") or "").lower() == "cocina"
        for s in (dual_result.get("sectores") or [])
    )
    if has_cocina:
        assumptions.append({
            "field": "Pileta (tipo de montaje)",
            "value": "Empotrada (PEGADOPILETA)",
            "source": "rule",
            "note": "Regla D'Angelo: en cocina siempre empotrada, nunca apoyo.",
        })

    # Zócalos: brief dice "con zócalos" → regla = trasero por tramo, 7cm
    if brief and _ZOCALO_YES.search(brief):
        alto = config_defaults.get("default_zocalo_height", 0.07)
        assumptions.append({
            "field": "Zócalos",
            "value": f"Trasero por tramo, {alto * 100:.0f} cm",
            "source": "brief+rule",
            "note": "Brief dice 'con zócalos'. Regla D'Angelo: trasero por tramo del largo real.",
        })

    # Colocación: brief dice sí/no
    if brief and _COLOC_YES.search(brief):
        assumptions.append({
            "field": "Colocación",
            "value": "Incluye",
            "source": "brief",
        })
    elif brief and _COLOC_NO.search(brief):
        assumptions.append({
            "field": "Colocación",
            "value": "No incluye",
            "source": "brief",
        })

    # Forma de pago default
    pago = config_defaults.get("default_payment", "Contado")
    assumptions.append({
        "field": "Forma de pago",
        "value": pago,
        "source": "config_default",
        "note": "Default del sistema. Corrigí si el cliente acordó otra forma.",
    })

    # Demora default
    demora = config_defaults.get("default_delivery_days", "30 días")
    assumptions.append({
        "field": "Demora",
        "value": demora if isinstance(demora, str) else f"{demora} días",
        "source": "config_default",
    })

    # Tipo (particular / edificio)
    is_building = bool((quote or {}).get("is_building"))
    tipo = "Edificio" if is_building else "Particular"
    assumptions.append({
        "field": "Tipo",
        "value": tipo,
        "source": "inferred",
        "note": "Inferido del brief / flag del quote. Si tiene >3 unidades, probablemente edificio.",
    })

    return assumptions


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def build_context_analysis(
    brief: str,
    quote: dict | None,
    dual_result: dict,
    config_defaults: dict | None = None,
) -> dict:
    """Arma el objeto `context_analysis` que emite el backend como chunk SSE.

    Shape:
    {
      "data_known": [{field, value, source}, ...],
      "assumptions": [{field, value, source, note?}, ...],
      "pending_questions": [...],  # copy de dual_result.pending_questions si existe
      "sector_summary": "Cocina U con isla" | None,  # opcional, del topology
    }
    """
    config_defaults = config_defaults or {}
    data = _build_data_known(brief or "", quote)
    assumptions = _build_assumptions(brief or "", quote, dual_result, config_defaults)
    pending = list(dual_result.get("pending_questions") or [])

    # Sector summary: cuántos sectores y de qué tipo
    sectores = dual_result.get("sectores") or []
    sector_desc = None
    if sectores:
        tipos = [(s.get("tipo") or "").lower() for s in sectores]
        tramos_count = sum(len(s.get("tramos") or []) for s in sectores)
        unique = []
        for t in tipos:
            if t and t not in unique:
                unique.append(t)
        if unique:
            sector_desc = f"{tramos_count} mesada(s) en {' + '.join(unique)}"

    return {
        "data_known": data,
        "assumptions": assumptions,
        "pending_questions": pending,
        "sector_summary": sector_desc,
    }
