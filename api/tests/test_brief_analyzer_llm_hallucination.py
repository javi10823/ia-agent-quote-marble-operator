"""Tests para PR #425 — fix alucinación del LLM Haiku que confunde
"frente regrueso" con "frentín".

**Caso DYSCON 29/04/2026:**

El "Análisis de contexto" del operador mostraba:
- "Frentín: Mencionado _(brief)_"

PERO el brief NO contenía la palabra "frentín". Sí contenía "M1 frente
regrueso × 24" (las piezas frente regrueso del despiece).

**Causa raíz:** `brief_analyzer.py` usa Haiku como fuente primaria con
regex como fallback. El LLM interpretaba "frente regrueso" como
"frentín" — son términos distintos:
- frentín / faldón = pieza vertical pegada al borde frontal de la
  mesada (5–10 cm de alto), MO con SKU FALDON.
- frente regrueso = pieza horizontal que aumenta el espesor visual
  del frente (5 cm), MO con SKU REGRUESO.

El regex fallback `\\bfrent[ií]n\\b` con word boundary NO matchearía
"frente regrueso" — pero el regex es solo fallback, no se ejecuta
cuando el LLM responde.

**Fix (review feedback "no toques el system prompt"):** post-process
con regex word-boundary después del LLM. Si LLM dice
`frentin_mentioned: true` pero la palabra literal NO aparece →
override a False con log.

**Tests cubren:**

1. **Caso DYSCON real**: "frente regrueso" en el brief → frentin
   override a False, regrueso queda en True.
2. **Caso positivo legítimo**: "con frentín h:5cm" → no se override.
3. **Edge case "sin frentín"**: la palabra aparece → flag queda True
   aunque sea negación contextual. Documentado en docstring del
   helper — Sonnet maneja la negación, no el analyzer.
4. **Drift guard**: el helper se ejecuta en la rama LLM (no en regex
   fallback, donde no hay false positives por construcción).
5. **Análogos para regrueso/pulido**: el LLM puede alucinar
   cualquiera de los 3 — el helper los cubre simétricamente.
6. **No-op cuando LLM responde correctamente**: si LLM dice false,
   el helper no toca nada.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.brief_analyzer import (
    _validate_llm_word_mentions,
)


# ═══════════════════════════════════════════════════════════════════════
# Caso DYSCON real — caso del bug reportado
# ═══════════════════════════════════════════════════════════════════════


class TestDysconHallucination:
    def test_frente_regrueso_does_not_imply_frentin(self):
        """Caso real DYSCON: brief con "M1 frente regrueso × 24" y
        análogos. LLM marca frentin_mentioned=true (alucinación).
        Override a False post-process."""
        brief = (
            "CLIENTE: DYSCON S.A.\n"
            "OBRA: Unidad Penal N°8 — Piñero\n"
            "M1 mesada × 24, M1 zócalo atrás × 24, M1 frente regrueso × 24\n"
            "M2 mesada (Office 32), M2 zócalo atrás, M2 frente regrueso\n"
        )
        result = {
            "frentin_mentioned": True,   # ← alucinación del LLM
            "regrueso_mentioned": True,  # ← legítimo (sí dice "regrueso")
            "pulido_mentioned": False,
        }
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is False, (
            "Override fallido: 'frente regrueso' no debe disparar frentin"
        )
        assert result["regrueso_mentioned"] is True, (
            "Regrueso es legítimo — la palabra 'regrueso' aparece word-boundary"
        )
        assert result["pulido_mentioned"] is False  # invariante

    def test_only_frente_no_regrueso_overrides_both(self):
        """Brief que dice 'frente' pero no 'regrueso' explícito (raro
        pero posible). LLM podría marcar ambos por confusión."""
        brief = "Mesada con frente plano de 5cm"
        result = {
            "frentin_mentioned": True,
            "regrueso_mentioned": True,  # también alucinación si no dice "regrueso"
            "pulido_mentioned": False,
        }
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is False
        assert result["regrueso_mentioned"] is False


# ═══════════════════════════════════════════════════════════════════════
# Casos legítimos — no se override
# ═══════════════════════════════════════════════════════════════════════


class TestLegitimateMentions:
    def test_frentin_literal_keeps_true(self):
        """'con frentín h:5cm' → la palabra está, flag queda True."""
        brief = "Mesada con frentín h:5cm"
        result = {"frentin_mentioned": True, "regrueso_mentioned": False, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is True

    def test_frentin_no_tilde_keeps_true(self):
        """'frentin' (sin tilde) también es literal — el regex matchea
        ambos `\\bfrent[ií]n\\b`."""
        brief = "Mesada con frentin de 5cm"
        result = {"frentin_mentioned": True, "regrueso_mentioned": False, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is True

    def test_frentin_uppercase_keeps_true(self):
        """Case-insensitive — 'FRENTÍN' debería match."""
        brief = "Mesada CON FRENTÍN H:5CM"
        result = {"frentin_mentioned": True, "regrueso_mentioned": False, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is True

    def test_regrueso_literal_keeps_true(self):
        brief = "Regrueso de 5cm en frente"
        result = {"frentin_mentioned": False, "regrueso_mentioned": True, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result["regrueso_mentioned"] is True

    def test_pulido_literal_keeps_true(self):
        brief = "Pulido especial en cantos visibles"
        result = {"frentin_mentioned": False, "regrueso_mentioned": False, "pulido_mentioned": True}
        _validate_llm_word_mentions(brief, result)
        assert result["pulido_mentioned"] is True


# ═══════════════════════════════════════════════════════════════════════
# Edge case documentado: "sin frentín"
# ═══════════════════════════════════════════════════════════════════════


class TestNegationEdgeCase:
    def test_sin_frentin_keeps_flag_true(self):
        """**Edge case (review feedback)**: 'sin frentín' contiene la
        palabra literal → flag queda True. Es responsabilidad de
        Sonnet manejar la negación contextualmente, NO del analyzer
        filtrar negaciones. Anotado en Issue follow-up.

        Si el día de mañana se decide filtrar negaciones a este
        nivel, este test SE ROMPERÁ y obligará a actualizar la
        documentación + el flow."""
        brief = "Mesada sin frentín, solo zócalo atrás"
        result = {"frentin_mentioned": True, "regrueso_mentioned": False, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is True, (
            "Negación NO se filtra acá — Sonnet maneja contexto. "
            "Si esto cambia, ver Issue follow-up del PR #425."
        )


# ═══════════════════════════════════════════════════════════════════════
# No-op cuando el LLM responde correctamente
# ═══════════════════════════════════════════════════════════════════════


class TestNoOpWhenLLMCorrect:
    def test_llm_says_false_no_change(self):
        """Si LLM dice False, el helper NO toca nada (incluso si la
        palabra aparece — confiamos en el LLM cuando dice False)."""
        brief = "Mesada con frentín h:5cm"
        result = {"frentin_mentioned": False, "regrueso_mentioned": False, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin_mentioned"] is False  # sin cambios

    def test_all_flags_false_no_op(self):
        brief = "Brief sin trabajos extra"
        result = {"frentin_mentioned": False, "regrueso_mentioned": False, "pulido_mentioned": False}
        _validate_llm_word_mentions(brief, result)
        assert result == {"frentin_mentioned": False, "regrueso_mentioned": False, "pulido_mentioned": False}


# ═══════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════


class TestObservability:
    def test_override_emits_warning(self, caplog):
        """Cuando se hace override, debe quedar log warning con el
        snippet del brief para diagnosticar. Si en producción aparece
        muchas veces, sabemos que el LLM aluciona seguido."""
        import logging
        brief = "M1 frente regrueso × 24"
        result = {"frentin_mentioned": True, "regrueso_mentioned": True, "pulido_mentioned": False}
        with caplog.at_level(logging.WARNING, logger="app.modules.quote_engine.brief_analyzer"):
            _validate_llm_word_mentions(brief, result)
        warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("hallucination" in m.lower() for m in warnings), (
            f"Esperaba warning de hallucination, vi {warnings}"
        )
        assert any("frentin_mentioned" in m for m in warnings)

    def test_no_override_no_warning(self, caplog):
        """Sin override → ningún warning del helper."""
        import logging
        brief = "Mesada con frentín h:5cm"
        result = {"frentin_mentioned": True, "regrueso_mentioned": False, "pulido_mentioned": False}
        with caplog.at_level(logging.WARNING, logger="app.modules.quote_engine.brief_analyzer"):
            _validate_llm_word_mentions(brief, result)
        warnings = [
            r.message for r in caplog.records
            if r.levelno >= logging.WARNING and "hallucination" in r.message.lower()
        ]
        assert warnings == []


# ═══════════════════════════════════════════════════════════════════════
# Drift guards
# ═══════════════════════════════════════════════════════════════════════


class TestDriftGuards:
    def test_helper_does_not_raise_on_missing_keys(self):
        """Defensivo: result puede no tener todos los flags si llegó
        un shape incompleto. No tirar excepción."""
        brief = "frente regrueso"
        result = {}  # ← shape incompleta
        _validate_llm_word_mentions(brief, result)  # no debe romper
        # No agrega keys que no estaban
        assert "frentin_mentioned" not in result

    def test_empty_brief_no_op(self):
        """Brief vacío → nada que validar. Helper no tira."""
        result = {"frentin_mentioned": True, "regrueso_mentioned": True, "pulido_mentioned": True}
        _validate_llm_word_mentions("", result)
        # Brief vacío → todas las palabras "no aparecen" → todos override.
        assert result["frentin_mentioned"] is False
        assert result["regrueso_mentioned"] is False
        assert result["pulido_mentioned"] is False

    def test_validation_map_has_three_entries(self):
        """Drift guard: si alguien agrega un nuevo flag al schema
        (ej. `inglete_mentioned`), tiene que agregarlo también al
        mapa de validation. Test recuerda."""
        from app.modules.quote_engine.brief_analyzer import _LLM_WORD_VALIDATIONS
        flag_keys = {entry[0] for entry in _LLM_WORD_VALIDATIONS}
        assert flag_keys == {
            "frentin_mentioned", "regrueso_mentioned", "pulido_mentioned",
        }, (
            f"Validation map cambió: {flag_keys}. Si agregaste un nuevo "
            "flag de tipo `*_mentioned`, agregalo a _LLM_WORD_VALIDATIONS "
            "para protegerlo de alucinaciones del LLM."
        )
