"""Tests de context_analyzer — construye la card de análisis previa al despiece."""
from app.modules.quote_engine.context_analyzer import build_context_analysis


def _dual(has_cocina: bool = True) -> dict:
    sectores = []
    if has_cocina:
        sectores.append({
            "id": "s1",
            "tipo": "cocina",
            "tramos": [{
                "id": "t1",
                "descripcion": "Mesada",
                "largo_m": {"valor": 2.0, "status": "CONFIRMADO"},
                "ancho_m": {"valor": 0.6, "status": "CONFIRMADO"},
                "m2": {"valor": 1.2, "status": "CONFIRMADO"},
                "zocalos": [], "frentin": [], "regrueso": [],
            }],
            "ambiguedades": [],
        })
    return {"sectores": sectores, "source": "MULTI_CROP"}


class TestBuildContextAnalysis:
    def test_shape(self):
        out = build_context_analysis("brief", {"client_name": "Juan"}, _dual())
        assert "data_known" in out
        assert "assumptions" in out
        assert "pending_questions" in out
        assert "sector_summary" in out

    def test_client_from_quote(self):
        out = build_context_analysis("", {"client_name": "Juan"}, _dual())
        clientes = [r for r in out["data_known"] if r["field"] == "Cliente"]
        assert len(clientes) == 1
        assert clientes[0]["value"] == "Juan"
        assert clientes[0]["source"] == "quote"

    def test_material_from_brief(self):
        out = build_context_analysis("material silestone blanco norte", None, _dual())
        materiales = [r for r in out["data_known"] if r["field"] == "Material"]
        assert len(materiales) == 1
        assert "silestone" in materiales[0]["value"].lower()
        assert materiales[0]["source"] == "brief"

    def test_localidad_from_brief(self):
        out = build_context_analysis("cliente en rosario", None, _dual())
        assert any(r["field"] == "Localidad" for r in out["data_known"])

    def test_cocina_triggers_pileta_empotrada_rule(self):
        out = build_context_analysis("", None, _dual(has_cocina=True))
        piletas = [a for a in out["assumptions"] if "Pileta" in a["field"]]
        assert len(piletas) == 1
        assert "empotrada" in piletas[0]["value"].lower()
        assert piletas[0]["source"] == "rule"

    def test_no_cocina_no_pileta_rule(self):
        out = build_context_analysis("", None, _dual(has_cocina=False))
        assert not any("Pileta" in a["field"] for a in out["assumptions"])

    def test_con_zocalos_triggers_assumption(self):
        out = build_context_analysis("cocina con zocalos en rosario", None, _dual())
        zoc = [a for a in out["assumptions"] if a["field"] == "Zócalos"]
        assert len(zoc) == 1
        assert "trasero" in zoc[0]["value"].lower()

    def test_con_colocacion_included(self):
        out = build_context_analysis("cocina con colocacion", None, _dual())
        coloc = [a for a in out["assumptions"] if a["field"] == "Colocación"]
        assert len(coloc) == 1
        assert "incluye" in coloc[0]["value"].lower()

    def test_defaults_always_included(self):
        out = build_context_analysis("", None, _dual())
        fields = [a["field"] for a in out["assumptions"]]
        assert "Forma de pago" in fields
        assert "Demora" in fields
        assert "Tipo" in fields

    def test_pending_questions_propagated(self):
        dual = _dual()
        dual["pending_questions"] = [{"id": "q1", "label": "X", "question": "¿?", "type": "radio_with_detail"}]
        out = build_context_analysis("", None, dual)
        assert len(out["pending_questions"]) == 1
        assert out["pending_questions"][0]["id"] == "q1"

    def test_sector_summary(self):
        out = build_context_analysis("", None, _dual())
        assert out["sector_summary"] is not None
        assert "cocina" in out["sector_summary"].lower()

    def test_empty_inputs_does_not_crash(self):
        """Brief vacío + dual vacío: no debería romper, devuelve shape mínima."""
        out = build_context_analysis("", None, {"sectores": []})
        assert "data_known" in out
        assert "assumptions" in out
        assert out["pending_questions"] == []


# ── Round-trip: build context → apply answers → verify result ──────────────
# Simula el flow end-to-end de PR G sin DB ni LLM. Verifica que las
# respuestas del operador a pending_questions efectivamente modifican el
# dual_read_result via apply_answers del módulo pending_questions.


