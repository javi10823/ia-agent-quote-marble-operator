"""Unit tests for card_editor — detector + applier.

No testamos extract_card_patch (requiere LLM call — se testea manual/E2E).
"""
from app.modules.agent.card_editor import (
    is_card_modification_message,
    apply_card_patch,
    format_patch_summary,
)


class TestIsCardModificationMessage:
    def test_falto_zocalo(self):
        assert is_card_modification_message("te falto un zocalo de 1x1")

    def test_agregar_mesada(self):
        assert is_card_modification_message("agregá una mesada nueva")

    def test_sacar_tramo(self):
        assert is_card_modification_message("sacá el tramo chico")

    def test_cambiar_zocalo(self):
        assert is_card_modification_message("cambiá el zócalo a 1.5ml")

    def test_question_ignored(self):
        assert not is_card_modification_message("¿cuánto sale?")

    def test_confirmation_ignored(self):
        assert not is_card_modification_message("dale")

    def test_empty(self):
        assert not is_card_modification_message("")
        assert not is_card_modification_message("   ")

    def test_noun_without_action(self):
        # "zocalo" sin verbo de acción → no es modificación
        assert not is_card_modification_message("vi el zocalo")

    def test_action_without_noun(self):
        # "agregá" sin sustantivo de pieza → no es modificación
        assert not is_card_modification_message("agregá el IVA")


def _sample_card() -> dict:
    return {
        "sectores": [
            {
                "id": "cocina",
                "tipo": "L",
                "tramos": [
                    {
                        "id": "tramo_1",
                        "descripcion": "Mesada principal",
                        "largo_m": {"valor": 1.28, "status": "CONFIRMADO"},
                        "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
                        "m2": {"valor": 0.77, "status": "CONFIRMADO"},
                        "zocalos": [
                            {"lado": "trasero", "ml": 1.28, "alto_m": 0.07,
                             "status": "CONFIRMADO"},
                        ],
                        "frentin": [],
                        "regrueso": [],
                    },
                    {
                        "id": "tramo_2",
                        "descripcion": "Retorno L",
                        "largo_m": {"valor": 1.61, "status": "CONFIRMADO"},
                        "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
                        "m2": {"valor": 0.97, "status": "CONFIRMADO"},
                        "zocalos": [],
                        "frentin": [],
                        "regrueso": [],
                    },
                ],
                "ambiguedades": [],
            }
        ],
        "source": "DUAL",
        "view_type": "render_3d",
    }


