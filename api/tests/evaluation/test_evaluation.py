"""
Evaluation suite — runs all 34 validated examples against calculate_quote().

Each JSON case in cases/ defines:
  - input: pieces, material, flags → passed to calculate_quote()
  - expected: m² approx, currency, MO items that must/must-not appear, total bounds

Usage:
  pytest tests/evaluation/test_evaluation.py -v
  pytest tests/evaluation/test_evaluation.py -k "quote-030"  # single case
  pytest tests/evaluation/test_evaluation.py -k "building"    # by tag
"""

import json
import glob
import os
import pytest

from app.modules.quote_engine.calculator import calculate_quote, calculate_m2


CASES_DIR = os.path.join(os.path.dirname(__file__), "cases")


def load_cases():
    """Load all JSON test cases from the cases/ directory."""
    cases = []
    for path in sorted(glob.glob(os.path.join(CASES_DIR, "quote-*.json"))):
        with open(path) as f:
            case = json.load(f)
        cases.append(case)
    return cases


ALL_CASES = load_cases()


# ── Parametrize by case ID ───────────────────────────────────────────────────

@pytest.fixture(params=ALL_CASES, ids=[c["id"] for c in ALL_CASES])
def case(request):
    return request.param


# ── Test: m² calculation ─────────────────────────────────────────────────────

class TestM2Calculation:
    """Verify m² total matches expected value (within tolerance)."""

    @pytest.fixture(params=ALL_CASES, ids=[c["id"] for c in ALL_CASES])
    def case(self, request):
        return request.param

    def test_m2_matches_expected(self, case):
        pieces = case["input"]["pieces"]
        m2, details = calculate_m2(pieces)
        expected = case["expected"]["material_m2_approx"]
        # Allow 5% tolerance — examples may have slightly different rounding
        assert abs(m2 - expected) / max(expected, 0.01) < 0.05, \
            f'{case["id"]}: m²={m2}, expected≈{expected} (diff={abs(m2 - expected):.4f})'


# ── Test: calculate_quote runs without error ─────────────────────────────────

class TestQuoteExecution:
    """Verify calculate_quote() runs successfully for each case."""

    @pytest.fixture(params=ALL_CASES, ids=[c["id"] for c in ALL_CASES])
    def case(self, request):
        return request.param

    def test_quote_succeeds(self, case):
        result = calculate_quote(case["input"])
        assert result.get("ok") is True, \
            f'{case["id"]}: calculate_quote failed: {result.get("error")}'

    def test_currency_matches(self, case):
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")
        assert result["material_currency"] == case["expected"]["material_currency"], \
            f'{case["id"]}: currency={result["material_currency"]}, expected={case["expected"]["material_currency"]}'


# ── Test: MO items presence/absence ──────────────────────────────────────────

class TestMOItems:
    """Verify correct MO items are present and incorrect ones are absent."""

    @pytest.fixture(params=ALL_CASES, ids=[c["id"] for c in ALL_CASES])
    def case(self, request):
        return request.param

    def test_required_mo_items_present(self, case):
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        mo_descs = [m["description"].lower() for m in result.get("mo_items", [])]
        mo_text = " ".join(mo_descs)

        for required in case["expected"].get("mo_items_must_have", []):
            found = any(required.lower() in d for d in mo_descs)
            assert found, \
                f'{case["id"]}: MO item "{required}" not found. Got: {mo_descs}'

    def test_forbidden_mo_items_absent(self, case):
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        mo_descs = [m["description"].lower() for m in result.get("mo_items", [])]

        for forbidden in case["expected"].get("mo_items_must_not_have", []):
            found = any(forbidden.lower() in d for d in mo_descs)
            assert not found, \
                f'{case["id"]}: MO item "{forbidden}" should NOT appear. Got: {mo_descs}'


# ── Test: totals are in expected range ───────────────────────────────────────

class TestTotals:
    """Verify totals are within expected bounds."""

    @pytest.fixture(params=ALL_CASES, ids=[c["id"] for c in ALL_CASES])
    def case(self, request):
        return request.param

    def test_total_usd_in_range(self, case):
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        min_usd = case["expected"].get("total_usd_gt", 0)
        if min_usd > 0:
            assert result["total_usd"] >= min_usd, \
                f'{case["id"]}: total_usd={result["total_usd"]}, expected>={min_usd}'

    def test_total_ars_in_range(self, case):
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        min_ars = case["expected"].get("total_ars_gt", 0)
        if min_ars > 0:
            assert result["total_ars"] >= min_ars, \
                f'{case["id"]}: total_ars={result["total_ars"]}, expected>={min_ars}'


# ── Test: structural integrity ───────────────────────────────────────────────

class TestStructuralIntegrity:
    """Verify output structure is complete and consistent."""

    @pytest.fixture(params=ALL_CASES, ids=[c["id"] for c in ALL_CASES])
    def case(self, request):
        return request.param

    def test_has_required_fields(self, case):
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        required = [
            "material_m2", "material_price_unit", "material_currency",
            "material_total", "mo_items", "total_ars", "total_usd",
            "piece_details",
        ]
        for field in required:
            assert field in result, f'{case["id"]}: missing field "{field}"'

    def test_mo_items_have_base_price(self, case):
        """BUG-045: every MO item must include base_price for IVA traceability."""
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        for item in result.get("mo_items", []):
            assert "base_price" in item, \
                f'{case["id"]}: MO item "{item["description"]}" missing base_price'

    def test_mo_items_have_total(self, case):
        """Verify each MO item has a numeric total (prevents $NaN in frontend)."""
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        for item in result.get("mo_items", []):
            assert "total" in item and isinstance(item["total"], (int, float)), \
                f'{case["id"]}: MO item "{item["description"]}" has invalid total: {item.get("total")}'

    def test_colocacion_matches_m2(self, case):
        """Colocación quantity must equal material_m2 (single source of truth)."""
        result = calculate_quote(case["input"])
        if not result.get("ok"):
            pytest.skip(f"quote failed: {result.get('error')}")

        if not case["input"].get("colocacion", True):
            pytest.skip("no colocación in this case")

        coloc = [m for m in result.get("mo_items", []) if "colocación" in m["description"].lower()]
        if not coloc:
            pytest.skip("no colocación MO item found")

        expected_qty = max(result["material_m2"], 1.0)
        assert coloc[0]["quantity"] == expected_qty, \
            f'{case["id"]}: colocación qty={coloc[0]["quantity"]}, material_m2={result["material_m2"]}'
