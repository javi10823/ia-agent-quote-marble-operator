"""Tests de pending_questions — detección + aplicación de respuestas.

Principio: nunca asumir. Si falta info en brief y plano, preguntar y
bloquear Confirmar hasta que el operador conteste.
"""
from app.modules.quote_engine.pending_questions import (
    apply_answers,
    apply_zocalos_answer,
    brief_mentions_zocalos,
    detect_pending_questions,
)


def _make_dual_result(has_zocalos: bool = False) -> dict:
    zocalos = [{"lado": "trasero", "ml": 2.05, "alto_m": 0.07}] if has_zocalos else []
    return {
        "sectores": [
            {
                "id": "s1",
                "tipo": "cocina",
                "tramos": [
                    {
                        "id": "t1",
                        "descripcion": "Mesada 1",
                        "largo_m": {"valor": 2.05, "status": "CONFIRMADO"},
                        "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
                        "m2": {"valor": 1.23, "status": "CONFIRMADO"},
                        "zocalos": zocalos,
                        "frentin": [],
                        "regrueso": [],
                    }
                ],
                "ambiguedades": [],
            }
        ],
        "source": "MULTI_CROP",
    }


# ── Brief keyword detection ──────────────────────────────────────────────────

class TestBriefMentionsZocalos:
    def test_explicit_yes(self):
        assert brief_mentions_zocalos("cocina con zocalos") == "yes"
        assert brief_mentions_zocalos("Cliente Juan, lleva zócalos") == "yes"
        assert brief_mentions_zocalos("zócalos sí, alto 5cm") == "yes"

    def test_explicit_no(self):
        assert brief_mentions_zocalos("cocina sin zocalos") == "no"
        assert brief_mentions_zocalos("no lleva zocalos") == "no"
        assert brief_mentions_zocalos("no van zócalos") == "no"

    def test_not_mentioned_returns_none(self):
        assert brief_mentions_zocalos("cliente juan material silestone") is None
        assert brief_mentions_zocalos("") is None
        assert brief_mentions_zocalos("") is None


# ── Zocalos question detector ────────────────────────────────────────────────

class TestDetectZocalosQuestion:
    def test_emits_when_brief_silent_and_plano_no_zocalos(self):
        """Caso Bernardi: brief no dice nada, plano tampoco → preguntar."""
        qs = detect_pending_questions(
            brief="material puraprima onix white cliente Erica",
            dual_result=_make_dual_result(has_zocalos=False),
        )
        assert len(qs) == 1
        assert qs[0]["id"] == "zocalos"
        assert len(qs[0]["options"]) == 3
        # Sí con default, Sí custom, No lleva
        vals = [o["value"] for o in qs[0]["options"]]
        assert "default_trasero" in vals
        assert "custom" in vals
        assert "no" in vals

    def test_skips_when_brief_says_con_zocalos(self):
        qs = detect_pending_questions(
            brief="cocina con zocalos",
            dual_result=_make_dual_result(has_zocalos=False),
        )
        assert all(q["id"] != "zocalos" for q in qs)

    def test_skips_when_brief_says_sin_zocalos(self):
        qs = detect_pending_questions(
            brief="cocina sin zocalos",
            dual_result=_make_dual_result(has_zocalos=False),
        )
        assert all(q["id"] != "zocalos" for q in qs)

    def test_skips_when_card_already_has_zocalos(self):
        """Si dual_read ya detectó zócalos (ml > 0), no preguntar."""
        qs = detect_pending_questions(
            brief="",
            dual_result=_make_dual_result(has_zocalos=True),
        )
        assert all(q["id"] != "zocalos" for q in qs)


# ── Apply answers ────────────────────────────────────────────────────────────

