"""Tests del helper compartido `app.modules.analytics.plans_vectorality`.

Cubre:
- Clasificación de source_files según mime / bytes.
- Resumen formateado con recommend_2d boolean.
- Integración end-to-end con el PDF real de Bernardi (fixture).
"""
import io
from pathlib import Path

from PIL import Image

from app.modules.analytics.plans_vectorality import (
    analyze_source_files,
    classify_pdf,
    classify_source_file,
    format_summary,
)


FIXTURES = Path(__file__).parent / "fixtures"


class TestClassifySourceFile:
    def test_jpg_classified_as_raster(self):
        sf = {"type": "image/jpeg", "filename": "foto.jpg"}
        assert classify_source_file(sf, None) == "raster_only"

    def test_png_classified_as_raster(self):
        sf = {"type": "image/png", "filename": "scan.png"}
        assert classify_source_file(sf, None) == "raster_only"

    def test_webp_classified_as_raster_by_filename(self):
        sf = {"type": "", "filename": "foto.webp"}
        assert classify_source_file(sf, None) == "raster_only"

    def test_pdf_without_bytes_is_unknown(self):
        sf = {"type": "application/pdf", "filename": "plano.pdf"}
        assert classify_source_file(sf, None) == "unknown"

    def test_bernardi_pdf_classified_as_vectorial_clean(self):
        """Fixture del caso real: PDF vectorial limpio de Bernardi.
        lines=133, curves=873 según pdfplumber → vectorial_clean."""
        pdf_bytes = (FIXTURES / "bernardi_erica_mesadas_cocina.pdf").read_bytes()
        sf = {"type": "application/pdf", "filename": "bernardi.pdf"}
        assert classify_source_file(sf, pdf_bytes) == "vectorial_clean"


class TestClassifyPdf:
    def test_bernardi_has_vectors_no_raster(self):
        pdf_bytes = (FIXTURES / "bernardi_erica_mesadas_cocina.pdf").read_bytes()
        result = classify_pdf(pdf_bytes)
        assert result.get("error") is None
        assert result["has_vectors"] is True
        assert result["has_raster"] is False

    def test_corrupt_bytes_returns_error(self):
        result = classify_pdf(b"not a pdf")
        assert "error" in result


class TestFormatSummary:
    def test_shape_matches_spec(self):
        """Shape exacto: total_analyzed, counts, percentages, recommend_2d."""
        categories = ["vectorial_clean"] * 6 + ["raster_only"] * 3 + ["unknown"] * 1
        summary = format_summary(categories)
        assert set(summary.keys()) == {
            "total_analyzed", "counts", "percentages", "recommend_2d",
        }
        assert summary["total_analyzed"] == 10
        assert summary["counts"]["vectorial_clean"] == 6
        assert summary["percentages"]["vectorial_clean"] == 60.0
        # 60% usable → recommend_2d True (umbral es 60%)
        assert summary["recommend_2d"] is True

    def test_recommend_2d_false_when_below_threshold(self):
        categories = ["vectorial_clean"] * 4 + ["raster_only"] * 6
        summary = format_summary(categories)
        # 40% < 60% → no vale 2d
        assert summary["recommend_2d"] is False

    def test_recommend_2d_true_when_combined_vectorial_over_threshold(self):
        """vectorial_clean + vectorial_and_raster deben sumar juntos."""
        categories = (
            ["vectorial_clean"] * 5
            + ["vectorial_and_raster"] * 2
            + ["raster_only"] * 3
        )
        summary = format_summary(categories)
        # 7/10 = 70% usable → recommend_2d True
        assert summary["recommend_2d"] is True

    def test_empty_categories_returns_zero_and_false(self):
        summary = format_summary([])
        assert summary["total_analyzed"] == 0
        assert summary["counts"] == {}
        assert summary["recommend_2d"] is False


class TestEndpoint:
    """Smoke test del endpoint admin."""

    import pytest

    @pytest.mark.asyncio
    async def test_endpoint_returns_summary_shape_on_empty_db(self, client):
        """Con DB vacía, el endpoint responde 200 + shape correcto."""
        resp = await client.post("/api/admin/analyze-plans-vectorality?limit=50")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "total_analyzed", "counts", "percentages", "recommend_2d",
        }
        assert data["total_analyzed"] == 0
        assert data["counts"] == {}
        assert data["recommend_2d"] is False

    @pytest.mark.asyncio
    async def test_endpoint_respects_limit_bounds(self, client):
        """Query param `limit` tiene bounds 1..1000."""
        # Fuera de rango → 422
        resp = await client.post("/api/admin/analyze-plans-vectorality?limit=0")
        assert resp.status_code == 422
        resp = await client.post("/api/admin/analyze-plans-vectorality?limit=2000")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_requires_auth(self, client_no_auth):
        """Sin cookie → 401."""
        resp = await client_no_auth.post(
            "/api/admin/analyze-plans-vectorality?limit=50"
        )
        assert resp.status_code == 401


class TestAnalyzeSourceFiles:
    def test_end_to_end_with_mixed_types(self):
        """Itera items heterogéneos + fetch fake, devuelve summary completo."""
        pdf_bytes = (FIXTURES / "bernardi_erica_mesadas_cocina.pdf").read_bytes()
        items = [
            ("q1", {"type": "image/jpeg", "filename": "foto.jpg"}),
            ("q2", {"type": "application/pdf", "filename": "bernardi.pdf"}),
            ("q3", {"type": "application/pdf", "filename": "otro.pdf"}),
            ("q4", {"type": "image/png", "filename": "scan.png"}),
        ]
        # Solo devuelve bytes para "bernardi.pdf"; el resto queda unknown.
        def _fetch(qid, sf):
            if sf.get("filename") == "bernardi.pdf":
                return pdf_bytes
            return None

        summary = analyze_source_files(items, _fetch)
        assert summary["total_analyzed"] == 4
        assert summary["counts"]["raster_only"] == 2  # jpg + png
        assert summary["counts"]["vectorial_clean"] == 1  # bernardi
        assert summary["counts"]["unknown"] == 1  # otro.pdf sin bytes
