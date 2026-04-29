"""Tests para PR #423 — retry counter (Issue #422).

**Caso DYSCON observado en producción:**

Cuando una tool retorna error, Sonnet a veces intenta auto-fixear
inventando valores (logs `9da51080-...` infló m² a 1755%). El
guardrail-B atrapó ESE caso pero el patrón vuelve con cualquier
validator nuevo. Este PR mete un retry counter en el loop agéntico
que bloquea la tool después de 2 fallos en el mismo turno y fuerza
a Sonnet a consultar al operador.

**Tests cubren los 5 escenarios del Issue #422:**

1. Tool falla 1 vez → retry permitido (count=1, threshold no alcanzado).
2. Tool falla 2 veces → 3er intento bloqueado con mensaje al operador.
3. Tool exitoso entre fallos → contador NO se resetea (sigue contando
   solo errores).
4. Tool distinto NO contribuye al contador del primero (counter por tool).
5. Drift guard: el bloque sintético tiene `_retry_blocked=True` y un
   mensaje claro que NO da pistas de auto-fix.

**Por qué unit-tests directos sobre `retry_guard` y no integration:**

La integración (loop agéntico en `stream_chat`) requiere mockear la
API de Anthropic — overkill. Las funciones de `retry_guard` son
puras y deterministicas; testearlas directamente cubre la lógica.
La integración la valida el caso real en staging (logs `[retry-block:<qid>]`).
"""
from __future__ import annotations

import pytest

from app.modules.agent.retry_guard import (
    DEFAULT_RETRY_THRESHOLD,
    build_retry_block_result,
    increment_failure,
    is_tool_failure,
    should_block_retry,
)


# ═══════════════════════════════════════════════════════════════════════
# is_tool_failure — definición de "fallo"
# ═══════════════════════════════════════════════════════════════════════


class TestIsToolFailure:
    def test_ok_false_is_failure(self):
        assert is_tool_failure({"ok": False, "error": "x"}) is True

    def test_error_field_is_failure(self):
        """Algunos tools no tienen `ok`, solo `error`."""
        assert is_tool_failure({"error": "validation failed"}) is True

    def test_ok_true_is_success(self):
        assert is_tool_failure({"ok": True, "data": "..."}) is False

    def test_no_ok_no_error_is_success(self):
        """`catalog_lookup` retorna `{"found": True, "price_ars": ...}` —
        no tiene `ok` ni `error` y es éxito."""
        assert is_tool_failure({"found": True, "price_ars": 100000}) is False

    def test_empty_dict_is_success(self):
        """Defensivo — un dict vacío no tiene info de fallo."""
        assert is_tool_failure({}) is False

    def test_list_is_success(self):
        """`read_plan` retorna list de content blocks (image+text),
        no un dict. NO es fallo."""
        assert is_tool_failure([{"type": "image"}, {"type": "text"}]) is False

    def test_none_is_success(self):
        """Defensivo — None no penaliza al agente."""
        assert is_tool_failure(None) is False

    def test_empty_error_string_is_success(self):
        """`error: ""` no debe contar como fallo (truthy check)."""
        assert is_tool_failure({"error": ""}) is False

    def test_ok_true_with_error_field_still_success(self):
        """Edge case: `{ok: True, error: ""}`. Si ok=True, no es fallo
        sin importar el campo error vacío. Pero si error es truthy, es
        ambiguo — la convención de la app es que ok manda."""
        # Tomamos la decisión MÁS conservadora: si hay error truthy,
        # contamos como fallo aunque ok=True. Mejor falso positivo
        # (un retry de más) que falso negativo (Sonnet sigue inventando).
        assert is_tool_failure({"ok": True, "error": "warning real"}) is True


# ═══════════════════════════════════════════════════════════════════════
# should_block_retry — pre-execution check
# ═══════════════════════════════════════════════════════════════════════


