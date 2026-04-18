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
        zocalos_qs = [q for q in qs if q["id"] == "zocalos"]
        assert len(zocalos_qs) == 1
        assert len(zocalos_qs[0]["options"]) == 3
        # Sí con default, Sí custom, No lleva
        vals = [o["value"] for o in zocalos_qs[0]["options"]]
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
    def test_emits_for_cocina_always(self):
        """Regla nueva: en cocina siempre preguntar (pileta existe + tipo).
        Cubre casos donde el dual_read no detectó pileta."""
        qs = detect_pending_questions("cliente juan", _make_dual_result())
        pileta_qs = [q for q in qs if q["id"] == "pileta_simple_doble"]
        assert len(pileta_qs) == 1
        # 3 opciones: simple / doble / no (nunca apoyo en cocina)
        options = pileta_qs[0]["options"]
        assert len(options) == 3
        assert {o["value"] for o in options} == {"simple", "doble", "no"}
        assert not any("apoyo" in o["value"].lower() for o in options)

    def test_skips_when_brief_says_doble(self):
        qs = detect_pending_questions("cocina con pileta doble", _make_cocina_with_pileta())
        assert all(q["id"] != "pileta_simple_doble" for q in qs)

    def test_skips_when_brief_says_simple(self):
        qs = detect_pending_questions("cocina con bacha simple", _make_cocina_with_pileta())
        assert all(q["id"] != "pileta_simple_doble" for q in qs)

    def test_skips_when_brief_says_sin_pileta(self):
        qs = detect_pending_questions("cocina sin pileta", _make_cocina_with_pileta())
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


# ── PR D: Isla profundidad / patas / colocación / anafe count ───────────────

def _make_with_isla(ancho_status: str = "CONFIRMADO", ancho_val: float = 0.60):
    return {
        "sectores": [
            {
                "id": "s1",
                "tipo": "cocina",
                "tramos": [],
                "ambiguedades": [],
            },
            {
                "id": "s2",
                "tipo": "isla",
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Isla",
                    "largo_m": {"valor": 1.60, "status": "CONFIRMADO"},
                    "ancho_m": {"valor": ancho_val, "status": ancho_status},
                    "m2": {"valor": round(1.60 * ancho_val, 2), "status": ancho_status},
                    "zocalos": [],
                    "frentin": [],
                    "regrueso": [],
                }],
                "ambiguedades": [],
            }
        ],
        "source": "MULTI_CROP",
    }


class TestDetectIslaProfundidad:
    def test_always_emits_when_isla_present(self):
        """Regla nueva: siempre preguntar profundidad isla cuando hay isla."""
        result = _make_with_isla(ancho_status="CONFIRMADO", ancho_val=0.60)
        qs = detect_pending_questions("", result)
        assert any(q["id"] == "isla_profundidad" for q in qs)

    def test_emits_when_ancho_is_dudoso(self):
        result = _make_with_isla(ancho_status="DUDOSO")
        qs = detect_pending_questions("", result)
        assert any(q["id"] == "isla_profundidad" for q in qs)

    def test_skips_when_brief_gives_profundidad_explicit(self):
        """Skip solo si brief da la profundidad explícita."""
        result = _make_with_isla(ancho_status="CONFIRMADO", ancho_val=0.60)
        qs = detect_pending_questions("isla de 0.80", result)
        assert all(q["id"] != "isla_profundidad" for q in qs)
        qs2 = detect_pending_questions("profundidad isla 0.70", result)
        assert all(q["id"] != "isla_profundidad" for q in qs2)

    def test_emits_alongside_isla_presence_when_no_isla_sector(self):
        """Nueva conducta: aunque no haya sector isla, si la pregunta
        isla_presence se emite, profundidad y patas van juntas (cascada).
        Se ocultan en frontend cuando operador responde 'no' a presence."""
        qs = detect_pending_questions("", _make_cocina_with_pileta())
        ids = [q["id"] for q in qs]
        assert "isla_presence" in ids
        assert "isla_profundidad" in ids
        assert "isla_patas" in ids

    def test_skips_when_brief_says_sin_isla(self):
        """Si brief niega isla, ni presence ni detalles se emiten."""
        qs = detect_pending_questions("cocina sin isla", _make_cocina_with_pileta())
        ids = [q["id"] for q in qs]
        assert "isla_profundidad" not in ids
        assert "isla_patas" not in ids
        assert "isla_presence" not in ids


