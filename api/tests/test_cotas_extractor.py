"""Tests for cotas_extractor — deterministic dimension extraction from plans."""
import os
import pytest
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from app.modules.quote_engine.cotas_extractor import (
    Cota,
    extract_cotas_from_drawing,
    format_cotas_for_prompt,
    _normalize_value,
    _rejoin_adjacent_numeric_tokens,
    _apply_mm_heuristic,
)

FIXTURES = Path(__file__).parent / "fixtures"
MUNGE_PDF = FIXTURES / "munge_planilla.pdf"


# ═══════════════════════════════════════════════════════
# Unit tests — pure functions
# ═══════════════════════════════════════════════════════

class TestNormalizeValue:
    def test_decimal_point(self):
        assert _normalize_value("1.72") == 1.72

    def test_decimal_comma_to_float(self):
        """'2,50' must normalize to float 2.5, not string equality."""
        result = _normalize_value("2,50")
        assert result == 2.5
        assert isinstance(result, float)

    def test_integer_rejected(self):
        """Plain integers are NOT cotas (could be codes, scales)."""
        assert _normalize_value("600") is None
        assert _normalize_value("02") is None

    def test_invalid_string(self):
        assert _normalize_value("abc") is None
        assert _normalize_value("") is None

    def test_ratio_rejected(self):
        """'1:50' is not a decimal cota."""
        assert _normalize_value("1:50") is None


class TestRejoinAdjacent:
    def test_joins_split_numeric(self):
        """['1', '.74'] adjacent on same line should join to '1.74'."""
        words = [
            {"text": "1", "x0": 100, "x1": 105, "top": 200, "bottom": 210},
            {"text": ".74", "x0": 106, "x1": 115, "top": 200, "bottom": 210},
        ]
        joined = _rejoin_adjacent_numeric_tokens(words)
        assert len(joined) == 1
        assert joined[0]["text"] == "1.74"

    def test_does_not_join_different_lines(self):
        """Tokens on different lines should NOT be merged."""
        words = [
            {"text": "1", "x0": 100, "x1": 105, "top": 200, "bottom": 210},
            {"text": ".74", "x0": 106, "x1": 115, "top": 400, "bottom": 410},
        ]
        joined = _rejoin_adjacent_numeric_tokens(words)
        assert len(joined) == 2

    def test_does_not_join_if_invalid_number(self):
        """If the concatenation isn't a valid cota, don't merge."""
        words = [
            {"text": "MESADA", "x0": 100, "x1": 150, "top": 200, "bottom": 210},
            {"text": "COCINA", "x0": 151, "x1": 210, "top": 200, "bottom": 210},
        ]
        joined = _rejoin_adjacent_numeric_tokens(words)
        assert len(joined) == 2


class TestMmHeuristic:
    def test_does_not_convert_small_values(self):
        values = [0.60, 1.72, 0.75, 1.55, 1.74]
        converted, was_mm = _apply_mm_heuristic(values)
        assert was_mm is False
        assert converted == values

    def test_converts_when_80pct_are_big(self):
        """5 of 5 values > 100 → all converted."""
        values = [600.0, 1720.0, 750.0, 1550.0, 1740.0]
        converted, was_mm = _apply_mm_heuristic(values)
        assert was_mm is True
        assert converted[0] == 0.6
        assert converted[1] == 1.72

    def test_mixed_under_threshold_not_converted(self):
        """3 of 5 values > 100 (60%) — below 80% → no conversion."""
        values = [600.0, 1720.0, 750.0, 1.55, 1.74]
        converted, was_mm = _apply_mm_heuristic(values)
        assert was_mm is False
        assert converted == values

    def test_empty_list(self):
        converted, was_mm = _apply_mm_heuristic([])
        assert was_mm is False
        assert converted == []


# ═══════════════════════════════════════════════════════
# Integration test — real Munge PDF
# ═══════════════════════════════════════════════════════

