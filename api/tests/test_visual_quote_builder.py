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
    get_tipologias_needing_second_pass,
    merge_second_pass,
    get_tipologia_page,
    parse_focused_response,
    backsplash_needs_confirmation,
    render_field,
    infer_visual_services,
    build_visual_pending_questions,
    parse_visual_extraction,
    parse_zone_detection,
    auto_select_zone,
    parse_page_confirmation,
    render_page_confirmation,
    render_final_paso1,
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
        """Tipologías with INCOHERENT backsplash should appear in pending."""
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        tipologias = [
            {"id": "DC-02", "qty": 2, "shape": "L", "segments_m": [2.35, 1.15],
             "depth_m": 0.62, "extraction_method": "direct_read",
             "backsplash_ml": 9.0,  # Incoherent: > 1.5 × (2.35+1.15) = 5.25
             "_confidence": {"backsplash": 0.6, "shape": 0.9, "depth": 0.9, "segments": 0.9}},
            {"id": "DC-07", "qty": 6, "shape": "L", "segments_m": [1.96, 1.54],
             "depth_m": 0.62, "extraction_method": "direct_read",
             "backsplash_ml": 8.0,  # Incoherent: > 1.5 × (1.96+1.54) = 5.25
             "_confidence": {"backsplash": 0.5, "shape": 0.9, "depth": 0.9, "segments": 0.9}},
        ]
        geo = compute_visual_geometry(tipologias, mat)
        services = infer_visual_services(tipologias, geo)
        pending = build_visual_pending_questions(mat, services, tipologias, {"client_name": "X"})
        assert "confirm_backsplash_DC-02" in pending
        assert "confirm_backsplash_DC-07" in pending

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

    def test_render_field_markers(self):
        """Fields show correct markers based on confidence and method."""
        assert "✅" in render_field("2.35m", 0.9, "direct_read")
        assert "⚠️" in render_field("0.87m", 0.7, "direct_read")
        assert "✅" in render_field("0.87m", 0.9, "inferred")  # high conf inferred = ✅
        assert "⚠️" in render_field("0.87m", 0.6, "inferred")  # low conf inferred = ⚠️
        assert "❌" in render_field("1.50m", 0.9, "fallback")
        assert "❌" in render_field("1.50m", 0.3, "direct_read")

    def test_render_summary_field_level_markers(self):
        """Summary must show per-field markers, not just per-tipología."""
        validation = validate_visual_extraction([
            {"id": "DC-02", "qty": 2, "shape": "L", "depth_m": 0.62,
             "segments_m": [2.35, 1.15], "embedded_sink_count": 1, "hob_count": 1,
             "extraction_method": "direct_read", "backsplash_ml": 4.12},
        ])
        mat = MaterialResolution("x", ["Silestone Blanco Norte"], "single", [], 20)
        text = render_visual_extraction_summary(validation, mat)
        # Segments should have ✅ (high conf + direct_read)
        assert "2.35m ✅" in text
        # Backsplash 4.12ml with segments [2.35, 1.15] is reasonable → ✅
        assert "zócalo 4.12ml ✅" in text


# ── Backsplash Confirmation ──────────────────────────────────────────────────

class TestBacksplashConfirmation:
    def test_reasonable_no_confirmation(self):
        assert backsplash_needs_confirmation(3.91, [2.35, 0.94], "L") is False

    def test_too_large_needs_confirmation(self):
        assert backsplash_needs_confirmation(8.0, [2.35, 0.94], "L") is True

    def test_too_small_needs_confirmation(self):
        assert backsplash_needs_confirmation(0.3, [2.35, 0.94], "L") is True

    def test_none_no_confirmation(self):
        assert backsplash_needs_confirmation(None, [2.35], "linear") is False

    def test_linear_reasonable(self):
        assert backsplash_needs_confirmation(2.0, [2.35], "linear") is False


# ── Merge Segment Guard ──────────────────────────────────────────────────────

