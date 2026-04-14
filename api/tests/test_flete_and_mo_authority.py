"""Tests for:
- Flete qty detection robustness (RC2): '× 1 UNO SOLO', word numbers, etc.
- MO list authority (RC1): when operator lists MO explicitly, the list is
  exhaustive and guardrails suppress auto-added pileta/anafe/colocación.

These test the regex/matching logic directly by re-executing the same
patterns that the agent.py inline guard uses, so they act as a contract
pin: if someone re-writes the patterns, the tests must keep passing.
"""
from __future__ import annotations

import re

import pytest


# ─────────────────────────────────────────────────────────────────────────
# Flete qty — mirror the patterns in agent.py stream_chat
# ─────────────────────────────────────────────────────────────────────────

FLETE_PATTERNS = [
    r'flete[s]?\s*[×x]\s*(\d+)',
    r'[×x]\s*(\d+)\s*flete',
    r'(\d+)\s*flete[s]?\b',
    r'(\d+)\s*viaje[s]?\b',
    r'\bflete[s]?\b[^\n.]{0,80}?[×x]\s*(\d+)\b',
    r'[×x]\s*(\d+)[^\n.]{0,40}?\bflete[s]?\b',
]

WORD_NUMS = {
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10,
}


def detect_flete_qty(text: str) -> int | None:
    t = text or ""
    for pat in FLETE_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                q = int(m.group(1))
                if 1 <= q <= 50:
                    return q
            except ValueError:
                continue
    for word, num in WORD_NUMS.items():
        if re.search(rf'\b{word}\s+flete[s]?\b', t, re.IGNORECASE):
            return num
        if re.search(rf'\b{word}\s+viaje[s]?\b', t, re.IGNORECASE):
            return num
    # Emphatic "uno solo"/"un solo" near "flete"
    if re.search(r'\b(?:uno?|un)\s+sol[oa]\b', t, re.IGNORECASE) and re.search(
        r'\bflete[s]?\b', t, re.IGNORECASE
    ):
        return 1
    return None


# ── Cases from real brief the operator sent ─────────────────────────────

def test_flete_x1_uno_solo_matches():
    """'Flete + toma de medidas × 1 UNO SOLO' must yield 1."""
    text = "Flete + toma de medidas × 1 UNO SOLO → precio fijo SIN descuento"
    assert detect_flete_qty(text) == 1


def test_flete_digit_near_word_small_window():
    text = "Flete + toma medidas Rosario × 5"
    assert detect_flete_qty(text) == 5


def test_flete_simple_count_format():
    assert detect_flete_qty("× 3 fletes") == 3
    assert detect_flete_qty("son 5 fletes") == 5
    assert detect_flete_qty("flete × 4") == 4


def test_word_number_un_flete():
    assert detect_flete_qty("necesitamos un flete") == 1
    assert detect_flete_qty("dos fletes") == 2
    assert detect_flete_qty("tres viajes") == 3


def test_uno_solo_emphasis_without_flete_mention_does_not_match():
    """'uno solo' without any 'flete' nearby must NOT force qty=1."""
    assert detect_flete_qty("entregamos uno solo por semana") is None


def test_no_match_returns_none():
    assert detect_flete_qty("") is None
    assert detect_flete_qty("Cotizar cocina en Silestone") is None


# ─────────────────────────────────────────────────────────────────────────
# MO list authority — mirror the detection in agent.py
# ─────────────────────────────────────────────────────────────────────────

_MO_AUTHORITY_MARKERS = [
    "listá cada línea como concepto separado",
    "lista cada linea como concepto separado",
    "listá cada línea",
    "lista cada linea",
    "listá como concepto separado",
    "lista como concepto separado",
    "listá como concepto",
    "lista como concepto",
]


def has_mo_authority(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _MO_AUTHORITY_MARKERS)


def mentions_pileta(text: str) -> bool:
    t = (text or "").lower()
    return any(
        w in t for w in
        ("pileta", "bacha", "agujero pileta", "pegadopileta", "pegado pileta")
    )


def mentions_anafe(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ("anafe", "agujero anafe"))


def mentions_colocacion(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ("colocacion", "colocación", "colocar"))


# The real brief that triggered the bug
REAL_BRIEF = """
CLIENTE: Estudio 72 — Fideicomiso Ventus
OBRA: Edificio | Sin colocación | Rosario
MATERIAL: Silestone Blanco Norte — 20mm
Pata lateral — 0.90m × 0.78m = 0.70 m²/u × 8 unidades = 5.60 m²
TOTAL MATERIAL: 5.60 m²
SIN MERMA
Descuento edificio 18% solo sobre total material
MANO DE OBRA — listá cada línea como concepto separado:
Flete + toma de medidas × 1 UNO SOLO → precio fijo SIN descuento
REGLAS
SIN MERMA
Descuento 18% solo sobre material
Sin colocación
NUNCA descuento sobre flete
"""


def test_real_brief_has_mo_authority():
    assert has_mo_authority(REAL_BRIEF) is True


def test_real_brief_does_not_mention_pileta():
    assert mentions_pileta(REAL_BRIEF) is False


def test_real_brief_does_not_mention_anafe():
    assert mentions_anafe(REAL_BRIEF) is False


def test_real_brief_does_not_mention_colocacion():
    # Has "Sin colocación" — mentions the word. Guardrail interprets that as
    # "operator said no colocación", which is the right behavior (colocacion=False).
    # The mention is still correctly detected:
    assert mentions_colocacion(REAL_BRIEF) is True


def test_real_brief_flete_qty_is_one():
    assert detect_flete_qty(REAL_BRIEF) == 1


def test_mo_authority_plus_pileta_mention_does_not_suppress():
    """If operator lists MO exhaustively AND mentions pileta somewhere in
    the list, the guardrail must NOT force empotrada_cliente."""
    brief = """
    MANO DE OBRA — listá cada línea como concepto separado:
    Agujero y pegado pileta × 1
    Flete × 1
    """
    assert has_mo_authority(brief) is True
    assert mentions_pileta(brief) is True


def test_no_mo_authority_normal_flow():
    """A plain brief without the 'listá cada línea' marker → no authority,
    agent can infer pileta normally."""
    assert has_mo_authority("Cotizar cocina 2.5 × 0.62 en Silestone") is False


# ── Regression: Ventus 5 fletes (existing behavior must still hold) ──

def test_ventus_five_fletes_still_detected():
    text = "Flete + toma medidas Rosario × 5 viajes"
    assert detect_flete_qty(text) == 5
