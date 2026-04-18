"""Tests del multi_crop_reader — aggregator + orquestación.

LLM calls y PIL image ops se mockean. La idea es verificar:
- aggregator arma el schema dual_read correcto desde topology + results
- fallback graceful si global topology falla
- crop + filter de cotas locales por bbox funciona
"""
from unittest.mock import AsyncMock, patch

import io
import pytest
from PIL import Image

from app.modules.quote_engine.cotas_extractor import Cota
from app.modules.quote_engine.multi_crop_reader import (
    _aggregate,
    read_plan_multi_crop,
)


def _make_cota(value: float, x: float = 0, y: float = 0) -> Cota:
    return Cota(text=str(value), value=value, x=x, y=y, width=20, height=10)


def _make_image_bytes(w: int = 1000, h: int = 800) -> bytes:
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Aggregator ───────────────────────────────────────────────────────────────

class TestAggregate:
    def test_u_plus_isla_4_regions_2_sectors(self):
        """Cocina en U + isla → sector cocina (3 tramos) + sector isla (1 tramo)."""
        topology = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "sector": "cocina"},
                {"id": "R2", "sector": "cocina"},
                {"id": "R3", "sector": "cocina"},
                {"id": "R4", "sector": "isla"},
            ],
        }
        results = [
            {"region_id": "R1", "largo_m": 2.95, "ancho_m": 0.60},
            {"region_id": "R2", "largo_m": 2.05, "ancho_m": 0.60},
            {"region_id": "R3", "largo_m": 1.20, "ancho_m": 0.60},
            {"region_id": "R4", "largo_m": 1.60, "ancho_m": 0.60},
        ]
        out = _aggregate(topology, results)
        assert len(out["sectores"]) == 2
        cocina = next(s for s in out["sectores"] if s["tipo"] == "cocina")
        isla = next(s for s in out["sectores"] if s["tipo"] == "isla")
        assert len(cocina["tramos"]) == 3
        assert len(isla["tramos"]) == 1
        # m² recalculado (determinístico, no confía en el LLM)
        assert cocina["tramos"][0]["m2"]["valor"] == round(2.95 * 0.60, 2)
        assert isla["tramos"][0]["largo_m"]["valor"] == 1.60
        # source del output
        assert out["source"] == "MULTI_CROP"

    def test_region_with_error_becomes_dudoso(self):
        topology = {"regions": [{"id": "R1", "sector": "cocina"}]}
        results = [{"region_id": "R1", "error": "region_timeout"}]
        out = _aggregate(topology, results)
        tramo = out["sectores"][0]["tramos"][0]
        assert tramo["largo_m"]["status"] == "DUDOSO"
        assert out["requires_human_review"] is True

    def test_no_regions_fallback_empty_sector(self):
        out = _aggregate({"regions": []}, [])
        assert len(out["sectores"]) == 1
        assert out["sectores"][0]["tramos"] == []
        assert out["requires_human_review"] is True


# ── End-to-end with mocks ────────────────────────────────────────────────────

class TestReadPlanMultiCrop:
    @pytest.mark.asyncio
    async def test_global_topology_failure_propagates(self):
        """Si el global call falla, se devuelve error sin llamar per-region."""
        image = _make_image_bytes()
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value={"error": "global_topology_timeout"}),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader._measure_region",
            new=AsyncMock(),
        ) as mock_region:
            result = await read_plan_multi_crop(image, cotas=[])
        assert result.get("error") == "global_topology_timeout"
        mock_region.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_regions_returns_error(self):
        image = _make_image_bytes()
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value={"view_type": "planta", "regions": []}),
        ):
            result = await read_plan_multi_crop(image, cotas=[])
        assert result.get("error") == "no_regions_detected"

    @pytest.mark.asyncio
    async def test_happy_path_bernardi_like(self):
        """3 mesadas U + 1 isla, cada una con su medida correcta."""
        image = _make_image_bytes()
        topology = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "sector": "cocina", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}},
                {"id": "R2", "sector": "cocina", "bbox_rel": {"x": 0.35, "y": 0.1, "w": 0.3, "h": 0.1}},
                {"id": "R3", "sector": "isla",   "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.15, "h": 0.25}},
            ],
        }

        async def fake_measure(full_bytes, size, region, cotas, model, brief_text=""):
            values = {
                "R1": (2.95, 0.60),
                "R2": (2.05, 0.60),
                "R3": (1.60, 0.60),
            }
            L, A = values[region["id"]]
            return {"region_id": region["id"], "largo_m": L, "ancho_m": A, "confidence": 0.95}

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=topology),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader._measure_region",
            new=fake_measure,
        ):
            result = await read_plan_multi_crop(image, cotas=[], brief_text="cliente Bernardi")
        assert result.get("error") is None
        assert result["source"] == "MULTI_CROP"
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        assert len(cocina["tramos"]) == 2
        assert cocina["tramos"][0]["largo_m"]["valor"] == 2.95
        assert cocina["tramos"][1]["largo_m"]["valor"] == 2.05
        assert isla["tramos"][0]["largo_m"]["valor"] == 1.60

    @pytest.mark.asyncio
    async def test_partial_region_failure_still_aggregates(self):
        """Si 1 de 3 regiones falla, las otras 2 igual se agregan al output."""
        image = _make_image_bytes()
        topology = {
            "regions": [
                {"id": "R1", "sector": "cocina", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}},
                {"id": "R2", "sector": "cocina", "bbox_rel": {"x": 0.4, "y": 0.1, "w": 0.2, "h": 0.2}},
                {"id": "R3", "sector": "isla",   "bbox_rel": {"x": 0.3, "y": 0.5, "w": 0.2, "h": 0.2}},
            ],
        }

        async def fake_measure(full_bytes, size, region, cotas, model, brief_text=""):
            if region["id"] == "R2":
                return {"region_id": "R2", "error": "region_timeout"}
            return {"region_id": region["id"], "largo_m": 2.0, "ancho_m": 0.6}

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=topology),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader._measure_region",
            new=fake_measure,
        ):
            result = await read_plan_multi_crop(image, cotas=[])
        tramos_cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")["tramos"]
        # R1 OK, R2 DUDOSO
        assert tramos_cocina[0]["largo_m"]["status"] == "CONFIRMADO"
        assert tramos_cocina[1]["largo_m"]["status"] == "DUDOSO"
        # requires_human_review se dispara por el DUDOSO
        assert result["requires_human_review"] is True
