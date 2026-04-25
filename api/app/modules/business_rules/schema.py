"""Pydantic schemas del payload de `GET /api/v1/business-rules`.

Shape v0 prescriptivo (PR #399, rework de #398): el bot web copia
estos strings literal en su system prompt. Por eso los campos son
copy-paste-into-prompt (question literal, notes literales, flags
booleanas), no vocabulario abstracto.

Cualquier cambio breaking debe bumpear `version` y notificar al
consumer (bot web). El formato de version es `YYYY-MM-DD-vN` —
permite múltiples versiones el mismo día si hace falta.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BachaRules(BaseModel):
    """Reglas de captura de pileta/bacha para el bot web."""

    requires_clarification_when_mentioned: bool = Field(
        ...,
        description=(
            "Si True, cuando el cliente mencione pileta/bacha/agujero "
            "para pileta o diga que no tiene la pileta, el bot debe "
            "preguntar si la trae o la compra en D'Angelo antes de "
            "cerrar el lead."
        ),
    )
    question: str = Field(
        ...,
        description=(
            "Texto literal que el bot debe usar para preguntar. "
            "Copy-paste exacto."
        ),
    )
    do_not_ask: list[str] = Field(
        ...,
        description=(
            "Topics que el bot NO debe preguntar al cliente — son "
            "detalles internos que el operador resuelve después."
        ),
    )
    payload_mapping: dict[
        Literal["propia", "dangelo", "apoyo"],
        Literal["empotrada_cliente", "empotrada_johnson", "apoyo"],
    ] = Field(
        ...,
        description=(
            "Mapping de la respuesta del cliente al valor del enum "
            "`pileta` que se manda en POST /api/v1/quote. "
            "'propia' = cliente la trae; 'dangelo' = D'Angelo la "
            "provee; 'apoyo' = pileta sobre mesada."
        ),
    )
    notes: list[str] = Field(
        ...,
        description=(
            "Notas adicionales que el bot puede usar como contexto en "
            "el prompt. Texto literal en español."
        ),
    )


class MaterialsRules(BaseModel):
    """Reglas y vocabulario de materiales para el bot web."""

    marble_not_recommended_for_kitchen: bool = Field(
        ...,
        description=(
            "Si True, el bot debe desaconsejar mármol para cocina (es "
            "poroso, se mancha con ácidos). Sugerir alternativas "
            "(granito / sintéticos)."
        ),
    )
    silestone_purastone_not_for_exterior: bool = Field(
        ...,
        description=(
            "Si True, el bot debe desaconsejar Silestone y Purastone "
            "para exterior (no resistentes a UV / temperatura). "
            "Sugerir Dekton / Neolith."
        ),
    )
    families: list[str] = Field(
        ...,
        description=(
            "Familias canónicas de material reconocidas por el matcher "
            "interno. Útil para que el bot sugiera opciones sin mezclar "
            "familias incompatibles. Subordinado al shape rules.* — "
            "vocabulario, no endpoint paralelo."
        ),
    )


class NamingRules(BaseModel):
    """Reglas de ortografía / naming que el bot debe seguir."""

    purastone_one_word: bool = Field(
        ...,
        description=(
            "Si True, escribir 'Purastone' como una sola palabra "
            "(no 'Pura Stone')."
        ),
    )
    puraprima_one_word: bool = Field(
        ...,
        description=(
            "Si True, escribir 'Puraprima' como una sola palabra "
            "(no 'Pura Prima')."
        ),
    )


class RulesPayload(BaseModel):
    """Wrapper de las reglas v0. El bot web itera por sub-secciones
    (bacha / materials / naming) para construir su prompt."""

    bacha: BachaRules
    materials: MaterialsRules
    naming: NamingRules


class BusinessRulesV0(BaseModel):
    """Payload completo de `GET /api/v1/business-rules`."""

    version: str = Field(
        ...,
        description=(
            "Versión del payload en formato `YYYY-MM-DD-vN`. Se bumpea "
            "manualmente cuando hay cambio breaking. El bot web puede "
            "comparar contra su versión cacheada para revalidación."
        ),
    )
    rules: RulesPayload