class TestApplyZocalosAnswer:
    def test_default_trasero_adds_zocalo_per_tramo(self):
        result = _make_dual_result(has_zocalos=False)
        # Agregar un segundo tramo para verificar que aplica a todos
        result["sectores"][0]["tramos"].append({
            "id": "t2",
            "descripcion": "Mesada 2",
            "largo_m": {"valor": 2.95, "status": "CONFIRMADO"},
            "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
            "m2": {"valor": 1.77, "status": "CONFIRMADO"},
            "zocalos": [],
            "frentin": [],
            "regrueso": [],
        })
        apply_zocalos_answer(result, {"id": "zocalos", "value": "default_trasero"})
        t1_z = result["sectores"][0]["tramos"][0]["zocalos"]
        t2_z = result["sectores"][0]["tramos"][1]["zocalos"]
        assert len(t1_z) == 1
        assert t1_z[0]["lado"] == "trasero"
        assert t1_z[0]["ml"] == 2.05
        assert t1_z[0]["alto_m"] == 0.07
        assert t1_z[0]["source"] == "brief_rule"
        assert len(t2_z) == 1
        assert t2_z[0]["ml"] == 2.95

    def test_no_answer_does_nothing(self):
        result = _make_dual_result(has_zocalos=False)
        apply_zocalos_answer(result, {"id": "zocalos", "value": "no"})
        assert result["sectores"][0]["tramos"][0]["zocalos"] == []

    def test_custom_preserves_detail(self):
        result = _make_dual_result(has_zocalos=False)
        apply_zocalos_answer(
            result,
            {"id": "zocalos", "value": "custom", "detail": "10cm trasero y lateral izq", "alto_m": 0.10},
        )
        z = result["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["source"] == "brief_rule_custom"
        assert z["alto_m"] == 0.10
        assert z["detail_raw"] == "10cm trasero y lateral izq"

    def test_does_not_overwrite_existing_zocalos(self):
        """Si dual_read ya puso zócalos, la respuesta del brief no pisa."""
        result = _make_dual_result(has_zocalos=True)
        apply_zocalos_answer(result, {"id": "zocalos", "value": "default_trasero"})
        # Aún hay solo 1 zócalo (el original), no se agregó otro
        assert len(result["sectores"][0]["tramos"][0]["zocalos"]) == 1

    def test_apply_answers_entry_point(self):
        """apply_answers dispatchea por question id."""
        result = _make_dual_result(has_zocalos=False)
        apply_answers(result, [
            {"id": "zocalos", "value": "default_trasero"},
            {"id": "unknown_id", "value": "whatever"},  # ignored
        ])
        assert len(result["sectores"][0]["tramos"][0]["zocalos"]) == 1


# ── Pileta simple/doble detector (PR C) ─────────────────────────────────────

def _make_cocina_with_pileta():
    return {
        "sectores": [{
            "id": "s1",
            "tipo": "cocina",
            "tramos": [{
                "id": "t1",
                "descripcion": "Mesada con pileta",
                "largo_m": {"valor": 2.05, "status": "CONFIRMADO"},
                "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
                "m2": {"valor": 1.23, "status": "CONFIRMADO"},
                "zocalos": [],
                "frentin": [],
                "regrueso": [],
                "features": {"has_pileta": True},
            }],
            "ambiguedades": [],
        }],
        "source": "MULTI_CROP",
    }


class TestDetectPiletaTypeQuestion:
    def test_emits_for_cocina_with_pileta_no_mention(self):
        qs = detect_pending_questions("cliente juan material silestone", _make_cocina_with_pileta())
        pileta_qs = [q for q in qs if q["id"] == "pileta_simple_doble"]
        assert len(pileta_qs) == 1
        # Nunca preguntar apoyo/empotrada en cocina — solo simple vs doble
        options = pileta_qs[0]["options"]
        assert len(options) == 2
        assert {o["value"] for o in options} == {"simple", "doble"}
        assert not any("apoyo" in o["value"].lower() for o in options)

    def test_skips_when_brief_says_doble(self):
        qs = detect_pending_questions("cocina con pileta doble", _make_cocina_with_pileta())
        assert all(q["id"] != "pileta_simple_doble" for q in qs)

    def test_skips_when_brief_says_simple(self):
        qs = detect_pending_questions("cocina con bacha simple", _make_cocina_with_pileta())
        assert all(q["id"] != "pileta_simple_doble" for q in qs)

    def test_skips_when_card_has_sink_double_feature(self):
        result = _make_cocina_with_pileta()
        result["sectores"][0]["tramos"][0]["features"]["sink_double"] = True
        qs = detect_pending_questions("", result)
        assert all(q["id"] != "pileta_simple_doble" for q in qs)

    def test_skips_when_no_cocina_sector(self):
        result = _make_cocina_with_pileta()
        result["sectores"][0]["tipo"] = "baño"
        qs = detect_pending_questions("", result)
        assert all(q["id"] != "pileta_simple_doble" for q in qs)

    def test_skips_when_no_pileta_detected(self):
        """Sin pileta en card ni brief → no preguntar."""
        result = _make_dual_result(has_zocalos=False)  # no pileta
        qs = detect_pending_questions("cliente juan", result)
        assert all(q["id"] != "pileta_simple_doble" for q in qs)


class TestApplyPiletaTypeAnswer:
    def test_doble_sets_sink_type_on_cocina_sector(self):
        result = _make_cocina_with_pileta()
        apply_answers(result, [{"id": "pileta_simple_doble", "value": "doble"}])
        sector = result["sectores"][0]
        assert sector["sink_type"]["basin_count"] == "doble"
        assert sector["sink_type"]["mount_type"] == "abajo"
        assert sector["pileta_type_hint"] == "empotrada"

    def test_simple_sets_sink_type_simple(self):
        result = _make_cocina_with_pileta()
        apply_answers(result, [{"id": "pileta_simple_doble", "value": "simple"}])
        assert result["sectores"][0]["sink_type"]["basin_count"] == "simple"

    def test_noop_on_invalid_value(self):
        result = _make_cocina_with_pileta()
        apply_answers(result, [{"id": "pileta_simple_doble", "value": "invalid"}])
        assert "sink_type" not in result["sectores"][0]
