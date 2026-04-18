"""Tests del módulo required_fields — campos obligatorios por tipo de
trabajo. Hoy cubre material + localidad (siguientes iteraciones: descuento,
forma de pago, particular vs edificio)."""
from app.modules.quote_engine.required_fields import (
    apply_localidad_answer,
    apply_material_answer,
    detect_required_field_questions,
    has_localidad,
    has_material,
)


def _dual(sectores: list | None = None) -> dict:
    return {"sectores": sectores or [], "source": "MULTI_CROP"}


# ── has_material ─────────────────────────────────────────────────────────────

class TestHasMaterial:
    def test_from_quote_column(self):
        assert has_material("", {"material": "Silestone Blanco Norte"}, _dual()) is True

    def test_from_brief_keyword(self):
        assert has_material("material puraprima onix white", None, _dual()) is True
        assert has_material("cliente juan cotiza silestone", None, _dual()) is True
        assert has_material("granito negro brasil", None, _dual()) is True

    def test_absent_returns_false(self):
        assert has_material("cliente juan", None, _dual()) is False
        assert has_material("", None, _dual()) is False


class TestHasLocalidad:
    def test_from_quote_column(self):
        assert has_localidad("", {"localidad": "Funes"}) is True

    def test_from_brief_keyword(self):
        assert has_localidad("cliente juan en rosario", None) is True
        assert has_localidad("zona funes", None) is True
        assert has_localidad("entrega en puerto san martín", None) is True

    def test_absent_returns_false(self):
        assert has_localidad("cliente juan material silestone", None) is False


# ── detect_required_field_questions ─────────────────────────────────────────

class TestDetectRequiredFieldQuestions:
    def test_emits_both_when_missing(self):
        qs = detect_required_field_questions("cliente juan", None, _dual())
        ids = [q["id"] for q in qs]
        assert "material" in ids
        assert "localidad" in ids

    def test_skips_when_quote_has_material(self):
        qs = detect_required_field_questions(
            "", {"material": "Silestone"}, _dual()
        )
        assert all(q["id"] != "material" for q in qs)

    def test_skips_when_brief_has_both(self):
        qs = detect_required_field_questions(
            "cliente juan material silestone blanco norte en rosario", None, _dual()
        )
        assert qs == []

    def test_material_question_shape(self):
        qs = detect_required_field_questions("cliente juan", None, _dual())
        mat_q = next(q for q in qs if q["id"] == "material")
        vals = {o["value"] for o in mat_q["options"]}
        assert {"silestone", "granito", "dekton", "custom"} <= vals

    def test_localidad_question_shape(self):
        qs = detect_required_field_questions("", None, _dual())
        loc_q = next(q for q in qs if q["id"] == "localidad")
        vals = {o["value"] for o in loc_q["options"]}
        assert {"rosario", "custom"} <= vals


# ── Apply answers ────────────────────────────────────────────────────────────

class TestApplyMaterialAnswer:
    def test_preset_records_hint(self):
        result = _dual()
        apply_material_answer(result, {"id": "material", "value": "silestone", "detail": "Blanco Norte"})
        assert "silestone" in result["material_hint"].lower()
        assert "Blanco Norte" in result["material_hint"]

    def test_custom_requires_detail(self):
        result = _dual()
        apply_material_answer(result, {"id": "material", "value": "custom", "detail": "Piedra Patagónica"})
        assert result["material_hint"] == "Piedra Patagónica"

    def test_custom_without_detail_noop(self):
        result = _dual()
        apply_material_answer(result, {"id": "material", "value": "custom", "detail": ""})
        assert "material_hint" not in result


class TestApplyLocalidadAnswer:
    def test_preset(self):
        result = _dual()
        apply_localidad_answer(result, {"id": "localidad", "value": "rosario"})
        assert result["localidad_hint"] == "rosario"

    def test_custom(self):
        result = _dual()
        apply_localidad_answer(result, {"id": "localidad", "value": "custom", "detail": "Villa Eloisa"})
        assert result["localidad_hint"] == "Villa Eloisa"

    def test_custom_without_detail_noop(self):
        result = _dual()
        apply_localidad_answer(result, {"id": "localidad", "value": "custom", "detail": ""})
        assert "localidad_hint" not in result
