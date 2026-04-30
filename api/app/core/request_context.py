"""Middleware que asigna `request_id` (correlation) y reserva
`session_id` para cada request.

- `request.state.request_id` — UUID4 generado al entrar el request.
  Si el caller mandó `X-Request-Id`, lo respetamos (útil para
  correlacionar logs de frontend ↔ backend si en el futuro
  decidimos hacerlo). En la response sale como `X-Request-Id`.

- `request.state.session_id` — `None` por default. Cuando exista
  un modelo de sesión real, esta línea se cambia para resolverlo
  (ej. JWT.session_id, cookie de sesión, etc.). Por ahora el audit
  helper hace fallback a `quote_id`.

Esto se monta en `main.py` antes que cualquier otro middleware que
necesite leer `request.state.request_id` (incluyendo nuestro
`auth_middleware`, que también podría querer loggear con el id).
"""
from __future__ import annotations

import uuid

from fastapi import Request


async def request_context_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id")
    request.state.request_id = incoming or str(uuid.uuid4())

    # Placeholder. Hoy no hay sesión modelada. El helper de audit
    # caerá a quote_id si está disponible.
    if not getattr(request.state, "session_id", None):
        request.state.session_id = None

    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response