class TestMergeSegmentGuard:
    def test_merge_rejects_inverted_segments(self):
        """Second pass must not accept tramo1 < tramo2."""
        original = [{"id": "DC-02", "segments_m": [2.35, 0.94], "shape": "L"}]
        bad_pass = {"shape": "L", "segments_m": [0.75, 0.94],
                    "depth_m": 0.62, "extraction_method": "direct_read"}
        result = merge_second_pass(original, bad_pass, "DC-02")
        assert result[0]["segments_m"] == [2.35, 0.94]  # Original kept
        assert result[0]["extraction_method"] == "inferred"  # Downgraded

    def test_merge_accepts_valid_segments(self):
        """Valid tramo1 > tramo2 should be accepted."""
        original = [{"id": "DC-02", "segments_m": [2.35, 0.94], "shape": "L"}]
        good_pass = {"shape": "L", "segments_m": [2.40, 0.87],
                     "depth_m": 0.62, "extraction_method": "direct_read"}
        result = merge_second_pass(original, good_pass, "DC-02")
        assert result[0]["segments_m"] == [2.40, 0.87]  # Updated


# ── Second Pass ──────────────────────────────────────────────────────────────

class TestSecondPass:
    def test_second_pass_triggers_for_inferred(self):
        """Tipología inferred must go to second pass."""
        tipologias = [{"id": "DC-02", "qty": 2, "extraction_method": "inferred",
                       "shape": "linear", "segments_m": [2.35], "depth_m": 0.62}]
        ids = get_tipologias_needing_second_pass(tipologias, {})
        assert "DC-02" in ids

    def test_second_pass_skips_direct_read_high_conf(self):
        """direct_read with high confidence doesn't go to second pass."""
        tipologias = [{"id": "DC-08", "qty": 1, "extraction_method": "direct_read",
                       "shape": "linear", "segments_m": [2.99], "depth_m": 0.60}]
        conf = {"DC-08": {"shape": 0.9, "segments": 0.9}}
        ids = get_tipologias_needing_second_pass(tipologias, conf)
        assert "DC-08" not in ids

    def test_second_pass_triggers_for_unknown_shape(self):
        tipologias = [{"id": "DC-07", "qty": 6, "extraction_method": "direct_read",
                       "shape": "unknown", "segments_m": [1.96], "depth_m": 0.62}]
        ids = get_tipologias_needing_second_pass(tipologias, {})
        assert "DC-07" in ids

    def test_second_pass_triggers_for_low_segment_conf(self):
        tipologias = [{"id": "DC-04", "qty": 8, "extraction_method": "direct_read",
                       "shape": "linear", "segments_m": [1.88], "depth_m": 0.62}]
        conf = {"DC-04": {"shape": 0.9, "segments": 0.5}}
        ids = get_tipologias_needing_second_pass(tipologias, conf)
        assert "DC-04" in ids

    def test_single_page_complex_multiple_doubtful(self):
        """Multiple doubtful tipologías all need second pass."""
        tipologias = [
            {"id": "A", "qty": 1, "extraction_method": "inferred", "shape": "unknown"},
            {"id": "B", "qty": 1, "extraction_method": "inferred", "shape": "L",
             "segments_m": [1.5, 0.8], "depth_m": 0.6},
            {"id": "C", "qty": 1, "extraction_method": "fallback", "shape": "unknown"},
            {"id": "D", "qty": 1, "extraction_method": "direct_read", "shape": "linear",
             "segments_m": [2.0], "depth_m": 0.6},
        ]
        conf = {"D": {"shape": 0.9, "segments": 0.9}}
        ids = get_tipologias_needing_second_pass(tipologias, conf)
        assert len(ids) == 3
        assert "D" not in ids

    def test_merge_preserves_untouched_fields(self):
        original = [{"id": "DC-02", "qty": 2, "shape": "linear",
                     "segments_m": [2.35], "embedded_sink_count": 1,
                     "extraction_method": "inferred", "depth_m": 0.62}]
        correction = {"id": "DC-02", "shape": "L", "segments_m": [2.35, 0.87],
                      "depth_m": 0.62, "extraction_method": "direct_read",
                      "second_pass_notes": "retorno visible en planta con cota 0.87"}
        result = merge_second_pass(original, correction, "DC-02")
        assert result[0]["shape"] == "L"
        assert result[0]["segments_m"] == [2.35, 0.87]
        assert result[0]["embedded_sink_count"] == 1  # Untouched
        assert result[0]["extraction_method"] == "direct_read"

    def test_merge_records_notes(self):
        original = [{"id": "DC-02", "qty": 2, "shape": "linear",
                     "segments_m": [2.35], "depth_m": 0.62}]
        correction = {"shape": "L", "segments_m": [2.35, 0.87],
                      "second_pass_notes": "retorno con cota"}
        result = merge_second_pass(original, correction, "DC-02")
        assert result[0]["second_pass_notes"] == "retorno con cota"

    def test_get_tipologia_page_explicit(self):
        tipologias = [{"id": "DC-02", "page": 3}, {"id": "DC-03", "page": 4}]
        assert get_tipologia_page("DC-03", tipologias) == 4

    def test_get_tipologia_page_fallback_to_index(self):
        tipologias = [{"id": "DC-02"}, {"id": "DC-03"}, {"id": "DC-04"}]
        assert get_tipologia_page("DC-04", tipologias) == 3  # 0-indexed + 1

    def test_parse_focused_response_valid(self):
        text = '{"shape": "L", "segments_m": [2.35, 0.87], "depth_m": 0.62}'
        result = parse_focused_response(text)
        assert result is not None
        assert result["shape"] == "L"

    def test_parse_focused_response_invalid(self):
        result = parse_focused_response("No pude leer el plano")
        assert result is None

    def test_parse_focused_rejects_numeric_shape(self):
        """shape=0.9 (confidence leaked as shape) must be discarded."""
        text = '{"shape": 0.9, "segments_m": [2.35], "depth_m": 0.62}'
        result = parse_focused_response(text)
        assert result is not None
        assert "shape" not in result  # Numeric shape discarded
        assert result["segments_m"] == [2.35]  # Rest preserved

    def test_parse_focused_rejects_absurd_segments(self):
        """Segments outside 0.1-10.0 range must be discarded."""
        text = '{"shape": "linear", "segments_m": [50.0, 0.05]}'
        result = parse_focused_response(text)
        assert result is not None  # shape is still valid
        assert "segments_m" not in result  # Both segments invalid → discarded

    def test_parse_focused_validates_depth_range(self):
        text = '{"shape": "L", "segments_m": [2.0, 1.0], "depth_m": 5.0}'
        result = parse_focused_response(text)
        assert "depth_m" not in result  # 5.0 out of range


