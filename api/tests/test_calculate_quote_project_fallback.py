"""Fallback determinístico de `project` en calculate_quote, limpieza de
`project_source` en update_quote y bloque de system prompt del project sugerido."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update as sql_update

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService, _build_inferred_project_block


async def _quote(db_session, project: str, breakdown=None) -> str:
    qid = f"test-pj-fallback-{uuid.uuid4()}"
    db_session.add(Quote(
        id=qid, client_name="Maria Lopez", project=project,
        material="Silestone Blanco Norte", localidad="puerto san martin",
        messages=[], status=QuoteStatus.DRAFT,
    ))
    await db_session.commit()
    if breakdown is not None:
        await db_session.execute(
            sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=breakdown)
        )
        await db_session.commit()
    return qid


def _inputs(project: str) -> dict:
    return {
        "client_name": "Maria Lopez",
        "project": project,
        "material": "Silestone Blanco Norte",
        "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        "localidad": "puerto san martin",
        "plazo": "30 días",
    }


async def _calc(db_session, qid: str, project: str) -> dict:
    return await AgentService()._execute_tool(
        "calculate_quote", _inputs(project), quote_id=qid, db=db_session
    )


class TestCalculateQuoteFallback:
    @pytest.mark.asyncio
    async def test_db_valido_e_input_vacio_completa(self, db_session):
        qid = await _quote(db_session, "Juan Pérez - Silestone Blanco Norte")
        res = await _calc(db_session, qid, "")
        assert res["ok"] is True, res.get("error")
        assert res["project"] == "Juan Pérez - Silestone Blanco Norte"

    @pytest.mark.asyncio
    async def test_input_na_se_completa(self, db_session):
        qid = await _quote(db_session, "Cocina con isla")
        res = await _calc(db_session, qid, "n/a")
        assert res["ok"] is True, res.get("error")
        assert res["project"] == "Cocina con isla"

    @pytest.mark.asyncio
    async def test_columna_fijada_gana_sobre_input_del_llm(self, db_session):
        # Ajustado (antes: el input del LLM pisaba la columna). La obra fijada
        # por el operador/brief (sin marca inferred) gana.
        qid = await _quote(db_session, "Cocina Belgrano")
        res = await _calc(db_session, qid, "Otra obra")
        assert res["ok"] is True, res.get("error")
        assert res["project"] == "Cocina Belgrano"

    @pytest.mark.asyncio
    async def test_columna_inferida_es_pisada_por_input_valido(self, db_session):
        qid = await _quote(db_session, "Juan - Silestone", {
            "project": "Juan - Silestone", "project_source": "inferred",
        })
        res = await _calc(db_session, qid, "Casa López")
        assert res["ok"] is True, res.get("error")
        assert res["project"] == "Casa López"

    @pytest.mark.asyncio
    async def test_columna_vacia_e_input_valido_usa_input(self, db_session):
        qid = await _quote(db_session, "")
        res = await _calc(db_session, qid, "Casa López")
        assert res["ok"] is True, res.get("error")
        assert res["project"] == "Casa López"

    @pytest.mark.asyncio
    async def test_db_vacio_e_input_vacio_rechaza(self, db_session):
        qid = await _quote(db_session, "")
        res = await _calc(db_session, qid, "")
        assert res["ok"] is False
        assert "Falta el nombre del proyecto" in res["error"]

    @pytest.mark.asyncio
    async def test_db_placeholder_rechaza(self, db_session):
        qid = await _quote(db_session, "-")
        res = await _calc(db_session, qid, "")
        assert res["ok"] is False
        assert "Falta el nombre del proyecto" in res["error"]


class TestUpdateQuoteProjectSource:
    async def _update(self, db_session, qid, updates):
        res = await AgentService()._execute_tool(
            "update_quote", {"updates": updates}, quote_id=qid, db=db_session
        )
        assert res["ok"] is True
        db_session.expire_all()
        return (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()

    @pytest.mark.asyncio
    async def test_project_nuevo_marca_edited(self, db_session):
        qid = await _quote(db_session, "Juan - Silestone", {
            "project": "Juan - Silestone", "project_source": "inferred", "x": 1,
        })
        q = await self._update(db_session, qid, {"project": "Casa López"})
        assert q.project == "Casa López"
        assert q.quote_breakdown["project_source"] == "edited"
        assert q.quote_breakdown["x"] == 1

    @pytest.mark.asyncio
    async def test_project_igual_al_sugerido_tambien_marca_edited(self, db_session):
        qid = await _quote(db_session, "Juan - Silestone", {
            "project": "Juan - Silestone", "project_source": "inferred",
        })
        q = await self._update(db_session, qid, {"project": "Juan - Silestone"})
        assert q.quote_breakdown["project_source"] == "edited"

    @pytest.mark.asyncio
    async def test_project_del_brief_sin_marca_no_se_marca(self, db_session):
        qid = await _quote(db_session, "", {"x": 1})
        q = await self._update(db_session, qid, {"project": "Casa López"})
        assert "project_source" not in q.quote_breakdown

    @pytest.mark.asyncio
    async def test_solo_client_name_mantiene_la_marca(self, db_session):
        qid = await _quote(db_session, "Juan - Silestone", {
            "project": "Juan - Silestone", "project_source": "inferred",
        })
        q = await self._update(db_session, qid, {"client_name": "Otro Cliente"})
        assert q.quote_breakdown["project_source"] == "inferred"


class TestInferredProjectBlock:
    def _q(self, project, bd):
        return SimpleNamespace(project=project, quote_breakdown=bd)

    def test_inferred_devuelve_bloque_sin_cache_control(self):
        b = _build_inferred_project_block(
            self._q("Juan - Silestone", {"project_source": "inferred"})
        )
        assert b["type"] == "text"
        assert "Juan - Silestone" in b["text"]
        assert "PROYECTO/OBRA YA DEFINIDO" in b["text"]
        assert "cache_control" not in b

    @pytest.mark.parametrize("q", [
        None,
        SimpleNamespace(project="X", quote_breakdown=None),
        SimpleNamespace(project="X", quote_breakdown={}),
        SimpleNamespace(project="X", quote_breakdown={"project_source": "brief"}),
        SimpleNamespace(project="", quote_breakdown={"project_source": "inferred"}),
        SimpleNamespace(project="   ", quote_breakdown={"project_source": "inferred"}),
        SimpleNamespace(project=None, quote_breakdown={"project_source": "inferred"}),
    ])
    def test_sin_marca_o_sin_project_none(self, q):
        assert _build_inferred_project_block(q) is None
