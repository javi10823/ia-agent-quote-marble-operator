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
