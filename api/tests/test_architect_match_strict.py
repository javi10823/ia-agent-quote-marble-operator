"""Strict architect matching · sprint-4/architect-match-strict.

Cubre el algoritmo two-pass (exact + match_tokens word-boundary) sobre los
8 architects oficiales de architects.json. Reverse substring fue eliminado
para cerrar bug B (clientes con nombre que contenía un architect recibían
auto-descuento).

Decisión Javi 16.06.2026: match_tokens conservador desde día 0 · expandible
vía JSON sin merge si la realidad operativa lo pide.
"""
import os

# ── Fix environment before app imports ──
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

import pytest

from app.modules.agent.tools.catalog_tool import (
    _matches_token_word_boundary,
    _normalize_architect_text,
    check_architect,
)


# ═══════════════════════════════════════════════════════
# Helpers — pure functions
# ═══════════════════════════════════════════════════════

class TestNormalize:
    def test_lowercase(self):
        assert _normalize_architect_text("ALMA Estudio") == "alma estudio"

    def test_drops_accents(self):
        assert _normalize_architect_text("María Pérez") == "maria perez"

    def test_collapses_whitespace(self):
        assert _normalize_architect_text("  Alma   Estudio  ") == "alma estudio"

    def test_empty_returns_empty(self):
        assert _normalize_architect_text("") == ""
        assert _normalize_architect_text("   ") == ""


class TestWordBoundary:
    def test_match_at_start(self):
        assert _matches_token_word_boundary("munge films", "munge")

    def test_match_at_end(self):
        assert _matches_token_word_boundary("estudio munge", "munge")

    def test_match_with_hyphen(self):
        assert _matches_token_word_boundary("estudio cueto-heredia", "cueto-heredia")

    def test_no_match_inside_word(self):
        # "mungetar" must NOT match token "munge" (no word boundary after)
        assert not _matches_token_word_boundary("mungetar films", "munge")

    def test_no_match_when_missing(self):
        assert not _matches_token_word_boundary("juan cueto", "cueto-heredia")

    def test_empty_inputs(self):
        assert not _matches_token_word_boundary("", "munge")
        assert not _matches_token_word_boundary("munge", "")


# ═══════════════════════════════════════════════════════
# Positivos — los 8 architects con al menos un token cada uno
# ═══════════════════════════════════════════════════════

class TestArchitectsPositive:
    @pytest.mark.parametrize("client_name,expected_name", [
        # ARQ. NADIA → ["arq. nadia", "arq nadia"]
        ("ARQ. NADIA", "ARQ. NADIA"),
        ("arq. nadia", "ARQ. NADIA"),
        ("Arq Nadia", "ARQ. NADIA"),
        ("ARQ. NADIA Pérez", "ARQ. NADIA"),  # token + nombre extra
        # ARQ. PAMELA FURIGO → ["pamela furigo", "furigo arquitectura", "arq. pamela furigo"]
        ("Pamela Furigo", "ARQ. PAMELA FURIGO"),
        ("Furigo Arquitectura", "ARQ. PAMELA FURIGO"),
        ("ARQ. PAMELA FURIGO", "ARQ. PAMELA FURIGO"),
        # ALMA ESTUDIO → ["alma estudio"]
        ("ALMA ESTUDIO", "ALMA ESTUDIO"),
        ("alma estudio", "ALMA ESTUDIO"),
        # ARQ. RAFAEL ARAYA → ["rafael araya", "arq. rafael araya"]
        ("Rafael Araya", "ARQ. RAFAEL ARAYA"),
        ("ARQ. RAFAEL ARAYA", "ARQ. RAFAEL ARAYA"),
        # LUCIANA PACOR → ["luciana pacor"]
        ("Luciana Pacor", "LUCIANA PACOR"),
        # SCALONA ARQUITECTURA → ["scalona arquitectura"] (conservador, sin "scalona" solo)
        ("Scalona Arquitectura", "SCALONA ARQUITECTURA"),
        ("SCALONA ARQUITECTURA", "SCALONA ARQUITECTURA"),
        # CUETO-HEREDIA ARQUITECTAS → ["cueto-heredia", "cueto heredia", "cueto-heredia arquitectas"]
        ("Estudio Cueto-Heredia", "CUETO-HEREDIA ARQUITECTAS"),
        ("Cueto Heredia", "CUETO-HEREDIA ARQUITECTAS"),
        ("CUETO-HEREDIA ARQUITECTAS", "CUETO-HEREDIA ARQUITECTAS"),
        # ESTUDIO MUNGE → ["estudio munge"] (conservador, sin "munge" solo)
        ("Estudio Munge", "ESTUDIO MUNGE"),
        ("ESTUDIO MUNGE", "ESTUDIO MUNGE"),
    ])
    def test_architect_matches(self, client_name, expected_name):
        result = check_architect(client_name)
        assert result["found"] is True, f"'{client_name}' debería matchear pero no matcheó"
        assert result["name"] == expected_name, (
            f"'{client_name}' matcheó '{result['name']}' en lugar de '{expected_name}'"
        )
        assert result.get("discount") is True


