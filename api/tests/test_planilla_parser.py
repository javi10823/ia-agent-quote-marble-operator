"""Tests for planilla de marmolería parser."""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from app.modules.quote_engine.planilla_parser import (
    parse_planilla_table,
    build_planilla_context,
    crop_drawing_from_page,
    PlanillaData,
)


class TestParsePlanillaTable:
    """Test deterministic parsing of planilla tables."""

    def _munge_table(self):
        """Simulated Munge planilla table from pdfplumber."""
        return [[
            ["CARACTERÍSTICAS", None],
            ["UBICACIÓN", "COCINA"],
            ["CANTIDAD", "1"],
            ["MATERIAL", "PURASTONE BLANCO PALOMA"],
            ["ESPESOR", "2 cm"],
            ["CANTOS", "// (pulidos)"],
            ["PILETA", "Johnson LUXOR COMPACT SI71"],
            ["GRIFERIA", "CD Roma Cromo Monocomando"],
            ["ZOCALOS", "7 cm de altura"],
            ["M2", "2,50 m2 - Con zócalos incluídos"],
        ]]

    def test_detects_planilla(self):
        result = parse_planilla_table(self._munge_table())
        assert result is not None

    def test_extracts_material(self):
        result = parse_planilla_table(self._munge_table())
        assert "PURASTONE" in result.material.upper()
        assert "PALOMA" in result.material.upper()

    def test_extracts_m2(self):
        result = parse_planilla_table(self._munge_table())
        assert result.m2 == 2.50

    def test_extracts_pileta(self):
        result = parse_planilla_table(self._munge_table())
        assert "LUXOR" in result.pileta.upper()
        assert "SI71" in result.pileta.upper()

    def test_extracts_zocalos(self):
        result = parse_planilla_table(self._munge_table())
        assert "7 cm" in result.zocalos

    def test_extracts_cantos(self):
        result = parse_planilla_table(self._munge_table())
        assert "pulidos" in result.cantos.lower()

    def test_extracts_espesor(self):
        result = parse_planilla_table(self._munge_table())
        assert "2 cm" in result.espesor

    def test_extracts_ubicacion(self):
        result = parse_planilla_table(self._munge_table())
        assert result.ubicacion == "COCINA"

    def test_no_planilla_returns_none(self):
        """Random table should not be detected as planilla."""
        table = [[["Nombre", "Juan"], ["Edad", "30"]]]
        result = parse_planilla_table(table)
        assert result is None

    def test_empty_table(self):
        result = parse_planilla_table([])
        assert result is None


class TestBuildPlanillaContext:
    """Test context string generation."""

    def test_contains_material(self):
        data = PlanillaData(material="PURASTONE BLANCO PALOMA", m2=2.50, m2_raw="2,50 m2")
        ctx = build_planilla_context(data)
        assert "PURASTONE BLANCO PALOMA" in ctx

    def test_contains_m2_warning(self):
        data = PlanillaData(m2=2.50, m2_raw="2,50 m2")
        ctx = build_planilla_context(data)
        assert "2.5" in ctx
        assert "DEBEN sumar" in ctx

    def test_contains_deterministic_label(self):
        data = PlanillaData(material="test")
        ctx = build_planilla_context(data)
        assert "DETERMINÍSTICO" in ctx

    def test_contains_pileta(self):
        data = PlanillaData(pileta="Johnson LUXOR COMPACT SI71")
        ctx = build_planilla_context(data)
        assert "LUXOR" in ctx


class TestCropDrawing:
    """Test image cropping logic."""

    def test_crop_with_valid_bbox(self):
        """Crop should reduce image width."""
        from PIL import Image
        # Simulate a 1000x1000 page with table starting at 60% width
        img = Image.new("RGB", (1000, 1000), "white")
        data = PlanillaData(
            table_x0=600,  # Table starts at 600 of 1000 points
            page_width=1000,
            page_height=1000,
        )
        cropped = crop_drawing_from_page(img, data, dpi=200)
        # Should be cropped to ~590px wide (600 - 10 margin)
        assert cropped.width < img.width
        assert cropped.width > 500

    def test_crop_without_bbox_returns_full(self):
        """No bbox → return full image."""
        from PIL import Image
        img = Image.new("RGB", (1000, 1000), "white")
        data = PlanillaData()  # No bbox
        result = crop_drawing_from_page(img, data, dpi=200)
        assert result.width == img.width


class TestWithRealPDF:
    """Test with the actual Munge planilla if available."""

    PLAN_PATH = "/Users/javierolivieri/projects/dangelo-marble-ia/planos/07.A1335 - Planillas Marmoleria COCINA FINAL.pdf"

    @pytest.mark.skipif(
        not os.path.exists(PLAN_PATH),
        reason="Munge planilla not available locally"
    )
    def test_real_munge_planilla(self):
        """Parse the actual Munge planilla PDF."""
        import pdfplumber

        with pdfplumber.open(self.PLAN_PATH) as pdf:
            page = pdf.pages[0]
            tables = page.extract_tables()
            table_objects = page.find_tables()

            result = parse_planilla_table(
                tables,
                page_width=page.width,
                page_height=page.height,
                table_bboxes=table_objects,
            )

            assert result is not None, "Should detect planilla in real Munge PDF"
            assert result.m2 == 2.50, f"Expected 2.50 m2, got {result.m2}"
            assert "PALOMA" in result.material.upper()
            assert "LUXOR" in result.pileta.upper()
            assert result.table_x0 > 0, "Should have table bbox"
            print(f"\nReal planilla parsed:")
            print(f"  Material: {result.material}")
            print(f"  M2: {result.m2}")
            print(f"  Pileta: {result.pileta}")
            print(f"  Zócalos: {result.zocalos}")
            print(f"  Table bbox: x0={result.table_x0:.0f}")
