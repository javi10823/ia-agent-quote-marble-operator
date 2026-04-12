"""Tests for visual_quote_builder — deterministic pipeline for CAD/visual building quotes."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.modules.quote_engine.visual_quote_builder import (
    resolve_visual_materials,
    compute_field_confidence,
    validate_visual_extraction,
    compute_visual_geometry,
    compute_physical_pieces,
    infer_visual_services,
    build_visual_pending_questions,
    parse_visual_extraction,
    parse_operator_corrections,
    apply_corrections,
    normalize_field_name,
    render_visual_extraction_summary,
    render_visual_building_step1,
    MaterialResolution,
    CONF_HIGH,
    CONF_REVIEW,
)


# ── Material Resolution ──────────────────────────────────────────────────────

class TestMaterialResolution:
    def test_single_alias(self):
        res = resolve_visual_materials("Cuarzo Blanco Norte 2cm espesor")
        assert res.mode == "single"
        assert "Silestone Blanco Norte" in res.resolved
        assert res.thickness_mm == 20

    def test_two_variants(self):
        res = resolve_visual_materials("Cuarzo Blanco Norte o Granito Blanco Ceara 2 cm de espesor")
        assert res.mode == "variants"
        assert len(res.resolved) == 2
        assert "Silestone Blanco Norte" in res.resolved
        assert "Granito Ceara" in res.resolved

    def test_unknown_material(self):
        res = resolve_visual_materials("Marmol Inexistente xyz")
        assert res.mode == "needs_clarification"
        assert len(res.unresolved) > 0

    def test_thickness_cm(self):
        res = resolve_visual_materials("Blanco Norte 2cm espesor")
        assert res.thickness_mm == 20

    def test_thickness_mm(self):
        res = resolve_visual_materials("Blanco Norte 20mm espesor")
        assert res.thickness_mm == 20

    def test_slash_separator(self):
        res = resolve_visual_materials("Blanco Norte / Ceara")
        assert res.mode == "variants"


# ── Field Confidence ─────────────────────────────────────────────────────────

class TestFieldConfidence:
    def test_l_shape_two_segments(self):
        conf = compute_field_confidence({
            "shape": "L", "segments_m": [2.35, 1.15], "depth_m": 0.62,
        })
        assert conf.shape >= CONF_HIGH
        assert conf.segments >= CONF_HIGH
        assert conf.depth >= CONF_HIGH

    def test_l_shape_wrong_segments(self):
        """L with 1 segment should drop confidence."""
        conf = compute_field_confidence({
            "shape": "L", "segments_m": [2.35], "depth_m": 0.62,
        })
        assert conf.segments < CONF_REVIEW  # Should be very low

    def test_linear_wrong_segments(self):
        """Linear with 2 segments should drop confidence."""
        conf = compute_field_confidence({
            "shape": "linear", "segments_m": [2.35, 1.15], "depth_m": 0.62,
        })
        assert conf.segments < CONF_REVIEW

    def test_extreme_depth(self):
        conf = compute_field_confidence({
            "shape": "linear", "segments_m": [2.0], "depth_m": 3.0,
        })
        assert conf.depth < CONF_REVIEW

    def test_backsplash_always_review(self):
        conf = compute_field_confidence({
            "shape": "linear", "segments_m": [2.0], "depth_m": 0.60,
            "backsplash_ml": 2.0,
        })
        assert conf.backsplash < CONF_HIGH  # Always needs review


# ── Geometry Computation ─────────────────────────────────────────────────────

class TestGeometry:
    def test_linear_m2(self):
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        geo = compute_visual_geometry([{
            "id": "DC-04", "qty": 8, "shape": "linear",
            "segments_m": [1.88], "depth_m": 0.62,
        }], mat)
        expected_unit = round(1.88 * 0.62, 2)
        assert geo.tipologias[0].m2_unit == expected_unit
        # Total = rounded unit × qty (not raw × qty then round)
        assert geo.tipologias[0].m2_total == round(expected_unit * 8, 2)

    def test_l_shape_subtracts_corner(self):
        """L-shape must subtract corner overlap (depth × depth)."""
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        geo = compute_visual_geometry([{
            "id": "DC-02", "qty": 2, "shape": "L",
            "segments_m": [2.35, 1.15], "depth_m": 0.62,
        }], mat)
        expected = round((2.35 * 0.62) + (1.15 * 0.62) - (0.62 * 0.62), 2)
        assert geo.tipologias[0].m2_unit == expected

    def test_total_closes_with_rows(self):
        """Total m² must equal sum of all row totals."""
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        geo = compute_visual_geometry([
            {"id": "A", "qty": 2, "shape": "linear", "segments_m": [2.0], "depth_m": 0.60},
            {"id": "B", "qty": 3, "shape": "L", "segments_m": [1.5, 0.8], "depth_m": 0.55},
        ], mat)
        row_sum = sum(t.m2_total for t in geo.tipologias)
        assert geo.total_mesada_m2 == round(row_sum, 2)

    def test_physical_pieces_short_slab(self):
        """Segment shorter than max slab = 1 piece."""
        assert compute_physical_pieces([2.0], 3.20) == 1

    def test_physical_pieces_long_slab(self):
        """Segment longer than max slab = 2 pieces."""
        assert compute_physical_pieces([3.50], 3.20) == 2

    def test_physical_pieces_multiple_segments(self):
        assert compute_physical_pieces([2.35, 1.15], 3.20) == 2  # 1 + 1

    def test_flete_calculation(self):
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        geo = compute_visual_geometry([
            {"id": "A", "qty": 10, "shape": "linear", "segments_m": [2.0], "depth_m": 0.60},
        ], mat)
        # 10 pieces, each 1 physical piece = 10 total. ceil(10/6) = 2
        assert geo.flete_qty == 2


# ── Services ─────────────────────────────────────────────────────────────────

class TestServices:
    def test_building_services(self):
        tipologias = [
            {"id": "A", "qty": 25, "embedded_sink_count": 1, "hob_count": 1,
             "_confidence": {"sink": 0.9, "hob": 0.9}},
        ]
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        geo = compute_visual_geometry([
            {"id": "A", "qty": 25, "shape": "linear", "segments_m": [2.0], "depth_m": 0.60},
        ], mat)
        services = infer_visual_services(tipologias, geo)
        assert services.pegadopileta_qty == 25
        assert services.anafe_qty == 25
        assert services.colocacion is False
        assert services.is_building is True


# ── Pending Questions ────────────────────────────────────────────────────────

class TestPendingQuestions:
    def test_material_resolved_not_asked(self):
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        services = infer_visual_services(
            [{"qty": 1, "embedded_sink_count": 0, "hob_count": 0, "_confidence": {}}],
            compute_visual_geometry([{"id": "A", "qty": 1, "shape": "linear", "segments_m": [1.0], "depth_m": 0.6}], mat),
        )
        pending = build_visual_pending_questions(mat, services, [], {"client_name": "Test"})
        assert "material_definition" not in pending

    def test_needs_clarification_asked(self):
        mat = MaterialResolution("xyz", [], "needs_clarification", ["xyz"], 20)
        services = infer_visual_services([], compute_visual_geometry([], mat))
        pending = build_visual_pending_questions(mat, services, [], {})
        assert "material_definition" in pending

    def test_planilla_always_first(self):
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        services = infer_visual_services([], compute_visual_geometry([], mat))
        pending = build_visual_pending_questions(mat, services, [], {})
        assert pending[0] == "planilla_marmoleria"

    def test_unknown_shape_goes_to_pending(self):
        """Tipología with shape unknown must appear in pending questions."""
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        tipologias = [{"id": "DC-08", "qty": 1, "shape": "unknown",
                       "segments_m": [2.0], "depth_m": 0.60,
                       "extraction_method": "fallback",
                       "_confidence": {"backsplash": 0.9}}]
        geo = compute_visual_geometry(tipologias, mat)
        services = infer_visual_services(tipologias, geo)
        pending = build_visual_pending_questions(mat, services, tipologias, {"client_name": "X"})
        assert "DC-08_extraction_needs_review" in pending

    def test_inferred_extraction_goes_to_pending(self):
        """Tipología with extraction_method inferred must appear in pending."""
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        tipologias = [{"id": "DC-05", "qty": 1, "shape": "linear",
                       "segments_m": [1.88], "depth_m": 0.62,
                       "extraction_method": "inferred",
                       "_confidence": {"backsplash": 0.9}}]
        geo = compute_visual_geometry(tipologias, mat)
        services = infer_visual_services(tipologias, geo)
        pending = build_visual_pending_questions(mat, services, tipologias, {"client_name": "X"})
        assert "DC-05_extraction_needs_review" in pending

    def test_all_backsplash_confirmations_listed(self):
        """ALL tipologías with low backsplash conf should appear, not just first."""
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        tipologias = [
            {"id": "DC-02", "qty": 2, "shape": "L", "segments_m": [2.35, 1.15],
             "depth_m": 0.62, "extraction_method": "direct_read",
             "_confidence": {"backsplash": 0.6, "shape": 0.9, "depth": 0.9, "segments": 0.9}},
            {"id": "DC-07", "qty": 6, "shape": "L", "segments_m": [1.96, 1.54],
             "depth_m": 0.62, "extraction_method": "direct_read",
             "_confidence": {"backsplash": 0.5, "shape": 0.9, "depth": 0.9, "segments": 0.9}},
        ]
        geo = compute_visual_geometry(tipologias, mat)
        services = infer_visual_services(tipologias, geo)
        pending = build_visual_pending_questions(mat, services, tipologias, {"client_name": "X"})
        assert "confirm_backsplash_DC-02" in pending
        assert "confirm_backsplash_DC-07" in pending  # Must NOT be skipped by break

    def test_large_obra_all_in_needs_review(self):
        """When total units > threshold, ALL tipologías go to needs_review."""
        tipologias = [
            {"id": "DC-02", "qty": 5, "shape": "L", "segments_m": [2.35, 1.15],
             "depth_m": 0.62, "embedded_sink_count": 1, "hob_count": 1},
            {"id": "DC-03", "qty": 6, "shape": "L", "segments_m": [2.29, 1.15],
             "depth_m": 0.62, "embedded_sink_count": 1, "hob_count": 1},
        ]
        validation = validate_visual_extraction(tipologias)
        # Total units = 11 > VALIDATION_ALWAYS_THRESHOLD (10)
        assert validation.requires_operator_validation is True
        assert len(validation.high_confidence) == 0  # All moved to review
        assert len(validation.needs_review) == 2

    def test_direct_read_not_in_pending(self):
        """Tipología with direct_read should NOT appear in extraction pending."""
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        tipologias = [{"id": "DC-02", "qty": 2, "shape": "L",
                       "segments_m": [2.35, 1.15], "depth_m": 0.62,
                       "extraction_method": "direct_read",
                       "_confidence": {"backsplash": 0.9}}]
        geo = compute_visual_geometry(tipologias, mat)
        services = infer_visual_services(tipologias, geo)
        pending = build_visual_pending_questions(mat, services, tipologias, {"client_name": "X"})
        assert "DC-02_extraction_needs_review" not in pending


# ── Operator Corrections ─────────────────────────────────────────────────────

class TestCorrections:
    def test_parse_standard_format(self):
        text = "DC-02 profundidad = 0.65\nDC-07 tramo2 = 1.54"
        result = parse_operator_corrections(text)
        assert len(result) == 2
        assert result[0]["tipologia_id"] == "DC-02"
        assert result[0]["field"] == "depth_m"
        assert result[0]["value"] == 0.65

    def test_parse_flexible_ids(self):
        """IDs like BAÑ-01, COC-03 should work."""
        text = "COC-03 profundidad = 0.55"
        result = parse_operator_corrections(text)
        assert len(result) == 1
        assert result[0]["tipologia_id"] == "COC-03"

    def test_parse_comma_decimal(self):
        text = "DC-04 tramo1 = 1,88"
        result = parse_operator_corrections(text)
        assert result[0]["value"] == 1.88

    def test_no_correction_returns_empty(self):
        result = parse_operator_corrections("confirmo")
        assert result == []

    def test_failed_correction_returns_none(self):
        result = parse_operator_corrections("DC-04 la profundidad deberia ser mas grande")
        assert result is None  # Looks like correction but can't parse

    def test_apply_depth_correction(self):
        tipologias = [{"id": "DC-02", "depth_m": 0.62, "segments_m": [2.35, 1.15]}]
        corrections = [{"tipologia_id": "DC-02", "field": "depth_m", "value": 0.65}]
        result = apply_corrections(tipologias, corrections)
        assert result[0]["depth_m"] == 0.65

    def test_apply_segment_correction(self):
        tipologias = [{"id": "DC-07", "segments_m": [1.96, 1.54]}]
        corrections = [{"tipologia_id": "DC-07", "field": "segments_m_1", "value": 1.60}]
        result = apply_corrections(tipologias, corrections)
        assert result[0]["segments_m"][1] == 1.60


# ── JSON Parser ──────────────────────────────────────────────────────────────

class TestJSONParser:
    def test_parse_valid_json(self):
        response = '''Análisis del plano:
```json
{
  "material_text": "Cuarzo Blanco Norte 2cm",
  "tipologias": [
    {"id": "DC-02", "qty": 2, "shape": "L", "depth_m": 0.62, "segments_m": [2.35, 1.15]}
  ]
}
```'''
        result = parse_visual_extraction(response)
        assert result is not None
        assert len(result["tipologias"]) == 1
        assert result["tipologias"][0]["id"] == "DC-02"

    def test_dedup_tipologias(self):
        response = '''```json
{"tipologias": [
  {"id": "DC-02", "qty": 2, "shape": "L", "depth_m": 0.62, "segments_m": [2.35, 1.15]},
  {"id": "DC-02", "qty": 2, "shape": "L", "depth_m": 0.62, "segments_m": [2.35, 1.15]}
]}```'''
        result = parse_visual_extraction(response)
        assert len(result["tipologias"]) == 1

    def test_reject_absurd_segments(self):
        response = '''```json
{"tipologias": [
  {"id": "X", "qty": 1, "shape": "linear", "depth_m": 0.6, "segments_m": [50.0]}
]}```'''
        result = parse_visual_extraction(response)
        assert result is None  # 50m segment is out of range

    def test_no_json_returns_none(self):
        result = parse_visual_extraction("Just some text without JSON")
        assert result is None

    def test_invalid_json_returns_none(self):
        result = parse_visual_extraction("```json\n{broken json\n```")
        assert result is None


# ── Render Functions ─────────────────────────────────────────────────────────

class TestRender:
    def test_render_summary_contains_tipologias(self):
        validation = validate_visual_extraction([
            {"id": "DC-02", "qty": 2, "shape": "L", "depth_m": 0.62,
             "segments_m": [2.35, 1.15], "embedded_sink_count": 1, "hob_count": 1},
        ])
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        text = render_visual_extraction_summary(validation, mat)
        assert "DC-02" in text
        assert "Silestone Blanco Norte" in text

    def test_render_step1_total_closes(self):
        mat = MaterialResolution("x", ["Silestone Blanco Norte", "Granito Ceara"], "variants", [], 20)
        geo = compute_visual_geometry([
            {"id": "A", "qty": 5, "shape": "linear", "segments_m": [2.0], "depth_m": 0.60},
            {"id": "B", "qty": 3, "shape": "L", "segments_m": [1.5, 0.8], "depth_m": 0.55},
        ], mat)
        services = infer_visual_services(
            [{"qty": 5, "embedded_sink_count": 1, "hob_count": 1, "_confidence": {"sink": 0.9, "hob": 0.9}},
             {"qty": 3, "embedded_sink_count": 1, "hob_count": 0, "_confidence": {"sink": 0.9, "hob": 0.9}}],
            geo,
        )
        text = render_visual_building_step1(geo, services, mat, [])
        assert "TOTAL GENERAL" in text
        assert str(geo.total_m2) in text
        assert "ambos materiales" in text
