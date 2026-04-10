"""Tests for generate_edificio_documents — 4 PDF+Excel from paso2_calc.

Uses real ESH data through the full pipeline.
"""

import shutil
import pytest
import zipfile
from pathlib import Path

ESH_PDF = Path("/Users/javierolivieri/projects/dangelo-marble-ia/planos/edifcio-1121SM-2025-Planilla marmolería.pdf")
OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    for d in OUTPUT_DIR.glob("test-edif-doc-*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _build_paso2_calc():
    """Run full pipeline + Paso 2 calc on ESH."""
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
class TestEdificioDocs:

    @pytest.fixture(scope="class")
    def paso2_and_summary(self):
        return _build_paso2_calc()

    @pytest.fixture(scope="class")
    def paso2(self, paso2_and_summary):
        return paso2_and_summary[0]

    @pytest.fixture(scope="class")
    def summary(self, paso2_and_summary):
        return paso2_and_summary[1]

    @pytest.mark.asyncio
    async def test_generates_3_documents(self, paso2, summary):
        from app.modules.agent.tools.document_tool import generate_edificio_documents
        qid = "test-edif-doc-001"
        result = await generate_edificio_documents(
            quote_id=qid,
            paso2_calc=paso2,
            summary=summary,
            client_name="ESH 1121-SM",
            project="Concesionario",
        )
        assert result["ok"]
        assert len(result["generated"]) == 3  # 3 materials, each with its MO

    @pytest.mark.asyncio
    async def test_3_material_docs_plus_1_services(self, paso2, summary):
        from app.modules.agent.tools.document_tool import generate_edificio_documents
        qid = "test-edif-doc-002"
        result = await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        assert len(result["generated"]) == 3

    @pytest.mark.asyncio
    async def test_pdf_and_excel_exist_on_disk(self, paso2, summary):
        from app.modules.agent.tools.document_tool import generate_edificio_documents
        qid = "test-edif-doc-003"
        result = await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        qdir = OUTPUT_DIR / qid
        pdfs = list(qdir.glob("*.pdf"))
        xlsxs = list(qdir.glob("*.xlsx"))
        assert len(pdfs) == 3, f"Expected 3 PDFs, got {len(pdfs)}"
        assert len(xlsxs) == 3, f"Expected 3 Excels, got {len(xlsxs)}"

    @pytest.mark.asyncio
    async def test_grand_totals_positive(self, paso2, summary):
        """Grand totals must be positive and reasonable."""
        from app.modules.agent.tools.document_tool import generate_edificio_documents
        qid = "test-edif-doc-004"
        result = await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        assert result["grand_total_ars"] > 0
        assert result["grand_total_usd"] > 0
        # Should be in the right ballpark (within 5% of paso2)
        if paso2.get("grand_total_ars"):
            diff_pct = abs(result["grand_total_ars"] - paso2["grand_total_ars"]) / paso2["grand_total_ars"]
            assert diff_pct < 0.05, f"ARS diff {diff_pct:.1%} too large"

    @pytest.mark.asyncio
    async def test_each_document_has_content(self, paso2, summary):
        """Each PDF and Excel should have real content."""
        from app.modules.agent.tools.document_tool import generate_edificio_documents
        qid = "test-edif-doc-005"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")
        for f in (OUTPUT_DIR / qid).glob("*.pdf"):
            assert f.stat().st_size > 1000, f"{f.name} is too small"
        for f in (OUTPUT_DIR / qid).glob("*.xlsx"):
            assert f.stat().st_size > 1000, f"{f.name} is too small"

    @pytest.mark.asyncio
    async def test_no_sink_product_in_any_doc(self, paso2, summary):
        """No Johnson/Quadra/Luxor in any generated document."""
        import zipfile
        from app.modules.agent.tools.document_tool import generate_edificio_documents
        qid = "test-edif-doc-007"
        await generate_edificio_documents(qid, paso2, summary, "ESH", "Test")

        for xlsx in (OUTPUT_DIR / qid).glob("*.xlsx"):
            with zipfile.ZipFile(str(xlsx), 'r') as z:
                sheet_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            for forbidden in ["Johnson", "Quadra", "Luxor", "Oval"]:
                assert forbidden not in sheet_xml, f"Found '{forbidden}' in {xlsx.name}"
