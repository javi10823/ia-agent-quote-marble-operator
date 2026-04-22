"""Unit tests for card_editor — detector + applier.

No testamos extract_card_patch (requiere LLM call — se testea manual/E2E).
"""
from app.modules.agent.card_editor import (
    is_card_modification_message,
    apply_card_patch,
    format_patch_summary,
    truncate_history_at_card,
    reset_quote_to_pre_context,
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
        """Mismo criterio para context_analysis — si el breakdown no
        tiene `context_analysis_pending` (quote viejo antes de #383, o
        quote que nunca pasó por la card), el helper no fabrica data.
        Nota: post-#383 el handler [CONTEXT_CONFIRMED] preserva
        context_analysis_pending, pero los breakdowns legacy pueden no
        tenerlo."""
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


# ═══════════════════════════════════════════════════════════════════════
# PR #382 — rehydrate usa verified_measurements sobre dual_read_result
# ═══════════════════════════════════════════════════════════════════════
#
# Caso observado por Javi: quote Bernardi rehidratado con #380 mostraba
# las mesadas de cocina vacías en la card del despiece, mientras que
# el mensaje de Valentina en Paso 2 listaba las 3 medidas confirmadas.
#
# Root cause: #380 leía solo `dual_read_result` (estado pre-confirm
# del backend — las mesadas de cocina quedaban vacías esperando que
# el operador las llenara con candidatas sugeridas o edits). Tras la
# confirmación del operador, las medidas reales viven en
# `verified_measurements`.
#
# Fix: el helper prioriza verified_measurements > dual_read_result.


def _bernardi_with_verified_measurements() -> dict:
    """Breakdown de Bernardi post-confirm. `dual_read_result` tiene las
    mesadas de cocina vacías (el estado que el dual_read detectó
    originalmente), pero `verified_measurements` tiene las 3 medidas
    confirmadas por el operador."""
    return {
        "dual_read_result": {
            "sectores": [
                {
                    "id": "cocina", "tipo": "cocina",
                    "tramos": [
                        # Vacías — el dual_read no pudo resolverlas
                        {"id": "t1", "descripcion": "Mesada con pileta",
                         "largo_m": {"valor": 0}, "ancho_m": {"valor": 0}, "m2": {"valor": 0}},
                        {"id": "t2", "descripcion": "Mesada 2",
                         "largo_m": {"valor": 0}, "ancho_m": {"valor": 0}, "m2": {"valor": 0}},
                    ],
                },
                {
                    "id": "isla", "tipo": "isla",
                    "tramos": [
                        # La única que el dual_read resolvió
                        {"id": "t3", "descripcion": "Mesada isla",
                         "largo_m": {"valor": 1.60}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 0.96}},
                    ],
                },
            ],
        },
        "verified_measurements": {
            "sectores": [
                {
                    "id": "cocina", "tipo": "cocina",
                    "tramos": [
                        # Ahora con las medidas confirmadas por el operador
                        {"id": "t1", "descripcion": "Mesada con pileta",
                         "largo_m": {"valor": 2.05}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.23}},
                        {"id": "t2", "descripcion": "Mesada 2",
                         "largo_m": {"valor": 2.95}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.77}},
                    ],
                },
                {
                    "id": "isla", "tipo": "isla",
                    "tramos": [
                        {"id": "t3", "descripcion": "Mesada isla",
                         "largo_m": {"valor": 1.60}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 0.96}},
                    ],
                },
            ],
        },
    }


