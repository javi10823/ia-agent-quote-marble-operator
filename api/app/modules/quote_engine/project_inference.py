"""Sugerencia de `project` (obra) cuando el brief no lo trae.

El calculator rechaza project vacío/placeholder ("Falta el nombre del
proyecto"). Este módulo arma un valor sugerido, SIEMPRE marcado como
`inferred` por el caller, para que el operador no tenga que tipearlo.

Prioridad: (1) analysis.project del brief → (2) cliente + material →
(3) tipo de trabajo derivado de work_types.

Funciones puras, sin I/O.
"""
from __future__ import annotations

import re
from typing import Optional

# Copia literal del set de calculator.py (rechazo de project placeholder).
# El test guardia `test_project_inference.py` verifica que el calculator
# siga rechazando cada uno.
PROJECT_PLACEHOLDERS = {"", "n/a", "n/d", "sin proyecto", "sin obra", "-", "—", "."}

_MAX_FIELD = 450
_SEPARATOR = " - "

_WORK_TYPE_NAMES = {
    "cocina": "Cocina",
    "baño": "Baño",
    "lavadero": "Lavadero",
}


def is_placeholder_project(value) -> bool:
    """True si `value` no es str o es vacío/placeholder genérico."""
    if not isinstance(value, str):
        return True
    return value.strip().lower() in PROJECT_PLACEHOLDERS


def clean_project(value) -> str:
    """Sanea un texto: saltos de línea → espacio, sin `*`, strip, máx 450."""
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\r\n]+", " ", value)
    value = re.sub(r"\*+", "", value)
    return value.strip()[:_MAX_FIELD]


def _join_es(names: list) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " y " + names[-1]


def derive_project_from_brief(analysis) -> Optional[str]:
    """Deriva un nombre de obra desde `work_types` (+ `isla_mentioned`)."""
    if not isinstance(analysis, dict):
        return None
    raw = analysis.get("work_types")
    if not isinstance(raw, (list, tuple)):
        return None
    kinds: list = []
    for item in raw:
        if not isinstance(item, str):
            continue
        key = item.strip().lower().replace("banio", "baño")
        if key in _WORK_TYPE_NAMES and key not in kinds:
            kinds.append(key)
    if not kinds:
        return None
    names = []
    for key in kinds:
        name = _WORK_TYPE_NAMES[key]
        if key == "cocina" and analysis.get("isla_mentioned") is True:
            name = "Cocina con isla"
        names.append(name)
    return _join_es(names)


def suggest_project_name(client, material) -> Optional[str]:
    """'Cliente - Material' (o el que haya). None si no hay ninguno útil."""
    parts = []
    for value in (client, material):
        cleaned = clean_project(value)
        if cleaned and not is_placeholder_project(cleaned):
            parts.append(cleaned)
    if not parts:
        return None
    return _SEPARATOR.join(parts)[:_MAX_FIELD]


def resolve_project_for_persist(
    analysis,
    *,
    current_project,
    pending_project,
    client_name,
    material,
) -> Optional[tuple]:
    """Decide qué `project` persistir en el early-persist.

    Devuelve `(valor, "brief"|"inferred")` o None si no hay nada que hacer
    (ya hay un project válido en la columna o pendiente de persistir, o no
    se pudo armar ningún valor).
    """
    if not is_placeholder_project(current_project):
        return None
    if not is_placeholder_project(pending_project):
        return None
    if isinstance(analysis, dict):
        from_brief = clean_project(analysis.get("project"))
        if from_brief and not is_placeholder_project(from_brief):
            return (from_brief, "brief")
    suggested = suggest_project_name(client_name, material)
    if suggested:
        return (suggested, "inferred")
    derived = derive_project_from_brief(analysis)
    if derived:
        return (derived, "inferred")
    return None
