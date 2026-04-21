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
# PR #347 — Reconciliación brief ↔ dual_read con observabilidad explícita
#
# El brief_analyzer extrae SOLO lo que dice el texto (contrato limpio:
# extractor textual puro). La reconciliación con el topology/dual_read
# la hace ESTE módulo vía _detect_* + _reconcile_*.
#
# Criterio crítico: cuando brief y dual_read tienen ambos un valor
# válido pero distintos, NO hacer merge silencioso. Loggear explícitamente
# `divergent=True` y dejar que el operador lo vea (vía UI fields con
# source="brief"/"dual_read" + confidence). Esto evita el anti-patrón
# "el sistema eligió uno de los dos sin avisar".
# ─────────────────────────────────────────────────────────────────────────────


def _log_reconcile(
    field: str,
    brief_value,
    dual_read_value,
    final,
    source: str,  # "brief" | "dual_read" | "default" | "merged"
    confidence: float | None = None,
    divergent: bool = False,
) -> None:
    """Log estructurado de la decisión de reconciliación brief↔dual_read.

    Formato key=value grep-friendly. `divergent=True` cuando ambas fuentes
    tenían valores no-null y distintos — señal de inconsistencia real
    que el operador puede tener que resolver visualmente. No se silencia
    el merge: se muestra qué ganó y qué se descartó.

    Se emite SIEMPRE, incluso cuando no hay divergencia, para dejar
    trazabilidad completa de cómo se construyó la card de contexto.
    """
    conf_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "None"
    logger.info(
        "[context-reconcile] field=%s brief_value=%s dual_read_value=%s "
        "final=%s source=%s confidence=%s divergent=%s",
        field, brief_value, dual_read_value, final, source, conf_str, divergent,
    )


