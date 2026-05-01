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

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.observability.cleanup import (
    DEFAULT_RETENTION_DAYS,
    cleanup_old_audit_events,
)
from app.modules.observability.models import AuditEvent
from app.modules.observability.system_config import (
    GLOBAL_DEBUG_KEY,
    MANUAL_MODE_HARD_CAP_HOURS,
    SystemConfig,
)

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
    debug_payload: bool = False  # Phase 2.
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


class ObservabilityQuoteRow(BaseModel):
    """Una fila de la lista de quotes en `/admin/observability`.
    Refactor PR — agrupa events por quote_id."""
    quote_id: str
    client_name: Optional[str]
    actor: Optional[str]
    events_count: int
    errors_count: int
    has_debug_payloads: bool
    first_event_at: datetime
    last_event_at: datetime


class ObservabilityQuotesResponse(BaseModel):
    quotes: list[ObservabilityQuoteRow]
    total: int
    limit: int
    offset: int


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


@router.get(
    "/admin/observability/quotes",
    response_model=ObservabilityQuotesResponse,
)
async def get_observability_quotes(
    q: Optional[str] = Query(None, description="Búsqueda por quote_id o client_name"),
    actor: Optional[str] = None,
    has_errors: Optional[bool] = None,
    has_debug: Optional[bool] = None,
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Vista agrupada por quote_id. Reemplaza la lista de events sueltos
    en `/admin/observability`.

    Performance medido (10K events, 200 quotes): p95 = 6.81ms.
    Usa el índice `idx_audit_quote_created (quote_id, created_at DESC)`.

    Filtros:
    - `q`: substring match contra quote_id O client_name (case-insensitive).
    - `actor`: match exacto del actor del primer event del quote.
    - `has_errors`: solo quotes con al menos 1 event success=false.
    - `has_debug`: solo quotes con al menos 1 event debug_payload=true.
    - `from`/`to`: rango sobre `last_event_at`.

    Sort: `last_event_at DESC` (default y único — los activos arriba).
    """
    # Subquery del actor del primer event del quote.
    # SQLite no soporta `(SELECT ... LIMIT 1)` correlacionado eficiente,
    # pero la query funciona en ambos. Postgres usa el índice.
    actor_subq = (
        select(AuditEvent.actor)
        .where(AuditEvent.quote_id == AuditEvent.quote_id)
        .order_by(AuditEvent.created_at.asc())
        .limit(1)
        .scalar_subquery()
    )

    # Query dialect-agnostic. `NOT ae.success` y `MAX(ae.debug_payload)`
    # funcionan idéntico en Postgres (BOOLEAN) y SQLite (0/1 INTEGER).
    # Probado contra ambos.
    base_sql = """
        SELECT
            ae.quote_id,
            (SELECT q.client_name FROM quotes q WHERE q.id = ae.quote_id) as client_name,
            (SELECT a.actor FROM audit_events a
             WHERE a.quote_id = ae.quote_id
             ORDER BY a.created_at ASC LIMIT 1) as actor,
            COUNT(*) as events_count,
            SUM(CASE WHEN NOT ae.success THEN 1 ELSE 0 END) as errors_count,
            MAX(CASE WHEN ae.debug_payload THEN 1 ELSE 0 END) as has_debug,
            MIN(ae.created_at) as first_event_at,
            MAX(ae.created_at) as last_event_at
        FROM audit_events ae
        WHERE ae.quote_id IS NOT NULL
    """

    params: dict = {}
    if from_ts:
        base_sql += " AND ae.created_at >= :from_ts"
        params["from_ts"] = from_ts
    if to_ts:
        base_sql += " AND ae.created_at <= :to_ts"
        params["to_ts"] = to_ts

    base_sql += " GROUP BY ae.quote_id"

    # Filtros HAVING aplican al agregado.
    having: list[str] = []
    err_expr = "SUM(CASE WHEN NOT ae.success THEN 1 ELSE 0 END)"
    debug_expr = "MAX(CASE WHEN ae.debug_payload THEN 1 ELSE 0 END)"
    if has_errors is True:
        having.append(f"{err_expr} > 0")
    if has_errors is False:
        having.append(f"{err_expr} = 0")
    if has_debug is True:
        having.append(f"{debug_expr} = 1")
    if has_debug is False:
        having.append(f"{debug_expr} = 0")
    if having:
        base_sql += " HAVING " + " AND ".join(having)

    # `q` y `actor` se aplican como wrapper sobre la query agregada.
    # Subquery permite filtrar por columnas computadas (client_name, actor).
    inner = base_sql
    outer_filters: list[str] = []
    if q:
        outer_filters.append(
            "(LOWER(quote_id) LIKE :q OR LOWER(COALESCE(client_name, '')) LIKE :q)"
        )
        params["q"] = f"%{q.lower()}%"
    if actor:
        outer_filters.append("actor = :actor")
        params["actor"] = actor

    if outer_filters:
        wrapped = (
            f"SELECT * FROM ({inner}) inner_q "
            f"WHERE {' AND '.join(outer_filters)}"
        )
    else:
        wrapped = inner

    # Total para paginación.
    count_sql = f"SELECT COUNT(*) FROM ({wrapped}) c"
    total_result = await db.execute(text(count_sql), params)
    total = int(total_result.scalar_one() or 0)

    # Paginada.
    final_sql = f"{wrapped} ORDER BY last_event_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    rows_result = await db.execute(text(final_sql), params)

    quotes_rows = [
        ObservabilityQuoteRow(
            quote_id=r.quote_id,
            client_name=r.client_name,
            actor=r.actor,
            events_count=int(r.events_count or 0),
            errors_count=int(r.errors_count or 0),
            has_debug_payloads=bool(r.has_debug),
            first_event_at=r.first_event_at,
            last_event_at=r.last_event_at,
        )
        for r in rows_result.all()
    ]
    return ObservabilityQuotesResponse(
        quotes=quotes_rows, total=total, limit=limit, offset=offset,
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


# ─────────────────────────────────────────────────────────────────────
# Phase 2 — Global debug toggle
# ─────────────────────────────────────────────────────────────────────


class GlobalDebugStatus(BaseModel):
    enabled: bool
    mode: Optional[str] = None  # "1h" | "end_of_day" | "manual"
    until: Optional[datetime] = None
    started_at: Optional[datetime] = None
    started_by: Optional[str] = None
    remaining_seconds: Optional[int] = None


class GlobalDebugToggleBody(BaseModel):
    mode: str  # "1h" | "end_of_day" | "manual" | "off"


def _reject_api_key(request: Request) -> str:
    """Rechaza API key con 403; devuelve username del JWT user.
    Para endpoints solo-operador (toggles, configuración)."""
    actor = getattr(request.state, "user_email", None)
    if actor == "api-key" or not actor:
        raise HTTPException(
            status_code=403,
            detail="Endpoint solo accesible con sesión JWT (API key rechazada).",
        )
    return actor


def _compute_mode(
    mode: str, now: datetime, actor: str
) -> tuple[bool, Optional[datetime], Optional[datetime], Optional[str], str]:
    """Para `mode`, devuelve `(enabled, until, started_at, started_by, mode_label)`.

    `1h`: 1 hora desde ahora.
    `end_of_day`: 23:59 zona AR (UTC-3) del día actual.
    `manual`: sin `until`, hard cap 24h por cron.
    `off`: enabled=false.
    """
    if mode == "off":
        return False, None, None, None, ""
    started_at = now
    started_by = actor
    if mode == "1h":
        return True, now + timedelta(hours=1), started_at, started_by, "1h"
    if mode == "end_of_day":
        # 23:59 AR (UTC-3). En UTC, son las 02:59 del día siguiente.
        ar_offset = timedelta(hours=-3)
        ar_now = now + ar_offset
        ar_eod = ar_now.replace(hour=23, minute=59, second=0, microsecond=0)
        utc_eod = ar_eod - ar_offset
        # Si por alguna razón el cómputo da un instante pasado (ej.
        # request a las 23:59:30 AR ya pasó las 23:59), avanzar 24h.
        if utc_eod <= now:
            utc_eod += timedelta(days=1)
        return True, utc_eod, started_at, started_by, "end_of_day"
    if mode == "manual":
        return True, None, started_at, started_by, "manual"
    raise HTTPException(status_code=400, detail=f"Modo inválido: {mode!r}")


async def _read_global_debug_value(db: AsyncSession) -> dict:
    """Lee la fila actual de `system_config[global_debug]`. Devuelve
    `{}` si no existe."""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == GLOBAL_DEBUG_KEY)
    )
    row = result.scalar_one_or_none()
    if not row or not isinstance(row.value, dict):
        return {}
    return dict(row.value)


def _compute_remaining(value: dict, now: datetime) -> Optional[int]:
    """Para el GET endpoint. Segundos restantes si está activo, None si no."""
    if not value.get("enabled"):
        return None
    until_iso = value.get("until")
    if until_iso:
        try:
            until = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            return max(0, int((until - now).total_seconds()))
        except (ValueError, TypeError):
            return None
    # Modo manual: 24h desde started_at.
    started_iso = value.get("started_at")
    if started_iso:
        try:
            started = datetime.fromisoformat(started_iso.replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            cap = started + timedelta(hours=MANUAL_MODE_HARD_CAP_HOURS)
            return max(0, int((cap - now).total_seconds()))
        except (ValueError, TypeError):
            return None
    return None


@router.get("/admin/system-config/global-debug", response_model=GlobalDebugStatus)
async def get_global_debug(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Estado actual del modo debug global. Frontend lo polea para el
    banner sticky + el toggle en `/admin/observability`."""
    _reject_api_key(request)
    value = await _read_global_debug_value(db)
    now = datetime.now(timezone.utc)
    return GlobalDebugStatus(
        enabled=bool(value.get("enabled", False)),
        mode=value.get("mode"),
        until=value.get("until"),
        started_at=value.get("started_at"),
        started_by=value.get("started_by"),
        remaining_seconds=_compute_remaining(value, now),
    )


@router.post(
    "/admin/system-config/global-debug",
    response_model=GlobalDebugStatus,
)
async def post_global_debug(
    body: GlobalDebugToggleBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Activa/desactiva el modo debug global. JWT requerido (API key
    rechazada). Loggea `audit.global_debug_toggled`.
    """
    actor = _reject_api_key(request)
    now = datetime.now(timezone.utc)

    # Estado previo para el audit.
    previous = await _read_global_debug_value(db)

    enabled, until, started_at, started_by, mode_label = _compute_mode(
        body.mode, now, actor,
    )
    new_value = {
        "enabled": enabled,
        "mode": mode_label or None,
        "until": until.isoformat() if until else None,
        "started_at": started_at.isoformat() if started_at else None,
        "started_by": started_by,
    }

    # Upsert. Postgres: ON CONFLICT (key) DO UPDATE; SQLite: igual via
    # MERGE de SQLAlchemy ORM (.merge()).
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == GLOBAL_DEBUG_KEY)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = new_value
        existing.updated_at = now
        existing.updated_by = actor
    else:
        db.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY,
            value=new_value,
            updated_at=now,
            updated_by=actor,
        ))

    # Audit del toggle.
    from app.modules.observability.helper import log_event
    await log_event(
        db,
        event_type="audit.global_debug_toggled",
        source="observability",
        summary=f"Global debug {body.mode} (by {actor})",
        request=request,
        payload={
            "previous_state": {
                "enabled": bool(previous.get("enabled")),
                "mode": previous.get("mode"),
                "until": previous.get("until"),
            },
            "new_state": new_value,
            "action": body.mode,
        },
    )
    await db.commit()

    return GlobalDebugStatus(
        enabled=enabled,
        mode=mode_label or None,
        until=until,
        started_at=started_at,
        started_by=started_by,
        remaining_seconds=_compute_remaining(new_value, now),
    )


class GlobalDebugShutoffResponse(BaseModel):
    apagados: int
    razones: dict


@router.post(
    "/admin/audit/global-debug-shutoff",
    response_model=GlobalDebugShutoffResponse,
)
async def post_global_debug_shutoff(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Cron auto-shutoff. Apaga `global_debug` si:
    - `until < NOW()` (modo timed expirado)
    - `until IS NULL AND started_at < NOW() - 24h` (manual hardcap)

    Loggea `audit.global_debug_auto_disabled` con la razón cuando
    apaga, y SIEMPRE loguea `audit.global_debug_shutoff_run` (con
    `rows_affected`, puede ser 0) — breadcrumb que permite detectar
    si el cron está silently muerto. Si falta esa fila durante varias
    horas seguidas, el cron de Railway dejó de correr.

    Idempotente.
    """
    now = datetime.now(timezone.utc)
    razones = {"expired": 0, "manual_24h_cap": 0}

    from app.modules.observability.helper import log_event

    async def _log_run(rows_affected: int, reason: str | None = None) -> None:
        """Breadcrumb del cron, SIEMPRE — incluso con rows=0."""
        await log_event(
            db,
            event_type="audit.global_debug_shutoff_run",
            source="observability",
            summary=(
                f"Shutoff cron run: rows_affected={rows_affected}"
                + (f" (reason={reason})" if reason else "")
            ),
            actor="system",
            actor_kind="system",
            payload={"rows_affected": rows_affected, "reason": reason},
        )

    value = await _read_global_debug_value(db)
    if not value.get("enabled"):
        await _log_run(0)
        await db.commit()
        return GlobalDebugShutoffResponse(apagados=0, razones=razones)

    reason: Optional[str] = None
    until_iso = value.get("until")
    started_iso = value.get("started_at")

    if until_iso:
        try:
            until = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until <= now:
                reason = "expired"
        except (ValueError, TypeError):
            reason = "expired"
    elif started_iso:
        try:
            started = datetime.fromisoformat(started_iso.replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if (now - started) >= timedelta(hours=MANUAL_MODE_HARD_CAP_HOURS):
                reason = "manual_24h_cap"
        except (ValueError, TypeError):
            reason = "manual_24h_cap"

    if reason is None:
        # Está activo y dentro del límite — no hacer nada.
        await _log_run(0, reason="within_window")
        await db.commit()
        return GlobalDebugShutoffResponse(apagados=0, razones=razones)

    # Apagar.
    new_value = {
        "enabled": False,
        "mode": None,
        "until": None,
        "started_at": None,
        "started_by": None,
    }
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == GLOBAL_DEBUG_KEY)
    )
    existing = result.scalar_one()
    existing.value = new_value
    existing.updated_at = now
    existing.updated_by = "system"

    razones[reason] = 1

    await log_event(
        db,
        event_type="audit.global_debug_auto_disabled",
        source="observability",
        summary=f"Global debug auto-disabled ({reason})",
        actor="system",
        actor_kind="system",
        payload={
            "reason": reason,
            "previous_state": value,
        },
    )
    # Breadcrumb adicional del cron (siempre se loguea, incluso en
    # paths con apagado). Permite detectar silencios del cron.
    await _log_run(1, reason=reason)
    await db.commit()
    return GlobalDebugShutoffResponse(apagados=1, razones=razones)
