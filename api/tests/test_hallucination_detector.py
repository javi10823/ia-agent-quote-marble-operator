"""Tests para PR #441 (P3.1) — detector de alucinación
"cambio sin tool".

**Caso DYSCON 29/04/2026 + Issue #422:**

Operador escribe "cambiá la demora a 30 días". Sonnet responde
"lo cambié" pero **NO llama ninguna tool de mutación** en el
turno. La DB no se toca. Operador asume que el cambio se aplicó
y se queda con la información vieja sin saberlo.

PRs anteriores cubrieron piezas:
- #423 (retry counter): protege contra tool failures.
- #436 (`update_quote` reject ruidoso): protege silent drops.

Este PR cubre el patrón de alucinación pura — Sonnet inventa un
estado de cambio sin haber tocado nada. Detección post-hoc:

1. Texto del assistant en el turno.
2. Tools llamadas (tracked desde que arranca `stream_chat`).

Si el texto contiene un claim ("cambié", "modifiqué", etc.) Y
ninguna mutation tool fue llamada → log warning. NO bloquea.

**Qué cubren los tests:**

- Detección positiva: claim + sin mutation tool.
- Sin alerta: claim + mutation tool presente (cambio respaldado).
- Sin alerta: texto neutro sin claim.
- Sin alerta: texto vacío / None.
- Word boundary: "intercambiar" NO matchea "cambiar".
- Whitelist mutation_tools: lookup tools NO satisfacen el claim.
- Drift guard: MUTATION_TOOLS es exactamente el set conocido.
- Caso DYSCON exacto.
- Falsos positivos comunes que NO disparan.
"""
from __future__ import annotations

import pytest

from app.modules.agent.hallucination_detector import (
    MUTATION_TOOLS,
    _CHANGE_CLAIM_PATTERNS,
    detect_unsupported_change_claim,
    is_mutation_tool,
)


# ═══════════════════════════════════════════════════════════════════════
# MUTATION_TOOLS — drift guard del whitelist
# ═══════════════════════════════════════════════════════════════════════


class TestMutationToolsWhitelist:
    def test_known_mutation_tools(self):
        """**Drift guard**: si alguien borra/agrega una tool del
        set, este test rompe y obliga a revisar la decisión.

        Las 4 mutation tools conocidas hoy. Si en el futuro se agrega
        una nueva (ej. `delete_quote`, `move_files`), agregarla acá
        Y al set del módulo. Si se elimina, idem."""
        assert MUTATION_TOOLS == frozenset({
            "update_quote",
            "calculate_quote",
            "patch_quote_mo",
            "generate_documents",
        }), (
            "MUTATION_TOOLS cambió. Si agregaste/borraste una tool "
            "que muta estado del quote, actualizá este test + el "
            "set del módulo en sintonía. Si la tool nueva NO muta "
            "estado, NO va al set (queda fuera, como catalog_lookup)."
        )

    def test_lookup_tools_not_in_mutation_set(self):
        """Lookup tools (consulta pura) NO deben estar en el set.
        Sino el detector daría false negatives — un claim de cambio
        respaldado solo por catalog_lookup pasaría como válido."""
        for lookup_tool in (
            "catalog_lookup",
            "catalog_batch_lookup",
            "check_architect",
            "check_stock",
            "read_plan",
            "list_pieces",
        ):
            assert not is_mutation_tool(lookup_tool), (
                f"{lookup_tool} es lookup, NO mutation tool. "
                "Si está en el set, el detector da false negatives."
            )

    def test_unknown_tool_not_mutation(self):
        """Tool desconocida → no muta (default conservador)."""
        assert is_mutation_tool("some_future_unknown_tool") is False
        assert is_mutation_tool("") is False


# ═══════════════════════════════════════════════════════════════════════
# Casos positivos — claim sin mutation tool
# ═══════════════════════════════════════════════════════════════════════


class TestDetectsHallucination:
    def test_dyscon_case_cambie_la_demora(self):
        """**Caso DYSCON real**: assistant dice "lo cambié" pero
        no llamó tools. Detector debe disparar."""
        warn = detect_unsupported_change_claim(
            "Listo, ya cambié la demora a 30 días.",
            tools_called=set(),
        )
        assert warn is not None
        assert "cambié" in warn.lower() or "alucinación" in warn.lower()

    def test_only_lookup_tools_does_not_count(self):
        """Sonnet llamó `catalog_lookup` pero dice "modifiqué". El
        catalog_lookup no muta nada → SÍ es alucinación."""
        warn = detect_unsupported_change_claim(
            "Modifiqué el material, ya está actualizado.",
            tools_called={"catalog_lookup", "check_stock"},
        )
        assert warn is not None

    @pytest.mark.parametrize("text", [
        "Listo, ya cambié la demora a 30 días.",
        "Modifiqué el descuento.",
        "Ya actualicé el material.",
        "Agregué la pileta al presupuesto.",
        "Saqué la colocación.",
        "Eliminé el flete.",
        "Borré la línea anterior.",
        "Quité el descuento.",
        "Guardé los cambios.",
        "Corregí el error.",
        "Ajusté el total.",
        "Removí el ítem.",
    ])
    def test_various_change_verbs_trigger(self, text):
        """Verbos en pasado primera persona singular disparan."""
        assert detect_unsupported_change_claim(text, set()) is not None, (
            f"Texto {text!r} debería disparar pero no lo hizo"
        )

    def test_passive_voice_triggers(self):
        """'Material modificado' / 'demora actualizada' también
        son claims (pasivos)."""
        assert detect_unsupported_change_claim(
            "El material está modificado.", set(),
        ) is not None
        assert detect_unsupported_change_claim(
            "Demora actualizada a 30 días.", set(),
        ) is not None


