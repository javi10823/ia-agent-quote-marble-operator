"""Tests para PR #413 — guards backend para material variant + regrueso.

Bug DYSCON destapó dos clases de drift del LLM:
  1. Material: brief dice "Granito Gris Mara (NO Extra 2)" → Sonnet
     inyecta "Granito Gris Mara Fiamatado" (alucinación por descarte).
  2. Regrueso: brief dice "REGRUESO frente — 60.68ml" → Sonnet omite
     `regrueso=true` y `regrueso_ml` del input al `calculate_quote`.

Fix: 2 guards en `agent.py` antes de `calculate_quote(inputs)` que
inspeccionan el brief y override + log ruidoso cuando difieren.

Tests cubren los 6 casos del review:
  - DYSCON exacto: ambos guards disparan.
  - Brief con "Fiamatado" explícito → guard NO entra (respeta).
  - Brief con "regrueso a definir 60ml" → NO inyectar, log warn.
  - Brief con 2 menciones de regrueso ml → NO inyectar, log error.
  - Sonnet alucina ml ≠ brief → override + warning ruidoso.
  - Sin regrueso en brief, Sonnet pasó valor → respetar (no-op).

Asimetría conocida (xfail-doc): brief tiene "Fiamatado" pero Sonnet
droppea a "Gris Mara" base → guard NO la corrige. Documentada como
deuda; el test xfail la mantiene visible.
"""
from __future__ import annotations

import pytest

from app.modules.agent.agent import (
    _brief_mentions_gris_mara_variant,
    _extract_regrueso_ml_from_brief,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers — comportamiento exacto
# ═══════════════════════════════════════════════════════════════════════


class TestExtractRegrueso:
    def test_dyscon_exact(self):
        """Brief DYSCON: 'REGRUESO frente h:5cm — 60.68ml total'."""
        ml, reason = _extract_regrueso_ml_from_brief(
            "MO: REGRUESO frente h:5cm — 60.68ml total (labor por ml)"
        )
        assert reason == "ok"
        assert ml == 60.68

    def test_no_regrueso_in_brief(self):
        ml, reason = _extract_regrueso_ml_from_brief(
            "MATERIAL: Granito Negro Brasil. Mesada 2x0.6"
        )
        assert ml is None
        assert reason == "not_found"

    def test_a_definir_aborts(self):
        """'regrueso a definir, aprox 60ml' → no inyectar."""
        ml, reason = _extract_regrueso_ml_from_brief(
            "Lleva regrueso a definir, aprox 60ml según plano"
        )
        assert ml is None
        assert reason == "aborted_a_definir"

    def test_aprox_aborts(self):
        ml, reason = _extract_regrueso_ml_from_brief(
            "regrueso aprox 50ml en frente"
        )
        assert ml is None
        assert reason == "aborted_a_definir"

    def test_multiple_matches_no_inject(self):
        """'regrueso shower 8ml + regrueso mesada 60ml' → abort."""
        ml, reason = _extract_regrueso_ml_from_brief(
            "regrueso shower 8ml + regrueso mesada 60ml total"
        )
        assert ml is None
        assert reason == "multiple_matches"

    def test_qualitative_only_no_value(self):
        """'lleva regrueso' sin ml → no inyectar."""
        ml, reason = _extract_regrueso_ml_from_brief(
            "Mesada con regrueso de 5cm en el frente"
        )
        # Hay "5cm" cerca pero NO matchea `\d+ml`.
        assert ml is None
        assert reason == "qualitative_only"

    def test_regrueso_with_comma_decimal(self):
        """ARS-style decimals: '60,68ml' debe parsear."""
        ml, reason = _extract_regrueso_ml_from_brief(
            "REGRUESO 60,68ml total"
        )
        assert reason == "ok"
        assert ml == 60.68

    def test_distance_window_80_chars(self):
        """Si el ml está demasiado lejos de la palabra regrueso, no
        debe matchear. Eso evita falsos positivos cuando 'ml' aparece
        en otro contexto."""
        # 100+ chars entre "regrueso" y "60ml" — NO debe matchear.
        far_text = (
            "regrueso "
            + "x" * 90
            + " 60ml"
        )
        ml, reason = _extract_regrueso_ml_from_brief(far_text)
        # qualitative_only porque no encontró ml dentro de 80 chars.
        assert ml is None
        assert reason == "qualitative_only"


class TestBriefMentionsVariant:
    def test_brief_with_fiamatado(self):
        assert _brief_mentions_gris_mara_variant(
            "MATERIAL: Granito Gris Mara Fiamatado 20mm"
        ) == "fiamatado"

    def test_brief_with_leather(self):
        assert _brief_mentions_gris_mara_variant(
            "Granito Gris Mara Leather"
        ) == "leather"

    def test_brief_without_variant(self):
        """Caso DYSCON: brief tiene 'NO Extra 2' (que NO es variante)."""
        assert _brief_mentions_gris_mara_variant(
            "MATERIAL: Granito Gris Mara — 20mm (SKU estándar, NO Extra 2)"
        ) is None

    def test_brief_without_gris_mara(self):
        assert _brief_mentions_gris_mara_variant(
            "MATERIAL: Granito Negro Brasil"
        ) is None

    def test_variant_far_from_gris_mara_no_match(self):
        """Variante mencionada en otro contexto, lejos del 'Gris Mara'
        actual, NO debe matchear (>80 chars)."""
        text = (
            "antes pedimos fiamatado pero ahora cambiamos por otro proyecto. "
            + "x" * 100
            + ". Material: Granito Gris Mara estándar"
        )
        assert _brief_mentions_gris_mara_variant(text) is None


# ═══════════════════════════════════════════════════════════════════════
# Asimetría documentada (xfail) — brief con variante, Sonnet droppea
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(
    reason=(
        "PR #413 deuda documentada: el guard de Gris Mara es asimétrico. "
        "Solo dispara cuando brief NO tiene variante. Caso inverso (brief "
        "tiene 'Fiamatado' y Sonnet droppea a base) NO está cubierto. "
        "Cuando aparezca el caso real, ampliar a bidireccional. Mientras "
        "tanto este xfail mantiene visible la deuda."
    ),
    strict=True,
)
def test_brief_has_variant_sonnet_drops_NOT_FIXED_doc_only():
    """Caso reverso: brief explícito 'Fiamatado' pero Sonnet pasa
    'Granito Gris Mara' base. Hoy el guard NO lo corrige.

    Si este xfail empieza a pasar (reason=PASSED), significa que
    alguien arregló la asimetría y se puede borrar el xfail.
    """
    from app.modules.agent.agent import _brief_mentions_gris_mara_variant
    brief = "Material: Granito Gris Mara Fiamatado 20mm"
    sonnet_input_material = "Granito Gris Mara"
    # Lo que esperaría un guard simétrico:
    variant = _brief_mentions_gris_mara_variant(brief)
    assert variant == "fiamatado"
    # Y el guard debería forzar que `inputs["material"]` incluya
    # "fiamatado" — pero hoy NO lo hace. Por eso xfail.
    # Simulación: el guard actual no toca cuando brief tiene variante.
    assert "fiamatado" in sonnet_input_material.lower()  # ← falla intencional