class TestMungeRealPDF:
    """Tests with the real Munge planilla PDF from tests/fixtures/."""

    @pytest.mark.skipif(
        not MUNGE_PDF.exists(),
        reason=f"Munge fixture not found at {MUNGE_PDF}"
    )
    def test_extracts_all_five_cotas(self):
        """Extract exactly [0.60, 1.55, 1.72, 0.75, 1.74] from Munge plan.

        These are the 5 cotas visible in the drawing:
          - 0.60 m (ancho del tramo con pileta)
          - 1.55 m (largo del tramo con pileta, rotada)
          - 1.72 m (largo del tramo principal)
          - 0.75 m (ancho del tramo principal, rotada)
          - 1.74 m (largo del zócalo de fondo)
        """
        import pdfplumber
        from app.modules.quote_engine.planilla_parser import detect_table_x_from_words

        with pdfplumber.open(MUNGE_PDF) as pdf:
            page = pdf.pages[0]
            table_x0 = detect_table_x_from_words(page)
            assert table_x0 > 0, "Could not detect table x0 in Munge plan"

            cotas = extract_cotas_from_drawing(page, table_x0, dpi=300)

        values = sorted([c.value for c in cotas])
        expected = sorted([0.60, 1.55, 1.72, 0.75, 1.74])
        assert values == pytest.approx(expected, abs=0.01), (
            f"Expected cotas {expected}, got {values}"
        )

    @pytest.mark.skipif(
        not MUNGE_PDF.exists(),
        reason="Munge fixture not found"
    )
    def test_coordinates_in_crop_space(self):
        """Coordinates must be in pixels at the given DPI, not PDF points."""
        import pdfplumber
        from app.modules.quote_engine.planilla_parser import detect_table_x_from_words

        with pdfplumber.open(MUNGE_PDF) as pdf:
            page = pdf.pages[0]
            table_x0 = detect_table_x_from_words(page)
            cotas = extract_cotas_from_drawing(page, table_x0, dpi=300)

        # Page width is 1191 pt, so at 300 DPI the crop is ~4960 pixels wide.
        # Table starts at ~713 pt = ~2970 pixels — cotas must all be < 2970.
        table_x_px = table_x0 * (300 / 72)
        for c in cotas:
            assert c.x < table_x_px, (
                f"Cota {c.text} at x={c.x} px should be < table_x_px={table_x_px:.0f}"
            )
            # All cotas should have positive width/height (valid bbox)
            assert c.width > 0 and c.height > 0, f"Invalid bbox for {c.text}"

    @pytest.mark.skipif(
        not MUNGE_PDF.exists(),
        reason="Munge fixture not found"
    )
    def test_scale_factor_correct(self):
        """With DPI=300, scale is 300/72=4.17. A cota at PDF x0=100pt
        should be at crop_x ≈ 417 px."""
        import pdfplumber
        from app.modules.quote_engine.planilla_parser import detect_table_x_from_words

        with pdfplumber.open(MUNGE_PDF) as pdf:
            page = pdf.pages[0]
            table_x0 = detect_table_x_from_words(page)
            # Get raw PDF x of the 1.74 cota (we know it's at ~x0=373 pt)
            raw_words = page.extract_words(use_text_flow=True)
            cota_1_74 = next((w for w in raw_words if w['text'] == '1.74'), None)
            assert cota_1_74 is not None, "1.74 word not found in Munge PDF"
            pdf_x = cota_1_74['x0']

            cotas = extract_cotas_from_drawing(page, table_x0, dpi=300)
            cota = next((c for c in cotas if c.text == '1.74'), None)
            assert cota is not None
            expected_crop_x = pdf_x * (300 / 72)
            assert abs(cota.x - expected_crop_x) < 1.0, (
                f"Expected crop x ≈ {expected_crop_x:.1f}, got {cota.x}"
            )


# ═══════════════════════════════════════════════════════
# Fallback + prompt formatting
# ═══════════════════════════════════════════════════════

class TestFallbackAndFormatting:
    def test_empty_page_returns_empty_list(self):
        """Page with no text (scanned) → empty list, no crash."""

        class FakePage:
            width = 1000
            height = 800
            chars = []

            def extract_words(self, **kwargs):
                return []

        result = extract_cotas_from_drawing(FakePage(), table_x0=700, dpi=300)
        assert result == []

    def test_format_empty_cotas(self):
        assert format_cotas_for_prompt([]) == ""

    def test_format_includes_coordinates_and_values(self):
        cotas = [
            Cota(text="1.72", value=1.72, x=100.0, y=200.0, width=20, height=10),
            Cota(text="0.60", value=0.60, x=300.0, y=50.0, width=20, height=10),
        ]
        out = format_cotas_for_prompt(cotas)
        assert "1.72" in out
        assert "0.60" in out
        assert "COTAS DETECTADAS" in out
        assert "píxeles" in out  # coordinate note

    def test_format_marks_rotated(self):
        cotas = [
            Cota(text="0.75", value=0.75, x=100, y=200, width=10, height=20, rotated=True),
        ]
        out = format_cotas_for_prompt(cotas)
        assert "rotada" in out

    def test_format_marks_prefix(self):
        cotas = [
            Cota(text="Z0.07", value=0.07, x=100, y=200, width=20, height=10, prefix="Z"),
        ]
        out = format_cotas_for_prompt(cotas)
        assert "prefix=Z" in out
