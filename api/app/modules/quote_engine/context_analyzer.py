"""Context analyzer — construye el resumen de contexto que se muestra al
operador ANTES del despiece.

Usa `brief_analyzer.analyze_brief` (LLM) como fuente primaria para
extraer campos del brief. Robusto contra fallas: si el LLM falla, el
brief_analyzer cae a regex fallback que cubre los campos críticos.

Output: card con 3 secciones:
1. Datos conocidos (del brief/quote/catalog)
2. Asunciones aplicadas (reglas D'Angelo + defaults del config)
3. Preguntas bloqueantes (de pending_questions)

Campos del contrato (required_fields.py):
COCINA: geometría, dimensiones, material, zócalos, alzada, pileta,
anafe, isla, colocación, localidad, descuento.
BAÑO: geometría, dimensiones, material, zócalos, pileta (tipo), cant,
colocación, localidad, descuento.
LAVADERO: dimensiones, material, zócalos, pileta, colocación, localidad.
GLOBAL: cliente, obra, particular/edificio, forma de pago, demora.
"""
from __future__ import annotations

import asyncio
import logging

from app.modules.quote_engine.brief_analyzer import EMPTY_SCHEMA, analyze_brief

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Section builders — usan data extraída por brief_analyzer
# ─────────────────────────────────────────────────────────────────────────────

def _build_data_known(analysis: dict, quote: dict | None) -> list[dict]:
    """Datos ciertos del brief/quote. Cada row lleva source explícito."""
    known: list[dict] = []

    # Cliente
    client = (quote or {}).get("client_name") or analysis.get("client_name")
    if client:
        source = "quote" if (quote or {}).get("client_name") else "brief"
        known.append({"field": "Cliente", "value": client, "source": source})

    # Proyecto
    project = (quote or {}).get("project") or analysis.get("project")
    if project:
        source = "quote" if (quote or {}).get("project") else "brief"
        known.append({"field": "Proyecto", "value": project, "source": source})

    # Material
    material = (quote or {}).get("material") or analysis.get("material")
    if material:
        source = "quote" if (quote or {}).get("material") else "brief"
        known.append({"field": "Material", "value": material, "source": source})

    # Localidad
    loc = (quote or {}).get("localidad") or analysis.get("localidad")
    if loc:
        source = "quote" if (quote or {}).get("localidad") else "brief"
        known.append({"field": "Localidad", "value": loc, "source": source})

    # Tipos de trabajo detectados
    work = analysis.get("work_types") or []
    if work:
        pretty = ", ".join(w.capitalize() for w in work)
        known.append({"field": "Tipo de trabajo", "value": pretty, "source": "brief"})

    # Descuento si se mencionó
    if analysis.get("descuento_mentioned"):
        tipo = analysis.get("descuento_tipo") or "mencionado"
        pct = analysis.get("descuento_pct")
        value = f"{pct}% {tipo}" if pct else tipo.capitalize()
        known.append({"field": "Descuento", "value": value, "source": "brief"})

    return known