class TestApplyCardPatch:
    def test_add_zocalo(self):
        card = _sample_card()
        ops = [{"op": "add_zocalo", "sector_id": "cocina", "tramo_id": "tramo_2",
                "lado": "trasero", "ml": 1.61, "alto_m": 0.07}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        assert len(applied) == 1
        zs = patched["sectores"][0]["tramos"][1]["zocalos"]
        assert len(zs) == 1
        assert zs[0]["lado"] == "trasero"
        assert zs[0]["ml"] == 1.61
        assert zs[0]["_manual"] is True

    def test_remove_zocalo(self):
        card = _sample_card()
        ops = [{"op": "remove_zocalo", "sector_id": "cocina",
                "tramo_id": "tramo_1", "lado": "trasero"}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        assert patched["sectores"][0]["tramos"][0]["zocalos"] == []

    def test_edit_zocalo_ml(self):
        card = _sample_card()
        ops = [{"op": "edit_zocalo_ml", "sector_id": "cocina",
                "tramo_id": "tramo_1", "lado": "trasero", "ml": 1.50}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        assert patched["sectores"][0]["tramos"][0]["zocalos"][0]["ml"] == 1.50

    def test_edit_zocalo_alto(self):
        card = _sample_card()
        ops = [{"op": "edit_zocalo_alto", "sector_id": "cocina",
                "tramo_id": "tramo_1", "lado": "trasero", "alto_m": 0.10}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        assert patched["sectores"][0]["tramos"][0]["zocalos"][0]["alto_m"] == 0.10

    def test_add_tramo(self):
        card = _sample_card()
        ops = [{"op": "add_tramo", "sector_id": "cocina",
                "descripcion": "Cajonera", "largo_m": 0.42, "ancho_m": 0.60}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        tramos = patched["sectores"][0]["tramos"]
        assert len(tramos) == 3
        assert tramos[2]["descripcion"] == "Cajonera"
        assert tramos[2]["largo_m"]["valor"] == 0.42
        assert tramos[2]["m2"]["valor"] == 0.25  # 0.42 * 0.60 = 0.252 → 0.25

    def test_remove_tramo(self):
        card = _sample_card()
        ops = [{"op": "remove_tramo", "sector_id": "cocina", "tramo_id": "tramo_2"}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        assert len(patched["sectores"][0]["tramos"]) == 1

    def test_edit_tramo_largo_recomputes_m2(self):
        card = _sample_card()
        ops = [{"op": "edit_tramo", "sector_id": "cocina",
                "tramo_id": "tramo_1", "field": "largo_m", "value": 2.0}]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        t = patched["sectores"][0]["tramos"][0]
        assert t["largo_m"]["valor"] == 2.0
        assert t["m2"]["valor"] == 1.20  # 2.0 * 0.60

    def test_unknown_op_error(self):
        card = _sample_card()
        ops = [{"op": "hacer_algo_raro"}]
        _, applied, errors = apply_card_patch(card, ops)
        assert applied == []
        assert any("desconocida" in e.lower() for e in errors)

    def test_sector_not_found(self):
        card = _sample_card()
        ops = [{"op": "remove_tramo", "sector_id": "inexistente", "tramo_id": "X"}]
        _, applied, errors = apply_card_patch(card, ops)
        # Fallback: single sector → usa ese, pero tramo_id "X" no existe
        assert len(errors) >= 1

    def test_ask_operator_reported(self):
        card = _sample_card()
        ops = [{"op": "ask_operator", "reason": "¿qué tramo?"}]
        _, applied, errors = apply_card_patch(card, ops)
        assert applied == []
        assert any("ask_operator" in e for e in errors)

    def test_multiple_ops_sequential(self):
        card = _sample_card()
        ops = [
            {"op": "add_zocalo", "sector_id": "cocina", "tramo_id": "tramo_2",
             "lado": "trasero", "ml": 1.61, "alto_m": 0.07},
            {"op": "edit_zocalo_ml", "sector_id": "cocina", "tramo_id": "tramo_1",
             "lado": "trasero", "ml": 1.50},
        ]
        patched, applied, errors = apply_card_patch(card, ops)
        assert errors == []
        assert len(applied) == 2
        assert len(patched["sectores"][0]["tramos"][1]["zocalos"]) == 1
        assert patched["sectores"][0]["tramos"][0]["zocalos"][0]["ml"] == 1.50


class TestFormatPatchSummary:
    def test_all_applied(self):
        s = format_patch_summary(
            ["agregué zócalo trasero 0.5ml"], []
        )
        assert "Card actualizado" in s
        assert "agregué zócalo trasero 0.5ml" in s

    def test_errors_only(self):
        s = format_patch_summary([], ["sector 'X' no encontrado"])
        assert "No pude aplicar" in s
        assert "más detalle" in s

    def test_empty_both(self):
        s = format_patch_summary([], [])
        assert "detallar" in s


# ═══════════════════════════════════════════════════════════════════════
# PR #378 — reset_quote_to_paso1 + is_paso2_confirmed helpers
# ═══════════════════════════════════════════════════════════════════════

from app.modules.agent.card_editor import (  # noqa: E402
    reset_quote_to_paso1,
    is_paso2_confirmed,
    _PASO2_DERIVED_KEYS,
)


def _full_paso2_breakdown() -> dict:
    """Breakdown de un quote post Paso 2 — todos los campos derivados
    llenos. Usado para validar que el reset los limpia todos."""
    return {
        # Campos que DEBEN preservarse (Paso 1 + metadata)
        "dual_read_result": {"sectores": [{"tipo": "cocina", "tramos": [{"id": "t1"}]}]},
        "dual_read_plan_hash": "abc123",
        "brief_analysis": {"client_name": "Erica Bernardi"},
        "context_analysis_pending": {"tech_detections": []},
        "verified_context_analysis": {"answers": []},
        # Campos de Paso 2 — TODOS deben limpiarse
        "verified_context": "[MEDIDAS VERIFICADAS...]",
        "verified_measurements": {"sectores": []},
        "measurements_confirmed": True,  # legacy
        "verified_commercial_attrs": {"anafe_count": {"value": 1}},
        "verified_derived_pieces": [{"description": "Pata frontal"}],
        "material_name": "PURASTONE",
        "material_m2": 6.48,
        "material_price_unit": 527,
        "material_currency": "USD",
        "discount_amount": 0,
        "discount_pct": 0,
        "total_ars": 797177,
        "total_usd": 4128,
        "total_mo_ars": 797177,
        "mo_items": [{"description": "Colocación"}],
        "sectors": [{"label": "COCINA"}],
        "sinks": [],
        "piece_details": [{"description": "Mesada"}],
        "mo_discount_amount": 0,
        "mo_discount_pct": 0,
        "sobrante_m2": 0,
        "sobrante_total": 0,
        "paso1_pieces": [],
        "paso1_total_m2": 6.48,
    }


class TestIsPaso2Confirmed:
    def test_none_is_false(self):
        assert is_paso2_confirmed(None) is False

    def test_empty_is_false(self):
        assert is_paso2_confirmed({}) is False

    def test_verified_context_marker(self):
        assert is_paso2_confirmed({"verified_context": "X"}) is True

    def test_measurements_confirmed_legacy_marker(self):
        assert is_paso2_confirmed({"measurements_confirmed": True}) is True

    def test_only_dual_read_result_is_not_confirmed(self):
        """Quote en Paso 1 con card emitida pero sin confirmar → no bloqueado."""
        bd = {"dual_read_result": {"sectores": []}}
        assert is_paso2_confirmed(bd) is False


class TestResetQuoteToPaso1:
    """El helper deja el breakdown en estado 'Paso 1 editable', preservando
    metadata (brief_analysis, dual_read_result, client context)."""

    def test_removes_all_paso2_derived_keys(self):
        bd = _full_paso2_breakdown()
        reset = reset_quote_to_paso1(bd)
        for key in _PASO2_DERIVED_KEYS:
            assert key not in reset, f"{key} no se limpió"

    def test_preserves_dual_read_result_by_default(self):
        bd = _full_paso2_breakdown()
        reset = reset_quote_to_paso1(bd)
        assert "dual_read_result" in reset
        assert reset["dual_read_result"] == bd["dual_read_result"]

    def test_preserves_brief_analysis_and_metadata(self):
        bd = _full_paso2_breakdown()
        reset = reset_quote_to_paso1(bd)
        assert reset.get("brief_analysis") == {"client_name": "Erica Bernardi"}
        assert reset.get("dual_read_plan_hash") == "abc123"
        assert "context_analysis_pending" in reset
        assert "verified_context_analysis" in reset

    def test_preserve_dual_read_result_false_removes_it(self):
        bd = _full_paso2_breakdown()
        reset = reset_quote_to_paso1(bd, preserve_dual_read_result=False)
        assert "dual_read_result" not in reset

    def test_idempotent_on_empty_breakdown(self):
        assert reset_quote_to_paso1({}) == {}
        assert reset_quote_to_paso1(None) == {}

    def test_idempotent_second_call(self):
        """Aplicar reset dos veces == aplicarlo una vez. No falla."""
        bd = _full_paso2_breakdown()
        once = reset_quote_to_paso1(bd)
        twice = reset_quote_to_paso1(once)
        assert once == twice

    def test_does_not_mutate_input(self):
        """Funcional puro — el dict original queda intacto."""
        bd = _full_paso2_breakdown()
        bd_snapshot = dict(bd)
        _ = reset_quote_to_paso1(bd)
        assert bd == bd_snapshot

    def test_handles_partial_paso2_state(self):
        """Si solo algunos campos de Paso 2 están presentes, limpia los que
        hay sin romper por los que faltan."""
        bd = {
            "dual_read_result": {"x": 1},
            "verified_context": "texto",
            "material_name": "X",
        }
        reset = reset_quote_to_paso1(bd)
        assert reset == {"dual_read_result": {"x": 1}}


# ═══════════════════════════════════════════════════════════════════════
# PR #380 — rehydrate_messages helper (historial legacy)
# ═══════════════════════════════════════════════════════════════════════

import json  # noqa: E402
from app.modules.agent.card_editor import rehydrate_messages  # noqa: E402


def _legacy_bernardi_messages() -> list[dict]:
    """Historial real de un quote pre-#379 — con todos los patrones
    contaminados que el helper debe limpiar."""
    return [
        # Brief del operador con el bloque PDF pegado (bug copy.deepcopy)
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "nuevo presupuesto material en pura prima onix white mate "
                        "Cliente: Erica Bernardi SIN zocalos en rosario\n\n"
                        "[TEXTO EXTRAÍDO DEL PDF — DATOS EXACTOS]\n"
                        "⛔ Extraído con precisión 100%...\n"
                        "Tabla 3 (página 1) --- 1,60 ---\n"
                        "[SISTEMA — EDICIÓN LIBRE]\n"
                        "Este presupuesto tiene un cálculo previo..."
                    ),
                }
            ],
        },
        # Marker placeholder — reemplazable si hay context_analysis_pending
        {"role": "assistant", "content": "__CONTEXT_ANALYSIS_SHOWN__"},
        # Turn real de confirmación de contexto (frontend lo marca como pill)
        {"role": "user", "content": '[CONTEXT_CONFIRMED]{"answers":[]}'},
        # Fake user turn — descartable
        {"role": "user", "content": "(contexto confirmado)"},
        # Marker del despiece — reemplazable si hay dual_read_result
        {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        # Turn de confirmación de medidas (pill)
        {"role": "user", "content": '[DUAL_READ_CONFIRMED]{"sectores":[]}'},
        # Paso 2 assistant markdown legítimo
        {"role": "assistant", "content": "## PASO 2 — Validación ..."},
        # Final user turn legítimo
        {"role": "user", "content": "Confirmo"},
    ]


def _bernardi_breakdown(with_context_pending: bool = True) -> dict:
    """Breakdown con data mínima para reconstruir las cards."""
    bd = {
        "dual_read_result": {
            "sectores": [{"id": "cocina", "tipo": "cocina", "tramos": []}],
        },
    }
    if with_context_pending:
        bd["context_analysis_pending"] = {
            "data_known": [{"field": "Cliente", "value": "Erica Bernardi", "source": "brief"}],
            "assumptions": [],
            "pending_questions": [],
        }
    return bd


class TestRehydrateMessagesBernardi:
    """Caso central: el historial Bernardi-shape con todos los patrones
    contaminados se transforma al shape post-#379 usando el breakdown
    como fuente de verdad."""

    def test_bernardi_full_rehydrate(self):
        msgs = _legacy_bernardi_messages()
        bd = _bernardi_breakdown()
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is True

        # Brief del operador: truncado al marker [TEXTO EXTRAÍDO
        brief = new_msgs[0]
        assert brief["role"] == "user"
        brief_text = brief["content"] if isinstance(brief["content"], str) else "".join(
            b.get("text", "") for b in brief["content"] if b.get("type") == "text"
        )
        assert "pura prima onix" in brief_text.lower()
        assert "TEXTO EXTRAÍDO" not in brief_text
        assert "[SISTEMA" not in brief_text

        # __CONTEXT_ANALYSIS_SHOWN__ → __CONTEXT_ANALYSIS__<json>
        ctx_turn = new_msgs[1]
        assert ctx_turn["role"] == "assistant"
        assert ctx_turn["content"].startswith("__CONTEXT_ANALYSIS__")
        ctx_json = json.loads(ctx_turn["content"].replace("__CONTEXT_ANALYSIS__", "", 1))
        assert any(
            r.get("field") == "Cliente" and r.get("value") == "Erica Bernardi"
            for r in ctx_json.get("data_known", [])
        )

        # [CONTEXT_CONFIRMED] preservado
        assert new_msgs[2]["content"].startswith("[CONTEXT_CONFIRMED]")

        # (contexto confirmado) descartado → el siguiente es el DUAL_READ
        dual_turn = new_msgs[3]
        assert dual_turn["role"] == "assistant"
        assert dual_turn["content"].startswith("__DUAL_READ__")
        dual_json = json.loads(dual_turn["content"].replace("__DUAL_READ__", "", 1))
        assert dual_json["sectores"][0]["tipo"] == "cocina"

        # [DUAL_READ_CONFIRMED] preservado
        assert new_msgs[4]["content"].startswith("[DUAL_READ_CONFIRMED]")

        # Paso 2 preservado
        assert new_msgs[5]["content"].startswith("## PASO 2")

        # "Confirmo" preservado
        assert new_msgs[6]["content"] == "Confirmo"

        # Total: 8 originales → 7 (se descartó "(contexto confirmado)")
        assert len(new_msgs) == 7

    def test_idempotent_second_call_returns_unchanged(self):
        """Idempotencia — condición del PR: correr 2 veces da el mismo
        resultado y la segunda marca changed=False."""
        msgs = _legacy_bernardi_messages()
        bd = _bernardi_breakdown()
        once, changed1 = rehydrate_messages(msgs, bd)
        assert changed1 is True
        twice, changed2 = rehydrate_messages(once, bd)
        assert changed2 is False
        assert once == twice

    def test_no_invention_when_dual_read_missing(self):
        """Si no hay `dual_read_result` en el breakdown, el marker
        __DUAL_READ_CARD_SHOWN__ se descarta en lugar de fabricar data."""
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        new_msgs, changed = rehydrate_messages(msgs, {})
        assert changed is True
        assert len(new_msgs) == 1  # marker descartado
        assert new_msgs[0]["content"] == "brief"

    def test_no_invention_when_context_pending_missing(self):
        """Mismo criterio para context_analysis — post-confirmación
        `context_analysis_pending` se poppea del breakdown. El helper no
        reconstruye la card (acepta perderla) en lugar de fabricar."""
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": "__CONTEXT_ANALYSIS_SHOWN__"},
        ]
        new_msgs, changed = rehydrate_messages(msgs, {"dual_read_result": {}})
        assert changed is True
        assert len(new_msgs) == 1
        assert new_msgs[0]["content"] == "brief"


class TestRehydrateMessagesIdempotence:
    """Condición explícita: quotes sanos quedan intactos."""

    def test_clean_history_is_noop(self):
        """Historial ya limpio (post-#379) → changed=False, identity."""
        msgs = [
            {"role": "user", "content": "cotizar cocina"},
            {
                "role": "assistant",
                "content": '__CONTEXT_ANALYSIS__{"data_known":[]}',
            },
            {"role": "user", "content": '[CONTEXT_CONFIRMED]{"answers":[]}'},
            {
                "role": "assistant",
                "content": '__DUAL_READ__{"sectores":[]}',
            },
            {"role": "user", "content": '[DUAL_READ_CONFIRMED]{"sectores":[]}'},
            {"role": "assistant", "content": "## PASO 2"},
            {"role": "user", "content": "Confirmo"},
        ]
        new_msgs, changed = rehydrate_messages(msgs, {"dual_read_result": {}})
        assert changed is False
        assert new_msgs == msgs

    def test_empty_messages(self):
        assert rehydrate_messages([], {}) == ([], False)
        assert rehydrate_messages(None, {}) == ([], False)

    def test_none_breakdown_still_cleans_contamination(self):
        """Aun sin breakdown: `(contexto confirmado)` y `[TEXTO
        EXTRAÍDO]` se limpian. Los markers `_SHOWN_` se descartan
        (sin data para rehidratar)."""
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "brief\n[TEXTO EXTRAÍDO DEL PDF]\ndump"}]},
            {"role": "user", "content": "(contexto confirmado)"},
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        new_msgs, changed = rehydrate_messages(msgs, None)
        assert changed is True
        # Brief truncado + fake user descartado + marker descartado
        assert len(new_msgs) == 1
        brief_text = new_msgs[0]["content"]
        assert "brief" in brief_text
        assert "TEXTO EXTRAÍDO" not in brief_text