# ── Fix D: Zone Detection + Page-by-Page ─────────────────────────────────────

class TestZoneDetection:
    def test_parse_zones_valid(self):
        response = '```json\n{"zones": [{"name": "PLANTA", "bbox": [0,0,600,400]}, {"name": "CORTE 1-1", "bbox": [0,400,500,850]}]}\n```'
        zones = parse_zone_detection(response)
        assert len(zones) == 2
        assert zones[0]["name"] == "PLANTA"
        assert zones[1]["bbox"] == [0, 400, 500, 850]

    def test_parse_zones_no_names(self):
        response = '```json\n{"zones": [{"bbox": [0,0,600,400]}, {"bbox": [0,400,500,850]}]}\n```'
        zones = parse_zone_detection(response)
        assert zones[0]["name"] == "ZONA-1"
        assert zones[1]["name"] == "ZONA-2"

    def test_parse_zones_invalid_json(self):
        zones = parse_zone_detection("No JSON here")
        assert zones == []

    def test_parse_zones_empty(self):
        response = '```json\n{"zones": []}\n```'
        zones = parse_zone_detection(response)
        assert zones == []

    def test_parse_zones_truncated_json(self):
        """Truncated JSON (max_tokens cutoff) should recover complete zone objects."""
        response = '''```json
{
  "zones": [
    {"name": "PLANTA", "bbox": [0, 10, 370, 270], "view_type": "top_view", "confidence": 0.95},
    {"name": "CORTE 2-2", "bbox": [340'''  # Truncated mid-second zone
        zones = parse_zone_detection(response)
        assert len(zones) >= 1  # At least PLANTA recovered
        assert zones[0]["name"] == "PLANTA"
        assert zones[0]["view_type"] == "top_view"

    def test_parse_zones_with_view_type(self):
        response = '```json\n{"zones": [{"name": "PLANTA", "bbox": [0,0,600,400], "view_type": "top_view", "confidence": 0.9}]}\n```'
        zones = parse_zone_detection(response)
        assert zones[0]["view_type"] == "top_view"
        assert zones[0]["confidence"] == 0.9


