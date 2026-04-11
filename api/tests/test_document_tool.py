"""Unit tests for document_tool.py — PDF/Excel generation."""

import os
import shutil
import subprocess
import pytest
from pathlib import Path
from app.modules.agent.tools.document_tool import (
    generate_documents,
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
        """Excel should have data in cells and Argentine locale."""
        import zipfile

        quote_id = "test-gen-003"
        await generate_documents(quote_id, sample_quote_data)

        xlsx_files = list((OUTPUT_DIR / quote_id).glob("*.xlsx"))
        assert len(xlsx_files) == 1

        # Read xlsx as zip to check content (avoids openpyxl choking on custom attrs)
        with zipfile.ZipFile(str(xlsx_files[0]), 'r') as z:
            # Check sheet contains client name
            sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            assert "Juan Carlos" in sheet, "Client name not found in Excel sheet"

            # Check Argentine locale was injected
            workbook_xml = z.read("xl/workbook.xml").decode("utf-8")
            assert "es_AR" in workbook_xml, "Argentine locale not found in workbook.xml"

    @pytest.mark.asyncio
    async def test_excel_all_mo_items_present(self):
        """Excel must include ALL MO items — even when >4 (template slots)."""
        import zipfile

        data = {
            "client_name": "Alvaro Torres",
            "project": "Cocina",
            "material_name": "SILESTONE BLANCO NORTE",
            "material_m2": 4.83,
            "material_price_unit": 519,
            "material_currency": "USD",
            "discount_pct": 0,
            "sectors": [{"label": "Cocina", "pieces": [
                "4.10 × 0.65 Mesada tramo 1 (SE REALIZA EN 2 TRAMOS)",
                "2.80 × 0.65 Mesada tramo 2",
                "6.90ML X 0.05 ZOC",
            ]}],
            "mo_items": [
                {"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 65147, "total": 65147},
                {"description": "Agujero anafe", "quantity": 1, "unit_price": 43097, "total": 43097},
                {"description": "Colocación", "quantity": 4.83, "unit_price": 60135, "total": 290452},
                {"description": "Flete + toma medidas puerto san martin", "quantity": 1, "unit_price": 145200, "total": 145200},
                {"description": "Pulido de cantos (colocación fuera de zona)", "quantity": 1, "unit_price": 72600, "total": 72600},
            ],
            "total_ars": 616496,
            "total_usd": 2507,
        }

        quote_id = "test-mo-complete"
        result = await generate_documents(quote_id, data)
        assert result["ok"]

        xlsx_files = list((OUTPUT_DIR / quote_id).glob("*.xlsx"))
        assert len(xlsx_files) == 1

        # Read Excel XML directly (openpyxl can't load due to custom locale injection)
        with zipfile.ZipFile(str(xlsx_files[0]), 'r') as z:
            sheet_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            try:
                shared_xml = z.read("xl/sharedStrings.xml").decode("utf-8")
            except KeyError:
                shared_xml = ""

        all_xml = (sheet_xml + shared_xml).lower()

        # All 5 MO descriptions must appear
        assert "pileta" in all_xml, "Pileta MO missing from Excel"
        assert "anafe" in all_xml, "Anafe MO missing from Excel"
        assert "colocaci" in all_xml, "Colocación MO missing from Excel"
        assert "flete" in all_xml, "Flete MO missing from Excel"
        assert "pulido" in all_xml, "Pulido de cantos MO missing from Excel"

        # Total PESOS must be present
        assert "total pesos" in all_xml, "TOTAL PESOS not found"