# ═══════════════════════════════════════════════════════
# Negativos — Bug B closed · clientes que NO deben matchear
# ═══════════════════════════════════════════════════════

class TestArchitectsNegative:
    @pytest.mark.parametrize("client_name", [
        # Casos explícitos del plan Javi
        "Juan Cueto",            # particular con apellido coincidente
        "Pacor",                 # particular con apellido coincidente
        "Munge SRL",             # empresa NO architect con palabra coincidente
        # Otros casos del bug class (reverse substring eliminado)
        "Nadia",                 # solo nombre, sin "arq."
        "Nadia Pérez",           # particular con nombre Nadia
        "Furigo",                # apellido solo, sin "pamela"
        "Araya",                 # apellido solo, sin "rafael"
        "Rafael",                # nombre solo, sin "araya"
        "Scalona",               # apellido solo (decisión conservadora)
        "Munge",                 # apellido solo (decisión conservadora)
        "Cueto",                 # apellido fragmento
        # Variantes que NO deben matchear
        "Alma",                  # primer término de ALMA ESTUDIO, sin "estudio"
        "Estudio",               # palabra genérica
        "Arquitectura",          # palabra genérica
        "Estudio 72",            # caso real (regresión documentada en comentario pre-refactor)
        # Empresas NO architects con nombre similar
        "Cueto SRL",
        "Pacor SA",
        "Araya Construcciones",
        # Random
        "ZZZNONEXISTENT999",
        "Cliente desconocido",
    ])
    def test_no_false_positive(self, client_name):
        result = check_architect(client_name)
        assert result["found"] is False, (
            f"'{client_name}' NO debería matchear pero matcheó: {result.get('name')}"
        )


# ═══════════════════════════════════════════════════════
# Edge cases · empty / whitespace / typos
# ═══════════════════════════════════════════════════════

class TestArchitectsEdge:
    def test_empty_string(self):
        result = check_architect("")
        assert result["found"] is False

    def test_only_whitespace(self):
        result = check_architect("   \t  \n  ")
        assert result["found"] is False

    def test_excess_internal_whitespace(self):
        # Triple-space en el medio se normaliza a single space.
        result = check_architect("ALMA    ESTUDIO")
        assert result["found"] is True
        assert result["name"] == "ALMA ESTUDIO"

    def test_typo_does_not_match(self):
        # Comportamiento documentado: typos NO matchean (algoritmo estricto).
        # Si el operador comete typo, debe corregir el nombre.
        result = check_architect("Estdio Munge")  # falta "u"
        assert result["found"] is False

    def test_accent_insensitive(self):
        # NFKD normalization → "María" matchea contra tokens sin acentos
        # (architects.json no tiene acentos en match_tokens actualmente).
        result = check_architect("Almá Estudio")  # acento espurio
        assert result["found"] is True
        assert result["name"] == "ALMA ESTUDIO"


# ═══════════════════════════════════════════════════════
# Ambigüedad · multiple architects matchean → no auto-discount
# ═══════════════════════════════════════════════════════

class TestArchitectsAmbiguous:
    def test_no_ambiguity_with_current_tokens(self):
        """Con el mapeo conservador actual, los match_tokens están diseñados
        para no colisionar entre architects. Si en el futuro se agrega un
        token que dispare ambigüedad, este test no se rompe pero se queda
        como guard contra regresión silenciosa."""
        # Sanity check sobre los 8 architects actuales: ninguno matchea con
        # ningún token de otro architect.
        from app.modules.agent.tools.catalog_tool import _load_catalog
        items = _load_catalog("architects")
        assert len(items) == 8, f"Esperado 8 architects en architects.json, hay {len(items)}"
        for item in items:
            for token in (item.get("match_tokens") or []):
                result = check_architect(token)
                # Debe matchear UN architect (no ambiguous, no zero)
                assert result["found"] is True, (
                    f"Token '{token}' del architect '{item['name']}' no matchea ningún architect"
                )
                assert result.get("ambiguous") is not True, (
                    f"Token '{token}' del architect '{item['name']}' matchea ambiguamente: "
                    f"{result.get('candidates')}"
                )
                assert result["name"] == item["name"], (
                    f"Token '{token}' del architect '{item['name']}' matcheó "
                    f"'{result['name']}' (cross-match indeseado)"
                )
