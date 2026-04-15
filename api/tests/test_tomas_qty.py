"""Tests for `tomas_qty` — override explícito del operador para Agujero
de toma corriente (PR #7 — caso DINALE 14/04/2026).

Antes del fix: brief decía "Agujero de toma × 1 unidad" pero el
calculator solo detectaba el ítem por heurística de zócalo alto o
revestimiento. Si ninguna aplicaba, el ítem se dropeaba aunque el
operador lo pidiera explícito.
"""
from __future__ import annotations

import re

import pytest

from app.modules.quote_engine.calculator import calculate_quote


# ── Regex mirror (también vive en agent.py) ─────────────────────────

_TOMAS_PATTERNS = [
    r'agujero\s+(?:de\s+)?toma(?:s)?\s*(?:de\s+corriente)?[^\n]{0,30}?[×x]\s*(\d{1,2})',
    r'agujero\s+(?:de\s+)?toma(?:s)?\s*(?:de\s+corriente)?[^\n]{0,30}?(\d{1,2})\s+unidad',
    r'(\d{1,2})\s+agujero(?:s)?\s+(?:de\s+)?toma',
]


def _detect_tomas(text: str) -> int | None:
    for pat in _TOMAS_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                qty = int(m.group(1))
                if 1 <= qty <= 50:
                    return qty
            except ValueError:
                continue
    return None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Agujero de toma × 1", 1),
        ("Agujero de toma × 1 unidad", 1),
        ("Agujero de toma x 2 unidades", 2),
        ("Agujero toma corriente × 4", 4),
        ("3 agujeros de toma", 3),
        ("Agujero de toma de corriente × 2", 2),
    ],
)
def test_tomas_regex_positive(text, expected):
    assert _detect_tomas(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "pileta × 3", "agujero anafe × 1", "toma de medidas en obra"],
)
def test_tomas_regex_negative(text):
    assert _detect_tomas(text) is None


class TestTomasQtyOverride:
    """Override explícito propaga al MO del presupuesto."""

    def test_tomas_qty_creates_mo_line(self):
        result = calculate_quote({
            "client_name": "DINALE",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 31.37},
            ],
            "localidad": "rosario",
            "plazo": "4 meses",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "tomas_qty": 1,
        })
        assert result.get("ok"), result
        toma = [m for m in result["mo_items"] if "toma" in m["description"].lower() and "flete" not in m["description"].lower()]
        assert len(toma) == 1, f"Expected 1 Agujero toma line, got: {[m['description'] for m in result['mo_items']]}"
        assert toma[0]["quantity"] == 1

    def test_tomas_qty_greater_than_one(self):
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 20}],
            "localidad": "rosario",
            "plazo": "30 dias",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "tomas_qty": 3,
        })
        toma = next(m for m in result["mo_items"] if m["description"] == "Agujero toma corriente")
        assert toma["quantity"] == 3
        # total ≈ unit_price × 3 (±1 rounding por ÷1.05 edificio)
        assert abs(toma["total"] - toma["unit_price"] * 3) <= 2

    def test_no_tomas_qty_preserves_auto_detect(self):
        """Sin tomas_qty ni zócalo alto/revestimiento → no hay toma."""
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.60}],
            "localidad": "rosario",
            "plazo": "30 dias",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
        })
        toma = [m for m in result["mo_items"] if "toma" in m["description"].lower() and "flete" not in m["description"].lower()]
        assert len(toma) == 0
