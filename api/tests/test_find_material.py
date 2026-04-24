"""Tests para PR #396 — family-gated fuzzy matching en `_find_material`.

Bug raíz atacado: antes el fuzzy corría sobre TODOS los catálogos
juntos. "Puraprima Metro Grey" matcheaba con "GRANITO SILVER GREY
LETHER - 2 ESP" por la palabra compartida "Grey". Son familias
ontológicamente distintas — sinterizado vs piedra natural difieren en
merma, colocación, precio base.

Ahora: detector de familia + scope intra-familia + cross-catalog con
cutoff más estricto cuando no se detecta familia. No hay fallback
cross-family silencioso.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import (
    _find_material,
    _detect_family,
    _normalize_input_string,
    _strip_family_keyword,
    _FAMILY_CATALOGS,
)


# ═══════════════════════════════════════════════════════════════════════
# Normalización
# ═══════════════════════════════════════════════════════════════════════


class TestNormalize:
    def test_lowercase(self):
        assert _normalize_input_string("GRANITO NEGRO BRASIL") == "granito negro brasil"

    def test_strips_accents(self):
        assert _normalize_input_string("Mármol Carrara") == "marmol carrara"

    def test_collapses_spaces(self):
        assert _normalize_input_string("Granito   Negro    Brasil") == "granito negro brasil"

    def test_replaces_separators(self):
        assert _normalize_input_string("Dekton-Vigil/12mm") == "dekton vigil 12mm"
        assert _normalize_input_string("Silestone — Blanco") == "silestone   blanco".replace("   ", " ")

    def test_empty_input(self):
        assert _normalize_input_string("") == ""
        assert _normalize_input_string(None) == ""


# ═══════════════════════════════════════════════════════════════════════
# Detector de familia
# ═══════════════════════════════════════════════════════════════════════


class TestDetectFamily:
    def test_puraprima_exact(self):
        assert _detect_family("Puraprima Metro Grey") == "puraprima"

    def test_puraprima_separated_spelling(self):
        """'Pura Prima' con espacio también matchea familia puraprima."""
        assert _detect_family("Pura Prima Metro Grey") == "puraprima"

    def test_puraprima_typo_via_fuzzy(self):
        """Typo 'Puraprma' (falta 'i') se detecta por fuzzy."""
        assert _detect_family("Puraprma Metro Grey") == "puraprima"

    def test_purastone_vs_puraprima_resolution(self):
        """'Purastone Prima' → familia puraprima (items PURASTONE PRIMA
        viven en materials-puraprima.json). 'Purastone' solo → familia
        purastone."""
        assert _detect_family("Purastone Prima Metro Grey") == "puraprima"
        assert _detect_family("Purastone Blanco Cana") == "purastone"

    def test_silestone(self):
        assert _detect_family("Silestone Blanco Norte") == "silestone"

    def test_dekton(self):
        assert _detect_family("Dekton Vigil") == "dekton"

    def test_neolith(self):
        assert _detect_family("Neolith Abu Dhabi") == "neolith"

    def test_granito(self):
        assert _detect_family("Granito Negro Brasil") == "granito"

    def test_marmol_with_accent(self):
        """Mármol con tilde es equivalente a marmol post-normalize."""
        assert _detect_family("Mármol Carrara") == "marmol"

    def test_marmol_without_accent(self):
        assert _detect_family("Marmol Carrara") == "marmol"

    def test_laminatto_variants(self):
        assert _detect_family("Laminatto Cristal") == "laminatto"
        assert _detect_family("Laminato cristal") == "laminatto"

    def test_no_family_keyword(self):
        """Sin keyword de familia reconocible → None → cae a
        cross-catalog con cutoff estricto."""
        assert _detect_family("Metro Grey") is None
        assert _detect_family("Negro Brasil") is None

    def test_empty_input_returns_none(self):
        assert _detect_family("") is None
        assert _detect_family(None) is None


# ═══════════════════════════════════════════════════════════════════════
# Strip keyword de familia
# ═══════════════════════════════════════════════════════════════════════


class TestStripFamilyKeyword:
    def test_strips_puraprima(self):
        assert _strip_family_keyword("Puraprima Metro Grey", "puraprima") == "metro grey"

    def test_strips_pura_prima_with_space(self):
        assert _strip_family_keyword("Pura Prima Metro Grey", "puraprima") == "metro grey"

    def test_strips_purastone_prima_longer_wins(self):
        """'purastone prima' es más largo que 'puraprima' — los keywords
        se strippean por orden decreciente de largo."""
        out = _strip_family_keyword("PURASTONE PRIMA METRO GREY - 12MM", "puraprima")
        assert "purastone" not in out
        assert "prima" not in out
        assert "metro grey" in out

    def test_strips_typo_via_fuzzy(self):
        """Typo 'puraprma' tokenizado se remueve por fuzzy (ratio ≥ 85)."""
        assert _strip_family_keyword("Puraprma Metro Grey", "puraprima") == "metro grey"

    def test_does_not_strip_other_family(self):
        """Con family=granito no se remueve 'puraprima' del input."""
        out = _strip_family_keyword("puraprima metro grey", "granito")
        assert "puraprima" in out


# ═══════════════════════════════════════════════════════════════════════
# _find_material — casos principales (el punto del PR)
# ═══════════════════════════════════════════════════════════════════════


class TestFindMaterialFamilyGated:
    """Los cases del scope del PR."""

    def test_puraprima_metro_grey_resolves_to_puragrey(self):
        """Caso Perdomo Fabiana — el bug original.
        Input 'Puraprima Metro Grey' DEBE ir al catálogo puraprima,
        NO a granito."""
        r = _find_material("Puraprima Metro Grey")
        assert r["found"] is True
        assert r["sku"] == "PURAGREY"
        assert r["fuzzy_catalog"] == "puraprima"
        assert r["fuzzy_family"] == "puraprima"
        assert "GRANITO" not in r["name"].upper()

    def test_pura_prima_metro_grey_typo_space(self):
        """'Pura Prima Metro Grey' (separado con espacio) → misma
        familia puraprima. SKU correcto."""
        r = _find_material("Pura Prima Metro Grey")
        assert r["found"] is True
        assert r["sku"] == "PURAGREY"
        assert r["fuzzy_catalog"] == "puraprima"

    def test_puraprma_typo_still_detects_family_and_matches(self):
        """Typo 'Puraprma' (falta 'i') → fuzzy-detect familia puraprima
        → match con PURAGREY. Este es el test crítico: antes caía a
        cross-catalog y matcheaba GRANITO."""
        r = _find_material("Puraprma Metro Grey")
        assert r["found"] is True
        assert r["sku"] == "PURAGREY"
        assert r["fuzzy_catalog"] == "puraprima"

    def test_dekton_vigil_matches_correct_sku(self):
        r = _find_material("Dekton Vigil")
        assert r["found"] is True
        assert "DEKTON" in r["name"].upper()
        assert "VIGIL" in r["name"].upper()

    def test_granito_negro_brasil_matches_granito_catalog(self):
        r = _find_material("Granito Negro Brasil")
        assert r["found"] is True
        assert "NEGRO BRASIL" in r["name"].upper()
        # Granito puede estar en importado o nacional. Clave: no sintético.
        cat = r.get("fuzzy_catalog", "")
        assert cat.startswith("granito")

    def test_silestone_blanco_norte_matches(self):
        r = _find_material("Silestone Blanco Norte")
        assert r["found"] is True
        assert "SILESTONE" in r["name"].upper()
        assert "BLANCO NORTE" in r["name"].upper()

    def test_marmol_carrara_with_accent(self):
        """'Mármol Carrara' con tilde → resuelve a catálogo marmol."""
        r = _find_material("Mármol Carrara")
        assert r["found"] is True
        assert "MARMOL" in r["name"].upper() or "MARMETA" in r["name"].upper() or "CARRARA" in r["name"].upper()
        assert r["fuzzy_catalog"] == "marmol" or r.get("name", "").upper().startswith("MARMOL")


# ═══════════════════════════════════════════════════════════════════════
# No cross-family bleed
# ═══════════════════════════════════════════════════════════════════════


class TestNoCrossFamilyBleed:
    """Ningún input con keyword sintético debe terminar en catálogo
    natural (granito/marmol) ni viceversa. Fuente del bug original."""

    @pytest.mark.parametrize("input_name", [
        "Puraprima Negro Brasil",  # Combinación adversarial.
        "Silestone Negro Brasil",
        "Dekton Negro Brasil",
        "Neolith Negro Brasil",
        "Laminatto Negro Brasil",
    ])
    def test_synthetic_input_never_matches_natural(self, input_name):
        r = _find_material(input_name)
        # Si encuentra → catálogo debe ser sintético, nunca granito/marmol.
        if r.get("found"):
            cat = r.get("fuzzy_catalog", "")
            assert not cat.startswith("granito"), (
                f"'{input_name}' matcheó granito: {r.get('name')!r}"
            )
            assert cat != "marmol", (
                f"'{input_name}' matcheó marmol: {r.get('name')!r}"
            )

    @pytest.mark.parametrize("input_name", [
        "Granito Metro Grey",      # "Grey" está en ambos.
        "Granito Blanco Norte",    # "Blanco Norte" suena silestone.
        "Mármol Aurora",
    ])
    def test_natural_input_never_matches_synthetic(self, input_name):
        r = _find_material(input_name)
        if r.get("found"):
            cat = r.get("fuzzy_catalog", "")
            assert cat not in (
                "puraprima", "purastone", "silestone", "dekton", "neolith", "laminatto"
            ), f"'{input_name}' matcheó sintético: {r.get('name')!r} (cat={cat})"


# ═══════════════════════════════════════════════════════════════════════
# Sin familia → cross-catalog con cutoff estricto
# ═══════════════════════════════════════════════════════════════════════


class TestNoFamilyKeyword:
    def test_no_family_accepts_via_exact_or_strict_fuzzy(self):
        """'Negro Brasil Extra' sin keyword de familia explícito →
        puede resolver por cualquiera de los 3 paths:
          1. Exact match cross-catalog (catalog_lookup directo).
          2. Normalize alias (_NORMALIZE_MAP score=100).
          3. Fuzzy cross-catalog con cutoff 85.
        Si resuelve por fuzzy, el score debe ser ≥ 85 (no bajamos el
        cutoff)."""
        r = _find_material("Negro Brasil Extra")
        if r.get("found"):
            score = r.get("fuzzy_score")
            # None → path 1 (exact sin score). OK.
            # >=85 → path 2 o 3. OK.
            if score is not None:
                assert score >= 85

    def test_generic_fuzzy_returns_suggestions_when_low(self):
        """'Material inexistente xyz' → sin match → suggestions estable."""
        r = _find_material("Material inexistente xyz")
        assert r["found"] is False
        assert "suggestions" in r
        assert isinstance(r["suggestions"], list)


# ═══════════════════════════════════════════════════════════════════════
# Suggestions: shape estable
# ═══════════════════════════════════════════════════════════════════════


class TestSuggestionsShape:
    def test_no_match_returns_structured_suggestions(self):
        r = _find_material("Material inexistente xyz")
        assert r["found"] is False
        sg = r.get("suggestions", [])
        for s in sg:
            assert "sku" in s  # puede ser None
            assert "name" in s and isinstance(s["name"], str)
            assert "score" in s and isinstance(s["score"], int)
            assert "catalog" in s and isinstance(s["catalog"], str)

    def test_unknown_in_family_returns_intra_family_suggestions(self):
        """Input con keyword de familia pero nombre específico ausente
        → suggestions SOLO de esa familia (nunca cross-family)."""
        r = _find_material("Puraprima MaterialInexistenteXYZ")
        # Si encuentra (con low cutoff puede no entrar) → OK. Si no →
        # suggestions deben ser todas de la familia.
        if not r.get("found"):
            sg = r.get("suggestions", [])
            if sg:
                cats = {s["catalog"] for s in sg}
                # Todas las suggestions de puraprima (no cross-family).
                assert cats.issubset({"puraprima"}), (
                    f"suggestions cross-family: {cats}"
                )


# ═══════════════════════════════════════════════════════════════════════
# Metadata en el resultado exitoso
# ═══════════════════════════════════════════════════════════════════════


class TestFuzzyMetadata:
    def test_successful_fuzzy_has_trace_fields(self):
        r = _find_material("Puraprima Metro Grey")
        assert r["found"] is True
        # fuzzy_corrected_from: input original.
        assert r.get("fuzzy_corrected_from") == "Puraprima Metro Grey"
        # fuzzy_score: int.
        assert isinstance(r.get("fuzzy_score"), int)
        assert r["fuzzy_score"] >= 80  # pasó el cutoff intra-familia.
        # fuzzy_catalog: familia corta.
        assert r.get("fuzzy_catalog") == "puraprima"
        # fuzzy_family: la que detectamos.
        assert r.get("fuzzy_family") == "puraprima"

    def test_exact_match_no_fuzzy_fields(self):
        """Match exacto (catalog_lookup directo) NO debería agregar
        fuzzy_* metadata."""
        # Buscar un nombre que exista EXACTO.
        r = _find_material("SILESTONE BLANCO NORTE")
        if r.get("found") and r.get("fuzzy_corrected_from") is None:
            # Exact path: no score/catalog/family.
            assert "fuzzy_score" not in r
            assert "fuzzy_catalog" not in r


# ═══════════════════════════════════════════════════════════════════════
# Guard de familia genérica (preserva comportamiento PR #59)
# ═══════════════════════════════════════════════════════════════════════


class TestAmbiguousFamilyGuard:
    @pytest.mark.parametrize("input_name", [
        "granito", "GRANITO", "Granito",
        "marmol", "Mármol",
        "silestone", "dekton", "neolith",
        "puraprima", "pura prima",
        "laminatto",
    ])
    def test_bare_family_name_is_ambiguous(self, input_name):
        """Input con solo la familia (sin variante específica) → no
        cotizar por default, preguntar al operador."""
        r = _find_material(input_name)
        assert r["found"] is False
        assert r.get("ambiguous_family") is True


# ═══════════════════════════════════════════════════════════════════════
# Catálogos de familia: granito es UNIÓN de 2 archivos
# ═══════════════════════════════════════════════════════════════════════


class TestGranitoIsUnion:
    def test_granito_family_has_two_catalogs(self):
        """La familia granito debe buscar sobre 2 archivos (nacional
        + importado). Ajuste del operador: no hardcodear 1 archivo =
        1 familia."""
        assert "materials-granito-nacional" in _FAMILY_CATALOGS["granito"]
        assert "materials-granito-importado" in _FAMILY_CATALOGS["granito"]
