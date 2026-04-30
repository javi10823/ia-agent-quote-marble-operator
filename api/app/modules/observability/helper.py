"""`log_event()` — helper síncrono fail-safe para `audit_events`.

Uso típico:

    from app.modules.observability import log_event

    await log_event(
        db,
        event_type="docs.regenerated",
        source="router",
        summary=f"Regenerated PDF + Excel for quote {qid}",
        request=request,        # opcional: extrae actor + request_id
        quote_id=qid,
        payload={"old_pdf_url": ..., "new_pdf_url": ...},
        success=True,
        elapsed_ms=elapsed,
    )

Reglas (acordadas con el operador):

1. **Fail-safe.** Si la DB falla, capturamos la excepción y emitimos
   `logger.warning`. **El flow del operador NO se rompe.**

2. **Síncrono.** No usamos background tasks. El INSERT corre en el
   request actual. Si pesa, batchear en una iteración futura.

3. **Sanitizado.** Aplicamos `sanitize_for_audit()` siempre, sin
   opt-out. Si el caller pasa una key sensible, queda redactada.

4. **Sin commit propio en el path normal.** Hacemos `db.add(event)`
   y `await db.flush()`. El commit lo hace el caller cuando quiera
   — eso preserva la semántica "si el endpoint rollbackea, el evento
   también". Si el caller no commitea, el evento se pierde con el
   resto (intencional, ver §F6 del diagnóstico).

   Excepción: si el caller pasa `commit=True`, hacemos commit
   inmediato. Útil cuando el evento es la única escritura del
   request (ej. login).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observability.models import AuditEvent
from app.modules.observability.sanitizer import (
    DEBUG_PAYLOAD_MAX_BYTES,
    DEFAULT_MAX_BYTES,
    LARGE_PAYLOAD_MAX_BYTES,
    sanitize_for_audit,
)
from app.modules.observability.system_config import (
    GLOBAL_DEBUG_KEY,
    MANUAL_MODE_HARD_CAP_HOURS,
)

logger = logging.getLogger(__name__)

# Eventos con payload estructurado pesado (breakdown completo, lista
# de pieces, links de Drive) → permitimos hasta 4 KB. El resto va al
# default de 2 KB. En modo debug global, todos suben a 16 KB.
_LARGE_PAYLOAD_EVENT_TYPES = frozenset({
    "quote.calculated",
    "docs.generated",
    "docs.regenerated",
})


def _max_bytes_for_event(
    event_type: str,
    override: int | None,
    debug_active: bool = False,
) -> int:
    if override is not None:
        return override
    if debug_active:
        return DEBUG_PAYLOAD_MAX_BYTES
    if event_type in _LARGE_PAYLOAD_EVENT_TYPES:
        return LARGE_PAYLOAD_MAX_BYTES
    return DEFAULT_MAX_BYTES


# ─────────────────────────────────────────────────────────────────────
# Global debug — leer estado desde system_config
# ─────────────────────────────────────────────────────────────────────


async def _is_global_debug_active(db: AsyncSession) -> bool:
    """Lee `system_config[global_debug]` y devuelve si está activo.

    Lógica del flag (acordada con el operador):
    - `enabled=False` → no activo, fin.
    - `enabled=True` y `until > NOW()` → activo (modo timed).
    - `enabled=True` y `until IS NULL` y
      `started_at > NOW() - 24h` → activo (modo manual dentro del
      hard cap de 24h).
    - `enabled=True` pero expirado (cualquiera de los dos timeouts) →
      no activo. El cron `/audit/global-debug-shutoff` se encarga
      de marcar `enabled=False` en la fila — esta función NO muta,
      solo lee.

    1 SELECT por evento. Si el test de carga lo demanda, agregar
    cache TTL 60s — pero NO antes (ver F del diagnóstico).

    Fail-safe: si la query falla o no hay fila, devuelve `False`.
    NUNCA rompe el flow del caller.
    """
    try:
        import json as _json

        from sqlalchemy import text

        result = await db.execute(
            text("SELECT value FROM system_config WHERE key = :k"),
            {"k": GLOBAL_DEBUG_KEY},
        )
        row = result.scalar_one_or_none()
        if not row:
            return False
        # Postgres JSONB devuelve dict; SQLite JSON column via raw
        # `text()` devuelve str. Normalizamos.
        if isinstance(row, str):
            try:
                row = _json.loads(row)
            except (ValueError, TypeError):
                return False
        if not isinstance(row, dict) or not row.get("enabled"):
            return False
        from datetime import datetime, timedelta, timezone as _tz

        now = datetime.now(_tz.utc)
        until_iso = row.get("until")
        started_iso = row.get("started_at")

        # Modo timed: respetar `until`.
        if until_iso:
            try:
                until = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
                if until.tzinfo is None:
                    until = until.replace(tzinfo=_tz.utc)
                return until > now
            except (ValueError, TypeError):
                return False

        # Modo manual: hard cap de 24h desde started_at.
        if started_iso:
            try:
                started = datetime.fromisoformat(started_iso.replace("Z", "+00:00"))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=_tz.utc)
                return (now - started) < timedelta(hours=MANUAL_MODE_HARD_CAP_HOURS)
            except (ValueError, TypeError):
                return False

        return False
    except Exception as e:
        logger.warning(f"[audit] _is_global_debug_active failed: {e}")
        return False


def _extract_actor(request: Optional[Request]) -> tuple[str, str]:
    """Devuelve `(actor, actor_kind)`.

    - JWT user → (`user_email`, "user"). Note: `user_email` viene del
      JWT.sub que es el username (legacy naming en auth.py).
    - API key → ("api-key", "api_key").
    - Sin request o sin state → ("system", "system") (cron, lifespan).
    """
    if request is None:
        return "system", "system"
    actor = getattr(request.state, "user_email", None)
    if not actor:
        return "system", "system"
    if actor == "api-key":
        return "api-key", "api_key"
    return actor, "user"


def _extract_request_id(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return getattr(request.state, "request_id", None)


def _extract_session_id(
    request: Optional[Request],
    quote_id: Optional[str],
) -> Optional[str]:
    """Por ahora: session_id explícito en request.state, o quote_id
    como fallback (un quote ≈ una sesión de chat hoy)."""
    if request is not None:
        sid = getattr(request.state, "session_id", None)
        if sid:
            return sid
    return quote_id


async def log_event(
    db: AsyncSession,
    *,
    event_type: str,
    source: str,
    summary: str,
    request: Optional[Request] = None,
    quote_id: Optional[str] = None,
    actor: Optional[str] = None,
    actor_kind: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    turn_index: Optional[int] = None,
    payload: Optional[Any] = None,
    debug_only_payload: Optional[dict] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
    payload_max_bytes: Optional[int] = None,
    commit: bool = False,
) -> Optional[AuditEvent]:
    """Persiste un evento en `audit_events`. Devuelve el event creado
    o `None` si falló silenciosamente.

    El flow del operador NUNCA se interrumpe por una falla acá.
    """
    try:
        # Resolución de actor (request override > argumentos > defaults).
        if actor is None or actor_kind is None:
            inferred_actor, inferred_kind = _extract_actor(request)
            actor = actor or inferred_actor
            actor_kind = actor_kind or inferred_kind

        if request_id is None:
            request_id = _extract_request_id(request)

        if session_id is None:
            session_id = _extract_session_id(request, quote_id)

        # Phase 2: chequear si modo debug global está activo. Esto
        # activa el techo de 16 KB para `tool_input` / `tool_result`
        # / brief completos y setea `debug_payload=True` en la fila.
        debug_active = await _is_global_debug_active(db)

        # Si debug está ON y el caller pasó `debug_only_payload`,
        # mergearlo al payload base. En modo normal, los datos
        # grandes (`tool_input`, `tool_result`, `message_text`) NI
        # SIQUIERA llegan a la fila — se descartan acá.
        merged_payload = dict(payload) if isinstance(payload, dict) else payload
        if debug_active and debug_only_payload:
            if isinstance(merged_payload, dict):
                merged_payload = {**merged_payload, **debug_only_payload}
            else:
                merged_payload = dict(debug_only_payload)

        # Sanitización + truncado. Eventos pesados (calculate, docs)
        # tienen 4 KB; el resto 2 KB. Debug ON → todos a 16 KB.
        # Override explícito si el caller pasa `payload_max_bytes`.
        max_bytes = _max_bytes_for_event(
            event_type, payload_max_bytes, debug_active=debug_active,
        )
        clean_payload, truncated = sanitize_for_audit(merged_payload, max_bytes=max_bytes)

        event = AuditEvent(
            id=str(uuid.uuid4()),
            # `created_at` se asigna client-side para preservar el orden
            # de inserción dentro de una misma transacción. El default
            # server-side `NOW()` de Postgres devuelve el mismo timestamp
            # para todos los inserts en la TX → el ORDER BY created_at
            # del timeline daba orden arbitrario. Sub-millisegundo de
            # diferencia entre cliente y servidor es aceptable para
            # auditoría operativa.
            created_at=datetime.now(timezone.utc),
            event_type=event_type,
            source=source,
            quote_id=quote_id,
            session_id=session_id,
            actor=actor,
            actor_kind=actor_kind,
            request_id=request_id,
            turn_index=turn_index,
            summary=summary[:8000] if summary else "",
            payload=clean_payload if clean_payload is not None else {},
            payload_truncated=truncated,
            success=success,
            error_message=error_message,
            elapsed_ms=elapsed_ms,
            debug_payload=debug_active,
        )
        db.add(event)
        await db.flush()
        if commit:
            await db.commit()
        return event
    except Exception as e:
        # NUNCA rompemos el flow del operador. Loggear y seguir.
        logger.warning(
            f"[audit] log_event failed (event_type={event_type} "
            f"quote_id={quote_id}): {e}"
        )
        # Intentar rollback parcial — si la sesión quedó en estado
        # inválido, próximas escrituras del caller fallarían.
        try:
            await db.rollback()
        except Exception:
            pass
        return None
