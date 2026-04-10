"""Tests for render_edificio_paso1 — deterministic Paso 1 output for edificio.

Uses real ESH PDF (1121-SM) to verify the rendered output matches
commercial expectations exactly.
"""

import pytest
from pathlib import Path

ESH_PDF = Path("/Users/javierolivieri/projects/dangelo-marble-ia/planos/edifcio-1121SM-2025-Planilla marmolería.pdf")


def _render_esh() -> str:
    """Run full pipeline on ESH PDF and return rendered Paso 1."""
    import pdfplumber
    from app.modules.quote_engine.edificio_parser import (
        parse_edificio_tables, normalize_edificio_data,
        compute_edificio_aggregates, render_edificio_paso1,
    )

    tables_all = []
    with pdfplumber.open(str(ESH_PDF)) as pdf:
        for page in pdf.pages:
            tables_all.extend(page.extract_tables())

    raw = parse_edificio_tables(tables_all)
    norm = normalize_edificio_data(raw)
    summary = compute_edificio_aggregates(norm)
    return render_edificio_paso1(norm, summary)


@pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
class TestESHRender:

    @pytest.fixture(scope="class")
    def rendered(self):
        return _render_esh()

    # ── MUST contain ─────────────────────────────────────────────────────

    def test_contains_marmol_sahara(self, rendered):
        """Alias must be applied: Granito new beige → Mármol Sahara."""
        assert "MÁRMOL SAHARA" in rendered or "MARMOL SAHARA" in rendered

    def test_contains_correct_total(self, rendered):
        """Grand total must be 54,10 m²."""
        assert "54,10" in rendered

    def test_contains_negro_boreal(self, rendered):
        assert "NEGRO BOREAL" in rendered

    def test_contains_negro_brasil(self, rendered):
        assert "NEGRO BRASIL" in rendered

    def test_contains_pegadopileta_15(self, rendered):
        assert "PEGADOPILETA ×15" in rendered

    def test_contains_agujeroapoyo_1(self, rendered):
        assert "AGUJEROAPOYO ×1" in rendered

    def test_contains_flete_7(self, rendered):
        assert "Flete ×7 viajes" in rendered

    def test_contains_49_piezas(self, rendered):
        assert "49 piezas" in rendered

    def test_contains_descuento_18(self, rendered):
        assert "18%" in rendered

    def test_contains_sin_colocacion(self, rendered):
        assert "Sin colocación" in rendered

    def test_contains_faldon_summary(self, rendered):
        """Faldones should appear as summary line, not as piece rows."""
        assert "faldón" in rendered.lower() or "faldones" in rendered.lower()

    def test_e01_shows_total_m2(self, rendered):
        """E-01 (×19) must show total m² = 9,12, not unit 0,48."""
        assert "9,12" in rendered

    def test_e02_shows_total_m2(self, rendered):
        """E-02 (×4) must show total m² = 1,20."""
        assert "1,20" in rendered

    def test_e01_shows_quantity(self, rendered):
        """E-01 must show ×19."""
        assert "×19" in rendered

    def test_e02_shows_quantity(self, rendered):
        """E-02 must show ×4."""
        assert "×4" in rendered

    # ── MUST NOT contain ─────────────────────────────────────────────────

    def test_no_granito_new_beige(self, rendered):
        """Raw PDF name must be replaced by alias."""
        assert "Granito new beige" not in rendered
        assert "GRANITO NEW BEIGE" not in rendered

    def test_no_wrong_total(self, rendered):
        """44,56 m² is the wrong total from list_pieces aplanado."""
        assert "44,56" not in rendered

    def test_no_faldon_as_piece_row(self, rendered):
        """Faldón M1, Faldón M2 etc should NOT appear as table rows."""
        assert "Faldón M1" not in rendered
        assert "Faldón M2" not in rendered

    def test_no_ocr_garbage(self, rendered):
        """AJAB ATNALP / ATNALP ATLA is reversed OCR garbage."""
        assert "AJAB" not in rendered
        assert "ATNALP" not in rendered

    # ── Structure ────────────────────────────────────────────────────────

    def test_separated_by_material(self, rendered):
        """Must have 3 material sections (### headers)."""
        sections = [l for l in rendered.split("\n") if l.startswith("### ") and "m²" in l]
        assert len(sections) == 3, f"Expected 3 material sections, got {len(sections)}: {sections}"

    def test_is_markdown(self, rendered):
        """Output must be valid markdown with tables."""
        assert "| ID |" in rendered
        assert "| --- |" in rendered or "|---|" in rendered

    def test_verificacion_header(self, rendered):
        assert rendered.startswith("## VERIFICACIÓN EDIFICIO")