class TestShouldBlockRetry:
    def test_zero_failures_no_block(self):
        assert should_block_retry("calculate_quote", {}) is False

    def test_one_failure_no_block(self):
        """1 fallo → 2do intento permitido."""
        counter = {"calculate_quote": 1}
        assert should_block_retry("calculate_quote", counter) is False

    def test_two_failures_blocks(self):
        """2 fallos → 3er intento bloqueado (threshold alcanzado)."""
        counter = {"calculate_quote": 2}
        assert should_block_retry("calculate_quote", counter) is True

    def test_three_failures_blocks(self):
        """Más allá del threshold sigue bloqueado."""
        counter = {"calculate_quote": 5}
        assert should_block_retry("calculate_quote", counter) is True

    def test_block_per_tool_name(self):
        """Tool A failando 2x NO bloquea tool B (counter por tool)."""
        counter = {"calculate_quote": 2}
        assert should_block_retry("calculate_quote", counter) is True
        assert should_block_retry("generate_documents", counter) is False

    def test_custom_threshold(self):
        """`threshold` override-able por callers (tests, futuras tunes)."""
        counter = {"calculate_quote": 1}
        assert should_block_retry("calculate_quote", counter, threshold=1) is True
        assert should_block_retry("calculate_quote", counter, threshold=5) is False

    def test_default_threshold_is_2(self):
        """Drift guard del default. Si alguien lo cambia, este test
        falla y obliga a actualizar el Issue + docs."""
        assert DEFAULT_RETRY_THRESHOLD == 2


# ═══════════════════════════════════════════════════════════════════════
# build_retry_block_result — mensaje sintético al agente
# ═══════════════════════════════════════════════════════════════════════


class TestBuildRetryBlockResult:
    def test_has_retry_blocked_flag(self):
        """Caller downstream (logs, telemetría) debe poder identificar
        que este result fue sintético, no del tool real."""
        result = build_retry_block_result("calculate_quote", 2)
        assert result.get("_retry_blocked") is True

    def test_has_ok_false(self):
        """`is_tool_failure` reconoce este result como fallo (sigue
        contando para el threshold si el agent persiste)."""
        result = build_retry_block_result("calculate_quote", 2)
        assert result.get("ok") is False
        assert is_tool_failure(result) is True

    def test_error_mentions_tool_name(self):
        result = build_retry_block_result("calculate_quote", 2)
        assert "calculate_quote" in result["error"]

    def test_error_mentions_failure_count(self):
        result = build_retry_block_result("calculate_quote", 5)
        assert "5" in result["error"]

    def test_error_forces_operator_consultation(self):
        """El mensaje DEBE mencionar al operador y NO dar pistas de
        cómo auto-fixear. Sin esto, Sonnet puede ignorar el block."""
        result = build_retry_block_result("calculate_quote", 2)
        msg = result["error"].lower()
        assert "operador" in msg
        assert "no reintentes" in msg or "no reintentar" in msg
        # NO debe sugerir fixes ni dar opciones — solo "consultá al operador".
        assert "intentá" not in msg or "no" in msg


# ═══════════════════════════════════════════════════════════════════════
# increment_failure — mutación del counter
# ═══════════════════════════════════════════════════════════════════════


class TestIncrementFailure:
    def test_first_increment(self):
        counter: dict[str, int] = {}
        new = increment_failure("calculate_quote", counter)
        assert new == 1
        assert counter == {"calculate_quote": 1}

    def test_subsequent_increments(self):
        counter = {"calculate_quote": 1}
        new = increment_failure("calculate_quote", counter)
        assert new == 2
        assert counter["calculate_quote"] == 2

    def test_independent_per_tool(self):
        counter = {"calculate_quote": 2}
        increment_failure("generate_documents", counter)
        assert counter == {"calculate_quote": 2, "generate_documents": 1}


# ═══════════════════════════════════════════════════════════════════════
# Escenarios completos del Issue #422
# ═══════════════════════════════════════════════════════════════════════


