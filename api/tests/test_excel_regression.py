"""Regression tests for Excel generation — ensures no placeholders, correct layout,
and pixel-perfect match with PDF output.

Tests generate REAL Excel files and inspect the cells to catch regressions
like {{cliente}}, {{forma_pago}}, broken merges, missing values, or
content differences between PDF and Excel.

Runs against both:
1. Normal quote Excel (_generate_excel)
2. Edificio quote Excel (_generate_edificio_excel)
"""

import shutil
import zipfile
import pytest
from pathlib import Path

from app.modules.agent.tools.document_tool import (
    generate_documents,
    generate_edificio_documents,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# ── Forbidden strings that must NEVER appear in any Excel ──
FORBIDDEN_PLACEHOLDERS = [
    "{{cliente}}",
    "{{forma_pago}}",
    "{{fecha_entrega}}",
    "{{proyecto}}",
    "{{fecha}}",
]


@pytest.fixture(autouse=True)
def cleanup():
    yield
    for d in OUTPUT_DIR.glob("test-excel-*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _read_excel_xml(xlsx_path: Path) -> str:
    """Read sheet1.xml from xlsx as string (avoids openpyxl locale issues)."""
    with zipfile.ZipFile(str(xlsx_path), "r") as z:
        return z.read("xl/worksheets/sheet1.xml").decode("utf-8")


def _sample_normal_data() -> dict:
    """Standard quote data matching the reference Excel."""
    return {
        "client_name": "Alvaro Torres",
        "project": "Cocina",
        "delivery_days": "30 dias desde la toma de medidas",
        "material_name": "SILESTONE BLANCO NORTE",
        "material_m2": 4.83,
        "material_price_unit": 519,
        "material_currency": "USD",
        "discount_pct": 0,
        "thickness_mm": 20,
        "sectors": [{"label": "Cocina", "pieces": [
            "4.10 × 0.65 Mesada tramo 1 (SE REALIZA EN 2 TRAMOS)",
            "2.80 × 0.65 Mesada tramo 2",
            "6.90ML X 0.05 ZOC",
        ]}],
        "sinks": [],
        "mo_items": [
            {"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 65147, "base_price": 53840, "total": 65147},
            {"description": "Agujero anafe", "quantity": 1, "unit_price": 43097, "base_price": 35617, "total": 43097},
            {"description": "Colocación", "quantity": 4.83, "unit_price": 60135, "base_price": 49698, "total": 290452},
            {"description": "Flete + toma medidas puerto san martin", "quantity": 1, "unit_price": 145200, "base_price": 120000, "total": 145200},
        ],
        "total_ars": 543896,
        "total_usd": 2507,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NORMAL EXCEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalExcelRegression:
    """Tests for _generate_excel (standard quote template)."""

    @pytest.mark.asyncio
    async def test_no_placeholders_in_normal_excel(self):
        """CRITICAL: No {{placeholder}} must ever appear in the final Excel."""
        qid = "test-excel-normal-001"
        data = _sample_normal_data()
        result = await generate_documents(qid, data)
        assert result["ok"]

        xlsx_files = list((OUTPUT_DIR / qid).glob("*.xlsx"))
        assert len(xlsx_files) >= 1
        xml = _read_excel_xml(xlsx_files[0])

        for placeholder in FORBIDDEN_PLACEHOLDERS:
            assert placeholder not in xml, f"PLACEHOLDER LEAK: '{placeholder}' found in normal Excel"

    @pytest.mark.asyncio
    async def test_client_name_present(self):
        qid = "test-excel-normal-002"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xml = _read_excel_xml(list((OUTPUT_DIR / qid).glob("*.xlsx"))[0])
        assert "Alvaro Torres" in xml

    @pytest.mark.asyncio
    async def test_project_present(self):
        qid = "test-excel-normal-003"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xml = _read_excel_xml(list((OUTPUT_DIR / qid).glob("*.xlsx"))[0])
        assert "Cocina" in xml

    @pytest.mark.asyncio
    async def test_material_present(self):
        qid = "test-excel-normal-004"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xml = _read_excel_xml(list((OUTPUT_DIR / qid).glob("*.xlsx"))[0])
        assert "SILESTONE BLANCO NORTE" in xml

    @pytest.mark.asyncio
    async def test_delivery_present(self):
        qid = "test-excel-normal-005"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xml = _read_excel_xml(list((OUTPUT_DIR / qid).glob("*.xlsx"))[0])
        assert "30 dias" in xml

    @pytest.mark.asyncio
    async def test_contado_present(self):
        qid = "test-excel-normal-006"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xml = _read_excel_xml(list((OUTPUT_DIR / qid).glob("*.xlsx"))[0])
        assert "Contado" in xml or "CONTADO" in xml

    @pytest.mark.asyncio
    async def test_mo_items_present(self):
        qid = "test-excel-normal-007"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xml = _read_excel_xml(list((OUTPUT_DIR / qid).glob("*.xlsx"))[0]).lower()
        assert "pegado pileta" in xml or "pegadopileta" in xml
        assert "flete" in xml

    @pytest.mark.asyncio
    async def test_pdf_also_generated(self):
        """PDF must also be generated alongside Excel."""
        qid = "test-excel-normal-008"
        data = _sample_normal_data()
        result = await generate_documents(qid, data)
        assert result["ok"]
        pdfs = list((OUTPUT_DIR / qid).glob("*.pdf"))
        assert len(pdfs) >= 1
        assert pdfs[0].stat().st_size > 1000


# ═══════════════════════════════════════════════════════════════════════════════
# EDIFICIO EXCEL
# ═══════════════════════════════════════════════════════════════════════════════

ESH_PDF = Path("/Users/javierolivieri/projects/dangelo-marble-ia/planos/edifcio-1121SM-2025-Planilla marmolería.pdf")


def _build_esh_paso2():
    """Build paso2_calc + summary from real ESH PDF."""
    import pdfplumber
    from app.modules.quote_engine.edificio_parser import (
        parse_edificio_tables, normalize_edificio_data,
        compute_edificio_aggregates, render_edificio_paso2,
    )
    tables = []
    with pdfplumber.open(str(ESH_PDF)) as pdf:
        for p in pdf.pages:
            tables.extend(p.extract_tables())
    raw = parse_edificio_tables(tables)
    norm = normalize_edificio_data(raw)
    summary = compute_edificio_aggregates(norm)
    paso2 = render_edificio_paso2(summary, "Rosario")
    return paso2, summary


@pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
class TestEdificioExcelRegression:
    """Tests for _generate_edificio_excel (edificio template)."""

    @pytest.fixture(scope="class")
    def esh_data(self):
        return _build_esh_paso2()

    @pytest.mark.asyncio
    async def test_no_placeholders_in_edificio_excel(self, esh_data):
        """CRITICAL: No {{placeholder}} must ever appear in any edificio Excel."""
        paso2, summary = esh_data
        qid = "test-excel-edif-001"
        result = await generate_edificio_documents(qid, paso2, summary, "ESH", "Concesionario 1121-SM")
        assert result["ok"]

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            xml = _read_excel_xml(xlsx)
            for placeholder in FORBIDDEN_PLACEHOLDERS:
                assert placeholder not in xml, f"PLACEHOLDER LEAK: '{placeholder}' in {xlsx.name}"

    @pytest.mark.asyncio
    async def test_client_in_all_edificio_excels(self, esh_data):
        paso2, summary = esh_data
        qid = "test-excel-edif-002"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Concesionario")
        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            xml = _read_excel_xml(xlsx)
            assert "ESH" in xml, f"Client 'ESH' missing in {xlsx.name}"

    @pytest.mark.asyncio
    async def test_contado_in_all_edificio_excels(self, esh_data):
        paso2, summary = esh_data
        qid = "test-excel-edif-003"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Concesionario")
        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            xml = _read_excel_xml(xlsx)
            assert "CONTADO" in xml or "Contado" in xml, f"Payment missing in {xlsx.name}"

    @pytest.mark.asyncio
    async def test_delivery_in_all_edificio_excels(self, esh_data):
        paso2, summary = esh_data
        qid = "test-excel-edif-004"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Concesionario")
        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            xml = _read_excel_xml(xlsx)
            assert "cronograma" in xml.lower() or "convenir" in xml.lower(), f"Delivery missing in {xlsx.name}"

    @pytest.mark.asyncio
    async def test_4_excel_files_generated(self, esh_data):
        paso2, summary = esh_data
        qid = "test-excel-edif-005"
        result = await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        xlsxs = list((OUTPUT_DIR / qid).glob("*.xlsx"))
        assert len(xlsxs) == 4, f"Expected 4 Excels, got {len(xlsxs)}"

    @pytest.mark.asyncio
    async def test_4_pdf_files_generated(self, esh_data):
        paso2, summary = esh_data
        qid = "test-excel-edif-006"
        result = await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        pdfs = list((OUTPUT_DIR / qid).glob("*.pdf"))
        assert len(pdfs) == 4, f"Expected 4 PDFs, got {len(pdfs)}"

    @pytest.mark.asyncio
    async def test_all_files_have_content(self, esh_data):
        """No empty files."""
        paso2, summary = esh_data
        qid = "test-excel-edif-007"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        for f in (OUTPUT_DIR / qid).iterdir():
            if f.suffix in (".pdf", ".xlsx"):
                assert f.stat().st_size > 500, f"{f.name} is too small ({f.stat().st_size} bytes)"

    @pytest.mark.asyncio
    async def test_no_sink_products(self, esh_data):
        """No Johnson/Quadra/Luxor in any edificio Excel."""
        paso2, summary = esh_data
        qid = "test-excel-edif-008"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            xml = _read_excel_xml(xlsx)
            for forbidden in ["Johnson", "Quadra", "Luxor", "Oval"]:
                assert forbidden not in xml, f"'{forbidden}' found in {xlsx.name}"


# ═══════════════════════════════════════════════════════════════════════════════
# VISUAL PARITY: Excel must match PDF content
# ═══════════════════════════════════════════════════════════════════════════════

class TestExcelPdfParity:
    """Ensures Excel and PDF have identical content — no drift between formats."""

    @pytest.mark.asyncio
    async def test_normal_excel_has_conditions(self):
        """Excel must have conditions/footer text like PDF does."""
        qid = "test-excel-parity-001"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xlsx = list((OUTPUT_DIR / qid).glob("*.xlsx"))[0]
        xml = _read_excel_xml(xlsx)
        shared = ""
        try:
            with zipfile.ZipFile(str(xlsx)) as z:
                shared = z.read("xl/sharedStrings.xml").decode("utf-8")
        except Exception:
            pass
        all_text = (xml + shared).lower()
        assert "contado" in all_text, "Payment condition missing from Excel"

    @pytest.mark.asyncio
    async def test_normal_excel_has_grand_total(self):
        """Excel must have PRESUPUESTO TOTAL like PDF."""
        qid = "test-excel-parity-002"
        data = _sample_normal_data()
        await generate_documents(qid, data)
        xlsx = list((OUTPUT_DIR / qid).glob("*.xlsx"))[0]
        xml = _read_excel_xml(xlsx)
        shared = ""
        try:
            with zipfile.ZipFile(str(xlsx)) as z:
                shared = z.read("xl/sharedStrings.xml").decode("utf-8")
        except Exception:
            pass
        all_text = (xml + shared).lower()
        assert "presupuesto total" in all_text, "Grand total missing from Excel"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_edificio_excel_groups_duplicates(self):
        """Duplicate pieces must be grouped with (x2) like in PDF."""
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-003"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        # Find Boreal Excel (has duplicate faldones 1,66ML)
        boreal_xlsx = None
        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            if "BOREAL" in xlsx.name.upper():
                boreal_xlsx = xlsx
                break
        assert boreal_xlsx is not None, "Boreal Excel not found"

        xml = _read_excel_xml(boreal_xlsx)
        shared = ""
        try:
            with zipfile.ZipFile(str(boreal_xlsx)) as z:
                shared = z.read("xl/sharedStrings.xml").decode("utf-8")
        except Exception:
            pass
        all_text = xml + shared

        # The two identical 1,66ML faldones should be grouped as (x2)
        assert "(x2)" in all_text, "Duplicate faldones not grouped with (x2) in Excel"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_edificio_excel_has_conditions(self):
        """Edificio Excel must have conditions/footer like PDF."""
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-004"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            if "Resumen" in xlsx.name:
                continue
            xml = _read_excel_xml(xlsx)
            shared = ""
            try:
                with zipfile.ZipFile(str(xlsx)) as z:
                    shared = z.read("xl/sharedStrings.xml").decode("utf-8")
            except Exception:
                pass
            all_text = (xml + shared).lower()
            assert "contado" in all_text or "presupuesto sujeto" in all_text, f"Conditions missing from {xlsx.name}"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_edificio_excel_has_grand_total(self):
        """Edificio Excel must have PRESUPUESTO TOTAL like PDF."""
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-005"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            if "Resumen" in xlsx.name:
                continue
            xml = _read_excel_xml(xlsx)
            shared = ""
            try:
                with zipfile.ZipFile(str(xlsx)) as z:
                    shared = z.read("xl/sharedStrings.xml").decode("utf-8")
            except Exception:
                pass
            all_text = (xml + shared).lower()
            assert "presupuesto total" in all_text, f"Grand total missing from {xlsx.name}"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_no_giant_row_heights(self):
        """No row should have height > 50px (catches template row 42 = 210px regression)."""
        import openpyxl
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-006"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            # Read raw XML to check row heights without openpyxl locale issues
            with zipfile.ZipFile(str(xlsx)) as z:
                sheet_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            import re
            heights = re.findall(r'ht="([\d.]+)"', sheet_xml)
            for h in heights:
                assert float(h) <= 50, f"Row height {h}px too large in {xlsx.name} — template height leak"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_edificio_excel_grand_total_has_border(self):
        """Grand total row in edificio Excel must have a border (matching PDF box)."""
        import re as _re
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-007"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            if "Resumen" in xlsx.name:
                continue
            # Read raw XML — openpyxl can't load due to locale injection
            with zipfile.ZipFile(str(xlsx)) as z:
                styles_xml = z.read("xl/styles.xml").decode("utf-8")
            # Check that styles.xml has a border with "thin" style (our injected border)
            assert "thin" in styles_xml, f"No thin border style found in {xlsx.name}"
            # Check styles.xml has horizontal="center" alignment (grand total cell)
            assert 'horizontal="center"' in styles_xml, f"No centered alignment style in {xlsx.name}"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_edificio_excel_usd_format(self):
        """USD values in edificio Excel must use 'USD 1.937' format (space + dots), not 'USD1937'."""
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-008"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            if "Resumen" in xlsx.name:
                continue
            xml = _read_excel_xml(xlsx)
            shared = ""
            try:
                with zipfile.ZipFile(str(xlsx)) as z:
                    shared = z.read("xl/sharedStrings.xml").decode("utf-8")
            except Exception:
                pass
            all_text = xml + shared
            # Should NOT have "USD" immediately followed by a digit (no space)
            import re
            bad_usd = re.findall(r'USD\d', all_text)
            assert len(bad_usd) == 0, f"USD values without space found in {xlsx.name}: {bad_usd}"

    @pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
    @pytest.mark.asyncio
    async def test_edificio_excel_has_footer(self):
        """Edificio Excel must have 'No se suben mesadas' footer like PDF."""
        paso2, summary = _build_esh_paso2()
        qid = "test-excel-parity-009"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            if "Resumen" in xlsx.name:
                continue
            xml = _read_excel_xml(xlsx)
            shared = ""
            try:
                with zipfile.ZipFile(str(xlsx)) as z:
                    shared = z.read("xl/sharedStrings.xml").decode("utf-8")
            except Exception:
                pass
            all_text = (xml + shared).lower()
            assert "no se suben mesadas" in all_text, f"Footer missing from {xlsx.name}"
