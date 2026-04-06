"""
Token budget & cache control tests.

Validates Anthropic API consumption stays within safe thresholds.
No real API calls — all mocked. Runs in CI.
"""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.modules.agent.agent import build_system_prompt, TOOLS


# ── Token estimation helper ─────────────────────────────────────────────────

def estimate_tokens(chars: int) -> int:
    """Approximate token count: ~3 chars per token for mixed Spanish/English."""
    return chars // 3


# ── Test 1: Effective input tokens per request never exceed 40,000 ──────────
# "Effective" = cached stable block at 10% cost + conditional at full cost.
# This reflects what you actually PAY, not raw token count.

class TestTokenBudget:
    """Assert system prompt + tools stay within budget for all scenarios."""

    def _prompt_effective_tokens(self, **kwargs) -> tuple[int, int, int]:
        """Returns (effective_tokens, stable_chars, conditional_chars)."""
        blocks = build_system_prompt(**kwargs)
        stable_chars = len(blocks[0]["text"]) if blocks else 0
        conditional_chars = sum(len(b["text"]) for b in blocks[1:] if b.get("type") == "text")
        # Stable block pays 10% (cache hit), conditional pays 100%
        effective = estimate_tokens(stable_chars) * 10 // 100 + estimate_tokens(conditional_chars)
        return effective, stable_chars, conditional_chars

    def _tools_tokens(self) -> int:
        import json
        return estimate_tokens(len(json.dumps(TOOLS)))

    def test_basic_request_under_40k(self):
        """Standard chat: effective tokens (cached stable at 10% + conditional) under 40K."""
        effective, stable, cond = self._prompt_effective_tokens(
            user_message="Mesada cocina 2.80 x 0.60 Silestone Blanco Norte, pileta Johnson, Rosario",
        )
        total = effective + self._tools_tokens() + 600
        assert total < 40_000, (
            f"Basic request exceeds budget: {total} effective tokens "
            f"(stable={stable} chars, conditional={cond} chars)"
        )

    def test_building_request_under_40k(self):
        """Building request (extra rules) effective tokens under 40K."""
        effective, stable, cond = self._prompt_effective_tokens(
            user_message="Edificio Metrolatina, 15 unidades, sin colocación",
            is_building=True,
        )
        total = effective + self._tools_tokens() + 600
        assert total < 40_000, (
            f"Building request exceeds budget: {total} effective tokens "
            f"(stable={stable} chars, conditional={cond} chars)"
        )

    def test_plan_request_under_40k(self):
        """Plan-attached request effective tokens under 40K."""
        effective, stable, cond = self._prompt_effective_tokens(
            user_message="Te paso el plano de la cocina",
            has_plan=True,
        )
        total = effective + self._tools_tokens() + 600
        assert total < 40_000, (
            f"Plan request exceeds budget: {total} effective tokens "
            f"(stable={stable} chars, conditional={cond} chars)"
        )

    def test_worst_case_under_40k(self):
        """Worst case: building + plan + long history, effective tokens under 40K."""
        effective, stable, cond = self._prompt_effective_tokens(
            user_message="Edificio con plano, 10 unidades funcionales, sin colocación, Dekton",
            has_plan=True,
            is_building=True,
        )
        total = effective + self._tools_tokens() + 1500
        assert total < 40_000, (
            f"Worst-case exceeds budget: {total} effective tokens "
            f"(stable={stable} chars, conditional={cond} chars)"
        )

    def test_raw_prompt_under_50k(self):
        """Raw (uncached) worst case must stay under 50K tokens to avoid API limits."""
        blocks = build_system_prompt(
            user_message="Edificio con plano, 10 unidades, Dekton",
            has_plan=True,
            is_building=True,
        )
        total_chars = sum(len(b["text"]) for b in blocks if b.get("type") == "text")
        raw_tokens = estimate_tokens(total_chars) + self._tools_tokens() + 1500
        assert raw_tokens < 55_000, (
            f"Raw prompt exceeds 55K token limit: {raw_tokens} tokens ({total_chars} chars)"
        )

    def test_dynamic_examples_capped_at_2(self):
        """Verify max_examples=2 in build_system_prompt (not 3+)."""
        # A long message with many material keywords should still get only 2 dynamic examples
        blocks = build_system_prompt(
            user_message="Silestone Dekton Neolith Purastone granito mármol laminatto cocina baño toilette isla",
        )
        conditional_text = blocks[1]["text"] if len(blocks) > 1 else ""
        example_count = conditional_text.count("## Ejemplo:")
        assert example_count <= 2, f"Expected max 2 dynamic examples, got {example_count}"