class TestContextConfirmationRoundTrip:
    def _dual_with_pending(self, pending: list[dict]) -> dict:
        d = _dual()
        d["pending_questions"] = pending
        return d

    def test_apply_answers_removes_pending_from_dual(self):
        """Handler [CONTEXT_CONFIRMED] aplica respuestas y limpia pending."""
        from app.modules.quote_engine.pending_questions import apply_answers

        pending = [{
            "id": "zocalos", "label": "Zócalos", "question": "?",
            "type": "radio_with_detail",
            "options": [{"value": "default_trasero", "label": "Sí"}],
        }]
        dual = self._dual_with_pending(pending)
        # Simulación del handler: aplica answers, limpia pending
        apply_answers(dual, [{"id": "zocalos", "value": "default_trasero"}])
        dual.pop("pending_questions", None)
        # Zócalos agregados al tramo con source=brief_rule
        assert len(dual["sectores"][0]["tramos"][0]["zocalos"]) == 1
        assert dual["sectores"][0]["tramos"][0]["zocalos"][0]["source"] == "brief_rule"
        assert "pending_questions" not in dual

    def test_pileta_simple_doble_applies_sink_type(self):
        from app.modules.quote_engine.pending_questions import apply_answers
        dual = _dual()
        dual["sectores"][0]["tramos"][0]["features"] = {"has_pileta": True}
        apply_answers(dual, [{"id": "pileta_simple_doble", "value": "doble"}])
        sector = dual["sectores"][0]
        assert sector["sink_type"]["basin_count"] == "doble"
        assert sector["pileta_type_hint"] == "empotrada"

    def test_multiple_answers_apply_in_one_pass(self):
        """Varios answers en un solo CONTEXT_CONFIRMED se aplican todos."""
        from app.modules.quote_engine.pending_questions import apply_answers
        dual = _dual()
        apply_answers(dual, [
            {"id": "zocalos", "value": "default_trasero"},
            {"id": "colocacion", "value": "si"},
            {"id": "anafe_count", "value": "2"},
        ])
        assert len(dual["sectores"][0]["tramos"][0]["zocalos"]) == 1
        assert dual["colocacion"] is True
        assert dual["anafe"] is True
        assert dual["anafe_qty"] == 2

    def test_full_flow_bernardi_like(self):
        """Caso Bernardi end-to-end (sin DB ni LLM):
        1. Construye context analysis desde brief + quote + dual_read
        2. Operador responde las preguntas bloqueantes
        3. apply_answers materializa todo en el dual_result
        4. pending_questions se limpia → card despiece queda lista.
        """
        from app.modules.quote_engine.pending_questions import apply_answers

        brief = "material pura prima onix white cliente erica bernardi con zocalos en rosario con colocacion"
        quote = None  # operador recién lo sube, sin datos previos en quote

        dual = _dual()
        dual["sectores"].append({
            "id": "s2", "tipo": "isla",
            "tramos": [{
                "id": "t_isla",
                "descripcion": "Mesada",
                "largo_m": {"valor": 1.60, "status": "CONFIRMADO"},
                "ancho_m": {"valor": 0.60, "status": "DUDOSO"},  # dispara pregunta
                "m2": {"valor": 0.96, "status": "DUDOSO"},
                "zocalos": [], "frentin": [], "regrueso": [],
            }],
            "ambiguedades": [],
        })
        # Agregar pending_questions típicos del caso
        dual["pending_questions"] = [
            {"id": "pileta_simple_doble", "label": "Pileta", "question": "?", "type": "radio_with_detail"},
            {"id": "isla_profundidad", "label": "Isla prof", "question": "?", "type": "radio_with_detail"},
            {"id": "isla_patas", "label": "Patas", "question": "?", "type": "radio_with_detail"},
        ]

        context = build_context_analysis(brief, quote, dual)
        assert any(r["field"] == "Material" for r in context["data_known"])
        assert any(r["field"] == "Localidad" for r in context["data_known"])
        assert any(a["field"] == "Pileta (tipo de montaje)" for a in context["assumptions"])
        assert any(a["field"] == "Zócalos" for a in context["assumptions"])
        assert any(a["field"] == "Colocación" for a in context["assumptions"])

        # Operador confirma respondiendo las 3 preguntas
        apply_answers(dual, [
            {"id": "pileta_simple_doble", "value": "doble"},
            {"id": "isla_profundidad", "value": "0.60"},
            {"id": "isla_patas", "value": "frontal_y_ambos_laterales", "alto_m": 0.90},
        ])
        dual.pop("pending_questions", None)

        # Verificamos el estado final listo para despiece:
        cocina = next(s for s in dual["sectores"] if s["tipo"] == "cocina")
        isla = next(s for s in dual["sectores"] if s["tipo"] == "isla")
        assert cocina["sink_type"]["basin_count"] == "doble"
        assert isla["tramos"][0]["ancho_m"]["valor"] == 0.60
        assert isla["patas"]["sides"] == ["frontal", "lateral_izq", "lateral_der"]
        assert "pending_questions" not in dual
