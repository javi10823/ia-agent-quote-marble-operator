"""Retention para `audit_events`. **NO se monta en el MVP.**

Razón: el operador pidió mantener Phase 2 acotada a persistencia +
eventos + vistas + bundle copy. La limpieza queda explícitamente
fuera de scope hasta Phase 3+ — para entonces tendremos data real
sobre tasa de inserción y podremos calibrar tanto el período de
retención como el trigger (cron Railway externo, command manual, o
endpoint admin).

Este módulo deja la implementación lista para cuando se active.

Reglas acordadas con el operador:

- **Sin background tasks.** Cuando se active, será un endpoint HTTP
  invocable por cron Railway externo (idempotente).

- **Loggear la propia ejecución.** Cada run del cleanup emite un
  evento `audit.cleanup_run` con `rows_deleted` y `elapsed_ms`. Esto
  evita falsos positivos en monitoreo si el cron corre 2× simultáneo
  (ambos hacen DELETE, el segundo loggea 0 deletions, pero el evento
  documenta la duplicación).

- **Idempotente.** `DELETE WHERE created_at < NOW() - INTERVAL N
  DAYS`. Postgres maneja la concurrencia.

Cuando se active, mover este archivo a `cleanup_active.py` o
similar y wirearlo en `router.py` con un endpoint dedicado (con
auth admin si aplica).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90


async def cleanup_old_audit_events(
    db: AsyncSession,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> int:
    """Borra eventos más viejos que `retention_days` y retorna el
    rowcount. Usar dentro de un endpoint HTTP triggereado por cron
    externo cuando se active.
    """
    from datetime import datetime, timedelta, timezone

    from app.modules.observability.helper import log_event

    started = time.monotonic()
    # Dialect-agnostic: pasamos el cutoff calculado en Python en vez
    # de depender de `INTERVAL` (Postgres) o `datetime('now', '-N day')`
    # (SQLite). Funciona idéntico en tests + prod.
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        text("DELETE FROM audit_events WHERE created_at < :cutoff"),
        {"cutoff": cutoff},
    )
    rows = int(result.rowcount or 0)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    # Trace de la propia ejecución (F7 del diagnóstico).
    await log_event(
        db,
        event_type="audit.cleanup_run",
        source="observability",
        summary=f"Retention cleanup: deleted {rows} events older than {retention_days}d",
        actor="system",
        actor_kind="system",
        payload={"rows_deleted": rows, "retention_days": retention_days},
        elapsed_ms=elapsed_ms,
    )
    await db.commit()
    logger.info(
        f"[audit-cleanup] deleted={rows} retention_days={retention_days} "
        f"elapsed_ms={elapsed_ms}"
    )
    return rows
