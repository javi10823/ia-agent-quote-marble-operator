"""Unit tests for document_tool.py — PDF/Excel generation."""

import os
import shutil
import subprocess
import pytest
from pathlib import Path
from app.modules.agent.tools.document_tool import (
    generate_documents,
    _build_html,
    _format_grand_total,
)

# fpdf2 is pure Python — PDF tests always run
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

requires_pdf = pytest.mark.skipif(
    not HAS_FPDF, reason="fpdf2 not installed"
)


OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.fixture(autouse=True)
def cleanup_output():
    """Clean up generated files after each test."""
    yield
    test_dirs = [d for d in OUTPUT_DIR.glob("test-*") if d.is_dir()]
    for d in test_dirs:
        shutil.rmtree(d, ignore_errors=True)


# ── _format_grand_total ──────────────────────────────────────────────────────

class TestFormatGrandTotal:
    def test_usd_and_ars(self):
        result = _format_grand_total(238420, 816, "USD")
        assert "$238.420" in result
        assert "USD 816" in result
        assert "mano de obra" in result.lower()

    def test_ars_only(self):
        result = _format_grand_total(500000, 0, "ARS")
        assert "$500.000" in result
        assert "USD" not in result

    def test_zero_values(self):
        result = _format_grand_total(0, 0, "ARS")
        assert "PRESUPUESTO TOTAL" in result


# ── _build_html ──────────────────────────────────────────────────────────────

class TestBuildHTML:
    def test_contains_client_name(self, sample_quote_data):
        html = _build_html(sample_quote_data)
        assert "Juan Carlos" in html

    def test_contains_material(self, sample_quote_data):
        html = _build_html(sample_quote_data)
        assert "SILESTONE BLANCO NORTE" in html

    def test_contains_forma_de_pago(self, sample_quote_data):
        html = _build_html(sample_quote_data)
        assert "Contado" in html

    def test_contains_footer_note(self, sample_quote_data):
        html = _build_html(sample_quote_data)
        assert "No se suben mesadas que no entren en ascensor" in html

    def test_contains_conditions(self, sample_quote_data):
        html = _build_html(sample_quote_data)
        assert "PRESUPUESTO SUJETO" in html

    def test_contains_grand_total(self, sample_quote_data):
        html = _build_html(sample_quote_data)
        assert "PRESUPUESTO TOTAL" in html


# ── generate_documents — file creation ───────────────────────────────────────

class TestGenerateDocuments:
    @requires_pdf
    @pytest.mark.asyncio
    async def test_creates_pdf_and_excel(self, sample_quote_data):
        quote_id = "test-gen-001"
        result = await generate_documents(quote_id, sample_quote_data)

        assert result["ok"] is True
        assert result["pdf_url"].endswith(".pdf")
        assert result["excel_url"].endswith(".xlsx")

        # Verify files exist on disk
        quote_dir = OUTPUT_DIR / quote_id
        assert quote_dir.exists()
        pdf_files = list(quote_dir.glob("*.pdf"))
        xlsx_files = list(quote_dir.glob("*.xlsx"))
        assert len(pdf_files) == 1
        assert len(xlsx_files) == 1

    @requires_pdf
    @pytest.mark.asyncio
    async def test_filename_sanitization(self, sample_quote_data):
        """Dates with / should be sanitized to . in filenames."""
        sample_quote_data["date"] = "30/12/2024"
        quote_id = "test-gen-002"
        result = await generate_documents(quote_id, sample_quote_data)

        assert result["ok"] is True
        # Filename should not contain /
        assert "/" not in result["pdf_url"].split("/")[-1]

    @pytest.mark.asyncio
    async def test_excel_has_content(self, sample_quote_data):
        """Excel should have data in cells, not be empty."""
        import openpyxl

        quote_id = "test-gen-003"
        await generate_documents(quote_id, sample_quote_data)

        xlsx_files = list((OUTPUT_DIR / quote_id).glob("*.xlsx"))
        assert len(xlsx_files) == 1

        wb = openpyxl.load_workbook(str(xlsx_files[0]))
        ws = wb.active
        # Should have client name somewhere in the sheet
        found_client = False
        for row in ws.iter_rows(min_row=1, max_row=20, values_only=True):
            for cell in row:
                if cell and "Juan Carlos" in str(cell):
                    found_client = True
                    break
        assert found_client, "Client name not found in Excel"
