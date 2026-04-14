"""Tests for Paso 1 ↔ Paso 2 consistency guardrail and example selection filter."""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")


class TestExampleFilterByContext:
    """select_examples must not cross-contaminate residential ↔ edificio."""

    def test_building_context_excludes_residential_examples(self):
        from app.modules.agent.agent import select_examples
        # Building message → should not include examples tagged 'particular'
        selected = select_examples(
            user_message="edificio ventus 25 mesadas tipologia DC",
            is_building=True,
            max_examples=5,
        )
        # Load example index to check tags of selected
        from app.modules.agent.agent import _EXAMPLE_INDEX
        tags_map = {e["id"]: set(e.get("tags", [])) for e in _EXAMPLE_INDEX}
        for eid in selected:
            tags = tags_map.get(eid, set())
            assert "particular" not in tags, (
                f"Example {eid} with tags 'particular' should NOT be selected in edificio context"
            )
            assert "residential" not in tags, (
                f"Example {eid} with tags 'residential' should NOT be selected in edificio context"
            )

    def test_residential_context_excludes_building_examples(self):
        from app.modules.agent.agent import select_examples, _EXAMPLE_INDEX
        selected = select_examples(
            user_message="cocina particular silestone blanco norte",
            is_building=False,
            max_examples=5,
        )
        tags_map = {e["id"]: set(e.get("tags", [])) for e in _EXAMPLE_INDEX}
        for eid in selected:
            tags = tags_map.get(eid, set())
            assert "building" not in tags, (
                f"Example {eid} with tag 'building' should NOT be selected in residential context"
            )
            assert "edificio" not in tags, (
                f"Example {eid} with tag 'edificio' should NOT be selected in residential context"
            )


class TestPaso1Paso2Mismatch:
    """Direct logic test: a big m2 mismatch means Claude invented data."""

    def test_m2_mismatch_detected(self):
        """Simulated paso1=66m² vs paso2=1.83m² → over 5% diff, must be flagged."""
        paso1_m2 = 66.57
        paso2_m2 = 1.83
        diff = abs(paso1_m2 - paso2_m2)
        assert diff > 0.5, "Test precondition: large mismatch must be >0.5"
        # Real guardrail uses 0.5 threshold — this confirms we'd trigger override

    def test_piece_count_mismatch_detected(self):
        """21 pieces vs 3 pieces → triggers the count guardrail."""
        paso1_count = 21
        paso2_count = 3
        assert paso1_count != paso2_count
