"""Tests for operator-web multi-material detection.

These assert the rule "1 material = 1 presupuesto" for the operator flow.
The chatbot endpoint (/api/v1/quote) is intentionally NOT exercised here —
it is asserted to be independent in the integration layer.
"""
from __future__ import annotations

import pytest

from app.modules.agent.material_detector import (
    detect_materials_in_brief,
    invalidate_material_detector_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    invalidate_material_detector_cache()
    yield
    invalidate_material_detector_cache()


# ─────────────────────────────────────────────────────────────────────────
# Happy paths: canonical names trigger detection
# ─────────────────────────────────────────────────────────────────────────

def test_two_full_canonical_names_triggers():
    """Two distinct full canonical names must yield 2 matches."""
    brief = "Cotizar en Silestone Blanco Norte o Granito Ceara"
    found = detect_materials_in_brief(brief)
    # Detector may match case-insensitive; accept >=2 distinct names
    assert len(found) >= 2
    lower = [n.lower() for n in found]
    assert any("silestone blanco norte" in n for n in lower)
    assert any("granito ceara" in n for n in lower)


def test_single_full_name_passes():
    """A single material mention must not trip the guardrail."""
    brief = "Cotizar en Silestone Blanco Norte — 2 mesadas"
    found = detect_materials_in_brief(brief)
    # Must be exactly 1 (the Silestone Blanco Norte)
    assert len(found) == 1
    assert "silestone blanco norte" in found[0].lower()


def test_same_name_different_casing_counts_once():
    """Mixed casing of the same material collapses to a single canonical."""
    brief = "silestone blanco norte para la cocina, y SILESTONE BLANCO NORTE para el baño"
    found = detect_materials_in_brief(brief)
    assert len(found) == 1


# ─────────────────────────────────────────────────────────────────────────
# False-positive guards (partial / substring words)
# ─────────────────────────────────────────────────────────────────────────

def test_no_false_positive_bathroom_and_kitchen():
    """'baño' must never match 'BAÑO' or partials that live inside catalog names."""
    brief = "Silestone Blanco Norte para la cocina y baño"
    found = detect_materials_in_brief(brief)
    assert len(found) == 1
    assert "silestone blanco norte" in found[0].lower()


def test_no_false_positive_partial_color_word():
    """A lone color word must NOT match a catalog material."""
    brief = "Color blanco, medidas 2.5 x 0.62"
    found = detect_materials_in_brief(brief)
    assert found == []


def test_no_false_positive_norte_alone():
    """'norte' alone must not match SILESTONE BLANCO NORTE."""
    brief = "entrega en la zona norte"
    found = detect_materials_in_brief(brief)
    assert found == []


def test_no_false_positive_with_typo():
    """A typo in a material name must fail-open (no match)."""
    brief = "cotizar en silestone blnaco norte"
    found = detect_materials_in_brief(brief)
    # typo → no canonical match → empty (fail-open behavior, operator keeps going)
    assert found == []


# ─────────────────────────────────────────────────────────────────────────
# Boundary cases
# ─────────────────────────────────────────────────────────────────────────

def test_empty_text_returns_empty():
    assert detect_materials_in_brief("") == []
    assert detect_materials_in_brief("   \n  ") == []


def test_none_text_safe():
    assert detect_materials_in_brief(None) == []  # type: ignore[arg-type]


def test_material_surrounded_by_punctuation_still_matches():
    """Word-boundary regex should recognize names inside punctuation."""
    brief = "(Silestone Blanco Norte). Pieza 1."
    found = detect_materials_in_brief(brief)
    assert len(found) == 1


def test_short_tokens_never_match():
    """2-3 char tokens (even if they existed in catalog somehow) are ignored."""
    # This is a behavioral guard — the detector drops keys < 4 chars.
    brief = "usa el m2 para calcular"
    found = detect_materials_in_brief(brief)
    assert found == []


# ─────────────────────────────────────────────────────────────────────────
# SKU recognition (if present as a complete token)
# ─────────────────────────────────────────────────────────────────────────

def test_sku_as_whole_token_matches():
    """A full catalog SKU appearing as its own token should match."""
    # Use an SKU guaranteed to exist in the current catalog.
    brief = "usar SILESTONENORTE para la cocina"
    found = detect_materials_in_brief(brief)
    assert len(found) >= 1


# ─────────────────────────────────────────────────────────────────────────
# Fail-open semantics
# ─────────────────────────────────────────────────────────────────────────

def test_detector_never_raises_on_garbled_input():
    """Any input, no matter how weird, must return a list (possibly empty)."""
    for junk in [
        "",
        "🔥🔥🔥",
        "<script>alert(1)</script>",
        "\x00\x00\x00",
        "a" * 10000,
    ]:
        out = detect_materials_in_brief(junk)
        assert isinstance(out, list)


def test_threshold_interpretation_is_callers_job():
    """
    The detector returns WHAT it saw; the >=2 threshold for interrupting is
    applied by the caller (agent.py). This test pins that contract.
    """
    brief = "Silestone Blanco Norte"
    found = detect_materials_in_brief(brief)
    # Caller only interrupts when len(found) >= 2 — detector is free to
    # return 0 or 1 without side effects.
    assert len(found) < 2
