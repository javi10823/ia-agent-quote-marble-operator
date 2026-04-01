"""End-to-end tests — run REAL code, only mock external services (Drive)."""

import uuid
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService


OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.fixture(autouse=True)
def cleanup_output():
    """Clean up generated files after each test."""
    yield
    for d in OUTPUT_DIR.glob("test-*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


async def _create_quote(db_session, quote_id=None):
    """Helper to create a quote in DB."""
    qid = quote_id or f"test-{uuid.uuid4()}"
    quote = Quote(
        id=qid, client_name="", project="",
        messages=[], status=QuoteStatus.DRAFT,
    )
    db_session.add(quote)
    await db_session.commit()
    return qid


DRIVE_MOCK = {"ok": True, "drive_url": "https://drive.google.com/test"}


# ── Tool dispatch ────────────────────────────────────────────────────────────

class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_catalog_lookup_real(self, db_session):
        """catalog_lookup runs real code against real catalog JSONs."""
        agent = AgentService()
        result = await agent._execute_tool(
            "catalog_lookup",
            {"catalog": "materials-silestone", "sku": "SILESTONENORTE"},
            quote_id="test-001",
            db=db_session,
        )
        assert result["found"] is True
        assert result["currency"] == "USD"
        assert result["price_usd"] > 0

    @pytest.mark.asyncio
    async def test_catalog_lookup_by_name_real(self, db_session):
        """Name-based search works against real catalog."""
        agent = AgentService()
        result = await agent._execute_tool(
            "catalog_lookup",
            {"catalog": "materials-purastone", "sku": "BLANCO PALOMA"},
            quote_id="test-001",
            db=db_session,
        )
        assert result["found"] is True
        assert "PALOMA" in result["name"].upper()

    @pytest.mark.asyncio
    async def test_unknown_tool(self, db_session):
        agent = AgentService()
        result = await agent._execute_tool(
            "nonexistent_tool", {}, quote_id="test-001", db=db_session,
        )
        assert "error" in result


# ── Single material — REAL generate_documents ─────────────────────────────────

class TestSingleMaterialReal:
    @pytest.mark.asyncio
    async def test_generates_excel_and_updates_db(self, db_session, sample_quote_data):
        """Real generate_documents: creates Excel, saves data to DB, sets validated."""
        qid = await _create_quote(db_session)

        agent = AgentService()
        with patch("app.modules.agent.agent.upload_to_drive", return_value=DRIVE_MOCK):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": [sample_quote_data]},
                quote_id=qid,
                db=db_session,
            )

        assert result["ok"] is True
        assert result["generated"] == 1
        assert result["results"][0]["ok"] is True

        # Verify REAL files on disk
        quote_dir = OUTPUT_DIR / qid
        assert quote_dir.exists()
        xlsx_files = list(quote_dir.glob("*.xlsx"))
        assert len(xlsx_files) >= 1, f"No Excel file in {quote_dir}"

        # Verify DB was updated with correct data
        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        db_quote = r.scalar_one()
        assert db_quote.client_name == "Juan Carlos"
        assert db_quote.material == "SILESTONE BLANCO NORTE"
        assert db_quote.total_ars == 238420
        assert db_quote.total_usd == 816
        assert db_quote.status == QuoteStatus.VALIDATED
        assert db_quote.excel_url is not None
        assert db_quote.excel_url.endswith(".xlsx")
        assert db_quote.drive_url == "https://drive.google.com/test"

    @pytest.mark.asyncio
    async def test_drive_failure_still_saves_data(self, db_session, sample_quote_data):
        """If Drive upload fails, quote data and files should still be saved."""
        qid = await _create_quote(db_session)

        agent = AgentService()
        with patch("app.modules.agent.agent.upload_to_drive", return_value={"ok": False, "error": "quota exceeded"}):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": [sample_quote_data]},
                quote_id=qid,
                db=db_session,
            )

        # Files should still be generated
        assert result["ok"] is True

        # DB should have quote data but no drive_url
        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        db_quote = r.scalar_one()
        assert db_quote.client_name == "Juan Carlos"
        assert db_quote.material == "SILESTONE BLANCO NORTE"
        assert db_quote.status == QuoteStatus.VALIDATED
        assert db_quote.drive_url is None


# ── Multi-material — REAL generate_documents ──────────────────────────────────