def _build_assumptions(
    analysis: dict,
    quote: dict | None,
    dual_result: dict,
    config_defaults: dict,
) -> list[dict]:
    """Reglas + defaults del config + inferencias. Operator debe validar."""
    assumptions: list[dict] = []
    sectores = dual_result.get("sectores") or []
    has_cocina = any((s.get("tipo") or "").lower() == "cocina" for s in sectores)
    has_banio = any((s.get("tipo") or "").lower() in ("baño", "banio") for s in sectores)

    # Regla D'Angelo: en cocina, pileta SIEMPRE empotrada (no apoyo).
    # Solo agregar la assumption si hay cocina Y pileta mencionada/detectada.
    pileta_mentioned = analysis.get("pileta_mentioned") or _card_has_pileta(dual_result)
    if has_cocina and pileta_mentioned:
        assumptions.append({
            "field": "Pileta (tipo de montaje)",
            "value": "Empotrada (PEGADOPILETA)",
            "source": "rule",
            "note": "Regla D'Angelo: en cocina la pileta siempre va empotrada, "
                    "nunca apoyo. El operador puede corregir si es excepción.",
        })

    # Zócalos: si brief dice "yes" → aplicamos regla default (trasero por tramo)
    z_val = analysis.get("zocalos")
    if z_val == "yes":
        alto_brief = analysis.get("zocalos_alto_cm")
        alto = alto_brief / 100.0 if alto_brief else config_defaults.get("default_zocalo_height", 0.07)
        assumptions.append({
            "field": "Zócalos",
            "value": f"Trasero por tramo, {int(alto * 100)} cm",
            "source": "brief+rule",
            "note": "Brief dice 'con zócalos'. Regla D'Angelo: trasero por tramo "
                    "del largo real.",
        })
    elif z_val == "no":
        assumptions.append({
            "field": "Zócalos",
            "value": "No lleva",
            "source": "brief",
            "note": "Brief explícito 'sin zócalos'.",
        })

    # Colocación: si brief lo menciona sí/no
    if analysis.get("colocacion") == "yes":
        assumptions.append({
            "field": "Colocación",
            "value": "Incluye",
            "source": "brief",
        })
    elif analysis.get("colocacion") == "no":
        assumptions.append({
            "field": "Colocación",
            "value": "No incluye",
            "source": "brief",
        })

    # Anafe si brief da count explícito
    anafe_count = analysis.get("anafe_count")
    if anafe_count is not None:
        assumptions.append({
            "field": "Anafe — cantidad",
            "value": f"{anafe_count} anafe{'s' if anafe_count != 1 else ''}"
                    + (" (gas + eléctrico)" if analysis.get("anafe_gas_y_electrico") else ""),
            "source": "brief",
        })

    # Pileta: si brief da tipo (apoyo/empotrada/doble)
    if analysis.get("pileta_type"):
        assumptions.append({
            "field": "Pileta — montaje",
            "value": analysis["pileta_type"].capitalize(),
            "source": "brief",
        })
    if analysis.get("pileta_simple_doble"):
        assumptions.append({
            "field": "Pileta — bachas",
            "value": analysis["pileta_simple_doble"].capitalize(),
            "source": "brief",
        })
    if analysis.get("mentions_johnson"):
        sku = analysis.get("johnson_sku") or "(modelo en brief)"
        assumptions.append({
            "field": "Pileta — marca",
            "value": f"Johnson {sku}",
            "source": "brief",
        })

    # Forma de pago default
    pago = analysis.get("forma_pago") or config_defaults.get("default_payment", "Contado")
    assumptions.append({
        "field": "Forma de pago",
        "value": pago.capitalize() if isinstance(pago, str) else str(pago),
        "source": "brief" if analysis.get("forma_pago") else "config_default",
        "note": None if analysis.get("forma_pago") else
                "Default del sistema. Corregí si el cliente acordó otra forma.",
    })

    # Demora default
    demora = analysis.get("demora_dias") or config_defaults.get("default_delivery_days", "30 días")
    demora_str = demora if isinstance(demora, str) else f"{demora} días"
    assumptions.append({
        "field": "Demora",
        "value": demora_str,
        "source": "brief" if analysis.get("demora_dias") else "config_default",
    })

    # Tipo particular/edificio
    is_building = bool((quote or {}).get("is_building") or analysis.get("es_edificio"))
    tipo = "Edificio" if is_building else "Particular"
    source = "brief" if analysis.get("es_edificio") else (
        "quote" if (quote or {}).get("is_building") else "inferred"
    )
    assumptions.append({
        "field": "Tipo",
        "value": tipo,
        "source": source,
        "note": None if source != "inferred" else
                "Inferido — si tiene varias unidades/tipologías, corregí a Edificio.",
    })

    # Descuento default si brief no lo menciona
    if not analysis.get("descuento_mentioned"):
        assumptions.append({
            "field": "Descuento",
            "value": "No aplica",
            "source": "config_default",
            "note": "Si el cliente tiene descuento (arquitecta u otro), corregí.",
        })

    # Trabajos extra mencionados (frentin, regrueso, pulido)
    if analysis.get("frentin_mentioned"):
        assumptions.append({"field": "Frentín", "value": "Mencionado", "source": "brief"})
    if analysis.get("regrueso_mentioned"):
        assumptions.append({"field": "Regrueso", "value": "Mencionado", "source": "brief"})
    if analysis.get("pulido_mentioned"):
        assumptions.append({"field": "Pulido especial", "value": "Mencionado", "source": "brief"})

    return assumptions


def _card_has_pileta(dual_result: dict) -> bool:
    for s in dual_result.get("sectores") or []:
        for t in s.get("tramos") or []:
            feats = t.get("features") or {}
            if feats.get("has_pileta") or feats.get("sink_double") or feats.get("sink_simple"):
                return True
            if "pileta" in (t.get("descripcion") or "").lower():
                return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (async porque llama al LLM analyzer)
# ─────────────────────────────────────────────────────────────────────────────

async def build_context_analysis(
    brief: str,
    quote: dict | None,
    dual_result: dict,
    config_defaults: dict | None = None,
) -> dict:
    """Construye la card de contexto. Llamada async — usa Haiku para
    parsear el brief robustamente. Siempre devuelve un shape estable
    incluso si el LLM falla.
    """
    config_defaults = config_defaults or {}
    analysis = await analyze_brief(brief or "")

    data = _build_data_known(analysis, quote)
    assumptions = _build_assumptions(analysis, quote, dual_result, config_defaults)
    pending = list(dual_result.get("pending_questions") or [])

    # Sector summary descriptivo
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
        "brief_analysis": {
            "extraction_method": analysis.get("extraction_method"),
            "work_types": analysis.get("work_types") or [],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sync wrapper para tests y uso legacy
# ─────────────────────────────────────────────────────────────────────────────

def build_context_analysis_sync(
    brief: str,
    quote: dict | None,
    dual_result: dict,
    config_defaults: dict | None = None,
) -> dict:
    """Wrapper síncrono para tests/scripts. Usa asyncio.run internamente."""
    return asyncio.run(build_context_analysis(brief, quote, dual_result, config_defaults))