class TestApplyIslaProfundidad:
    def test_060_preset_sets_ancho_and_recalcs_m2(self):
        result = _make_with_isla(ancho_status="DUDOSO", ancho_val=2.35)
        apply_answers(result, [{"id": "isla_profundidad", "value": "0.60"}])
        t = result["sectores"][1]["tramos"][0]
        assert t["ancho_m"]["valor"] == 0.60
        assert t["ancho_m"]["status"] == "CONFIRMADO"
        assert t["m2"]["valor"] == round(1.60 * 0.60, 2)

    def test_custom_value_parsed(self):
        result = _make_with_isla(ancho_status="DUDOSO", ancho_val=2.35)
        apply_answers(result, [{"id": "isla_profundidad", "value": "custom", "detail": "0.80"}])
        assert result["sectores"][1]["tramos"][0]["ancho_m"]["valor"] == 0.80

    def test_invalid_custom_is_noop(self):
        result = _make_with_isla(ancho_status="DUDOSO", ancho_val=2.35)
        apply_answers(result, [{"id": "isla_profundidad", "value": "custom", "detail": "gigante"}])
        # Valor original preservado
        assert result["sectores"][1]["tramos"][0]["ancho_m"]["valor"] == 2.35


class TestDetectIslaPatas:
    def test_always_emits_when_isla_present(self):
        qs = detect_pending_questions("", _make_with_isla())
        assert any(q["id"] == "isla_patas" for q in qs)

    def test_has_frontal_and_ambos_laterales_option(self):
        qs = detect_pending_questions("", _make_with_isla())
        q = next(q for q in qs if q["id"] == "isla_patas")
        vals = {o["value"] for o in q["options"]}
        assert "frontal_y_ambos_laterales" in vals
        assert "solo_frontal" in vals
        assert "solo_laterales" in vals
        assert "no" in vals


class TestApplyIslaPatas:
    def test_frontal_y_ambos_laterales(self):
        result = _make_with_isla()
        apply_answers(result, [{"id": "isla_patas", "value": "frontal_y_ambos_laterales", "alto_m": 0.85}])
        sector_isla = result["sectores"][1]
        assert sector_isla["patas"]["sides"] == ["frontal", "lateral_izq", "lateral_der"]
        assert sector_isla["patas"]["alto_m"] == 0.85

    def test_no_empty_sides(self):
        result = _make_with_isla()
        apply_answers(result, [{"id": "isla_patas", "value": "no"}])
        assert result["sectores"][1]["patas"]["sides"] == []


class TestDetectColocacion:
    def test_emits_when_brief_silent(self):
        qs = detect_pending_questions("cliente juan", _make_dual_result())
        assert any(q["id"] == "colocacion" for q in qs)

    def test_skips_when_brief_says_con_colocacion(self):
        qs = detect_pending_questions("cliente juan con colocacion", _make_dual_result())
        assert all(q["id"] != "colocacion" for q in qs)

    def test_skips_when_brief_says_sin_colocacion(self):
        qs = detect_pending_questions("cliente juan sin colocacion", _make_dual_result())
        assert all(q["id"] != "colocacion" for q in qs)


class TestApplyColocacion:
    def test_si_sets_flag_true(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "colocacion", "value": "si"}])
        assert result["colocacion"] is True

    def test_no_sets_flag_false(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "colocacion", "value": "no"}])
        assert result["colocacion"] is False


