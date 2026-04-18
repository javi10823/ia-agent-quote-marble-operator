"""Tests del anchor validator — marca UNANCHORED cotas inventadas por el VLM."""
from app.modules.quote_engine.plan_anchor_validator import annotate_anchoring


def _make_field(valor: float, status: str = "CONFIRMADO") -> dict:
    return {"opus": None, "sonnet": None, "valor": valor, "status": status}


def _make_tramo(largo: float, ancho: float, zocalos: list | None = None) -> dict:
    return {
        "id": "t1",
        "descripcion": "Mesada",
        "largo_m": _make_field(largo),
        "ancho_m": _make_field(ancho),
        "m2": _make_field(round(largo * ancho, 2)),
        "zocalos": zocalos or [],
        "frentin": [],
        "regrueso": [],
    }


def _make_result(tramos: list) -> dict:
    return {
        "sectores": [
            {"id": "s1", "tipo": "cocina", "tramos": tramos, "ambiguedades": []},
        ],
        "requires_human_review": False,
        "conflict_fields": [],
        "source": "SOLO_SONNET",
    }


class TestAnnotateAnchoring:
    def test_bernardi_invented_values_flagged(self):
        """Caso real: 1.75 y 2.35 como ancho/largo no están en las cotas del plano."""
        cotas = [2.95, 2.05, 1.60, 0.60, 4.15, 2.75, 1.20, 2.35]  # del PDF Bernardi
        result = _make_result([
            _make_tramo(2.05, 0.60),   # OK
            _make_tramo(1.75, 0.60),   # 1.75 NO está en las cotas → UNANCHORED
            _make_tramo(1.60, 2.35),   # 2.35 sí está (pero malinterpretado como ancho) — NO se flaguea por valor
        ])
        annotate_anchoring(result, cotas)
        tramos = result["sectores"][0]["tramos"]
        assert tramos[0]["largo_m"]["status"] == "CONFIRMADO"
        assert tramos[0]["ancho_m"]["status"] == "CONFIRMADO"
        assert tramos[1]["largo_m"]["status"] == "UNANCHORED"
        assert "unanchored_reason" in tramos[1]["largo_m"]
        # 2.35 SÍ está en cotas; el validator no sabe que es un contexto equivocado
        assert tramos[2]["ancho_m"]["status"] == "CONFIRMADO"
        # Al menos 1 UNANCHORED → requires_human_review
        assert result["requires_human_review"] is True

    def test_all_values_anchored_no_flags(self):
        cotas = [2.40, 0.60]
        result = _make_result([_make_tramo(2.40, 0.60)])
        annotate_anchoring(result, cotas)
        for f in ("largo_m", "ancho_m"):
            assert result["sectores"][0]["tramos"][0][f]["status"] != "UNANCHORED"
        assert result["requires_human_review"] is False

    def test_empty_cotas_list_is_noop(self):
        """Si no extrajimos cotas del text layer (PDF escaneado), el validator
        no debe flaguear nada — preservar comportamiento previo."""
        result = _make_result([_make_tramo(99.99, 88.88)])
        annotate_anchoring(result, [])
        for f in ("largo_m", "ancho_m"):
            assert result["sectores"][0]["tramos"][0][f]["status"] == "CONFIRMADO"

    def test_tolerance_allows_small_rounding_diffs(self):
        """Valores a < 2cm del real cuentan como anclados (OCR rounding)."""
        cotas = [2.95, 0.60]
        result = _make_result([_make_tramo(2.94, 0.61)])  # 1cm off
        annotate_anchoring(result, cotas)
        for f in ("largo_m", "ancho_m"):
            assert result["sectores"][0]["tramos"][0][f]["status"] == "CONFIRMADO"

    def test_zocalo_ml_validated(self):
        cotas = [2.05, 0.60]
        zocalo_ok = {"lado": "trasero", "ml": 2.05, "alto_m": 0.07, "status": "CONFIRMADO"}
        zocalo_bad = {"lado": "lateral", "ml": 1.75, "alto_m": 0.07, "status": "CONFIRMADO"}
        result = _make_result([_make_tramo(2.05, 0.60, zocalos=[zocalo_ok, zocalo_bad])])
        annotate_anchoring(result, cotas)
        zs = result["sectores"][0]["tramos"][0]["zocalos"]
        assert zs[0]["status"] == "CONFIRMADO"
        assert zs[1]["status"] == "UNANCHORED"

    def test_ambiguedad_added_when_unanchored(self):
        cotas = [2.05, 0.60]
        result = _make_result([_make_tramo(1.75, 0.60)])
        annotate_anchoring(result, cotas)
        ambs = result["sectores"][0]["ambiguedades"]
        assert len(ambs) == 1
        assert ambs[0]["tipo"] == "REVISION"
        assert "no coinciden" in ambs[0]["texto"].lower()

    def test_none_value_not_flagged(self):
        """Fields con valor None no deben romperse — se validan como OK."""
        tramo = _make_tramo(2.0, 0.6)
        tramo["largo_m"]["valor"] = None
        result = _make_result([tramo])
        annotate_anchoring(result, [2.0, 0.6])
        assert result["sectores"][0]["tramos"][0]["largo_m"]["status"] != "UNANCHORED"
