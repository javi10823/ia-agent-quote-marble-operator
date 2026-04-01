"""End-to-end tests for the quoting flow with mocked Anthropic API."""

import uuid
import shutil
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive


OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.fixture(autouse=True)
def cleanup_output():
    yield
    test_dirs = [d for d in OUTPUT_DIR.glob("*") if d.is_dir() and "test" in d.name]
    for d in test_dirs:
        shutil.rmtree(d, ignore_errors=True)


# ── Test: _execute_tool dispatches correctly ─────────────────────────────────

class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_catalog_lookup_dispatch(self, db_session):
        agent = AgentService()
        result = await agent._execute_tool(
            "catalog_lookup",
            {"catalog": "materials-silestone", "sku": "SILESTONENORTE"},
            quote_id="test-001",
            db=db_session,
        )
        assert result["found"] is True
        assert "BLANCO NORTE" in result["name"].upper()

    @pytest.mark.asyncio
    async def test_check_stock_dispatch(self, db_session):
        agent = AgentService()
        result = await agent._execute_tool(
            "check_stock",
            {"material_sku": "NONEXISTENT"},
            quote_id="test-001",
            db=db_session,
        )
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_unknown_tool(self, db_session):
        agent = AgentService()
        result = await agent._execute_tool(
            "nonexistent_tool",
            {},
            quote_id="test-001",
            db=db_session,
        )
        assert "error" in result


# ── Test: generate_documents saves to DB ─────────────────────────────────────

def _mock_generate_docs_result(quote_id, quote_data):
    """Fake generate_documents result without WeasyPrint."""
    material = quote_data.get("material_name", "MATERIAL")
    date = quote_data.get("date", "01.01.2026")
    client = quote_data.get("client_name", "Client")
    base = f"{client} - {material} - {date}"
    return {
        "ok": True,
        "pdf_url": f"/files/{quote_id}/{base}.pdf",
        "excel_url": f"/files/{quote_id}/{base}.xlsx",
        "filename_base": base,
    }


class TestGenerateDocumentsFlow:
    @pytest.mark.asyncio
    async def test_single_material_updates_db(self, db_session, sample_quote_data):
        """generate_documents should save client, material, totals, status to DB."""
        quote_id = f"test-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id, client_name="", project="",
            messages=[], status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        agent = AgentService()
        with patch("app.modules.agent.agent.generate_documents", side_effect=lambda qid, qd: _mock_generate_docs_result(qid, qd)), \
             patch("app.modules.agent.agent.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": [sample_quote_data]},
                quote_id=quote_id,
                db=db_session,
            )

        assert result["ok"] is True
        assert result["generated"] == 1

        # Verify DB was updated (fresh query to get committed data)
        result_q = await db_session.execute(select(Quote).where(Quote.id == quote_id))
        db_quote = result_q.scalar_one()
        assert db_quote.client_name == "Juan Carlos"
        assert db_quote.material == "SILESTONE BLANCO NORTE"
        assert db_quote.total_ars == 238420
        assert db_quote.total_usd == 816
        assert db_quote.status == QuoteStatus.VALIDATED
        assert db_quote.pdf_url is not None
        assert db_quote.pdf_url.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_multi_material_creates_separate_quotes(
        self, db_session, sample_multi_material_data
    ):
        """Two materials should create two quote records with correct data."""
        quote_id = f"test-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id, client_name="", project="",
            messages=[], status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        agent = AgentService()
        with patch("app.modules.agent.agent.generate_documents", side_effect=lambda qid, qd: _mock_generate_docs_result(qid, qd)), \
             patch("app.modules.agent.agent.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": sample_multi_material_data},
                quote_id=quote_id,
                db=db_session,
            )

        assert result["ok"] is True
        assert result["generated"] == 2

        # Fresh queries to get committed data
        r1 = await db_session.execute(select(Quote).where(Quote.id == quote_id))
        q1 = r1.scalar_one()
        assert q1.material == "SILESTONE BLANCO NORTE"
        assert q1.client_name == "Juan Carlos"
        assert q1.status == QuoteStatus.VALIDATED

        # Second material created a new quote
        second_result = result["results"][1]
        second_qid = second_result["quote_id"]
        assert second_qid != quote_id  # Different ID

        r2 = await db_session.execute(select(Quote).where(Quote.id == second_qid))
        q2 = r2.scalar_one()
        assert q2.material == "PURASTONE BLANCO PALOMA"
        assert q2.client_name == "Juan Carlos"
        assert q2.status == QuoteStatus.VALIDATED

    @pytest.mark.asyncio
    async def test_multi_material_each_has_urls(
        self, db_session, sample_multi_material_data
    ):
        """Each material should have PDF and Excel URLs in its result."""
        quote_id = f"test-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id, client_name="", project="",
            messages=[], status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        agent = AgentService()
        with patch("app.modules.agent.agent.generate_documents", side_effect=lambda qid, qd: _mock_generate_docs_result(qid, qd)), \
             patch("app.modules.agent.agent.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": sample_multi_material_data},
                quote_id=quote_id,
                db=db_session,
            )

        for r in result["results"]:
            assert r["ok"] is True
            assert r["pdf_url"] is not None
            assert r["excel_url"] is not None
            assert r["pdf_url"].endswith(".pdf")
            assert r["excel_url"].endswith(".xlsx")


# ── Test: update_quote tool ──────────────────────────────────────────────────

class TestUpdateQuoteTool:
    @pytest.mark.asyncio
    async def test_update_client_name(self, db_session):
        quote_id = f"test-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id, client_name="Old Name", project="",
            messages=[], status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        agent = AgentService()
        result = await agent._execute_tool(
            "update_quote",
            {"updates": {"client_name": "New Name"}},
            quote_id=quote_id,
            db=db_session,
        )

        assert result["ok"] is True
        assert "client_name" in result["updated_fields"]

        updated = await db_session.get(Quote, quote_id)
        assert updated.client_name == "New Name"

    @pytest.mark.asyncio
    async def test_update_rejects_unknown_fields(self, db_session):
        quote_id = f"test-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id, client_name="", project="",
            messages=[], status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        agent = AgentService()
        result = await agent._execute_tool(
            "update_quote",
            {"updates": {"hacker_field": "malicious_value"}},
            quote_id=quote_id,
            db=db_session,
        )

        assert result["ok"] is False