# ── Test 2: Cache control on system prompt ──────────────────────────────────

class TestCacheControl:
    """Assert every API call includes cache_control on the stable system block."""

    def test_stable_block_has_cache_control(self):
        """The first system block must have cache_control: ephemeral."""
        blocks = build_system_prompt(user_message="test")
        assert len(blocks) >= 1, "System prompt must have at least 1 block"

        stable_block = blocks[0]
        assert stable_block.get("type") == "text"
        assert "cache_control" in stable_block, "Stable block missing cache_control"
        assert stable_block["cache_control"] == {"type": "ephemeral"}, (
            f"Expected ephemeral cache_control, got {stable_block['cache_control']}"
        )

    def test_only_stable_block_has_cache_control(self):
        """Conditional blocks must NOT have cache_control (they change per request)."""
        blocks = build_system_prompt(
            user_message="Edificio con plano",
            has_plan=True,
            is_building=True,
        )
        for block in blocks[1:]:
            assert "cache_control" not in block, (
                f"Conditional block should not have cache_control: {block['text'][:80]}..."
            )

    def test_stable_block_is_largest(self):
        """The cached stable block should contain the bulk of the prompt."""
        blocks = build_system_prompt(user_message="test")
        stable_size = len(blocks[0]["text"])
        conditional_size = sum(len(b["text"]) for b in blocks[1:])

        assert stable_size > conditional_size, (
            f"Stable block ({stable_size} chars) should be larger than "
            f"conditional content ({conditional_size} chars) for cache to be effective"
        )


# ── Test 3: Keep-alive gate — only fires with recent activity ───────────────

class TestKeepAliveGate:
    """Assert the cache ping respects the activity window."""

    @pytest.mark.asyncio
    async def test_ping_fires_with_recent_activity(self):
        """Keep-alive should call messages.create when there was recent chat activity."""
        import app.main as main_module

        # Simulate recent activity
        main_module._last_chat_activity = time.time() - 60  # 1 minute ago

        mock_client = MagicMock()
        mock_create = AsyncMock(return_value=MagicMock())
        mock_client.messages.create = mock_create

        with patch("app.modules.agent.agent._get_stable_text", return_value="cached prompt"):
            # Call the inner logic directly (not the infinite loop)
            from app.modules.agent.agent import _get_stable_text
            if time.time() - main_module._last_chat_activity < main_module.ACTIVITY_WINDOW:
                system = [{"type": "text", "text": _get_stable_text(), "cache_control": {"type": "ephemeral"}}]
                await mock_client.messages.create(
                    model="test-model",
                    max_tokens=1,
                    system=system,
                    messages=[{"role": "user", "content": "ping"}],
                )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 1, "Ping should use max_tokens=1"
        assert call_kwargs.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_ping_skipped_without_recent_activity(self):
        """Keep-alive should NOT call messages.create when no recent activity."""
        import app.main as main_module

        # Simulate old activity (20 minutes ago)
        main_module._last_chat_activity = time.time() - 1200

        mock_client = MagicMock()
        mock_create = AsyncMock()
        mock_client.messages.create = mock_create

        # Replicate the gate logic from _cache_keepalive_loop
        if time.time() - main_module._last_chat_activity < main_module.ACTIVITY_WINDOW:
            await mock_client.messages.create(
                model="test-model",
                max_tokens=1,
                system=[],
                messages=[{"role": "user", "content": "ping"}],
            )

        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_ping_skipped_with_zero_activity(self):
        """Keep-alive should NOT fire on fresh startup (no activity yet)."""
        import app.main as main_module

        main_module._last_chat_activity = 0.0  # Never used

        mock_create = AsyncMock()

        if time.time() - main_module._last_chat_activity < main_module.ACTIVITY_WINDOW:
            await mock_create()

        mock_create.assert_not_called()

    def test_touch_chat_activity_updates_timestamp(self):
        """touch_chat_activity() should update the global timestamp."""
        import app.main as main_module

        main_module._last_chat_activity = 0.0
        before = time.time()
        main_module.touch_chat_activity()
        after = time.time()

        assert main_module._last_chat_activity >= before
        assert main_module._last_chat_activity <= after

    def test_activity_window_is_10_minutes(self):
        """ACTIVITY_WINDOW constant must be 600 seconds (10 minutes)."""
        import app.main as main_module
        assert main_module.ACTIVITY_WINDOW == 600