class TestDetectAnafeCount:
    def _with_cooktop(self, count: int):
        return {
            "sectores": [{
                "id": "s1", "tipo": "cocina",
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Mesada",
                    "largo_m": {"valor": 2.95, "status": "CONFIRMADO"},
                    "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
                    "m2": {"valor": 1.77, "status": "CONFIRMADO"},
                    "zocalos": [], "frentin": [], "regrueso": [],
                    "features": {"cooktop_groups": count},
                }],
                "ambiguedades": [],
            }],
            "source": "MULTI_CROP",
        }

    def test_emits_always_in_cocina(self):
        """Regla nueva: siempre preguntar anafe en cocina (yes/no + count)."""
        qs = detect_pending_questions("", self._with_cooktop(0))
        assert any(q["id"] == "anafe_count" for q in qs)

    def test_emits_when_card_detects_multiple(self):
        qs = detect_pending_questions("", self._with_cooktop(2))
        assert any(q["id"] == "anafe_count" for q in qs)

    def test_skips_when_brief_explicit_count(self):
        qs = detect_pending_questions("1 anafe", self._with_cooktop(2))
        assert all(q["id"] != "anafe_count" for q in qs)

    def test_skips_when_brief_says_sin_anafe(self):
        qs = detect_pending_questions("sin anafe", self._with_cooktop(0))
        assert all(q["id"] != "anafe_count" for q in qs)

    def test_skips_when_no_cocina_sector(self):
        r = self._with_cooktop(0)
        r["sectores"][0]["tipo"] = "baño"
        qs = detect_pending_questions("", r)
        assert all(q["id"] != "anafe_count" for q in qs)


class TestApplyAnafeCount:
    def test_2_sets_anafe_qty(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "anafe_count", "value": "2"}])
        assert result["anafe"] is True
        assert result["anafe_qty"] == 2

    def test_0_disables(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "anafe_count", "value": "0"}])
        assert result["anafe"] is False
        assert result["anafe_qty"] == 0

    def test_3plus_with_detail(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "anafe_count", "value": "3", "detail": "4"}])
        assert result["anafe_qty"] == 4


# ── PR G revision: isla_presence + alzada ───────────────────────────────────

class TestDetectIslaPresence:
    def test_emits_when_isla_not_detected_and_brief_silent(self):
        """Cocina sin isla detectada + brief no menciona isla → preguntar."""
        qs = detect_pending_questions("cliente juan cocina", _make_dual_result())
        assert any(q["id"] == "isla_presence" for q in qs)

    def test_skips_when_isla_already_detected(self):
        result = _make_with_isla()
        qs = detect_pending_questions("", result)
        assert all(q["id"] != "isla_presence" for q in qs)

    def test_skips_when_brief_says_sin_isla(self):
        qs = detect_pending_questions("cocina sin isla", _make_dual_result())
        assert all(q["id"] != "isla_presence" for q in qs)

    def test_skips_when_brief_mentions_isla(self):
        # Brief la menciona → no preguntar existencia (otras preguntan detalles)
        qs = detect_pending_questions("cocina con isla central", _make_dual_result())
        assert all(q["id"] != "isla_presence" for q in qs)


class TestApplyIslaPresence:
    def test_yes_sets_confirmed_flag(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "isla_presence", "value": "yes"}])
        assert result.get("isla_confirmed_by_operator") is True

    def test_no_removes_isla_sector(self):
        result = _make_with_isla()
        apply_answers(result, [{"id": "isla_presence", "value": "no"}])
        assert not any((s.get("tipo") or "").lower() == "isla" for s in result["sectores"])
        assert result.get("isla_excluded_by_operator") is True


class TestDetectAlzada:
    def test_emits_in_cocina_when_brief_silent(self):
        qs = detect_pending_questions("cliente juan", _make_dual_result())
        assert any(q["id"] == "alzada" for q in qs)

    def test_skips_when_brief_says_con_alzada(self):
        qs = detect_pending_questions("con alzada de 10", _make_dual_result())
        assert all(q["id"] != "alzada" for q in qs)

    def test_skips_when_brief_says_sin_alzada(self):
        qs = detect_pending_questions("sin alzada", _make_dual_result())
        assert all(q["id"] != "alzada" for q in qs)


class TestApplyAlzada:
    def test_preset_10cm(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "alzada", "value": "10"}])
        assert result["alzada"] is True
        assert result["alzada_alto_m"] == 0.10

    def test_no_sets_false(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "alzada", "value": "no"}])
        assert result["alzada"] is False

    def test_custom_value(self):
        result = _make_dual_result()
        apply_answers(result, [{"id": "alzada", "value": "custom", "detail": "15"}])
        assert result["alzada"] is True
        assert result["alzada_alto_m"] == 0.15
