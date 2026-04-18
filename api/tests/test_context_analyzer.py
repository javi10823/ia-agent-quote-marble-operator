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
