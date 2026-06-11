"""Tests para PR #425 (validator anti-alucinación) + PR #485 (Bug 5 —
schema ternary yes/no/null).

## Historia

**PR #425 — caso DYSCON 29/04/2026:**

El "Análisis de contexto" del operador mostraba "Frentín: Mencionado"
para un brief que decía "M1 frente regrueso × 24" pero NO "frentín".
El LLM Haiku interpretaba "frente regrueso" como "frentín" — son
términos distintos:
- frentín / faldón = pieza vertical pegada al borde frontal (5-10 cm).
- frente regrueso = pieza horizontal que aumenta espesor visual.

Fix PR #425: post-process con regex word-boundary. Si LLM marcaba
`frentin_mentioned=true` pero la palabra literal NO aparece, override
a False.

**PR #485 — Bug 5 (Issue follow-up activado):**

Los flags `frentin_mentioned: bool` no distinguían "Brief dice 'Frentín:
No'" (operador explícito) vs "Brief no menciona frentín" (silencio).
El test `test_sin_frentin_keeps_flag_true` documentaba esa deuda como
expected behavior. Caso Micaela (Run1 ≠ Run2) confirmó variabilidad.

Fix PR #485: schema ternary `"yes"|"no"|null`. El validator ahora:
- Si LLM setea valor no-null pero palabra NO aparece → override a None.
- "sin frentín" → el regex de fallback decide `"no"` (la palabra está).
- Drift guard de tuple `_LLM_WORD_VALIDATIONS` actualizado a 3 keys
  nuevas: `frentin`, `regrueso`, `pulido`.

## Tests cubren

1. **Caso DYSCON real**: "frente regrueso" en el brief → frentin
   override a None, regrueso queda en "yes" (palabra sí aparece).
2. **Casos positivos legítimos**: "con frentín" → no se override.
3. **No-op**: si LLM dijo None, el helper no toca nada.
4. **Drift guards**: el helper y la tupla de validation cubren los 3
   campos. Si se agrega un flag nuevo, drift guard rompe.
5. **Logging**: override emite warning con snippet del brief.
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
        análogos. LLM marca frentin="yes" (alucinación). Override a
        None post-process."""
        brief = (
            "CLIENTE: DYSCON S.A.\n"
            "OBRA: Unidad Penal N°8 — Piñero\n"
            "M1 mesada × 24, M1 zócalo atrás × 24, M1 frente regrueso × 24\n"
            "M2 mesada (Office 32), M2 zócalo atrás, M2 frente regrueso\n"
        )
        result = {
            "frentin": "yes",    # ← alucinación del LLM
            "regrueso": "yes",   # ← legítimo (sí dice "regrueso")
            "pulido": None,
        }
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] is None, (
            "Override fallido: 'frente regrueso' no debe disparar frentin"
        )
        assert result["regrueso"] == "yes", (
            "Regrueso es legítimo — la palabra 'regrueso' aparece word-boundary"
        )
        assert result["pulido"] is None  # invariante

    def test_only_frente_no_regrueso_overrides_both(self):
        """Brief que dice 'frente' pero no 'regrueso' explícito (raro
        pero posible). LLM podría marcar ambos por confusión."""
        brief = "Mesada con frente plano de 5cm"
        result = {
            "frentin": "yes",
            "regrueso": "yes",  # también alucinación si no dice "regrueso"
            "pulido": None,
        }
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] is None
        assert result["regrueso"] is None


# ═══════════════════════════════════════════════════════════════════════
# Casos legítimos — no se override
# ═══════════════════════════════════════════════════════════════════════


