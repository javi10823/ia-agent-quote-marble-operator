"""Construcción del payload de `business-rules` v0 prescriptivo.

PR #399 — rework del shape original (#398) a versión copy-paste para
prompt del bot web. El bot web no usa los strings como vocabulario
abstracto: los inserta literal en su system prompt para asegurar que
las preguntas al cliente final salgan idénticas a la convención del
operador.

Política de fuentes:
  - Strings literales (question, notes) — hardcoded acá. Son contenido
    de prompt, no derivable de constantes.
  - `families` — levantado de `_FAMILY_CATALOGS` (calculator post-#396).
    Drift guard: si renombran el dict, este módulo no importa.
  - Flags booleanas (requires_clarification, marble_not_recommended,
    purastone_one_word, etc.) — hardcoded reflejando reglas de negocio
    documentadas en `rules/quote-process-general.md` y CONTEXT.md.

Mapping interno (no se serializa al cliente — vive como descripción
del field `payload_mapping`):

    bot web manda → /api/v1/quote recibe
    "propia"      → pileta="empotrada_cliente"
    "dangelo"     → pileta="empotrada_johnson" (+ pileta_sku opcional)
    "apoyo"       → pileta="apoyo"
"""
from __future__ import annotations

from app.modules.business_rules.schema import (
    BachaRules,
    BusinessRulesV0,
    MaterialsRules,
    NamingRules,
    RulesPayload,
)


# ─────────────────────────────────────────────────────────────────────
# Versión del payload
# ─────────────────────────────────────────────────────────────────────
#
# Formato `YYYY-MM-DD-vN`. Bump manual al introducir cambios breaking
# (renombre de campos, cambio de tipos, remoción). Cambios aditivos
# (nuevo campo opcional) no requieren bump pero conviene actualizar
# la fecha si el cambio es significativo.
_VERSION = "2026-04-24-v1"


# ─────────────────────────────────────────────────────────────────────
# Strings literales — copy-paste del prompt del bot web
# ─────────────────────────────────────────────────────────────────────

_BACHA_QUESTION = "¿La pileta ya la tenés, o la comprás con nosotros?"

_BACHA_DO_NOT_ASK = [
    "simple/doble",
    "arriba/abajo",
]

_BACHA_PAYLOAD_MAPPING = {
    "propia": "empotrada_cliente",
    "dangelo": "empotrada_johnson",
    "apoyo": "apoyo",
}

_BACHA_NOTES = [
    (
        "Si el cliente menciona pileta, bacha, agujero para pileta o dice "
        "que no tiene la pileta, aclarar si la trae o la compra en "
        "D'Angelo antes de cerrar."
    ),
    (
        "No preguntar detalle fino de bacha como simple/doble o pegada "
        "arriba/abajo."
    ),
]


def _material_families() -> list[str]:
    """Levanta las familias canónicas del matcher de materiales
    (calculator.py post-#396). Si el dict se renombra, este módulo
    rompe en import — drift guard."""
    from app.modules.quote_engine.calculator import _FAMILY_CATALOGS

    return list(_FAMILY_CATALOGS.keys())


def build_rules() -> BusinessRulesV0:
    """Construye el payload completo del endpoint.

    Función pura — sin DB, sin LLM, sin side-effects. Llamable desde
    cualquier contexto (incluido tests sin fixtures).
    """
    return BusinessRulesV0(
        version=_VERSION,
        rules=RulesPayload(
            bacha=BachaRules(
                requires_clarification_when_mentioned=True,
                question=_BACHA_QUESTION,
                do_not_ask=list(_BACHA_DO_NOT_ASK),
                payload_mapping=dict(_BACHA_PAYLOAD_MAPPING),
                notes=list(_BACHA_NOTES),
            ),
            materials=MaterialsRules(
                marble_not_recommended_for_kitchen=True,
                silestone_purastone_not_for_exterior=True,
                families=_material_families(),
            ),
            naming=NamingRules(
                purastone_one_word=True,
                puraprima_one_word=True,
            ),
        ),
    )
