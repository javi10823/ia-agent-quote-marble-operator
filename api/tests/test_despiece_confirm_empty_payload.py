"""`[DUAL_READ_CONFIRMED]{}` desde /despiece (Paso 3): payload vacío →
el handler usa el `dual_read_result` guardado (con las ediciones del
operador) en vez de pisar `verified_measurements` con `{}`."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update as sql_update

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from tests.test_text_dispiece_skips_card import _build_completed_dual


async def _quote(db_session, breakdown: dict) -> str:
    qid = f"test-despiece-confirm-{uuid.uuid4()}"
    db_session.add(Quote(
        id=qid, client_name="Cliente", project="Cocina", material="Silestone",
        localidad="Rosario", messages=[], status=QuoteStatus.DRAFT,
    ))
    await db_session.commit()
    await db_session.execute(
        sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=breakdown)
    )
    await db_session.commit()
    return qid


async def _run(db_session, qid: str) -> list[dict]:
    chunks: list[dict] = []
    try:
        async for c in AgentService().stream_chat(
            quote_id=qid, messages=[], user_message="[DUAL_READ_CONFIRMED]{}",
            plan_bytes=None, plan_filename=None, db=db_session,
        ):
            chunks.append(c)
    except Exception:
        # Después del handler el turno sigue al LLM (no disponible en tests).
        pass
    return chunks


@pytest.mark.asyncio
async def test_empty_payload_uses_saved_dual_read(db_session):
    dual = _build_completed_dual("TEXT")
    qid = await _quote(db_session, {"dual_read_result": dual})
    await _run(db_session, qid)
    await db_session.commit()
    q = (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()
    vm = q.quote_breakdown.get("verified_measurements")
    assert vm and vm["sectores"] == dual["sectores"]


@pytest.mark.asyncio
async def test_empty_payload_without_saved_dual_stops_with_message(db_session):
    qid = await _quote(db_session, {})
    chunks = await _run(db_session, qid)
    assert chunks[0]["type"] == "text"
    assert "No hay despiece guardado" in chunks[0]["content"]
    assert chunks[-1]["type"] == "done"
    await db_session.commit()
    q = (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()
    assert "verified_measurements" not in (q.quote_breakdown or {})