class TestLegitimateMentions:
    def test_frentin_literal_keeps_yes(self):
        """'con frentín h:5cm' → la palabra está, valor queda en 'yes'."""
        brief = "Mesada con frentín h:5cm"
        result = {"frentin": "yes", "regrueso": None, "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] == "yes"

    def test_frentin_no_tilde_keeps_yes(self):
        """'frentin' (sin tilde) también es literal — el regex matchea
        ambos `\\bfrent[ií]n\\b`."""
        brief = "Mesada con frentin de 5cm"
        result = {"frentin": "yes", "regrueso": None, "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] == "yes"

    def test_frentin_uppercase_keeps_yes(self):
        """Case-insensitive — 'FRENTÍN' debería match."""
        brief = "Mesada CON FRENTÍN H:5CM"
        result = {"frentin": "yes", "regrueso": None, "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] == "yes"

    def test_regrueso_literal_keeps_yes(self):
        brief = "Regrueso de 5cm en frente"
        result = {"frentin": None, "regrueso": "yes", "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result["regrueso"] == "yes"

    def test_pulido_literal_keeps_yes(self):
        brief = "Pulido especial en cantos visibles"
        result = {"frentin": None, "regrueso": None, "pulido": "yes"}
        _validate_llm_word_mentions(brief, result)
        assert result["pulido"] == "yes"


# ═══════════════════════════════════════════════════════════════════════
# Edge case documentado: "sin frentín"
# ═══════════════════════════════════════════════════════════════════════


class TestNegationHandling:
    def test_sin_frentin_validator_keeps_no(self):
        """**Activación Issue follow-up PR #425** (cerrado por PR #485).

        Antes: el validator era binary (`True`/`False`) y "sin frentín"
        contenía la palabra literal → flag quedaba `True`. Sonnet
        debía manejar la negación. Caso Micaela demostró que NO la
        manejaba consistentemente (Run1≠Run2).

        Hoy: el schema es ternary y el LLM ya devuelve `"no"`
        directamente. El validator solo chequea presencia literal —
        si la palabra está y LLM devolvió `"no"`, queda `"no"` (es
        decisión legítima del operador). Si la palabra NO está y LLM
        devolvió cualquier valor, override a None."""
        brief = "Mesada sin frentín, solo zócalo atrás"
        result = {"frentin": "no", "regrueso": None, "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] == "no", (
            "Validator debe preservar 'no' cuando la palabra está. "
            "Sonnet ya NO maneja la negación — el analyzer la captura."
        )


# ═══════════════════════════════════════════════════════════════════════
# No-op cuando el LLM responde correctamente
# ═══════════════════════════════════════════════════════════════════════


class TestNoOpWhenLLMCorrect:
    def test_llm_says_null_no_change(self):
        """Si LLM dice None (no decidió), el helper NO toca nada —
        no hay nada que validar."""
        brief = "Mesada con frentín h:5cm"
        result = {"frentin": None, "regrueso": None, "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result["frentin"] is None  # sin cambios

    def test_all_flags_null_no_op(self):
        brief = "Brief sin trabajos extra"
        result = {"frentin": None, "regrueso": None, "pulido": None}
        _validate_llm_word_mentions(brief, result)
        assert result == {"frentin": None, "regrueso": None, "pulido": None}


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
        result = {"frentin": "yes", "regrueso": "yes", "pulido": None}
        with caplog.at_level(logging.WARNING, logger="app.modules.quote_engine.brief_analyzer"):
            _validate_llm_word_mentions(brief, result)
        warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("hallucination" in m.lower() for m in warnings), (
            f"Esperaba warning de hallucination, vi {warnings}"
        )
        assert any("frentin" in m for m in warnings)

    def test_no_override_no_warning(self, caplog):
        """Sin override → ningún warning del helper."""
        import logging
        brief = "Mesada con frentín h:5cm"
        result = {"frentin": "yes", "regrueso": None, "pulido": None}
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
        assert "frentin" not in result

    def test_empty_brief_overrides_to_null(self):
        """Brief vacío → nada que validar. Helper no tira."""
        result = {"frentin": "yes", "regrueso": "yes", "pulido": "yes"}
        _validate_llm_word_mentions("", result)
        # Brief vacío → todas las palabras "no aparecen" → todos override a None.
        assert result["frentin"] is None
        assert result["regrueso"] is None
        assert result["pulido"] is None

    def test_validation_map_has_three_entries(self):
        """Drift guard: si alguien agrega un nuevo flag al schema
        (ej. `inglete`), tiene que agregarlo también al mapa de
        validation. Test recuerda."""
        from app.modules.quote_engine.brief_analyzer import _LLM_WORD_VALIDATIONS
        flag_keys = {entry[0] for entry in _LLM_WORD_VALIDATIONS}
        assert flag_keys == {
            "frentin", "regrueso", "pulido",
        }, (
            f"Validation map cambió: {flag_keys}. Si agregaste un nuevo "
            "flag ternary (yes/no/null) de trabajo extra, agregalo a "
            "_LLM_WORD_VALIDATIONS para protegerlo de alucinaciones del LLM."
        )
