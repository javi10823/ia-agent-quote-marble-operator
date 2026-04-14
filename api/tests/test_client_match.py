"""Tests for fuzzy client-name matching."""
from __future__ import annotations

import pytest

from app.modules.agent.tools.client_match import (
    are_fuzzy_same_client,
    client_core_tokens,
    group_quotes_by_client,
    normalize_client_name,
)


# ── normalize ────────────────────────────────────────────────────────────

def test_normalize_lowercases_and_strips_accents():
    assert normalize_client_name("Estudio MUÑGE") == "estudio munge"
    assert normalize_client_name("  María  Pérez  ") == "maria perez"


def test_normalize_empty():
    assert normalize_client_name(None) == ""
    assert normalize_client_name("") == ""
    assert normalize_client_name("   ") == ""


# ── core tokens ──────────────────────────────────────────────────────────

def test_core_tokens_strips_professional_prefixes():
    assert client_core_tokens("Estudio Munge") == frozenset({"munge"})
    assert client_core_tokens("Arq. Pérez") == frozenset({"perez"})


def test_core_tokens_strips_legal_forms():
    assert client_core_tokens("Munge SA") == frozenset({"munge"})
    assert client_core_tokens("Constructora SRL") == frozenset({"constructora"})


def test_core_tokens_drops_connectors_and_short_tokens():
    assert client_core_tokens("Juan y María de la Nada") == frozenset(
        {"juan", "maria", "nada"}
    )


def test_core_tokens_drops_digits_and_punctuation():
    assert client_core_tokens("Estudio 72 — Ventus") == frozenset({"ventus"})


# ── fuzzy same client ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "a,b",
    [
        ("Estudio Munge", "Munge"),
        ("Arq. Munge", "Estudio Munge"),
        ("MUNGE", "munge"),
        ("Juan Pérez", "Sr. Pérez"),
        ("Estudio 72 Fideicomiso Ventus", "Fideicomiso Ventus"),
        ("Estudio Scalone", "Arq Scalone"),
    ],
)
def test_fuzzy_same_positive(a, b):
    assert are_fuzzy_same_client(a, b) is True


@pytest.mark.parametrize(
    "a,b",
    [
        ("Juan Pérez", "María González"),
        ("Estudio Munge", "Estudio Ventus"),
        ("Constructora SRL", "Inmobiliaria SA"),
        ("", "Estudio Munge"),
    ],
)
def test_fuzzy_same_negative(a, b):
    assert are_fuzzy_same_client(a, b) is False


def test_fuzzy_same_short_token_does_not_bridge():
    """Tokens shorter than 4 chars should not be enough to claim same client."""
    # "Ana" is len 3 — match threshold is 4, so:
    assert are_fuzzy_same_client("Ana Pérez", "Ana Suárez") is False


def test_fuzzy_same_both_none_is_true():
    """Edge: two quotes without any client name → treat as same (operator
    can always unify them later)."""
    assert are_fuzzy_same_client(None, None) is True


# ── grouping ─────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, client_name):
        self.client_name = client_name


def test_group_quotes_collapses_variants():
    qs = [
        _Q("Estudio Munge"),
        _Q("Munge"),
        _Q("Arq. Munge"),
        _Q("Juan Pérez"),
        _Q("Sr. Pérez"),
        _Q("Estudio Ventus"),
    ]
    groups = group_quotes_by_client(qs)
    # Expect 3 groups: Munge (3), Pérez (2), Ventus (1)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2, 3]


def test_group_quotes_empty():
    assert group_quotes_by_client([]) == []