class TestRehydrateUsesVerifiedMeasurements:
    def test_prefers_verified_over_dual_read_result(self):
        """Bernardi: si hay verified_measurements, la card debe reflejar
        ESOS valores (3 medidas), no dual_read_result (solo isla)."""
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        bd = _bernardi_with_verified_measurements()
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is True
        assert len(new_msgs) == 2

        card_content = new_msgs[1]["content"]
        assert card_content.startswith("__DUAL_READ__")
        parsed = json.loads(card_content.replace("__DUAL_READ__", "", 1))
        # Las 3 mesadas con sus medidas confirmadas
        cocina_tramos = parsed["sectores"][0]["tramos"]
        assert cocina_tramos[0]["largo_m"]["valor"] == 2.05
        assert cocina_tramos[1]["largo_m"]["valor"] == 2.95
        isla_tramo = parsed["sectores"][1]["tramos"][0]
        assert isla_tramo["largo_m"]["valor"] == 1.60

    def test_falls_back_to_dual_read_when_no_verified(self):
        """Sin verified_measurements (quote pre-confirm): usa dual_read_result
        como antes (compat con comportamiento previo)."""
        msgs = [
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        bd = {
            "dual_read_result": {"sectores": [{"tipo": "cocina", "tramos": []}]},
        }
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is True
        card_content = new_msgs[0]["content"]
        parsed = json.loads(card_content.replace("__DUAL_READ__", "", 1))
        assert parsed["sectores"][0]["tipo"] == "cocina"

    def test_regenerates_stale_dual_read_content(self):
        """Regresión del bug observado: un quote rehidratado previamente
        con el helper viejo quedó con `__DUAL_READ__<dual_read_result>`
        (incompleto). Al re-correr el helper con verified_measurements
        presente, debe REGENERAR el content con la fuente autoritativa."""
        bd = _bernardi_with_verified_measurements()
        # Content stale: tiene el dual_read_result (mesadas vacías) embebido
        stale_content = "__DUAL_READ__" + json.dumps(bd["dual_read_result"], ensure_ascii=False)
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": stale_content},
        ]
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is True
        # Regenerado con verified_measurements
        new_content = new_msgs[1]["content"]
        parsed = json.loads(new_content.replace("__DUAL_READ__", "", 1))
        cocina_tramos = parsed["sectores"][0]["tramos"]
        assert cocina_tramos[0]["largo_m"]["valor"] == 2.05
        assert cocina_tramos[1]["largo_m"]["valor"] == 2.95

    def test_idempotent_with_verified_source(self):
        """Run 2x → segundo call changed=False (el content ya tiene el
        JSON correcto desde el primero)."""
        bd = _bernardi_with_verified_measurements()
        msgs = [
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        once, changed1 = rehydrate_messages(msgs, bd)
        assert changed1 is True
        twice, changed2 = rehydrate_messages(once, bd)
        assert changed2 is False
        assert once == twice

    def test_preserves_content_when_already_matches_source(self):
        """Si el content actual coincide exactamente con dual_read_source,
        no se toca (idempotencia fuerte)."""
        bd = _bernardi_with_verified_measurements()
        good_content = (
            "__DUAL_READ__"
            + json.dumps(bd["verified_measurements"], ensure_ascii=False)
        )
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": good_content},
        ]
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is False
        assert new_msgs == msgs

    def test_stale_content_without_verified_preserved(self):
        """Si solo hay dual_read_result (sin verified), y el content
        actual `__DUAL_READ__<json>` ya coincide con dual_read_result,
        no se toca. Defensa: no regenerar sin causa."""
        bd = {"dual_read_result": {"sectores": [{"tipo": "cocina"}]}}
        current = "__DUAL_READ__" + json.dumps(bd["dual_read_result"], ensure_ascii=False)
        msgs = [
            {"role": "assistant", "content": current},
        ]
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is False
        assert new_msgs == msgs

    def test_invalid_json_in_stale_content_regenerated(self):
        """Content con `__DUAL_READ__<garbage>` (JSON roto) — el helper
        detecta el parse error y regenera con la fuente actual en lugar
        de preservar el garbage."""
        bd = _bernardi_with_verified_measurements()
        msgs = [
            {"role": "assistant", "content": "__DUAL_READ__{not valid json"},
        ]
        new_msgs, changed = rehydrate_messages(msgs, bd)
        assert changed is True
        parsed = json.loads(
            new_msgs[0]["content"].replace("__DUAL_READ__", "", 1)
        )
        # Regenerado con verified_measurements
        assert parsed["sectores"][0]["tramos"][0]["largo_m"]["valor"] == 2.05


# ═══════════════════════════════════════════════════════════════════════
# PR #383 — truncate_history_at_card (corte + regeneración al reabrir)
# ═══════════════════════════════════════════════════════════════════════
#
# Regla del operador: "Editar despiece / Editar contexto" debe cortar
# el chat desde la card respectiva y regenerarla con el estado nuevo.
# Nunca se borra lo previo a la card (brief del operador + comentarios
# iniciales). Nunca se deja historial viejo mezclado con estado nuevo.


def _bernardi_confirmed_history() -> list[dict]:
    """Historial completo de un quote que pasó contexto + medidas +
    Paso 2. Base para los tests de corte."""
    return [
        {"role": "user", "content": "cotizar cocina + isla en pura prima"},
        {"role": "assistant", "content": '__CONTEXT_ANALYSIS__{"data_known":[{"field":"Material","value":"Pura Prima"}],"pending_questions":[]}'},
        {"role": "user", "content": '[CONTEXT_CONFIRMED]{"answers":[]}'},
        {"role": "assistant", "content": '__DUAL_READ__{"sectores":[{"id":"cocina","tramos":[{"largo_m":{"valor":2.05}}]}]}'},
        {"role": "user", "content": '[DUAL_READ_CONFIRMED]{"sectores":[]}'},
        {"role": "assistant", "content": "## PASO 2 — Validación\nMaterial: PURASTONE\nTotal: $797.177"},
        {"role": "user", "content": "Confirmo"},
    ]