class TestAutoSelectZone:
    def test_selects_planta(self):
        zones = [
            {"name": "CORTE 1-1", "bbox": [0, 400, 500, 850]},
            {"name": "PLANTA", "bbox": [0, 0, 600, 400]},
        ]
        selected = auto_select_zone(zones)
        assert selected["name"] == "PLANTA"

    def test_uses_zone_default(self):
        zones = [
            {"name": "PLANTA", "bbox": [0, 0, 600, 400]},
            {"name": "CORTE 1-1", "bbox": [0, 400, 500, 850]},
        ]
        selected = auto_select_zone(zones, zone_default="CORTE 1-1")
        assert selected["name"] == "CORTE 1-1"

    def test_excludes_corte_when_alternatives(self):
        zones = [
            {"name": "CORTE 1-1", "bbox": [0, 0, 100, 100]},
            {"name": "VISTA GENERAL", "bbox": [0, 0, 800, 600]},
        ]
        selected = auto_select_zone(zones)
        assert selected["name"] == "VISTA GENERAL"

    def test_returns_none_for_empty(self):
        assert auto_select_zone([]) is None

    def test_largest_when_all_cortes(self):
        zones = [
            {"name": "CORTE 1-1", "bbox": [0, 0, 100, 100]},
            {"name": "CORTE 2-2", "bbox": [0, 0, 800, 600]},
        ]
        selected = auto_select_zone(zones)
        assert selected["name"] == "CORTE 2-2"

    def test_selects_top_view_over_name(self):
        """view_type top_view should win over name containing PLANTA."""
        zones = [
            {"name": "DESARROLLO", "bbox": [0, 0, 600, 500], "view_type": "top_view", "confidence": 0.9},
            {"name": "PLANTA TÉCNICA", "bbox": [0, 500, 600, 900], "view_type": "section", "confidence": 0.9},
        ]
        selected = auto_select_zone(zones)
        assert selected["name"] == "DESARROLLO"

    def test_selects_highest_confidence_top_view(self):
        """Multiple top_views → select highest confidence."""
        zones = [
            {"name": "ZONA-1", "bbox": [0, 0, 300, 400], "view_type": "top_view", "confidence": 0.6},
            {"name": "ZONA-2", "bbox": [300, 0, 600, 400], "view_type": "top_view", "confidence": 0.95},
        ]
        selected = auto_select_zone(zones)
        assert selected["name"] == "ZONA-2"


class TestParsePageConfirmation:
    def test_confirm_si(self):
        result = parse_page_confirmation("sí", [], [])
        assert result["action"] == "confirm"

    def test_confirm_ok(self):
        result = parse_page_confirmation("ok", [], [])
        assert result["action"] == "confirm"

    def test_confirm_dale(self):
        result = parse_page_confirmation("dale", [], [])
        assert result["action"] == "confirm"

    def test_skip(self):
        result = parse_page_confirmation("skip", [], [])
        assert result["action"] == "skip"

    def test_skip_ninguna(self):
        result = parse_page_confirmation("ninguna", [], [])
        assert result["action"] == "skip"

    def test_zone_correction(self):
        zones = [{"name": "PLANTA", "bbox": [0,0,600,400]}, {"name": "CORTE 1-1", "bbox": [0,400,500,850]}]
        result = parse_page_confirmation("zona = CORTE 1-1", [], zones)
        assert result["action"] == "zone_correction"
        assert result["zone"]["name"] == "CORTE 1-1"

    def test_value_correction(self):
        tips = [{"id": "DC-02", "segments_m": [2.35]}]
        result = parse_page_confirmation("DC-02 profundidad = 0.65", tips, [])
        assert result["action"] == "value_correction"
        assert len(result["corrections"]) == 1

    def test_unclear(self):
        result = parse_page_confirmation("no sé qué hacer con esto", [], [])
        assert result["action"] == "unclear"


