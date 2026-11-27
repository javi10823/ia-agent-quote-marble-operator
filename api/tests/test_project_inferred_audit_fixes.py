"""Fixes del audit de #517: marca project_source (merge, pisable, largo, bloque)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.quote_engine.project_inference import suggest_project_name
from tests.test_calculate_quote_project_fallback import _calc, _quote
from tests.test_e2e_flow import DRIVE_MOCK, _mock_upload_single, cleanup_output, seed_calc  # noqa: F401


async def _reload(db_session, qid):
    db_session.expire_all()
    return (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()


class TestMarkSurvivesCalculate:
    @pytest.mark.asyncio
    async def test_marca_se_conserva(self, db_session):
        qid = await _quote(db_session, "Juan - Silestone", {"project_source": "inferred"})
        res = await _calc(db_session, qid, "")
        assert res["ok"] is True, res.get("error")
        q = await _reload(db_session, qid)
        assert q.quote_breakdown["project_source"] == "inferred"

    @pytest.mark.asyncio
    async def test_quote_sin_marca_no_la_gana(self, db_session):
        qid = await _quote(db_session, "Cocina con isla", {"x": 1})
        res = await _calc(db_session, qid, "")
        assert res["ok"] is True, res.get("error")
        q = await _reload(db_session, qid)
        assert "project_source" not in q.quote_breakdown


class TestInferredIsOverridable:
    async def _generate(self, db_session, qid, sample_quote_data):
        await seed_calc(db_session, qid, sample_quote_data)
        with patch("app.modules.agent.agent.upload_to_drive", return_value=DRIVE_MOCK), patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            side_effect=_mock_upload_single,
        ):
            res = await AgentService()._execute_tool(
                "generate_documents", {"quotes": [sample_quote_data]},
                quote_id=qid, db=db_session,
            )
        assert res["ok"] is True, res
        return await _reload(db_session, qid)

    @pytest.mark.asyncio
    async def test_inferred_se_pisa_y_borra_marca(self, db_session, sample_quote_data):
        qid = f"test-{uuid.uuid4()}"
        db_session.add(Quote(
            id=qid, client_name="Juan Carlos", project="Juan Carlos - Silestone",
            messages=[], status=QuoteStatus.DRAFT,
            quote_breakdown={"project_source": "inferred"},
        ))
        await db_session.commit()
        sample_quote_data["project"] = "Obra Real"
        q = await self._generate(db_session, qid, sample_quote_data)
        assert q.project == "Obra Real"
        assert "project_source" not in (q.quote_breakdown or {})

    @pytest.mark.asyncio
    async def test_no_inferred_sigue_primero_gana(self, db_session, sample_quote_data):
        qid = f"test-{uuid.uuid4()}"
        db_session.add(Quote(
            id=qid, client_name="Juan Carlos", project="Obra Previa",
            messages=[], status=QuoteStatus.DRAFT,
        ))
        await db_session.commit()
        sample_quote_data["project"] = "Obra Real"
        q = await self._generate(db_session, qid, sample_quote_data)
        assert q.project == "Obra Previa"


class TestLargo:
    @pytest.mark.parametrize("n", [450, 600])
    def test_tope(self, n):
        out = suggest_project_name("C" * n, "M" * n)
        assert len(out) <= 450 <= 500

    def test_separador(self):
        assert suggest_project_name("Juan Pérez", "Silestone Blanco Norte") == (
            "Juan Pérez - Silestone Blanco Norte"
        )


class TestStreamChatInyectaBloque:
    @pytest.mark.asyncio
    async def test_system_prompt_lleva_el_bloque(self, db_session, monkeypatch):
        qid = f"test-{uuid.uuid4()}"
        db_session.add(Quote(
            id=qid, client_name="Juan", project="Juan - Silestone",
            messages=[], status=QuoteStatus.DRAFT,
            quote_breakdown={"project_source": "inferred"},
        ))
        await db_session.commit()
        captured = {}

        class _Stream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def get_final_message(self):
                return SimpleNamespace(
                    usage=SimpleNamespace(
                        input_tokens=1, output_tokens=1,
                        cache_read_input_tokens=0, cache_creation_input_tokens=0,
                    ),
                    content=[SimpleNamespace(type="text", text="ok")],
                    stop_reason="end_turn",
                )

        def _fake_stream(**kwargs):
            captured["system"] = kwargs.get("system")
            return _Stream()

        agent = AgentService()
        monkeypatch.setattr(agent.client.messages, "stream", _fake_stream)
        try:
            async for _ in agent.stream_chat(
                quote_id=qid, messages=[], user_message="hola",
                plan_bytes=None, plan_filename=None, db=db_session,
            ):
                pass
        except Exception:
            pass
        assert captured.get("system"), "el cliente LLM no fue invocado"
        texts = [b.get("text", "") for b in captured["system"] if isinstance(b, dict)]
        assert any("PROYECTO/OBRA YA DEFINIDO" in t and "Juan - Silestone" in t for t in texts)


class TestTextOnlyInferredPisable:
    @pytest.mark.asyncio
    async def test_obra_del_operador_pisa_inferred(self, db_session, monkeypatch):
        from tests.test_project_inferred_text_only import (
            _assert_flow_ran, _patch_pipeline, _run,
        )
        _patch_pipeline(monkeypatch, {"client_name": "Juan", "material": "Silestone"})
        qid = f"test-{uuid.uuid4()}"
        db_session.add(Quote(
            id=qid, client_name="Juan", project="Juan - Silestone", material="",
            messages=[], status=QuoteStatus.DRAFT,
            quote_breakdown={"project_source": "inferred"},
        ))
        await db_session.commit()
        chunks = await _run(
            db_session, qid, "Cliente: Juan, Obra: Casa López, material Silestone, mesada 2.30 x 0.60"
        )
        _assert_flow_ran(chunks)
        q = await _reload(db_session, qid)
        assert q.project == "Casa López"
        assert "project_source" not in q.quote_breakdown
