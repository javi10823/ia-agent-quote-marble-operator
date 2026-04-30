"""Endpoints de observability — TODOS bajo `/admin/...`.

Razón: el operador pidió explícitamente que la auditoría sea uso
**interno**. Nunca debe quedar expuesta al chat público ni al
frontend del cliente. Por eso todas las rutas viven bajo
`/api/admin/...` y requieren JWT (no API key — `auth_middleware`
ya lo enforce: `/api/v1/quote` es la única pública con API key).

Endpoints:

- `GET  /admin/quotes/{quote_id}/audit` → timeline ascendente.
- `GET  /admin/observability` → vista global con filtros.
- `GET  /admin/audit/coverage` → first_event_date para empty state.
- `POST /admin/audit/cleanup` → retention manual (lo invoca Railway
  scheduled job — NO APScheduler in-process).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.observability.cleanup import (
    DEFAULT_RETENTION_DAYS,
    cleanup_old_audit_events,
)
from app.modules.observability.models import AuditEvent

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────


class AuditEventResponse(BaseModel):
    id: str
    created_at: datetime
    event_type: str
    source: str
    quote_id: Optional[str]
    session_id: Optional[str]
    actor: str
    actor_kind: str
    request_id: Optional[str]
    turn_index: Optional[int]
    summary: str
    payload: dict
    payload_truncated: bool
    success: bool
    error_message: Optional[str]
    elapsed_ms: Optional[int]

    class Config:
        from_attributes = True


class AuditTimelineResponse(BaseModel):
    """Timeline por quote (ascendente). El bundle copy del frontend
    toma los **últimos 20** de esta lista."""
    quote_id: str
    events: list[AuditEventResponse]
    coverage: dict


class AuditGlobalResponse(BaseModel):
    events: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


class AuditCoverageResponse(BaseModel):
    first_event_date: Optional[datetime]
    total_events: int


class AuditCleanupResponse(BaseModel):
    rows_deleted: int
    retention_days: int


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/quotes/{quote_id}/audit",
    response_model=AuditTimelineResponse,
)
async def get_quote_audit(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.quote_id == quote_id)
        .order_by(AuditEvent.created_at.asc())
        .limit(500)
    )
    events = list(result.scalars().all())

    first_event = await db.execute(select(func.min(AuditEvent.created_at)))
    first_event_date = first_event.scalar_one_or_none()

    return AuditTimelineResponse(
        quote_id=quote_id,
        events=[AuditEventResponse.model_validate(e) for e in events],
        coverage={
            "first_event_date": first_event_date.isoformat() if first_event_date else None,
            "has_events_for_quote": len(events) > 0,
        },
    )


@router.get("/admin/observability", response_model=AuditGlobalResponse)
async def get_global_audit(
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
    success: Optional[bool] = None,
    quote_id: Optional[str] = None,
    source: Optional[str] = None,
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditEvent)
    count_stmt = select(func.count()).select_from(AuditEvent)

    filters = []
    if event_type:
        filters.append(AuditEvent.event_type == event_type)
    if actor:
        filters.append(AuditEvent.actor == actor)
    if success is not None:
        filters.append(AuditEvent.success == success)
    if quote_id:
        filters.append(AuditEvent.quote_id == quote_id)
    if source:
        filters.append(AuditEvent.source == source)
    if from_ts:
        filters.append(AuditEvent.created_at >= from_ts)
    if to_ts:
        filters.append(AuditEvent.created_at <= to_ts)

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one())

    stmt = stmt.order_by(desc(AuditEvent.created_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    return AuditGlobalResponse(
        events=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/admin/audit/coverage", response_model=AuditCoverageResponse)
async def get_audit_coverage(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.min(AuditEvent.created_at).label("first"),
            func.count().label("total"),
        )
    )
    row = result.one()
    return AuditCoverageResponse(
        first_event_date=row.first,
        total_events=int(row.total or 0),
    )


@router.post("/admin/audit/cleanup", response_model=AuditCleanupResponse)
async def post_audit_cleanup(
    retention_days: int = Query(DEFAULT_RETENTION_DAYS, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    """Retention manual. Lo invoca Railway scheduled job con un
    `curl POST /api/admin/audit/cleanup`. Idempotente. Loggea su
    propia ejecución como `audit.cleanup_run`.
    """
    rows = await cleanup_old_audit_events(db, retention_days=retention_days)
    return AuditCleanupResponse(
        rows_deleted=rows,
        retention_days=retention_days,
    )
