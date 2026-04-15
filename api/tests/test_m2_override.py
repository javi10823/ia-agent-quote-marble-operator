"""Tests for Planilla de Cómputo (m2_override) flow.

Covers:
  - calculate_m2 respects m2_override per piece
  - override flag is preserved through dedup
  - sectors labels get the '*' suffix + has_m2_override flag on calc result
  - _pdf_has_m2_override renderer helper
"""
from __future__ import annotations

from app.modules.quote_engine.calculator import calculate_m2
from app.modules.agent.tools.document_tool import _pdf_has_m2_override


def test_no_override_uses_largo_prof():
    total, details = calculate_m2(
        [{"description": "DC-02", "largo": 1.43, "prof": 0.62, "quantity": 2}]
    )
    # 1.43 * 0.62 = 0.8866 → half-up 2 dec = 0.89 → × 2 = 1.78
    # (PR consistencia m²: el total es suma de displays, no round(raw))
    assert abs(total - 1.78) < 0.01
    assert details[0]["override"] is False


def test_override_takes_precedence_over_largo_prof():
    total, details = calculate_m2(
        [
            {
                "description": "DC-02",
                "largo": 1.43,
                "prof": 0.62,
                "quantity": 2,
                "m2_override": 1.78,
            }
        ]
    )
    # 1.78 × 2 = 3.56, largo×prof ignored
    assert total == 3.56
    assert details[0]["override"] is True


def test_override_zero_or_none_falls_back():
    """m2_override=0 or None → calculator falls back to largo×prof."""
    t1, d1 = calculate_m2(
        [{"description": "x", "largo": 1.0, "prof": 0.5, "m2_override": 0}]
    )
    assert t1 == 0.5 and d1[0]["override"] is False
    t2, d2 = calculate_m2(
        [{"description": "x", "largo": 1.0, "prof": 0.5, "m2_override": None}]
    )
    assert t2 == 0.5 and d2[0]["override"] is False


def test_override_invalid_falls_back():
    t, d = calculate_m2(
        [
            {
                "description": "x",
                "largo": 2.0,
                "prof": 0.6,
                "m2_override": "not-a-number",
            }
        ]
    )
    assert t == 1.2
    assert d[0]["override"] is False


def test_override_mixed_pieces():
    """Some pieces with override, some without — totals are additive."""
    total, details = calculate_m2(
        [
            {"description": "A", "largo": 1.0, "prof": 0.5},  # 0.5
            {"description": "B", "largo": 2.0, "prof": 0.6, "m2_override": 2.0},  # 2.0
        ]
    )
    assert total == 2.5
    assert details[0]["override"] is False
    assert details[1]["override"] is True


def test_pdf_has_m2_override_via_flag():
    assert _pdf_has_m2_override({"has_m2_override": True}) is True
    assert _pdf_has_m2_override({"has_m2_override": False}) is False


def test_pdf_has_m2_override_via_piece_suffix():
    data = {
        "sectors": [
            {
                "label": "Obra",
                "pieces": ["1.43 × 0.62 DC-02 *", "0.60 × 0.38 Mesada"],
            }
        ]
    }
    assert _pdf_has_m2_override(data) is True


def test_pdf_has_m2_override_none_when_no_marker():
    data = {
        "sectors": [
            {
                "label": "Obra",
                "pieces": ["1.43 × 0.62 DC-02", "0.60 × 0.38 Mesada"],
            }
        ]
    }
    assert _pdf_has_m2_override(data) is False


def test_pdf_has_m2_override_empty_safe():
    assert _pdf_has_m2_override({}) is False
    assert _pdf_has_m2_override({"sectors": []}) is False
    assert _pdf_has_m2_override({"sectors": [{"label": "x", "pieces": []}]}) is False