class TestMultiMaterialReal:
    @pytest.mark.asyncio
    async def test_creates_two_quotes_with_correct_materials(
        self, db_session, sample_multi_material_data
    ):
        """Two materials: each gets its own quote record with correct data."""
        qid = await _create_quote(db_session)

        agent = AgentService()
        with patch("app.modules.agent.agent.upload_to_drive", return_value=DRIVE_MOCK):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": sample_multi_material_data},
                quote_id=qid,
                db=db_session,
            )

        assert result["ok"] is True
        assert result["generated"] == 2

        # Quote 1: Silestone (uses original quote_id)
        r1 = await db_session.execute(select(Quote).where(Quote.id == qid))
        q1 = r1.scalar_one()
        assert q1.material == "SILESTONE BLANCO NORTE"
        assert q1.client_name == "Juan Carlos"
        assert q1.total_usd == 816
        assert q1.status == QuoteStatus.VALIDATED
        assert q1.excel_url is not None

        # Quote 2: Purastone (new quote_id)
        second_qid = result["results"][1]["quote_id"]
        assert second_qid != qid

        r2 = await db_session.execute(select(Quote).where(Quote.id == second_qid))
        q2 = r2.scalar_one()
        assert q2.material == "PURASTONE BLANCO PALOMA"
        assert q2.client_name == "Juan Carlos"
        assert q2.total_usd == 529
        assert q2.status == QuoteStatus.VALIDATED
        assert q2.excel_url is not None

    @pytest.mark.asyncio
    async def test_each_material_has_separate_files(
        self, db_session, sample_multi_material_data
    ):
        """Each material should have its own output directory with files."""
        qid = await _create_quote(db_session)

        agent = AgentService()
        with patch("app.modules.agent.agent.upload_to_drive", return_value=DRIVE_MOCK):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": sample_multi_material_data},
                quote_id=qid,
                db=db_session,
            )

        for r in result["results"]:
            assert r["ok"] is True
            qdir = OUTPUT_DIR / r["quote_id"]
            assert qdir.exists(), f"Output dir missing: {qdir}"
            xlsx = list(qdir.glob("*.xlsx"))
            assert len(xlsx) >= 1, f"No Excel in {qdir}"

    @pytest.mark.asyncio
    async def test_materials_not_mixed_between_quotes(
        self, db_session, sample_multi_material_data
    ):
        """Silestone data must NOT appear in Purastone quote and vice versa."""
        qid = await _create_quote(db_session)

        agent = AgentService()
        with patch("app.modules.agent.agent.upload_to_drive", return_value=DRIVE_MOCK):
            result = await agent._execute_tool(
                "generate_documents",
                {"quotes": sample_multi_material_data},
                quote_id=qid,
                db=db_session,
            )

        # Verify filenames contain correct material
        for r in result["results"]:
            material = r["material"]
            excel_url = r["excel_url"]
            # The material name should appear in the file URL
            assert material.replace(" ", "%20") in excel_url or material in excel_url, \
                f"Material '{material}' not in excel_url '{excel_url}'"


# ── update_quote tool — REAL ─────────────────────────────────────────────────

class TestUpdateQuoteReal:
    @pytest.mark.asyncio
    async def test_update_client_name(self, db_session):
        qid = await _create_quote(db_session)

        agent = AgentService()
        result = await agent._execute_tool(
            "update_quote",
            {"updates": {"client_name": "Maria Lopez"}},
            quote_id=qid,
            db=db_session,
        )

        assert result["ok"] is True

        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        assert r.scalar_one().client_name == "Maria Lopez"

    @pytest.mark.asyncio
    async def test_update_status(self, db_session):
        qid = await _create_quote(db_session)

        agent = AgentService()
        await agent._execute_tool(
            "update_quote",
            {"updates": {"status": "sent"}},
            quote_id=qid,
            db=db_session,
        )

        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        assert r.scalar_one().status == "sent"

    @pytest.mark.asyncio
    async def test_rejects_unknown_fields(self, db_session):
        qid = await _create_quote(db_session)

        agent = AgentService()
        result = await agent._execute_tool(
            "update_quote",
            {"updates": {"hacker_field": "malicious"}},
            quote_id=qid,
            db=db_session,
        )

        assert result["ok"] is False
