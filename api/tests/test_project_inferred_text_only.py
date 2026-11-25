"""Early-persist del `project` sugerido (flujo solo texto y flujo con plano).

Prioridad: brief (sin marca) > cliente + material > tipo de trabajo,
siempre marcado `quote_breakdown.project_source = "inferred"` salvo el brief.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from tests.test_text_dispiece_skips_card import _build_completed_dual


async def _new_quote(db_session, **cols) -> str:
    qid = f"test-project-inferred-{uuid.uuid4()}"
    base = dict(client_name="", project="", material="", messages=[], status=QuoteStatus.DRAFT)
    base.update(cols)
    db_session.add(Quote(id=qid, **base))
    await db_session.commit()
    return qid


def _patch_pipeline(monkeypatch, brief_analysis: dict):
    async def _fake_parse(*_a, **_k):
        return _build_completed_dual("TEXT")

    async def _fake_ctx(*_a, **_k):
        return {
            "data_known": [],
            "assumptions": [],
            "pending_questions": [],
            "_brief_analysis_raw": brief_analysis,
        }

    monkeypatch.setattr(
        "app.modules.quote_engine.text_parser.parse_brief_to_card", _fake_parse
    )
    monkeypatch.setattr(
        "app.modules.quote_engine.context_analyzer.build_context_analysis", _fake_ctx
    )


async def _run(db_session, qid: str, msg: str = "mesada de 2.30 x 0.60") -> list:
    chunks = []
    try:
        async for c in AgentService().stream_chat(
            quote_id=qid, messages=[], user_message=msg,
            plan_bytes=None, plan_filename=None, db=db_session,
        ):
            chunks.append(c)
    except Exception:
        pass
    return chunks


async def _reload(db_session, qid: str) -> Quote:
    db_session.expire_all()
    return (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()


def _assert_flow_ran(chunks):
    assert any(
        c.get("type") == "action" and "Leyendo medidas del texto" in c.get("content", "")
        for c in chunks
    ), f"el flujo text-only no corrió: {chunks}"


@pytest.mark.asyncio
async def test_cliente_y_material_arman_el_project(db_session, monkeypatch):
    _patch_pipeline(monkeypatch, {
        "client_name": "Juan Pérez", "material": "Silestone Blanco Norte",
        "work_types": ["cocina"],
    })
    qid = await _new_quote(db_session)
    _assert_flow_ran(await _run(db_session, qid))
    q = await _reload(db_session, qid)
    assert q.project == "Juan Pérez - Silestone Blanco Norte"
    assert q.quote_breakdown["project_source"] == "inferred"


@pytest.mark.asyncio
async def test_sin_cliente_ni_material_usa_work_types(db_session, monkeypatch):
    _patch_pipeline(monkeypatch, {"work_types": ["cocina"], "isla_mentioned": True})
    qid = await _new_quote(db_session)
    _assert_flow_ran(await _run(db_session, qid))
    q = await _reload(db_session, qid)
    assert q.project == "Cocina con isla"
    assert q.quote_breakdown["project_source"] == "inferred"


@pytest.mark.asyncio
async def test_project_del_brief_no_lleva_marca(db_session, monkeypatch):
    _patch_pipeline(monkeypatch, {
        "project": "Casa López", "client_name": "Juan", "work_types": ["cocina"],
    })
    qid = await _new_quote(db_session)
    _assert_flow_ran(await _run(db_session, qid))
    q = await _reload(db_session, qid)
    assert q.project == "Casa López"
    assert "project_source" not in q.quote_breakdown


@pytest.mark.asyncio
async def test_project_previo_queda_intacto(db_session, monkeypatch):
    _patch_pipeline(monkeypatch, {"client_name": "Juan", "material": "Silestone"})
    qid = await _new_quote(db_session, project="Obra del operador")
    _assert_flow_ran(await _run(db_session, qid))
    q = await _reload(db_session, qid)
    assert q.project == "Obra del operador"
    assert "project_source" not in q.quote_breakdown


@pytest.mark.asyncio
async def test_analysis_vacio_deja_project_vacio(db_session, monkeypatch):
    _patch_pipeline(monkeypatch, {})
    qid = await _new_quote(db_session)
    _assert_flow_ran(await _run(db_session, qid))
    q = await _reload(db_session, qid)
    assert not q.project
    assert "project_source" not in q.quote_breakdown


@pytest.mark.asyncio
async def test_project_hint_del_mensaje_gana_y_sin_marca(db_session, monkeypatch):
    _patch_pipeline(monkeypatch, {"client_name": "Juan", "material": "Silestone"})
    qid = await _new_quote(db_session)
    chunks = await _run(
        db_session, qid, "Cliente: Juan, Obra: Casa López, material Silestone, mesada 2.30 x 0.60"
    )
    _assert_flow_ran(chunks)
    q = await _reload(db_session, qid)
    assert q.project == "Casa López"
    assert "project_source" not in q.quote_breakdown


# ── Flujo con plano: mismo patrón con el helper sobre un Quote simulado ──

def _make_quote(client_name="", project="", material="", localidad=""):
    q = MagicMock()
    q.client_name, q.project, q.material, q.localidad = client_name, project, material, localidad
    return q


def test_flujo_plano_mismo_patron_con_quote_mock():
    """Replica el cableado de `_run_dual_read`: columnas del brief primero,
    después el helper sobre lo que quedó vacío."""
    from app.modules.agent.agent import _extract_column_updates_from_analysis
    from app.modules.quote_engine.project_inference import resolve_project_for_persist

    brief = {"client_name": "Erica Bernardi", "material": "Puraprima Onix", "work_types": ["baño"]}
    quote = _make_quote()
    col_updates = _extract_column_updates_from_analysis(brief, quote)
    assert "project" not in col_updates
    res = resolve_project_for_persist(
        brief,
        current_project=quote.project,
        pending_project=col_updates.get("project"),
        client_name=col_updates.get("client_name") or quote.client_name,
        material=col_updates.get("material") or quote.material,
    )
    assert res == ("Erica Bernardi - Puraprima Onix", "inferred")


def test_flujo_plano_con_project_del_brief_no_marca():
    from app.modules.agent.agent import _extract_column_updates_from_analysis
    from app.modules.quote_engine.project_inference import resolve_project_for_persist

    brief = {"project": "Edificio Sol", "client_name": "X"}
    quote = _make_quote()
    col_updates = _extract_column_updates_from_analysis(brief, quote)
    assert col_updates["project"] == "Edificio Sol"
    assert resolve_project_for_persist(
        brief, current_project=quote.project, pending_project=col_updates.get("project"),
        client_name="X", material=None,
    ) is None
