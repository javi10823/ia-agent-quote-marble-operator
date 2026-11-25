"""Tests del helper puro `project_inference`."""
import pytest

from app.modules.quote_engine.calculator import calculate_quote
from app.modules.quote_engine.project_inference import (
    PROJECT_PLACEHOLDERS,
    clean_project,
    derive_project_from_brief,
    is_placeholder_project,
    resolve_project_for_persist,
    suggest_project_name,
)


class TestIsPlaceholder:
    @pytest.mark.parametrize("v", ["", " ", "N/A", "n/d", "Sin Proyecto", "sin obra", "-", "—", ".", None, 3, []])
    def test_placeholders(self, v):
        assert is_placeholder_project(v) is True

    @pytest.mark.parametrize("v", ["Cocina", "Casa López", "Obra N/A 2"])
    def test_validos(self, v):
        assert is_placeholder_project(v) is False


class TestCleanProject:
    def test_limpia(self):
        assert clean_project("  **Casa**\nLópez\r\n ") == "Casa López"

    def test_trunca_450(self):
        assert len(clean_project("a" * 600)) == 450

    @pytest.mark.parametrize("v", [None, 5, ["x"]])
    def test_no_str(self, v):
        assert clean_project(v) == ""


class TestDerive:
    def test_una(self):
        assert derive_project_from_brief({"work_types": ["cocina"]}) == "Cocina"

    def test_dos(self):
        assert derive_project_from_brief({"work_types": ["cocina", "baño"]}) == "Cocina y Baño"

    def test_tres(self):
        assert (
            derive_project_from_brief({"work_types": ["cocina", "baño", "lavadero"]})
            == "Cocina, Baño y Lavadero"
        )

    def test_isla_con_cocina(self):
        assert derive_project_from_brief({"work_types": ["cocina"], "isla_mentioned": True}) == "Cocina con isla"

    def test_isla_sin_cocina(self):
        assert derive_project_from_brief({"work_types": ["baño"], "isla_mentioned": True}) == "Baño"

    def test_duplicados_y_orden(self):
        assert derive_project_from_brief({"work_types": ["baño", "Cocina", "baño", "COCINA"]}) == "Baño y Cocina"

    def test_banio(self):
        assert derive_project_from_brief({"work_types": ["banio"]}) == "Baño"

    def test_otro_ignorado(self):
        assert derive_project_from_brief({"work_types": ["otro"]}) is None
        assert derive_project_from_brief({"work_types": ["otro", "cocina"]}) == "Cocina"

    @pytest.mark.parametrize("a", [None, "cocina", [], 3])
    def test_analysis_invalido(self, a):
        assert derive_project_from_brief(a) is None

    @pytest.mark.parametrize("wt", [None, "cocina", [], [None, 3]])
    def test_work_types_invalido(self, wt):
        assert derive_project_from_brief({"work_types": wt}) is None

    def test_work_types_mixto(self):
        assert derive_project_from_brief({"work_types": [None, 3, "cocina"]}) == "Cocina"


class TestSuggest:
    def test_ambos(self):
        assert suggest_project_name("Juan Pérez", "Silestone Blanco Norte") == "Juan Pérez · Silestone Blanco Norte"

    def test_solo_cliente(self):
        assert suggest_project_name("Juan Pérez", None) == "Juan Pérez"

    def test_solo_material(self):
        assert suggest_project_name("", "Silestone") == "Silestone"

    def test_ninguno(self):
        assert suggest_project_name(None, None) is None

    def test_placeholders(self):
        assert suggest_project_name("n/a", "-") is None
        assert suggest_project_name("n/a", "Silestone") == "Silestone"

    def test_limpia_markdown(self):
        assert suggest_project_name("**Juan**", "Granito\nNegro") == "Juan · Granito Negro"


class TestResolve:
    def _r(self, analysis, **kw):
        base = dict(current_project=None, pending_project=None, client_name=None, material=None)
        base.update(kw)
        return resolve_project_for_persist(analysis, **base)

    def test_brief_gana(self):
        r = self._r({"project": "Casa López", "work_types": ["cocina"]}, client_name="Juan", material="Silestone")
        assert r == ("Casa López", "brief")

    def test_cliente_material_antes_que_work_types(self):
        r = self._r({"work_types": ["cocina"]}, client_name="Juan", material="Silestone")
        assert r == ("Juan · Silestone", "inferred")

    def test_work_types_ultimo(self):
        r = self._r({"work_types": ["cocina"], "isla_mentioned": True})
        assert r == ("Cocina con isla", "inferred")

    def test_brief_placeholder_cae_a_siguiente(self):
        assert self._r({"project": "n/a"}, client_name="Juan") == ("Juan", "inferred")

    def test_current_valido_none(self):
        assert self._r({"project": "X"}, current_project="Obra previa") is None

    def test_pending_valido_none(self):
        assert self._r({"project": "X"}, pending_project="Obra hint") is None

    def test_current_placeholder_permite(self):
        assert self._r({"project": "X"}, current_project="n/a") == ("X", "brief")

    def test_nada(self):
        assert self._r({}) is None
        assert self._r(None) is None
        assert self._r("texto") is None

    def test_truncado(self):
        r = self._r({"project": "a" * 600})
        assert r is not None and len(r[0]) == 450


@pytest.mark.parametrize("p", sorted(PROJECT_PLACEHOLDERS))
def test_guardia_calculator_sigue_rechazando_placeholders(p):
    """Si el calculator cambia su set de placeholders, este test avisa."""
    res = calculate_quote({"client_name": "X", "project": p})
    assert res["ok"] is False
    assert "Falta el nombre del proyecto" in res["error"]
