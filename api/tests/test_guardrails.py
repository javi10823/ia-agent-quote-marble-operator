"""Tests for guardrails: list_pieces enforcement, unified edificio detection, file verification."""

import pytest
from app.modules.agent.agent import _detect_building, TOOLS


# ── Fix 1: list_pieces in TOOLS ──────────────────────────────────────────────

class TestListPiecesGuardrail:
    def test_list_pieces_is_first_tool(self):
        """list_pieces should be the first tool in TOOLS (high visibility to Claude)."""
        assert TOOLS[0]["name"] == "list_pieces"

    def test_list_pieces_description_says_obligatorio(self):
        """Description must make it clear this is mandatory for Paso 1."""
        tool = next(t for t in TOOLS if t["name"] == "list_pieces")
        desc = tool["description"].upper()
        assert "OBLIGATORIO" in desc or "SIEMPRE" in desc


# ── Fix 2: Unified edificio detection ────────────────────────────────────────

class TestUnifiedEdificioDetection:
    """_detect_building must delegate to detect_edificio (single source of truth)."""

    def test_edificio_keyword(self):
        assert _detect_building("presupuesto para edificio torres") is True

    def test_departamento_keyword(self):
        assert _detect_building("obra con 20 departamentos") is True

    def test_torre_keyword(self):
        assert _detect_building("torre central") is True

    def test_constructora_keyword(self):
        assert _detect_building("constructora del sur") is True

    def test_obra_nueva_keyword(self):
        assert _detect_building("esto es obra nueva") is True

    def test_consorcio_keyword(self):
        assert _detect_building("consorcio propietarios") is True

    def test_no_match(self):
        assert _detect_building("mesada cocina silestone 2m") is False

    def test_case_insensitive(self):
        assert _detect_building("EDIFICIO CENTRAL") is True

    def test_consistency_with_edificio_parser(self):
        """_detect_building must produce same result as detect_edificio for message-only."""
        from app.modules.quote_engine.edificio_parser import detect_edificio

        test_cases = [
            "presupuesto para edificio",
            "mesada cocina silestone",
            "departamentos torre norte",
            "obra nueva constructora",
        ]
        for msg in test_cases:
            agent_result = _detect_building(msg)
            parser_result = detect_edificio(msg, [])["is_edificio"]
            assert agent_result == parser_result, (
                f"Inconsistency for '{msg}': _detect_building={agent_result}, detect_edificio={parser_result}"
            )
