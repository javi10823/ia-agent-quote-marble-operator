"""Pydantic schemas del payload de `GET /api/v1/business-rules`.

Shape v0 acordado con el operador (2026-04-24). Cualquier cambio
breaking debe bumpear `version` y notificar al consumer (bot web).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SinkRules(BaseModel):
    """Vocabulario para captura de pileta/bacha en el bot web."""

    cocina_requires_capture: bool = Field(
        ...,
        description=(
            "Si True, el bot web debe capturar pileta antes de cerrar el "
            "lead cuando el proyecto incluye cocina. Refleja la regla "
            "interna 'en cocina la pileta siempre va empotrada' — el "
            "operador debe saber tipo y ownership antes de cotizar."
        ),
    )
    ownership_options: list[Literal["cliente", "dangelo"]] = Field(
        ...,
        description=(
            "Quién provee la pileta. 'cliente' = el cliente trae la pileta; "
            "'dangelo' = D'Angelo provee del catálogo Johnson (puede pasar "
            "`pileta_sku` opcional al endpoint /api/v1/quote para SKU "
            "específico)."
        ),
    )
    mount_options: list[Literal["abajo", "arriba"]] = Field(
        ...,
        description=(
            "Tipo de montaje. 'abajo' = bajo mesada (empotrada); 'arriba' "
            "= sobre mesada (apoyo). Mismo vocabulario que el campo "
            "`sink_type.mount_type` del POST /api/v1/quote."
        ),
    )


class MaterialsRules(BaseModel):
    """Vocabulario de familias de materiales para el bot web."""

    families: list[str] = Field(
        ...,
        description=(
            "Familias canónicas reconocidas por el matcher de materiales. "
            "El bot web puede usarlas para sugerir opciones al usuario sin "
            "mezclar familias (ej: no proponer granito cuando piden "
            "puraprima). El POST /api/v1/quote acepta `material` con "
            "cualquier string que contenga keyword de familia."
        ),
    )


class BusinessRulesV0(BaseModel):
    """Payload completo de `GET /api/v1/business-rules`."""

    version: str = Field(
        ...,
        description=(
            "Versión del payload en formato ISO YYYY-MM-DD. Se bumpea "
            "manualmente cuando hay cambio breaking. El bot web puede "
            "comparar contra su versión cacheada para revalidación."
        ),
    )
    sink: SinkRules
    materials: MaterialsRules
