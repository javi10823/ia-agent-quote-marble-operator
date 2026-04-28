"""Tests para PR #416 — `_user_intent` classifier (whitelist confirm).

**Bug observado (DYSCON post-#415):** dos cambios encadenados post-Paso 2.
Primer cambio (flete, msg largo) recalculó OK. Segundo cambio
("Armado frentín en mano de obra no va.", 51 chars) → Sonnet decidió
generate_documents directo, PDF con datos viejos.

Causa raíz: `_is_confirmation = len(msg) < 200` es heurística basura.
Cualquier mensaje corto se trataba como confirmación.

Fix: clasificador con whitelist positiva — confirmación requiere señal
explícita ("confirmo", "dale", "ok generá", etc.). Sin whitelist match,
no es confirm. Plus detector de modificación (imperativo+noun OR
negación+concepto). Bloquea generate_documents si intent != "confirm".

Tests cubren los casos del review feedback:
  - Whitelist gana sobre keyword de negación ("OK dale, sin cambios").
  - Negación+concepto detecta sin requerir imperativo.
  - "no va a haber problema, generá" → confirm (whitelist gana).
  - Mensajes vacíos → other (default conservador).
  - Mensajes ambiguos sin señal → other.
"""
from __future__ import annotations

import pytest

from app.modules.agent.agent import _user_intent


# ═══════════════════════════════════════════════════════════════════════
# Confirm intent — whitelist positiva
# ═══════════════════════════════════════════════════════════════════════


class TestConfirmWhitelist:
    @pytest.mark.parametrize("msg", [
        "Confirmo",
        "confirmo",
        "Confirmar",
        "Confirmá",
        "dale",
        "Dale",
        "ok genera",
        "OK generá",
        "Ok generar PDF",
        "imprimí",
        "Listo",
        "perfecto",
        "todo ok",
        "Todo bien",
        "está bien",
        "está perfecto",
        "Aprobado",
        "Sí",
        "yes",
        "ok dale",
    ])
    def test_explicit_confirm(self, msg):
        assert _user_intent(msg) == "confirm", (
            f"Esperaba confirm para {msg!r}"
        )

    def test_confirm_wins_over_negation_keyword(self):
        """'OK dale, sin cambios' — palabra 'sin' aparece pero whitelist
        de 'dale'/'ok' debe ganar (review feedback)."""
        assert _user_intent("OK dale, sin cambios") == "confirm"

    def test_confirm_with_extra_text(self):
        """'Confirmo, fuera de eso todo bien' — 'fuera' es keyword de
        negación pero whitelist de 'confirmo' gana."""
        assert _user_intent("Confirmo, fuera de eso todo bien") == "confirm"

    def test_confirm_phrase_with_neg_intent(self):
        """'no va a haber cambios, generá' — el operador dice 'generá'
        explícito → confirm. Sin whitelist de 'generá' caería como
        modify por 'no va'."""
        assert _user_intent("no va a haber cambios, generá") == "confirm"


# ═══════════════════════════════════════════════════════════════════════
# Modify intent — imperativo+noun OR negación+concepto
# ═══════════════════════════════════════════════════════════════════════


class TestModifyDetector:
    def test_dyscon_frentin_no_va(self):
        """Caso real DYSCON: 'Armado frentín en mano de obra no va.'
        → modify. Tiene 'no va' + 'frentín' + 'mano de obra'."""
        assert _user_intent("Armado frentín en mano de obra no va.") == "modify"

    def test_imperative_plus_noun(self):
        """'sacá el flete' → imperativo 'sac' + noun 'flete'."""
        assert _user_intent("sacá el flete") == "modify"

    def test_remove_pegadopileta(self):
        assert _user_intent("quitá el agujero de pileta") == "modify"

    def test_negation_with_concept(self):
        """'El descuento del 18% no va' — review feedback: detector
        de negación funciona aunque 'descuento' no esté como imperativo
        clásico de despiece."""
        assert _user_intent("El descuento del 18% no va") == "modify"

    def test_no_aplica(self):
        assert _user_intent("el flete no aplica") == "modify"

    def test_modify_zocalo(self):
        """Caso clásico del card-editor: agregar zócalo."""
        assert _user_intent("agregá un zócalo lateral") == "modify"

    def test_change_material(self):
        assert _user_intent("cambiar material a Negro Brasil") == "modify"


# ═══════════════════════════════════════════════════════════════════════
# Other / default conservador
# ═══════════════════════════════════════════════════════════════════════


class TestOtherDefault:
    def test_empty_string(self):
        assert _user_intent("") == "other"

    def test_whitespace_only(self):
        assert _user_intent("   \n\t  ") == "other"

    def test_none_input(self):
        assert _user_intent(None) == "other"

    def test_neutral_question(self):
        """'¿cuánto sale?' — pregunta, no confirma ni modifica."""
        assert _user_intent("¿cuánto sale?") == "other"

    def test_random_text(self):
        """Texto sin señales claras → other."""
        assert _user_intent("hola buenas tardes") == "other"

    def test_negation_without_concept(self):
        """'no va a haber problema' — tiene 'no va' pero ningún
        concepto (frentín/flete/etc) → other, NO modify. Esto evita
        bloquear confirmaciones legítimas que mencionan negación
        sin sustantivo (review feedback)."""
        # Nota: 'problema' no está en _MOD_NOUNS — correcto.
        assert _user_intent("no va a haber problema") == "other"


# ═══════════════════════════════════════════════════════════════════════
# Drift guards — combinaciones que importan al guardrail
# ═══════════════════════════════════════════════════════════════════════


class TestGuardrailIntegration:
    def test_only_confirm_unblocks_generate(self):
        """Solo intent='confirm' debe permitir generate_documents.
        Cualquier otro valor lo bloquea. Este test es contrato del
        guardrail — si rompe, el guardrail se rompió."""
        # Simulación de la condición que usa el guardrail:
        for msg, expected_unblock in [
            ("Confirmo", True),
            ("OK genera", True),
            ("Armado frentín no va", False),
            ("agregá zócalo", False),
            ("", False),
            ("hola", False),
        ]:
            intent = _user_intent(msg)
            unblocks = intent == "confirm"
            assert unblocks is expected_unblock, (
                f"msg={msg!r} → intent={intent} → unblocks={unblocks} "
                f"(esperaba {expected_unblock})"
            )