class TestTruncateHistoryAtCard:
    def test_truncates_at_dual_read_and_regenerates(self):
        """Corte en __DUAL_READ__: preserva brief + context + confirmación
        de contexto; descarta card vieja + [DUAL_READ_CONFIRMED] + Paso 2
        + confirmación del operador. Appendea card regenerada con payload
        nuevo."""
        msgs = _bernardi_confirmed_history()
        new_payload = {"sectores": [{"id": "cocina", "tramos": [{"largo_m": {"valor": 2.20}}]}]}

        new_msgs, changed = truncate_history_at_card(
            msgs,
            marker_prefix="__DUAL_READ__",
            new_payload=new_payload,
        )
        assert changed is True

        # Pre-card: brief + CONTEXT_ANALYSIS + CONTEXT_CONFIRMED → 3 turns.
        # Post-card: se descartan los 4 posteriores (card vieja, confirmación,
        # Paso 2 markdown, "Confirmo").
        # Nueva card regenerada → total 4 turns.
        assert len(new_msgs) == 4

        # Brief preservado
        assert new_msgs[0]["content"] == "cotizar cocina + isla en pura prima"
        # Card de contexto preservada
        assert new_msgs[1]["content"].startswith("__CONTEXT_ANALYSIS__")
        # Confirmación de contexto preservada
        assert new_msgs[2]["content"].startswith("[CONTEXT_CONFIRMED]")
        # Card de despiece regenerada con el payload nuevo
        assert new_msgs[3]["role"] == "assistant"
        assert new_msgs[3]["content"].startswith("__DUAL_READ__")
        parsed = json.loads(new_msgs[3]["content"].replace("__DUAL_READ__", "", 1))
        assert parsed["sectores"][0]["tramos"][0]["largo_m"]["valor"] == 2.20

    def test_truncates_at_context_analysis_and_regenerates(self):
        """Corte en __CONTEXT_ANALYSIS__: preserva solo el brief."""
        msgs = _bernardi_confirmed_history()
        new_payload = {"data_known": [{"field": "Material", "value": "PURASTONE"}]}

        new_msgs, changed = truncate_history_at_card(
            msgs,
            marker_prefix="__CONTEXT_ANALYSIS__",
            new_payload=new_payload,
        )
        assert changed is True

        # Solo el brief + card de contexto regenerada = 2 turns.
        assert len(new_msgs) == 2
        assert new_msgs[0]["content"] == "cotizar cocina + isla en pura prima"
        assert new_msgs[1]["content"].startswith("__CONTEXT_ANALYSIS__")
        parsed = json.loads(new_msgs[1]["content"].replace("__CONTEXT_ANALYSIS__", "", 1))
        assert parsed["data_known"][0]["value"] == "PURASTONE"

    def test_no_marker_returns_unchanged(self):
        """Si el historial no tiene la card, no hay nada que cortar."""
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": "Hola, te falta el plano."},
        ]
        new_msgs, changed = truncate_history_at_card(
            msgs,
            marker_prefix="__DUAL_READ__",
            new_payload={"sectores": []},
        )
        assert changed is False
        assert new_msgs == msgs

    def test_empty_messages_noop(self):
        new_msgs, changed = truncate_history_at_card(
            [],
            marker_prefix="__DUAL_READ__",
            new_payload={"x": 1},
        )
        assert changed is False
        assert new_msgs == []

    def test_none_messages_noop(self):
        new_msgs, changed = truncate_history_at_card(
            None,
            marker_prefix="__DUAL_READ__",
            new_payload={"x": 1},
        )
        assert changed is False
        assert new_msgs == []

    def test_cuts_at_last_card_when_multiple(self):
        """Si hay múltiples __DUAL_READ__ (ej: card re-emitida después
        de un patch desde chat), cortar al último — es el estado más
        reciente del despiece en el historial."""
        msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": '__DUAL_READ__{"v":1}'},  # vieja
            {"role": "user", "content": "agregá un zócalo"},
            {"role": "assistant", "content": '__DUAL_READ__{"v":2}'},  # última
            {"role": "user", "content": "[DUAL_READ_CONFIRMED]{}"},
            {"role": "assistant", "content": "Paso 2..."},
        ]
        new_msgs, changed = truncate_history_at_card(
            msgs,
            marker_prefix="__DUAL_READ__",
            new_payload={"v": 3},
        )
        assert changed is True
        # brief + card vieja + "agregá zócalo" + card regenerada = 4
        assert len(new_msgs) == 4
        assert new_msgs[1]["content"] == '__DUAL_READ__{"v":1}'  # primera preservada
        assert new_msgs[2]["content"] == "agregá un zócalo"
        last_parsed = json.loads(new_msgs[3]["content"].replace("__DUAL_READ__", "", 1))
        assert last_parsed["v"] == 3

    def test_no_payload_strips_card_without_regenerating(self):
        """new_payload=None → corta sin re-emitir. Caso defensivo."""
        msgs = _bernardi_confirmed_history()
        new_msgs, changed = truncate_history_at_card(
            msgs,
            marker_prefix="__DUAL_READ__",
            new_payload=None,
        )
        assert changed is True
        # brief + ctx card + ctx_confirmed = 3 turns
        assert len(new_msgs) == 3
        assert not any(
            m.get("content", "").startswith("__DUAL_READ__")
            for m in new_msgs if isinstance(m.get("content"), str)
        )

    def test_preserves_brief_with_plano_attachment(self):
        """Brief con content como lista (user subió plano) se preserva
        tal cual — incluyendo los blocks de image."""
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "cotizar"},
                    {"type": "image", "source": {"data": "..."}},
                ],
            },
            {"role": "assistant", "content": '__DUAL_READ__{}'},
        ]
        new_msgs, changed = truncate_history_at_card(
            msgs,
            marker_prefix="__DUAL_READ__",
            new_payload={"x": 1},
        )
        assert changed is True
        # Brief con image block intacto
        assert isinstance(new_msgs[0]["content"], list)
        assert len(new_msgs[0]["content"]) == 2

    def test_idempotent_with_same_payload(self):
        """Llamar 2 veces con el mismo payload produce el mismo resultado."""
        msgs = _bernardi_confirmed_history()
        payload = {"v": "new"}
        once, _ = truncate_history_at_card(
            msgs, marker_prefix="__DUAL_READ__", new_payload=payload,
        )
        twice, _ = truncate_history_at_card(
            once, marker_prefix="__DUAL_READ__", new_payload=payload,
        )
        assert once == twice


