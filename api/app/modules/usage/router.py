import calendar
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.modules.agent.tools.catalog_tool import get_ai_config

router = APIRouter(prefix="/usage", tags=["usage"])

AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


@router.get("/dashboard")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Get current month usage summary with alerts."""
    now = datetime.now(AR_TZ)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_passed = max(now.day, 1)
    days_left = days_in_month - days_passed

    # Get monthly total
    result = await db.execute(
        text("SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM token_usage WHERE created_at >= :start"),
        {"start": month_start},
    )
    row = result.first()
    spent = row[0] if row else 0
    requests = row[1] if row else 0

    # Config — read DIRECTLY from DB (not cached — multi-worker stale cache issue)
    _cfg_result = await db.execute(text("SELECT content FROM catalogs WHERE name = 'config'"))
    _cfg_row = _cfg_result.first()
    if _cfg_row:
        import json as _json
        _cfg = _json.loads(_cfg_row[0]) if isinstance(_cfg_row[0], str) else _cfg_row[0]
        limit = _cfg.get("ai_engine", {}).get("monthly_budget_usd", 300)
    else:
        limit = 300

    # Calculations
    daily_avg = spent / days_passed if days_passed > 0 else 0
    projected = spent + (daily_avg * days_left)
    daily_budget = limit / days_in_month
    pct_used = (spent / limit * 100) if limit > 0 else 0

    # Alert level
    if spent >= limit:
        alert = "blocked"
    elif projected > limit:
        alert = "red"
    elif pct_used >= 80:
        alert = "yellow"
    else:
        alert = "ok"

    return {
        "month": now.strftime("%Y-%m"),
        "month_label": now.strftime("%B %Y"),
        "spent_usd": round(spent, 4),
        "limit_usd": limit,
        "pct_used": round(pct_used, 1),
        "daily_avg": round(daily_avg, 4),
        "daily_budget": round(daily_budget, 4),
        "projected": round(projected, 2),
        "days_passed": days_passed,
        "days_left": days_left,
        "requests": requests,
        "alert": alert,
        "enable_hard_limit": ai_cfg.get("enable_hard_limit", True),
    }


@router.get("/daily")
async def get_daily(db: AsyncSession = Depends(get_db)):
    """Get daily usage breakdown for the last 30 days."""
    since = datetime.now(AR_TZ) - timedelta(days=30)
    result = await db.execute(
        text("""
            SELECT DATE(created_at AT TIME ZONE 'America/Argentina/Buenos_Aires') as day,
                   COALESCE(SUM(cost_usd), 0) as cost,
                   COUNT(*) as requests,
                   COALESCE(SUM(input_tokens), 0) as input_tokens,
                   COALESCE(SUM(output_tokens), 0) as output_tokens
            FROM token_usage
            WHERE created_at >= :since
            GROUP BY DATE(created_at AT TIME ZONE 'America/Argentina/Buenos_Aires')
            ORDER BY day DESC
        """),
        {"since": since},
    )
    rows = result.fetchall()
    return [
        {
            "date": str(r[0]),
            "cost_usd": round(r[1], 4),
            "requests": r[2],
            "input_tokens": r[3],
            "output_tokens": r[4],
        }
        for r in rows
    ]


@router.patch("/budget")
async def update_budget(body: dict, db: AsyncSession = Depends(get_db)):
    """Update monthly budget limit."""
    from app.modules.agent.tools.catalog_tool import invalidate_ai_config_cache
    limit = body.get("monthly_budget_usd")
    hard_limit = body.get("enable_hard_limit")

    # Read current config
    result = await db.execute(text("SELECT content FROM catalogs WHERE name = 'config'"))
    row = result.first()
    if row:
        import json
        cfg = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        ai = cfg.get("ai_engine", {})
        if limit is not None:
            ai["monthly_budget_usd"] = float(limit)
        if hard_limit is not None:
            ai["enable_hard_limit"] = bool(hard_limit)
        cfg["ai_engine"] = ai
        await db.execute(
            text("UPDATE catalogs SET content = CAST(:content AS jsonb) WHERE name = 'config'"),
            {"content": json.dumps(cfg, ensure_ascii=False)},
        )
        await db.commit()
        invalidate_ai_config_cache()
        logging.info(f"[budget] Updated: monthly_budget_usd={ai.get('monthly_budget_usd')}, enable_hard_limit={ai.get('enable_hard_limit')}")
    else:
        logging.warning("[budget] No config row found in catalogs table")

    return {"ok": True}
