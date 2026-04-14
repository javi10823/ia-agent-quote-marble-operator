"""Tests for discount_pct / mo_discount_pct auto-parsing from operator brief.

Mirrors the regex logic used inline in agent.stream_chat — acts as a contract
pin. Real-world triggers covered:
  - "Descuento 18% sobre material" (the Fideicomiso Ventus case that lost
    its discount because m² was below the auto-threshold)
  - "descuento edificio 18%"
  - "5% sobre MO", "descuento 5% sobre mano de obra"
"""
from __future__ import annotations

import re

import pytest


# ─── Mirror of agent.py patterns ────────────────────────────────────────

_MAT_PATTERNS = [
    r'descuento[^\n.]{0,30}?(\d{1,2})\s*%[^\n.]{0,30}?(?:sobre\s+)?material',
    r'(\d{1,2})\s*%[^\n.]{0,30}?(?:de\s+)?descuento[^\n.]{0,30}?(?:sobre\s+)?material',
    r'(\d{1,2})\s*%\s+sobre\s+(?:total\s+)?material',
    r'descuento\s+edificio\s+(\d{1,2})\s*%',
]

_MO_PATTERNS = [
    r'(\d{1,2})\s*%\s+sobre\s+(?:la\s+)?(?:mo\b|mano\s+de\s+obra)',
    r'descuento[^\n.]{0,30}?(\d{1,2})\s*%[^\n.]{0,30}?(?:mo\b|mano\s+de\s+obra)',
]


def detect_material_discount(text: str) -> int | None:
    t = text or ""
    for pat in _MAT_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                pct = int(m.group(1))
                if 1 <= pct <= 50:
                    return pct
            except ValueError:
                continue
    return None


def detect_mo_discount(text: str) -> int | None:
    t = text or ""
    for pat in _MO_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                pct = int(m.group(1))
                if 1 <= pct <= 50:
                    return pct
            except ValueError:
                continue
    return None


# ── Material discount ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Descuento 18% sobre material", 18),
        ("descuento 18% sobre material", 18),
        ("Descuento edificio 18%", 18),
        ("descuento edificio 18% solo sobre total material", 18),
        ("18% de descuento sobre material", 18),
        ("aplicar 10% sobre material", 10),
        ("5% sobre total material", 5),
        ("descuento del 20% sobre material importado", 20),
    ],
)
def test_material_discount_positive(text, expected):
    assert detect_material_discount(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Cotizar cocina 2.5 × 0.62 en Silestone",
        "descuento 5% sobre MO",  # MO only, not material
        "sin descuento",
        "100% terminado",  # outside 1-50 range
    ],
)
def test_material_discount_negative(text):
    assert detect_material_discount(text) is None


def test_material_discount_real_ventus_patas_brief():
    """The exact brief that failed in prod — 5.6 m² patas + 18% edificio."""
    brief = """
    CLIENTE: Estudio 72 — Fideicomiso Ventus
    MATERIAL: Silestone Blanco Norte
    Descuento edificio 18% solo sobre total material
    SIN MERMA
    Descuento 18% solo sobre material
    """
    assert detect_material_discount(brief) == 18


def test_material_discount_out_of_range():
    # 75% should be rejected (typos / noise protection)
    assert detect_material_discount("descuento 75% sobre material") is None
    # But 50 is the upper bound (included)
    assert detect_material_discount("descuento 50% sobre material") == 50


# ── MO discount ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("5% sobre MO", 5),
        ("5% sobre la MO", 5),
        ("5% sobre mano de obra", 5),
        ("descuento 10% sobre mano de obra", 10),
        ("aplicar 8% sobre la mano de obra", 8),
    ],
)
def test_mo_discount_positive(text, expected):
    assert detect_mo_discount(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "5% sobre material",  # material, not MO
        "descuento general 5%",  # no MO mention
    ],
)
def test_mo_discount_negative(text):
    assert detect_mo_discount(text) is None


def test_mo_and_material_detected_separately():
    """A brief can carry both — each detector picks its own."""
    brief = (
        "Descuento edificio 18% solo sobre material. "
        "Además 5% sobre MO excluye flete."
    )
    assert detect_material_discount(brief) == 18
    assert detect_mo_discount(brief) == 5


def test_no_false_positive_percentage_in_different_context():
    """Percentages unrelated to discount must not match."""
    assert detect_material_discount("IVA 21% sobre el total") is None
    assert detect_material_discount("el material tiene 3% de desperdicio") is None
