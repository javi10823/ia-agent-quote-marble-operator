"""Tests del adapter text-brief → card editable (mismo shape que dual_read).

`parsed_pieces_to_card()` transforma el output crudo del parser a la shape
que espera el frontend `DualReadResult.tsx`. `parse_brief_to_card()` es el
entry-point async usado por `stream_chat` cuando no hay archivos adjuntos.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.quote_engine.text_parser import (
    parsed_pieces_to_card,
    parse_brief_to_card,
)


# ── Adapter: parsed dict → card JSON ──────────────────────────────────────────

class TestParsedPiecesToCard:
    def test_simple_recta(self):
        parsed = {
            "pieces": [
                {"description": "Mesada cocina", "largo": 2.40, "prof": 0.60},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        assert card is not None
        assert card["source"] == "TEXT"
        assert card["view_type"] == "texto"
        assert card["_retry"] is True
        assert card["requires_human_review"] is False
        assert len(card["sectores"]) == 1
        sector = card["sectores"][0]
        assert sector["_manual"] is True
        assert len(sector["tramos"]) == 1
        tramo = sector["tramos"][0]
        assert tramo["_manual"] is True
        assert tramo["largo_m"]["valor"] == 2.40
        assert tramo["ancho_m"]["valor"] == 0.60
        # m2 re-calculado (el adapter no confía en el parser)
        assert tramo["m2"]["valor"] == round(2.40 * 0.60, 2)
        # opus/sonnet null — fuente única, no hay reconciliación
        assert tramo["largo_m"]["opus"] is None
        assert tramo["largo_m"]["sonnet"] is None
        # status semánticamente separado del source
        assert tramo["largo_m"]["status"] == "CONFIRMADO"

    def test_en_l_dos_tramos(self):
        parsed = {
            "pieces": [
                {"description": "Mesada L tramo 1", "largo": 2.40, "prof": 0.60},
                {"description": "Mesada L tramo 2", "largo": 1.80, "prof": 0.60},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramos = card["sectores"][0]["tramos"]
        assert len(tramos) == 2
        assert tramos[0]["largo_m"]["valor"] == 2.40
        assert tramos[1]["largo_m"]["valor"] == 1.80
        expected_total = round(2.40 * 0.60 + 1.80 * 0.60, 2)
        assert card["sectores"][0]["m2_total"]["valor"] == expected_total

    def test_mesada_con_zocalos(self):
        parsed = {
            "pieces": [
                {"description": "Mesada", "largo": 2.40, "prof": 0.60},
                {"description": "Zócalo trasero", "largo": 2.40, "alto": 0.05},
                {"description": "Zócalo lateral", "largo": 0.60, "alto": 0.05},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        # Zócalos van asignados al último tramo previo
        assert len(tramo["zocalos"]) == 2
        # m2 total incluye mesada + zócalos
        expected_total = round(2.40 * 0.60 + 2.40 * 0.05 + 0.60 * 0.05, 2)
        assert card["sectores"][0]["m2_total"]["valor"] == expected_total

    def test_m2_recalculated_ignores_parser_value(self):
        """Si el parser devuelve m2 inconsistente (bug conocido), el adapter
        lo pisa con largo × ancho. Seguridad GPT #9."""
        parsed = {
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6, "m2": 999.0},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        assert tramo["m2"]["valor"] == round(2.0 * 0.6, 2)  # 1.2, no 999

    def test_no_pieces_returns_none(self):
        assert parsed_pieces_to_card({"pieces": []}) is None
        assert parsed_pieces_to_card({}) is None
        assert parsed_pieces_to_card(None) is None

    def test_zero_largo_skipped(self):
        parsed = {"pieces": [{"description": "mal", "largo": 0, "prof": 0.6}]}
        assert parsed_pieces_to_card(parsed) is None

    def test_non_numeric_largo_skipped(self):
        parsed = {"pieces": [{"description": "mal", "largo": "dos metros", "prof": 0.6}]}
        assert parsed_pieces_to_card(parsed) is None

    def test_only_zocalos_no_mesada_returns_none(self):
        """Sin mesada pero con zócalos → None (no hay tramo donde colgarlos)."""
        parsed = {"pieces": [{"description": "Zócalo", "largo": 2.0, "alto": 0.05}]}
        assert parsed_pieces_to_card(parsed) is None

    def test_pending_zocalos_attached_to_first_tramo_when_order_reversed(self):
        """Si zócalo aparece antes de mesada, se cuelga del primer tramo luego."""
        parsed = {
            "pieces": [
                {"description": "Zócalo", "largo": 2.0, "alto": 0.05},
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        assert len(tramo["zocalos"]) == 1
        assert tramo["zocalos"][0]["ml"] == 2.0


# ── Entry-point async ─────────────────────────────────────────────────────────

class TestParseBriefToCard:
    @pytest.mark.asyncio
    async def test_returns_card_when_parser_succeeds(self):
        parsed = {"pieces": [{"description": "Mesada", "largo": 2.4, "prof": 0.6}]}
        with patch(
            "app.modules.quote_engine.text_parser.parse_measurements",
            new=AsyncMock(return_value=parsed),
        ):
            card = await parse_brief_to_card(
                "mesada 2.40 x 0.60 silestone cliente Juan", "", ""
            )
        assert card is not None
        assert card["source"] == "TEXT"

    @pytest.mark.asyncio
    async def test_returns_none_when_parser_returns_none(self):
        with patch(
            "app.modules.quote_engine.text_parser.parse_measurements",
            new=AsyncMock(return_value=None),
        ):
            card = await parse_brief_to_card("cliente Juan material silestone", "", "")
        assert card is None