class TestResetQuoteToPreContext:
    def test_clears_verified_context_analysis_and_paso2(self):
        bd = {
            "dual_read_result": {"sectores": []},
            "context_analysis_pending": {"data_known": []},
            "verified_context_analysis": {"answers": [{"q": 1, "a": "X"}]},
            "verified_context": "[MEDIDAS...]",
            "verified_measurements": {"sectores": []},
            "material_name": "PURASTONE",
            "total_ars": 797177,
            "brief_analysis": {"client_name": "Erica Bernardi"},
        }
        reset = reset_quote_to_pre_context(bd)
        # Paso 2 + verified_context_analysis limpio
        assert "verified_context_analysis" not in reset
        assert "verified_context" not in reset
        assert "verified_measurements" not in reset
        assert "material_name" not in reset
        assert "total_ars" not in reset
        # Preservados
        assert reset["dual_read_result"] == {"sectores": []}
        assert reset["context_analysis_pending"] == {"data_known": []}
        assert reset["brief_analysis"] == {"client_name": "Erica Bernardi"}

    def test_preserves_context_analysis_pending(self):
        """context_analysis_pending es el snapshot de la card original.
        Es la fuente para regenerarla al reabrir."""
        bd = {
            "verified_context_analysis": {"answers": []},
            "context_analysis_pending": {"data_known": [{"field": "x"}]},
        }
        reset = reset_quote_to_pre_context(bd)
        assert reset["context_analysis_pending"] == {"data_known": [{"field": "x"}]}

    def test_empty_breakdown(self):
        assert reset_quote_to_pre_context({}) == {}
        assert reset_quote_to_pre_context(None) == {}

    def test_does_not_mutate_input(self):
        bd = {
            "verified_context_analysis": {"answers": []},
            "verified_context": "X",
            "context_analysis_pending": {"data_known": []},
        }
        snapshot = json.loads(json.dumps(bd))
        reset_quote_to_pre_context(bd)
        assert bd == snapshot

    def test_idempotent(self):
        bd = {
            "verified_context_analysis": {"answers": []},
            "verified_context": "X",
            "context_analysis_pending": {"data_known": []},
        }
        once = reset_quote_to_pre_context(bd)
        twice = reset_quote_to_pre_context(once)
        assert once == twice

