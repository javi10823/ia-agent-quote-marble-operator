"""Construcción del payload de `business-rules` v0.

Política de fuentes (acordado con operador, 2026-04-24):
  - **Levantar de la fuente de verdad** cuando exista como dato
    estructurado (constante / enum / dict). Cero duplicación.
  - **Hardcodear en este módulo** solo las reglas que hoy son lógica
    Python (ej: "cocina_requires_capture" deriva de
    `_detect_pileta_question` que es una función con condicional, no
    una constante). Documentar el origen.

Si una constante / enum referenciado se renombra o cambia su shape,
este módulo va a romper en import — es la salvaguarda contra drift.
"""
from __future__ import annotations

from typing import get_args

from app.modules.business_rules.schema import (
    BusinessRulesV0,
    MaterialsRules,
    SinkRules,
)


# ─────────────────────────────────────────────────────────────────────
# Versión del payload v0
# ─────────────────────────────────────────────────────────────────────
#
# Formato ISO YYYY-MM-DD. Bump manual al introducir cambios breaking
# (renombre de campos, cambio de tipos, remoción). Cambios aditivos
# (nuevo campo opcional) no requieren bump.
_VERSION = "2026-04-24"


# ─────────────────────────────────────────────────────────────────────
# Mapping interno (NO se serializa al cliente)
# ─────────────────────────────────────────────────────────────────────
#
# El bot web ve el eje `ownership` con dos valores canónicos:
# `cliente` y `dangelo`. Backend interno usa el enum `PiletaType`
# del schema `QuoteInput`. Mapeo:
#
#   cliente  → PiletaType.EMPOTRADA_CLIENTE
#   dangelo  → PiletaType.EMPOTRADA_JOHNSON (+ opcional `pileta_sku`)
#
# El valor `apoyo` del enum no es ownership — es mount type. Por eso
# `apoyo` queda fuera de `ownership_options` y se modela como
# `mount_options=arriba` (ver `mount_options` abajo).
#
# Cuando el bot web envía a /api/v1/quote:
#   ownership=cliente, mount=abajo  → pileta=empotrada_cliente
#   ownership=dangelo, mount=abajo  → pileta=empotrada_johnson [+ pileta_sku]
#   ownership=cliente, mount=arriba → pileta=apoyo (cliente trae bacha de apoyo)
#   ownership=dangelo, mount=arriba → no soportado (D'Angelo no
#                                     provee piletas de apoyo, fuera
#                                     de catálogo).
_OWNERSHIP_OPTIONS = ("cliente", "dangelo")


def _mount_options() -> list[str]:
    """Levanta los valores válidos de `mount_type` desde la fuente
    canónica (schema del POST /api/v1/quote). Si alguien renombra el
    Literal, este módulo rompe en import — drift detectado."""
    from app.modules.quote_engine.schemas import SinkTypeInput

    field = SinkTypeInput.model_fields["mount_type"]
    return list(get_args(field.annotation))


def _material_families() -> list[str]:
    """Levanta las familias canónicas del matcher de materiales
    (calculator.py post-#396). Misma garantía anti-drift: si el dict
    se renombra, este módulo no importa."""
    from app.modules.quote_engine.calculator import _FAMILY_CATALOGS

    return list(_FAMILY_CATALOGS.keys())


def build_rules() -> BusinessRulesV0:
    """Construye el payload completo del endpoint.

    Función pura — sin DB, sin LLM, sin side-effects. Llamable desde
    cualquier contexto (incluido tests sin fixtures).
    """
    return BusinessRulesV0(
        version=_VERSION,
        sink=SinkRules(
            # `cocina_requires_capture=True` refleja la lógica de
            # `pending_questions.py::_detect_pileta_question` — la
            # pregunta de pileta se dispara SIEMPRE en cocina (salvo
            # que el brief la niegue explícito). Hardcodeado acá
            # porque es lógica condicional, no una constante.
            cocina_requires_capture=True,
            ownership_options=list(_OWNERSHIP_OPTIONS),
            mount_options=_mount_options(),
        ),
        materials=MaterialsRules(
            families=_material_families(),
        ),
    )
