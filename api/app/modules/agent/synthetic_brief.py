"""Construcción de brief sintético desde las columnas del Quote.

PR #395 — cuando el chatbot externo crea un quote vía `POST /api/v1/quote`
y sube un plano, el gate #394 bloquea el auto-estimate. El operador
necesita disparar el flow del agente manualmente desde la UI interna.
Para que la card de contexto salga llena con los datos del chatbot,
reconstruimos un "brief sintético" desde las columnas del Quote que
el brief_analyzer sabe parsear:

    Cliente: Erica Bernardi
    Proyecto: Cocina
    Material: Puraprima Onix White Mate
    Localidad: Rosario
    Con colocación
    Pileta: empotrada
    Con anafe

El operador aprieta "Procesar plano y contexto" en la UI → frontend
manda `[SYSTEM_TRIGGER:process_saved_plan]` → el handler en `stream_chat`
llama a este helper para reemplazar el trigger por el brief → el flow
normal corre con plan_bytes restaurado de `source_files`.

Este mismo shape de mensaje es el que usaba el bg task de
`_schedule_agent_background_processing` (antes del gate #394) — mantenerlo
coherente evita divergencia de wording.
"""
from __future__ import annotations

from typing import Any


def build_brief_from_quote_columns(quote: Any) -> str:
    """Construye un brief natural desde las columnas del Quote que el
    chatbot web haya llenado. No inventa nada: si una columna está en
    None / vacía, se omite la línea.

    Shape esperado del `quote`: ORM `app.models.quote.Quote` o cualquier
    objeto con atributos equivalentes (`getattr` seguro).

    Returns:
        String multi-línea con los campos presentes + línea final que
        indica al agente que es procesamiento inicial con plano adjunto
        (equivalente al user_message del bg task en `_process_plan_background`
        del router).
    """
    parts: list[str] = []

    client_name = getattr(quote, "client_name", None)
    if client_name:
        parts.append(f"Cliente: {client_name}")

    project = getattr(quote, "project", None)
    if project:
        parts.append(f"Proyecto: {project}")

    material = getattr(quote, "material", None)
    if material:
        parts.append(f"Material: {material}")

    localidad = getattr(quote, "localidad", None)
    if localidad:
        parts.append(f"Localidad: {localidad}")

    colocacion = getattr(quote, "colocacion", None)
    if colocacion is True:
        parts.append("Con colocación")
    elif colocacion is False:
        parts.append("Sin colocación")

    pileta_val = getattr(quote, "pileta", None)
    if pileta_val:
        parts.append(f"Pileta: {pileta_val}")

    anafe_val = getattr(quote, "anafe", None)
    if anafe_val:
        parts.append("Con anafe")

    sink_type_val = getattr(quote, "sink_type", None)
    if isinstance(sink_type_val, dict):
        bc = (sink_type_val.get("basin_count") or "").capitalize()
        mt = sink_type_val.get("mount_type") or ""
        pieces_bacha = " · ".join(p for p in (bc, f"Pegada de {mt}" if mt else "") if p)
        if pieces_bacha:
            parts.append(f"Tipo de bacha: {pieces_bacha}")

    notes = getattr(quote, "notes", None)
    if notes:
        notes_clean = str(notes).strip()
        if notes_clean:
            parts.append(f"Notas del cliente: {notes_clean}")

    # Línea final que aclara al agente el origen del flujo. No usa los
    # imperativos del bg task ("NO generar documentos") porque acá sí
    # queremos el flujo completo (el operador lo dispara a propósito).
    parts.append("Adjunto el plano cargado desde el chatbot web.")

    return "\n".join(parts)