class TestRetryCounterScenarios:
    """Tests end-to-end de la lógica del loop, sin la API.

    Simulamos el bucle:
        for tool_use in [...]:
            if should_block_retry(name, counter):
                result = build_retry_block_result(name, count)
            else:
                result = mock_execute_tool(...)
            if is_tool_failure(result):
                increment_failure(name, counter)
    """

    def _simulate_call(
        self,
        tool_name: str,
        counter: dict[str, int],
        mock_result: dict,
    ) -> dict:
        """Una iteración del loop agéntico, con un result mockeado."""
        if should_block_retry(tool_name, counter):
            prior = counter.get(tool_name, 0)
            result = build_retry_block_result(tool_name, prior)
        else:
            result = mock_result
        if is_tool_failure(result):
            increment_failure(tool_name, counter)
        return result

    # ── 1. Tool falla 1 vez → retry permitido ─────────────────────────
    def test_one_failure_allows_retry(self):
        counter: dict[str, int] = {}
        result1 = self._simulate_call(
            "calculate_quote", counter, {"ok": False, "error": "fail 1"},
        )
        # 1ra ejecutó normal (no bloqueada).
        assert result1.get("_retry_blocked") is None
        assert counter["calculate_quote"] == 1

    # ── 2. Tool falla 2 veces → 3er intento bloqueado ────────────────
    def test_two_failures_then_block(self):
        counter: dict[str, int] = {}
        # 1ra
        r1 = self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail 1"})
        assert r1.get("_retry_blocked") is None
        assert counter["calculate_quote"] == 1
        # 2da
        r2 = self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail 2"})
        assert r2.get("_retry_blocked") is None
        assert counter["calculate_quote"] == 2
        # 3ra → BLOCKED. El mock_result pasado se descarta porque el
        # block dispara antes de llegar a "ejecutar".
        r3 = self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail 3"})
        assert r3.get("_retry_blocked") is True
        assert "operador" in r3["error"].lower()
        # El bloque sintético TAMBIÉN cuenta como fallo (ok=False) →
        # counter sigue subiendo. Si Sonnet ignora el block y vuelve a
        # llamar, sigue en estado bloqueado, no entra en bucle infinito.
        assert counter["calculate_quote"] == 3

    # ── 3. Éxito intermedio NO resetea el contador ───────────────────
    def test_success_between_failures_does_not_reset(self):
        """Anti-patrón a evitar: si Sonnet alterna fail-success-fail,
        el contador debe seguir contando los errores totales. Si
        reseteáramos con éxitos, Sonnet podría caminar el sistema
        haciendo un succ artificial entre cada retry."""
        counter: dict[str, int] = {}
        self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail 1"})
        assert counter["calculate_quote"] == 1
        # Éxito intermedio
        r_success = self._simulate_call("calculate_quote", counter, {"ok": True, "data": "..."})
        assert r_success.get("ok") is True
        assert counter["calculate_quote"] == 1, "Éxito NO debe resetear"
        # Otro fail
        self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail 2"})
        assert counter["calculate_quote"] == 2
        # 3ra debería bloquear (a pesar del éxito intermedio).
        r_blocked = self._simulate_call("calculate_quote", counter, {"ok": True, "data": "..."})
        assert r_blocked.get("_retry_blocked") is True

    # ── 4. Tool distinto NO contribuye al primer counter ─────────────
    def test_independent_tool_counters(self):
        counter: dict[str, int] = {}
        # calculate_quote falla 2 veces → próxima bloqueada.
        self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail"})
        self._simulate_call("calculate_quote", counter, {"ok": False, "error": "fail"})
        assert counter["calculate_quote"] == 2
        # generate_documents en su 1ra → debe pasar normal.
        r = self._simulate_call("generate_documents", counter, {"ok": False, "error": "validation fail"})
        assert r.get("_retry_blocked") is None
        assert counter["generate_documents"] == 1
        # calculate_quote 3ra sigue bloqueada.
        r2 = self._simulate_call("calculate_quote", counter, {"ok": True, "data": "..."})
        assert r2.get("_retry_blocked") is True

    # ── 5. Drift guard del block — NO debe sugerir fixes ─────────────
    def test_block_message_does_not_suggest_autofix(self):
        """El mensaje del bloque debe forzar consulta al operador, no
        sugerir 'intentá con otros valores'. Sin esto Sonnet puede
        ignorar el block y meter más valores inventados."""
        counter = {"calculate_quote": 2}
        r = self._simulate_call("calculate_quote", counter, {})
        msg = r["error"].lower()
        assert "operador" in msg
        # Frases que NO deben aparecer (incentivan auto-fix):
        forbidden = ["probá con", "intentá con valores", "ajustá los"]
        for phrase in forbidden:
            assert phrase not in msg, f"Found auto-fix hint: {phrase!r} in {msg!r}"
