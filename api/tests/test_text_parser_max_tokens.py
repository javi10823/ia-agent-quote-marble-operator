"""Tests para PR #406 — `parse_measurements` no debe romper por
truncamiento del LLM en briefs largos (caso DYSCON).

**Bug que arregla:** PR #405 agregó instrucciones de `quantity` al
prompt y un campo extra al JSON. El budget de Haiku (`max_tokens=500`)
quedaba justo para casos simples, pero rompía con briefs largos
(edificios con N tipologías). Síntoma observado en logs Railway
2026-04-28 (caso DYSCON, quote b2c79fda):

  ERROR:app.modules.quote_engine.text_parser:Parser JSON decode error:
    Unterminated string starting at: line 15 column 78 (char 1130)

Cuando `parse_measurements` retorna None, todo el flow texto cae al
fallback (Sonnet arma Paso 1 como markdown plano vía tool `list_pieces`)
y el operador pierde:
  - card de `__CONTEXT_ANALYSIS__`
  - card editable de `__DUAL_READ__`
  - validación pre-despiece

Fix:
  1. `max_tokens=500` → `max_tokens=4000` — cubre edificios de ~80
     piezas con holgura.
  2. Log más explícito cuando el motivo es truncamiento (`stop_reason
     == "max_tokens"`) para que el operador no tenga que correlacionar
     el síntoma "card desapareció" con el error genérico de JSON.

Cobertura:
  - Caso DYSCON exacto (14 piezas con quantities) → no rompe, devuelve
    14 pieces parsed.
  - Caso simple (1-2 piezas) → comportamiento idéntico a pre-#406.
  - Mock de Haiku con `stop_reason="max_tokens"` → log dice
    "truncated by max_tokens" en vez de "JSON decode error" genérico.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.quote_engine.text_parser import parse_measurements


# Helper: mock del response.content[0].text + stop_reason.
def _mock_response(text: str, stop_reason: str = "end_turn") -> MagicMock:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = stop_reason
    return resp


# ═══════════════════════════════════════════════════════════════════════
# Caso DYSCON exacto — 14 piezas con quantity, debe parsear OK
# ═══════════════════════════════════════════════════════════════════════


class TestDysconBriefParses:
    @pytest.mark.asyncio
    async def test_dyscon_14_pieces_parses_ok(self):
        """Brief largo con 14 piezas + quantities. El JSON pesa más que
        500 tokens — con max_tokens=4000 (PR #406) cabe. Si volviéramos
        a 500, este test rompe con `JSONDecodeError`."""
        full_json = json.dumps({
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 24},
                {"description": "M2 mesada (Office 32)", "largo": 1.70, "prof": 0.6, "quantity": 1},
                {"description": "M2 zócalo atrás", "largo": 1.70, "alto": 0.10, "quantity": 1},
                {"description": "M3 mesada (Office 12) - SE REALIZA EN 2 TRAMOS", "largo": 2.50, "prof": 0.6, "quantity": 1},
                {"description": "M3 zócalo atrás", "largo": 2.50, "alto": 0.10, "quantity": 1},
                {"description": "M4 mesada (Office 27) - SE REALIZA EN 2 TRAMOS", "largo": 2.50, "prof": 0.6, "quantity": 1},
                {"description": "M4 zócalo atrás", "largo": 2.50, "alto": 0.10, "quantity": 1},
                {"description": "M5 mesada (Office 53)", "largo": 1.80, "prof": 0.6, "quantity": 1},
                {"description": "M5 zócalo atrás", "largo": 1.80, "alto": 0.10, "quantity": 1},
                {"description": "M6 mesada (Office 80/83)", "largo": 1.55, "prof": 0.6, "quantity": 2},
                {"description": "M6 zócalo atrás", "largo": 1.55, "alto": 0.10, "quantity": 2},
                {"description": "M7 mesada (Office 87/90)", "largo": 1.50, "prof": 0.6, "quantity": 2},
                {"description": "M7 zócalo atrás", "largo": 1.50, "alto": 0.10, "quantity": 2},
            ],
            "pileta": None,
            "anafe": False,
            "colocacion": False,
            "frentin": False,
        }, ensure_ascii=False)

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(full_json))

        with patch(
            "app.modules.quote_engine.text_parser.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await parse_measurements(
                notes="brief simulado dyscon (no se usa, mock manda response)",
                material="Granito Gris Mara",
                project="Unidad Penal N°8",
            )

        assert result is not None, "Parser devolvió None — bug regression: probablemente max_tokens volvió a 500"
        assert len(result["pieces"]) == 14
        # Verifica que `quantity` se propaga en el output (test que
        # entra fan-out con #405).
        assert result["pieces"][0]["quantity"] == 24
        assert result["pieces"][10]["quantity"] == 2

    @pytest.mark.asyncio
    async def test_max_tokens_is_at_least_4000(self):
        """Drift guard: si alguien revierte el max_tokens accidentalmente
        a un valor menor, este test rompe. Capturamos el kwarg pasado
        a Anthropic."""
        captured_kwargs = {}

        async def _capture(**kwargs):
            captured_kwargs.update(kwargs)
            return _mock_response(json.dumps({
                "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            }))

        mock_client = MagicMock()
        mock_client.messages.create = _capture

        with patch(
            "app.modules.quote_engine.text_parser.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            await parse_measurements("brief", "Material X")

        assert captured_kwargs.get("max_tokens", 0) >= 4000, (
            f"max_tokens regresión: encontrado {captured_kwargs.get('max_tokens')}, "
            f"esperaba ≥4000. PR #405 + briefs largos rompen con menos."
        )


# ═══════════════════════════════════════════════════════════════════════
# Regression — caso simple sigue funcionando idéntico
# ═══════════════════════════════════════════════════════════════════════


class TestSimpleBriefStillWorks:
    @pytest.mark.asyncio
    async def test_simple_2_pieces_parses_ok(self):
        """Brief mínimo (mesada + zócalo) → sin cambio post-#406."""
        simple_json = json.dumps({
            "pieces": [
                {"description": "Mesada cocina", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo trasero", "largo": 2.0, "alto": 0.05},
            ],
            "pileta": None,
            "anafe": False,
            "colocacion": True,
            "frentin": False,
        })

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(simple_json))

        with patch(
            "app.modules.quote_engine.text_parser.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await parse_measurements("cocina 2x60", "Silestone")

        assert result is not None
        assert len(result["pieces"]) == 2
        assert result["pieces"][0]["largo"] == 2.0


# ═══════════════════════════════════════════════════════════════════════
# Log mejor cuando trunca — operador sabe el motivo real
# ═══════════════════════════════════════════════════════════════════════


class TestTruncationLogIsExplicit:
    @pytest.mark.asyncio
    async def test_max_tokens_stop_reason_logs_truncation(self, caplog):
        """Si Haiku trunca (`stop_reason="max_tokens"`) → log dice
        "truncated by max_tokens" explícito, no solo "decode error"
        genérico. El operador puede correlacionar al ver "card de
        contexto desapareció" + este log."""
        truncated_json = '{"pieces": [{"description": "Mesada", "largo": 2.0, "prof":'  # cortado
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(truncated_json, stop_reason="max_tokens")
        )

        import logging as _logging
        with caplog.at_level(_logging.ERROR), patch(
            "app.modules.quote_engine.text_parser.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await parse_measurements("brief", "Material")

        assert result is None  # falla, como antes — pero con mejor log
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "truncated by max_tokens" in joined, (
            f"Log debe decir 'truncated by max_tokens' explícito. Got: {joined!r}"
        )

    @pytest.mark.asyncio
    async def test_other_decode_error_logs_normally(self, caplog):
        """Si el JSON está roto por otra razón (no truncamiento), el
        log NO debe decir 'truncated by max_tokens' (sería confuso)."""
        broken_json = "{ this is not json at all"
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(broken_json, stop_reason="end_turn")
        )

        import logging as _logging
        with caplog.at_level(_logging.ERROR), patch(
            "app.modules.quote_engine.text_parser.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await parse_measurements("brief", "Material")

        assert result is None
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "truncated by max_tokens" not in joined, (
            "No debería decir truncated cuando stop_reason != max_tokens"
        )
        assert "decode error" in joined.lower() or "stop_reason=end_turn" in joined