def _reconcile_work_types(analysis: dict, dual_result: dict) -> dict:
    """Merge de work_types: brief textual primero, dual_read.sectores
    como fallback.

    Caso Bernardi real: brief dice "nuevo presupuesto material en pura
    prima onix white mate Cliente: Erica Bernardi SIN zocalos en rosario
    con colocacion" — no menciona "cocina" explícito → analysis.work_types=[].
    Pero dual_result.sectores tiene ["cocina", "isla"]. Sin este merge
    "Tipo de trabajo" no aparecía en `data_known`.

    Devuelve dict con: final (list[str]), source (brief|dual_read|default),
    brief_value, dual_read_value, divergent (set-equality).
    """
    brief_wt = list(analysis.get("work_types") or [])

    # Normalizar tipos de sectores a canonical set.
    _NON_COCINA = {"baño", "banio", "isla", "lavadero"}
    dr_types: list[str] = []
    for s in dual_result.get("sectores") or []:
        t = (s.get("tipo") or "").lower().strip()
        pretty = t if t in _NON_COCINA else ("cocina" if t else None)
        if pretty and pretty not in dr_types:
            dr_types.append(pretty)

    if brief_wt:
        final = brief_wt
        source = "brief"
    elif dr_types:
        final = dr_types
        source = "dual_read"
    else:
        final = []
        source = "default"

    # Divergent: ambos no-vacíos Y conjuntos distintos.
    # Normalizar "banio"→"baño" para comparación canonical.
    def _canon(lst: list[str]) -> set[str]:
        return {("baño" if x == "banio" else x) for x in lst}
    divergent = (
        bool(brief_wt) and bool(dr_types) and _canon(brief_wt) != _canon(dr_types)
    )

    _log_reconcile(
        "work_types",
        brief_value=brief_wt,
        dual_read_value=dr_types,
        final=final,
        source=source,
        confidence=None,
        divergent=divergent,
    )
    return {
        "final": final,
        "source": source,
        "brief_value": brief_wt,
        "dual_read_value": dr_types,
        "divergent": divergent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Section builders — usan data extraída por brief_analyzer
# ─────────────────────────────────────────────────────────────────────────────

def _build_data_known(
    analysis: dict,
    quote: dict | None,
    dual_result: dict | None = None,
) -> list[dict]:
    """Datos ciertos del brief/quote/plano. Cada row lleva source explícito.

    PR #347: `dual_result` es ahora input — permite inferir
    "Tipo de trabajo" desde los sectores del plano cuando el brief no los
    menciona textualmente (caso Bernardi: brief sin "cocina", plano con
    cocina+isla). Default `None` para retrocompat de callers legacy.
    """
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

    # Tipos de trabajo — merge brief ↔ dual_read.sectores.
    # Antes: solo brief → "Tipo de trabajo" desaparecía cuando brief no
    # mencionaba explícito. Ahora cae al dual_read. El source del row
    # refleja de dónde salió (brief|dual_read|brief+dual_read si divergen).
    reconcile = _reconcile_work_types(analysis, dual_result or {})
    work = reconcile["final"]
    if work:
        pretty = ", ".join(w.capitalize() for w in work)
        # Si hubo divergencia, marcar source combinada para trazabilidad
        # en la card. El log [context-reconcile] ya dice qué ganó.
        if reconcile["divergent"]:
            src = "brief+dual_read"
        else:
            src = reconcile["source"]
        known.append({"field": "Tipo de trabajo", "value": pretty, "source": src})

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

    # Anafe — reconciliación brief ↔ dual_read. Antes: solo brief (si brief
    # no mencionaba anafe, la assumption desaparecía y el LLM post-confirm
    # re-leía el plano contando anafes visibles y podía decir "2 anafes
    # confirmados" aunque dual_read había detectado 1. Ahora con fallback
    # a dual_read, la assumption sale con el valor estructurado + source.
    # El wording del row evita "confirmado" si viene de dual_read (source
    # es lo que lleva la autoridad; el texto es informativo).
    feats = _scan_features(dual_result)
    anafe_rec = reconcile_anafe_count(analysis, feats)
    if anafe_rec["final"] is not None:
        n = anafe_rec["final"]
        source = anafe_rec["source"]
        brief_gas_elec = source == "brief" and analysis.get("anafe_gas_y_electrico")
        gas_elec_suffix = " (gas + eléctrico)" if brief_gas_elec else ""
        # Wording escalonado: "confirmado" NO lo usa el backend acá —
        # la palabra queda reservada para cuando el operador responde la
        # tech_detection o una pending_question. El post-confirm LLM debe
        # leer `source` y decidir wording según la precedencia explícita.
        if source == "brief":
            value = f"{n} anafe{'s' if n != 1 else ''}{gas_elec_suffix}"
        elif source == "dual_read":
            value = f"{n} anafe{'s' if n != 1 else ''} — detectado en plano"
        else:
            value = f"{n} anafe{'s' if n != 1 else ''}"
        note = None
        if anafe_rec["divergent"]:
            # Divergencia: surface-ear en la card como nota, no esconder.
            note = (
                f"Divergencia: brief={anafe_rec['brief_value']} vs "
                f"plano={anafe_rec['dual_read_value']}. Revisar visualmente."
            )
        assumptions.append({
            "field": "Anafe — cantidad",
            "value": value,
            "source": source,
            "note": note,
        })

    # Pileta — reconciliación brief ↔ dual_read (mismo patrón que anafe).
    # `pileta_simple_doble` es el campo canónico. `pileta_type` (apoyo /
    # empotrada) sigue como dato adicional del brief si existe.
    pileta_rec = reconcile_pileta_simple_doble(analysis, feats)
    if pileta_rec["final"] is not None:
        val = pileta_rec["final"]
        source = pileta_rec["source"]
        if val == "no":
            value = "No lleva"
        elif source == "brief":
            value = val.capitalize()
        else:  # dual_read
            label = "Simple (1 bacha)" if val == "simple" else "Doble (2 bachas)"
            value = f"{label} — detectada en plano"
        note = None
        if pileta_rec["divergent"]:
            note = (
                f"Divergencia: brief={pileta_rec['brief_value']} vs "
                f"plano={pileta_rec['dual_read_value']}. Revisar visualmente."
            )
        assumptions.append({
            "field": "Pileta — bachas",
            "value": value,
            "source": source,
            "note": note,
        })

    if analysis.get("pileta_type"):
        assumptions.append({
            "field": "Pileta — montaje",
            "value": analysis["pileta_type"].capitalize(),
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
# Tech detections — lo que el plano / dual_read detectó técnicamente.
#
# Shape por detection:
#   {
#     "field":        id único (coincide con pending_questions cuando aplica),
#     "label":        humano, para la UI,
#     "value":        valor canónico (ej "doble" | "yes" | "2"),
#     "display":      cómo mostrarlo en la card,
#     "options":      lista de {value,label} para corrección inline (radio),
#     "source":       "dual_read" | "brief" | "quote" | "rule",
#     "confidence":   0.0-1.0,
#     "status":       "verified"         — confidence >= 0.90, no necesita
#                                           confirmación; igual mostramos
#                                           badge con source.
#                     "needs_confirmation" — 0.60-0.90, UI muestra radio
#                                           inline con valor preseleccionado.
#                     "low_confidence"   — < 0.60; el field también aparece
#                                           como pending_question bloqueante.
#   }
#
# Sólo cubre detecciones técnicas (lo que se ve en el plano o se confirma
# en el brief con alta certeza). Los "commercial_defaults" (forma de pago,
# demora, zócalos default, etc.) siguen en assumptions/.
# ─────────────────────────────────────────────────────────────────────────────

_VERIFIED_T = 0.90
_LOW_T = 0.60


def _status_for(confidence: float) -> str | None:
    """verified si >= 0.90, needs_confirmation si 0.60-0.90, None si < 0.60
    (en ese caso el campo vuelve a pending_question sin preselección)."""
    if confidence >= _VERIFIED_T:
        return "verified"
    if confidence >= _LOW_T:
        return "needs_confirmation"
    return None


def _scan_features(dual_result: dict) -> dict:
    """Agrega features detectadas en el dual_result a nivel trabajo."""
    summary = {
        "sink_double": False,
        "sink_simple": False,
        "has_pileta": False,
        "cooktop_groups": 0,
        "has_isla": False,
    }
    for s in dual_result.get("sectores") or []:
        if (s.get("tipo") or "").lower() == "isla":
            summary["has_isla"] = True
        for t in s.get("tramos") or []:
            feats = t.get("features") or {}
            if feats.get("sink_double"):
                summary["sink_double"] = True
            if feats.get("sink_simple"):
                summary["sink_simple"] = True
            if feats.get("has_pileta"):
                summary["has_pileta"] = True
            cg = feats.get("cooktop_groups")
            if isinstance(cg, (int, float)) and cg > 0:
                summary["cooktop_groups"] += int(cg)
    return summary


_PILETA_OPTIONS = [
    {"value": "simple", "label": "Simple (1 bacha)"},
    {"value": "doble", "label": "Doble (2 bachas)"},
    {"value": "no", "label": "No lleva"},
]
_ISLA_OPTIONS = [
    {"value": "yes", "label": "Sí, hay isla"},
    {"value": "no", "label": "No hay isla"},
]
_ANAFE_OPTIONS = [
    {"value": "0", "label": "No lleva"},
    {"value": "1", "label": "1"},
    {"value": "2", "label": "2 (gas + eléctrico)"},
    {"value": "3", "label": "3+"},
]


# ─────────────────────────────────────────────────────────────────────────────
# PR #374 — Reconciliación pura (brief ↔ dual_read) exportable
#
# Extraídas de los `_detect_*` tech detections para que puedan ser usadas
# también por `_build_assumptions` y `build_verified_context` (dual_reader).
# Antes el assumptions layer solo miraba `analysis.get("anafe_count")` y si
# el brief no lo mencionaba el campo desaparecía del resumen → el LLM
# post-confirmación re-leía el plano y contaba 2 anafes cuando el dual_read
# había detectado 1. Ahora el assumption se cae al dual_read y el LLM
# recibe el valor estructurado como fuente de verdad.
#
# Precedencia canónica (enforcement en código, no en prompt):
#   operator_answer > brief > dual_read > default
#
# Diseño:
# - Funciones puras, sin side effects (excepto log de reconcile — mismo
#   formato que _reconcile_work_types).
# - Devuelven dict canónico: {final, source, confidence, divergent,
#   brief_value, dual_read_value}.
# - `_detect_*` se reescriben encima de estas, sumando solo la forma
#   schema de tech_detection.
# ─────────────────────────────────────────────────────────────────────────────

def reconcile_anafe_count(analysis: dict, feats: dict) -> dict:
    """Resuelve `anafe_count` con precedencia brief → dual_read.

    Returns dict con:
        final: int | None — valor resuelto
        source: "brief" | "dual_read" | "default"
        confidence: float | None
        divergent: bool — True si brief y dual_read discrepan
        brief_value, dual_read_value: los valores originales
    """
    ac = analysis.get("anafe_count")
    cg = feats.get("cooktop_groups") or 0

    brief_v = ac if isinstance(ac, int) and ac >= 0 else None
    dr_v = int(cg) if cg > 0 else None

    divergent = (
        brief_v is not None and dr_v is not None and brief_v != dr_v
    )

    if brief_v is not None:
        final, source, conf = brief_v, "brief", 0.95
    elif dr_v is not None:
        final, source, conf = dr_v, "dual_read", 0.70
    else:
        final, source, conf = None, "default", None

    _log_reconcile(
        "anafe_count",
        brief_value=brief_v,
        dual_read_value=dr_v,
        final=final,
        source=source,
        confidence=conf,
        divergent=divergent,
    )
    return {
        "final": final,
        "source": source,
        "confidence": conf,
        "divergent": divergent,
        "brief_value": brief_v,
        "dual_read_value": dr_v,
    }


def reconcile_pileta_simple_doble(analysis: dict, feats: dict) -> dict:
    """Resuelve `pileta_simple_doble` con precedencia brief → dual_read.

    Valores posibles: "simple" | "doble" | "no" | None.

    Returns dict con shape de `reconcile_anafe_count`.
    """
    brief_v = analysis.get("pileta_simple_doble")  # "simple"|"doble"|None

    if feats.get("sink_double"):
        dr_v = "doble"
    elif feats.get("sink_simple"):
        dr_v = "simple"
    elif feats.get("has_pileta"):
        dr_v = "present_unknown"
    else:
        dr_v = None

    # brief explicit "no pileta"
    brief_explicit_no = (
        analysis.get("pileta_mentioned") is False
        and _has_explicit_no_pileta(analysis)
    )

    divergent = False
    if brief_v in ("simple", "doble") and dr_v in ("simple", "doble"):
        divergent = brief_v != dr_v
    elif brief_explicit_no and dr_v in ("simple", "doble", "present_unknown"):
        divergent = True

    if brief_v in ("simple", "doble"):
        final, source, conf = brief_v, "brief", 0.95
    elif brief_explicit_no:
        final, source, conf = "no", "brief", 0.95
    elif dr_v == "doble":
        final, source, conf = "doble", "dual_read", 0.80
    elif dr_v == "simple":
        final, source, conf = "simple", "dual_read", 0.75
    elif dr_v == "present_unknown":
        final, source, conf = None, "dual_read", 0.55  # detectada pero tipo a confirmar
    else:
        final, source, conf = None, "default", None

    _log_reconcile(
        "pileta_simple_doble",
        brief_value=brief_v if brief_v is not None else (
            "explicit_no" if brief_explicit_no else None
        ),
        dual_read_value=dr_v,
        final=final,
        source=source,
        confidence=conf,
        divergent=divergent,
    )
    return {
        "final": final,
        "source": source,
        "confidence": conf,
        "divergent": divergent,
        "brief_value": brief_v,
        "dual_read_value": dr_v,
    }


def _detect_pileta(analysis: dict, feats: dict) -> dict | None:
    """Tech detection para la card UI. La reconciliación pura ya la hace
    `reconcile_pileta_simple_doble` — acá solo armamos el schema de
    display + options para el radio del frontend."""
    rec = reconcile_pileta_simple_doble(analysis, feats)
    final, source, conf = rec["final"], rec["source"], rec["confidence"]
    dr_v = rec["dual_read_value"]

    if final == "simple" and source == "brief":
        return _mk("pileta_simple_doble", "Pileta", "simple", "Simple (1 bacha)",
                   _PILETA_OPTIONS, source, conf)
    if final == "doble" and source == "brief":
        return _mk("pileta_simple_doble", "Pileta", "doble", "Doble (2 bachas)",
                   _PILETA_OPTIONS, source, conf)
    if final == "no":
        return _mk("pileta_simple_doble", "Pileta", "no", "No lleva",
                   _PILETA_OPTIONS, source, conf)
    if final == "doble" and source == "dual_read":
        return _mk("pileta_simple_doble", "Pileta", "doble",
                   "Doble (2 bachas) — detectada en plano",
                   _PILETA_OPTIONS, source, conf)
    if final == "simple" and source == "dual_read":
        return _mk("pileta_simple_doble", "Pileta", "simple",
                   "Simple (1 bacha) — detectada en plano",
                   _PILETA_OPTIONS, source, conf)
    if final is None and dr_v == "present_unknown":
        return _mk("pileta_simple_doble", "Pileta", None,
                   "Presente — tipo a confirmar",
                   _PILETA_OPTIONS, source, conf)
    return None


def _detect_isla(analysis: dict, feats: dict) -> dict | None:
    brief_v = bool(analysis.get("isla_mentioned"))
    dr_v = bool(feats["has_isla"])

    # Divergent: SOLO cuando brief afirma (isla_mentioned=True) Y plano
    # niega (has_isla=False). brief=False es "no mencionó", no "dijo que
    # no hay" — caso habitual (Bernardi) → brief silencio + plano detecta
    # es fallback natural, no divergencia. Consistente con anafe/pileta.
    divergent = brief_v is True and dr_v is False

    if brief_v:
        final, source, conf = True, "brief", 0.95
        result = _mk("isla_presence", "Isla central", "yes", "Sí — del brief",
                     _ISLA_OPTIONS, source, conf)
    elif dr_v:
        final, source, conf = True, "dual_read", 0.85
        result = _mk("isla_presence", "Isla central", "yes",
                     "Sí — detectada en plano", _ISLA_OPTIONS, source, conf)
    else:
        final, source, conf = False, "default", None
        result = None

    _log_reconcile(
        "isla_presence",
        brief_value=brief_v,
        dual_read_value=dr_v,
        final=final,
        source=source,
        confidence=conf,
        divergent=divergent,
    )
    return result


def _detect_anafe(analysis: dict, feats: dict) -> dict | None:
    """Tech detection para la card UI. La reconciliación pura ya la hace
    `reconcile_anafe_count` — acá solo armamos el schema del radio."""
    rec = reconcile_anafe_count(analysis, feats)
    final, source, conf = rec["final"], rec["source"], rec["confidence"]
    if final is None:
        return None
    if source == "brief":
        disp = (
            "2 (gas + eléctrico)"
            if final == 2 and analysis.get("anafe_gas_y_electrico")
            else f"{final}"
        )
        return _mk("anafe_count", "Anafe", str(final), disp,
                   _ANAFE_OPTIONS, source, conf)
    # dual_read o default — wording "detectado en plano" (no "confirmado")
    return _mk("anafe_count", "Anafe", str(final),
               f"{final} — detectado en plano",
               _ANAFE_OPTIONS, source, conf)


def _has_explicit_no_pileta(analysis: dict) -> bool:
    raw = (analysis.get("raw_notes") or "").lower()
    return "sin pileta" in raw or "no lleva pileta" in raw


def _mk(field: str, label: str, value, display: str, options: list[dict],
        source: str, confidence: float) -> dict | None:
    status = _status_for(confidence)
    if status is None:
        return None
    return {
        "field": field,
        "label": label,
        "value": value,
        "display": display,
        "options": options,
        "source": source,
        "confidence": round(confidence, 2),
        "status": status,
    }


def _extract_tech_detections(analysis: dict, dual_result: dict) -> list[dict]:
    """Devuelve la lista ordenada de detecciones técnicas de plano/brief.

    Orden: presencia de isla → pileta → anafe. (El operador valida la foto
    del plano leyendo de arriba a abajo.) Detecciones ausentes quedan como
    pending_questions en otro módulo.
    """
    feats = _scan_features(dual_result)
    detections: list[dict] = []
    for fn in (_detect_isla, _detect_pileta, _detect_anafe):
        d = fn(analysis, feats)
        if d is not None:
            detections.append(d)
    return detections


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

    data = _build_data_known(analysis, quote, dual_result)
    assumptions = _build_assumptions(analysis, quote, dual_result, config_defaults)
    tech_detections = _extract_tech_detections(analysis, dual_result)

    # Suprimir pending_questions ya cubiertas por un tech_detection. Para
    # status=verified no hay acción (sólo display). Para needs_confirmation
    # el operador corrige inline con el radio del tech_detection. En ambos
    # casos no queremos duplicar la pregunta bloqueante.
    detected_fields = {d["field"] for d in tech_detections}
    pending_src = list(dual_result.get("pending_questions") or [])
    pending = [q for q in pending_src if q.get("id") not in detected_fields]

    # Sector summary descriptivo
    sectores = dual_result.get("sectores") or []
    sector_desc = None
    if sectores:
        tramos_count = sum(len(s.get("tramos") or []) for s in sectores)
        # Normalizar el tipo a algo humano: "l"/"u"/"recta" → "cocina".
        # Respetar "baño", "isla", "lavadero" como nombres propios.
        human_types: list[str] = []
        _NON_COCINA = {"baño", "banio", "isla", "lavadero"}
        for s in sectores:
            raw = (s.get("tipo") or "").lower().strip()
            pretty = raw if raw in _NON_COCINA else "cocina"
            if pretty and pretty not in human_types:
                human_types.append(pretty)
        if human_types:
            sector_desc = f"{tramos_count} mesada(s) en {' + '.join(human_types)}"

    return {
        "data_known": data,
        "assumptions": assumptions,
        "tech_detections": tech_detections,
        "pending_questions": pending,
        "sector_summary": sector_desc,
        "brief_analysis": {
            "extraction_method": analysis.get("extraction_method"),
            "work_types": analysis.get("work_types") or [],
        },
        # PR #374 — Full analysis crudo expuesto para consumo backend-only
        # (handler DUAL_READ_CONFIRMED lo lee para construir commercial_attrs
        # con precedencia brief > dual_read). El frontend lo ignora.
        "_brief_analysis_raw": analysis,
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