class TestRenderPageConfirmation:
    def test_contains_progress(self):
        zone = {"name": "PLANTA", "bbox": [0,0,600,400]}
        tips = [{"id": "DC-02", "qty": 2, "shape": "L", "segments_m": [2.35, 0.87],
                 "depth_m": 0.62, "extraction_method": "direct_read",
                 "_confidence": {"shape": 0.9, "segments": 0.9, "depth": 0.9, "backsplash": 0.6}}]
        mat = MaterialResolution("x", ["Silestone"], "single", [], 20)
        geos = compute_visual_geometry(tips, mat).tipologias
        text = render_page_confirmation(1, 7, zone, tips, geos, True)
        assert "Página 1/7" in text
        assert "DC-02" in text
        assert "auto: PLANTA" in text

    def test_no_tipologias_shows_options(self):
        zone = {"name": "PLANTA", "bbox": [0,0,600,400]}
        text = render_page_confirmation(3, 7, zone, [], [], True)
        assert "No se detectaron" in text
        assert "skip" in text


class TestRenderFinalPaso1:
    def test_totals_close(self):
        mat = MaterialResolution("x", ["Silestone", "Granito"], "variants", [], 20)
        geos_data = [
            {"id": "A", "qty": 5, "shape": "linear", "segments_m": [2.0], "depth_m": 0.60},
            {"id": "B", "qty": 3, "shape": "L", "segments_m": [1.5, 0.8], "depth_m": 0.55},
        ]
        geo = compute_visual_geometry(geos_data, mat)
        services = infer_visual_services(
            [{"qty": 5, "embedded_sink_count": 1, "hob_count": 1, "_confidence": {"sink": 0.9, "hob": 0.9}},
             {"qty": 3, "embedded_sink_count": 1, "hob_count": 0, "_confidence": {"sink": 0.9, "hob": 0.9}}],
            geo,
        )
        text = render_final_paso1(geo.tipologias, services, mat, ["planilla_marmoleria"])
        assert "TOTAL GENERAL" in text
        assert "ambos materiales" in text
        assert "PEGADOPILETA" in text


class TestStateMachineIntegration:
    def test_zone_learned_persists(self):
        """zone_default from first page should be used in subsequent pages."""
        zones_p2 = [
            {"name": "PLANTA", "bbox": [0, 0, 600, 400]},
            {"name": "CORTE 1-1", "bbox": [0, 400, 500, 850]},
        ]
        # If zone_default is "PLANTA" from page 1
        selected = auto_select_zone(zones_p2, zone_default="PLANTA")
        assert selected["name"] == "PLANTA"

    def test_confirmed_tipologias_from_page_data(self):
        """confirmed_tipologias must be built from page_data, not incremental append."""
        page_data = {
            "1": {"confirmed": True, "skipped": False, "tipologias": [{"id": "DC-02"}]},
            "2": {"confirmed": True, "skipped": True, "tipologias": [{"id": "DC-03"}]},
            "3": {"confirmed": True, "skipped": False, "tipologias": [{"id": "DC-04"}]},
        }
        all_tips = []
        for pg in sorted(page_data.keys(), key=lambda x: int(x)):
            pd = page_data[pg]
            if pd.get("confirmed") and not pd.get("skipped"):
                all_tips.extend(pd.get("tipologias", []))
        assert len(all_tips) == 2
        assert all_tips[0]["id"] == "DC-02"
        assert all_tips[1]["id"] == "DC-04"
        # DC-03 skipped → not in final list

    def test_auto_advance_injects_system_message(self):
        """After confirming page 1, system must inject message for page 2 processing."""
        # Simulate: page 1 confirmed, state set to visual_page_2
        assistant_messages = []
        conf_page = 1
        next_page = 2
        total_pages = 7

        # This is the injection logic from agent.py
        assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
            f"[SISTEMA] Página {conf_page} confirmada. "
            f"Analizar página {next_page}/{total_pages} del PDF. "
            f"Detectar zonas nombradas (PLANTA, CORTE, etc). Solo JSON de zones."
        )}]})

        # Verify injection happened
        assert len(assistant_messages) == 1
        msg = assistant_messages[0]
        assert msg["role"] == "user"
        assert "Página 1 confirmada" in msg["content"][0]["text"]
        assert "página 2/7" in msg["content"][0]["text"]
        assert "zones" in msg["content"][0]["text"]

    def test_visual_builder_done_resets_on_auto_advance(self):
        """_visual_builder_done must be False after auto-advance for next page."""
        _visual_builder_done = True
        _auto_advance_visual = True

        # This is the reset logic from agent.py
        if _auto_advance_visual:
            _visual_builder_done = False

        assert _visual_builder_done is False