class TestRehydrateContentShape:
    """Tests de edge cases del shape de `content`: string vs list vs
    mixed."""

    def test_content_list_with_text_block_truncated(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "cotizar [TEXTO EXTRAÍDO DEL PDF] dump"},
                ],
            }
        ]
        new_msgs, changed = rehydrate_messages(msgs, {})
        assert changed is True
        # Se normaliza a string
        assert new_msgs[0]["content"] == "cotizar"

    def test_content_fully_contaminated_falls_back_to_placeholder(self):
        """Si todo el content es contaminación, queda placeholder."""
        msgs = [
            {
                "role": "user",
                "content": "[TEXTO EXTRAÍDO DEL PDF]\n dump completo sin brief",
            }
        ]
        new_msgs, changed = rehydrate_messages(msgs, {})
        assert changed is True
        assert new_msgs[0]["content"] == "(adjunto plano)"

    def test_content_with_multiple_markers_truncates_at_first(self):
        """Si aparecen ambos markers, corta en el que esté primero."""
        msgs = [
            {
                "role": "user",
                "content": (
                    "cotizar la cocina"
                    "\n[SISTEMA — EDICIÓN LIBRE]\nhint"
                    "\n[TEXTO EXTRAÍDO DEL PDF]\ndump"
                ),
            }
        ]
        new_msgs, changed = rehydrate_messages(msgs, {})
        assert changed is True
        assert new_msgs[0]["content"] == "cotizar la cocina"

    def test_ignores_legitimate_brackets_in_content(self):
        """Un texto con corchetes que no son markers internos (ej: el
        operador escribe '[x2]') no se toca."""
        msgs = [
            {
                "role": "user",
                "content": "necesito [x2] mesadas iguales",
            }
        ]
        new_msgs, changed = rehydrate_messages(msgs, {})
        assert changed is False
        assert new_msgs == msgs


class TestRehydrateDoesNotTouchBreakdown:
    """Condición del PR: el cálculo/totales no se tocan."""

    def test_breakdown_is_read_not_mutated(self):
        bd = _bernardi_breakdown()
        bd_snapshot = json.loads(json.dumps(bd))
        msgs = _legacy_bernardi_messages()
        rehydrate_messages(msgs, bd)
        # El breakdown no cambia
        assert bd == bd_snapshot