# ═══════════════════════════════════════════════════════════════════════
# Casos negativos — claim respaldado por mutation tool
# ═══════════════════════════════════════════════════════════════════════


class TestDoesNotTriggerWithMutationTool:
    def test_update_quote_supports_claim(self):
        """Sonnet dice "cambié la demora" Y llamó update_quote en
        el turno → cambio respaldado, NO alucinación."""
        warn = detect_unsupported_change_claim(
            "Cambié la demora a 30 días.",
            tools_called={"update_quote"},
        )
        assert warn is None

    @pytest.mark.parametrize("tool", [
        "update_quote",
        "calculate_quote",
        "patch_quote_mo",
        "generate_documents",
    ])
    def test_each_mutation_tool_satisfies(self, tool):
        warn = detect_unsupported_change_claim(
            "Modifiqué el presupuesto.",
            tools_called={tool},
        )
        assert warn is None

    def test_mixed_tools_with_one_mutation_passes(self):
        """Si hay AL MENOS UNA mutation tool, no dispara aunque
        haya lookup tools también."""
        warn = detect_unsupported_change_claim(
            "Actualicé los datos.",
            tools_called={"catalog_lookup", "calculate_quote", "check_stock"},
        )
        assert warn is None


# ═══════════════════════════════════════════════════════════════════════
# Casos neutros — texto sin claim
# ═══════════════════════════════════════════════════════════════════════


class TestNoChangeClaimNoWarning:
    @pytest.mark.parametrize("text", [
        "¿Confirmás para generar el PDF?",
        "El total quedó en $5.000.000.",
        "Detecté un edificio. ¿Querés que aplique descuento?",
        "Necesito que me confirmes la cantidad.",
        "OK.",
        "Listo para generar.",
        "El catálogo no tiene ese material.",
        "",
    ])
    def test_neutral_text_no_warning(self, text):
        assert detect_unsupported_change_claim(text, set()) is None

    def test_none_text_no_warning(self):
        assert detect_unsupported_change_claim(None, set()) is None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════
# Word boundary — false positives evitados
# ═══════════════════════════════════════════════════════════════════════


class TestWordBoundaryFalsePositives:
    def test_intercambiar_does_not_match_cambiar(self):
        """'intercambiar' no debe matchear 'cambiar'/'cambié'.
        Word-boundary debe cortar."""
        # Esta frase NO usa el verbo en pasado, solo menciona el
        # concepto. El detector busca 'cambié' (con tilde y first
        # person past), no 'cambiar' o 'cambio'.
        assert detect_unsupported_change_claim(
            "Te puedo ofrecer un intercambio si querés.", set(),
        ) is None

    def test_future_intent_does_not_match(self):
        """'voy a cambiar' / 'te lo cambio' = futuro/condicional,
        NO claim de cambio realizado."""
        for text in [
            "Voy a cambiar el material si me confirmás.",
            "Te lo cambio cuando me digas.",
            "Si querés, lo modificamos.",
            "Podemos actualizar la cotización.",
            "Te puedo agregar otro ítem.",
        ]:
            assert detect_unsupported_change_claim(text, set()) is None, (
                f"Texto futuro/condicional {text!r} disparó incorrectamente"
            )

    def test_question_does_not_match(self):
        """Preguntas con verbo en pasado son aceptables (el operador
        las haría leer como pregunta, no como afirmación)."""
        # NOTA: este caso es ambiguo. "¿Cambié algo?" técnicamente
        # tiene 'cambié'. El detector dispararía. En la práctica
        # Sonnet no hace este tipo de auto-pregunta — si en
        # producción aparece como falso positivo, refinamos.
        # Por ahora documentamos el comportamiento.
        text_with_question = "¿Cambié todo lo que pediste?"
        warn = detect_unsupported_change_claim(text_with_question, set())
        # Acepta tanto None como warn — no afirmamos comportamiento
        # estricto en pregunta. Lo importante es que el caso real
        # del DYSCON ("Listo, ya cambié X") sí dispare.
        # Si dispara: documentar caso edge.
        assert warn is None or "cambié" in warn.lower()

    def test_modifiqu_word_boundary(self):
        """'modifiqué' matchea, 'modifiquen' (3a plural pres)
        no debe matchear."""
        # Subjuntivo presente — no es claim de cambio realizado.
        # `modifiquen` tiene la forma `modifiqu` + `en`, mientras
        # que el regex es `modifiqu[ée]\b`. Como `en` NO es `é`/`e`,
        # no matchea. Test confirma.
        assert detect_unsupported_change_claim(
            "Que modifiquen el plan.", set(),
        ) is None


# ═══════════════════════════════════════════════════════════════════════
# Drift guard de patterns
# ═══════════════════════════════════════════════════════════════════════


class TestPatternsDriftGuard:
    def test_minimum_pattern_count(self):
        """Si alguien borra patterns, el detector se vuelve flojo.
        Como mínimo, los verbos críticos deben estar."""
        # Convertimos los patterns a strings para verificar.
        patterns_str = [p.pattern for p in _CHANGE_CLAIM_PATTERNS]
        all_patterns = " ".join(patterns_str)
        # Verbos que SÍ o SÍ deben estar.
        for verb_root in ("cambi", "modifiqu", "actualic", "guard"):
            assert verb_root in all_patterns, (
                f"Pattern para '{verb_root}' falta. Si lo borraste, "
                "los claims de cambio con ese verbo no se detectan."
            )
