"""Tests for render_edificio_paso2 — deterministic pricing for edificio.

Uses real ESH PDF (1121-SM) through full pipeline.
"""

import pytest
from pathlib import Path

ESH_PDF = Path("/Users/javierolivieri/projects/dangelo-marble-ia/planos/edifcio-1121SM-2025-Planilla marmolería.pdf")


def _render_paso2():
    """Run full pipeline + Paso 2 renderer on ESH."""
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
    return render_edificio_paso2(summary, "Rosario")


@pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
class TestESHPaso2:

    @pytest.fixture(scope="class")
    def result(self):
        return _render_paso2()

    @pytest.fixture(scope="class")
    def rendered(self, result):
        return result["rendered"]

    # ── MO quantities ────────────────────────────────────────────────────

    def test_pegadopileta_15(self, result):
        mo = next((m for m in result["mo_items"] if "pegado" in m["desc"].lower()), None)
        assert mo is not None
        assert mo["qty"] == 15

    def test_agujeroapoyo_1(self, result):
        mo = next((m for m in result["mo_items"] if "apoyo" in m["desc"].lower()), None)
        assert mo is not None
        assert mo["qty"] == 1

    def test_faldon_ml(self, result):
        mo = next((m for m in result["mo_items"] if "faldón" in m["desc"].lower()), None)
        assert mo is not None
        assert mo["qty"] == 14.87

    def test_flete_qty(self, result):
        mo = next((m for m in result["mo_items"] if "flete" in m["desc"].lower()), None)
        assert mo is not None
        assert mo["qty"] == 7

    # ── No forbidden content ─────────────────────────────────────────────

    def test_no_sink_product(self, rendered):
        """No physical sink product in edificio."""
        for forbidden in ["Johnson", "Quadra", "Luxor", "Oval", "QUADRA", "pileta Q"]:
            assert forbidden not in rendered, f"Found forbidden: {forbidden}"

    def test_no_colocacion(self, rendered):
        assert "Colocación" not in rendered or "Sin colocación" in rendered

    def test_no_corte45(self, rendered):
        assert "Corte 45" not in rendered

    # ── Render contains ──────────────────────────────────────────────────

    def test_contains_pegadopileta_in_render(self, rendered):
        assert "15" in rendered
        assert "pegado pileta" in rendered.lower()

    def test_contains_agujeroapoyo_in_render(self, rendered):
        assert "apoyo" in rendered.lower()

    def test_contains_faldon_in_render(self, rendered):
        assert "14,87" in rendered
        assert "faldón" in rendered.lower()

    def test_contains_flete_7_in_render(self, rendered):
        assert "Flete" in rendered

    def test_contains_descuento_18(self, rendered):
        assert "18%" in rendered

    def test_contains_sin_colocacion(self, rendered):
        assert "Sin colocación" in rendered

    def test_contains_mo_divido_105(self, rendered):
        assert "÷1.05" in rendered or "÷1,05" in rendered

    # ── 3 materials separated ────────────────────────────────────────────

    def test_3_material_sections(self, rendered):
        sections = [l for l in rendered.split("\n") if l.startswith("### ") and "m²" in l]
        assert len(sections) == 3, f"Expected 3, got: {sections}"

    def test_boreal_section(self, rendered):
        assert "NEGRO BOREAL" in rendered

    def test_brasil_section(self, rendered):
        assert "NEGRO BRASIL" in rendered

    def test_sahara_section(self, rendered):
        assert "MARMOL SAHARA" in rendered or "MÁRMOL SAHARA" in rendered

    # ── MO is global block, not per material ─────────────────────────────

    def test_mo_is_separate_section(self, rendered):
        assert "### MANO DE OBRA" in rendered

    def test_grand_total_section(self, rendered):
        assert "### GRAND TOTAL" in rendered

    # ── Totals are numeric and present ───────────────────────────────────

    def test_grand_total_ars_positive(self, result):
        assert result["grand_total_ars"] > 0

    def test_grand_total_usd_positive(self, result):
        assert result["grand_total_usd"] > 0

    def test_mo_total_positive(self, result):
        assert result["mo_total"] > 0

    # ── No mixed-currency ambiguity ──────────────────────────────────────

    def test_total_ars_and_usd_separate(self, rendered):
        assert "Total ARS" in rendered
        assert "Total USD" in rendered

    def test_shows_base_and_iva_price(self, rendered):
        """Must show both base (sin IVA) and IVA-inclusive price."""
        assert "sin IVA" in rendered
        assert "×1,21" in rendered
