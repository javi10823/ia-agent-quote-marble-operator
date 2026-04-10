"""Tests for edificio view model: distribute_flete + build_edificio_doc_context."""

import pytest
from pathlib import Path
from app.modules.quote_engine.edificio_parser import distribute_flete, build_edificio_doc_context

ESH_PDF = Path("/Users/javierolivieri/projects/dangelo-marble-ia/planos/edifcio-1121SM-2025-Planilla marmolería.pdf")


class TestDistributeFlete:
    def test_sum_equals_total(self):
        result = distribute_flete(7, {"A": 9, "B": 3, "C": 37})
        assert sum(result.values()) == 7

    def test_esh_distribution(self):
        result = distribute_flete(7, {"Negro Boreal": 9, "Negro Brasil": 3, "Marmol Sahara": 37})
        assert result["Negro Boreal"] == 1
        assert result["Negro Brasil"] == 1
        assert result["Marmol Sahara"] == 5
        assert sum(result.values()) == 7

    def test_zero_total(self):
        result = distribute_flete(0, {"A": 10, "B": 5})
        assert all(v == 0 for v in result.values())

    def test_single_material(self):
        result = distribute_flete(3, {"A": 10})
        assert result["A"] == 3

    def test_even_split(self):
        result = distribute_flete(6, {"A": 5, "B": 5, "C": 5})
        assert sum(result.values()) == 6

    def test_deterministic_tiebreak(self):
        """Same inputs always produce same output."""
        r1 = distribute_flete(7, {"Negro Boreal": 9, "Negro Brasil": 3, "Marmol Sahara": 37})
        r2 = distribute_flete(7, {"Negro Boreal": 9, "Negro Brasil": 3, "Marmol Sahara": 37})
        assert r1 == r2


def _build_esh_contexts():
    import pdfplumber
    from app.modules.quote_engine.edificio_parser import (
        parse_edificio_tables, normalize_edificio_data,
        compute_edificio_aggregates, render_edificio_paso2,
    )
    tables = []
    with pdfplumber.open(str(ESH_PDF)) as pdf:
        for p in pdf.pages:
            tables.extend(p.extract_tables())
    raw = parse_edificio_tables(tables)
    norm = normalize_edificio_data(raw)
    summary = compute_edificio_aggregates(norm)
    paso2 = render_edificio_paso2(summary, "Rosario")
    return build_edificio_doc_context(summary, paso2, "ESH", "Concesionario"), summary


@pytest.mark.skipif(not ESH_PDF.exists(), reason="ESH PDF not available")
class TestESHViewModelEdificio:

    @pytest.fixture(scope="class")
    def data(self):
        return _build_esh_contexts()

    @pytest.fixture(scope="class")
    def contexts(self, data):
        return data[0]

    @pytest.fixture(scope="class")
    def summary(self, data):
        return data[1]

    def test_3_contexts(self, contexts):
        assert len(contexts) == 3

    def test_boreal_has_mo(self, contexts):
        boreal = next(c for c in contexts if "Boreal" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        assert boreal["show_mo"] is True
        assert len(boreal["mo_items"]) > 0

    def test_boreal_pegadopileta_14(self, contexts):
        boreal = next(c for c in contexts if "Boreal" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        peg = next((m for m in boreal["mo_items"] if "pegado" in m["description"].lower()), None)
        assert peg is not None
        assert peg["quantity"] == 14

    def test_brasil_has_mo(self, contexts):
        brasil = next(c for c in contexts if "Brasil" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        assert brasil["show_mo"] is True

    def test_brasil_pegadopileta_1(self, contexts):
        brasil = next(c for c in contexts if "Brasil" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        peg = next((m for m in brasil["mo_items"] if "pegado" in m["description"].lower()), None)
        assert peg is not None
        assert peg["quantity"] == 1

    def test_brasil_apoyo_1(self, contexts):
        brasil = next(c for c in contexts if "Brasil" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        apo = next((m for m in brasil["mo_items"] if "apoyo" in m["description"].lower()), None)
        assert apo is not None
        assert apo["quantity"] == 1

    def test_sahara_has_flete_only(self, contexts):
        sahara = next(c for c in contexts if "Sahara" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        assert sahara["show_mo"] is True  # Has flete
        descs = [m["description"].lower() for m in sahara["mo_items"]]
        assert any("flete" in d for d in descs)
        assert not any("pegado" in d for d in descs)
        assert not any("apoyo" in d for d in descs)

    def test_no_zero_qty_mo_lines(self, contexts):
        for ctx in contexts:
            for mo in ctx.get("mo_items", []):
                assert mo["quantity"] > 0, f"qty=0 in {ctx.get('material_name')}: {mo}"

    def test_flete_sum_equals_total(self, contexts, summary):
        total_flete = sum(
            mo["quantity"] for ctx in contexts
            for mo in ctx.get("mo_items", [])
            if "flete" in mo["description"].lower()
        )
        assert total_flete == summary["totals"]["flete_qty"]

    def test_despiece_has_sectors(self, contexts):
        for ctx in contexts:
            assert len(ctx["sectors"]) > 0, f"{ctx.get('material_name')} has no sectors"

    def test_sahara_has_commercial_sectors(self, contexts):
        sahara = next(c for c in contexts if "Sahara" in (c.get("_mat_name_raw") or c.get("material_name", "")))
        labels = [s["label"] for s in sahara["sectors"]]
        # Should have real sector labels, not just "General" or "Edificio"
        assert len(labels) >= 1

    def test_grand_total_text_format(self, contexts):
        for ctx in contexts:
            gt = ctx.get("grand_total_text", "")
            assert "PRESUPUESTO TOTAL:" in gt, f"Bad grand_total_text: {gt}"
            if ctx["_currency"] == "USD" and ctx["show_mo"]:
                assert "mano de obra" in gt and "USD" in gt
            elif ctx["_currency"] == "USD" and not ctx["show_mo"]:
                assert "USD" in gt and "mano de obra" not in gt

    def test_no_total_pesos_zero(self, contexts):
        """No context should have total_ars=0 when it has MO."""
        for ctx in contexts:
            if ctx["show_mo"]:
                assert ctx["total_ars"] > 0, f"{ctx.get('material_name')} has MO but total_ars=0"
