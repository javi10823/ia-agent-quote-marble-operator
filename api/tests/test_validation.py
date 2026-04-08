"""Tests for post-despiece deterministic validation."""

import math
import copy
import pytest

from app.modules.agent.tools.validation_tool import (
    validate_despiece,
    ValidationResult,
    _check_iva_material,
    _check_iva_mo,
    _check_material_total,
    _check_merma_rules,
    _check_pegadopileta,
    _check_piece_m2,
    _check_mo_item_totals,
    _check_colocacion_qty,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

IVA = 1.21


def _valid_qdata() -> dict:
    """A fully valid qdata for Silestone Blanco Norte."""
    base_price = 519
    unit_price = math.floor(base_price * IVA)  # floor(627.99) = 627

    mo_base_coloc = 49699
    mo_unit_coloc = round(mo_base_coloc * IVA)  # 60136
    mo_base_pileta = 53840
    mo_unit_pileta = round(mo_base_pileta * IVA)  # 65146
    mo_base_flete = 42975
    mo_unit_flete = round(mo_base_flete * IVA)  # 51999

    m2 = 1.30
    material_total = round(m2 * unit_price)  # round(815.1) = 815

    return {
        "ok": True,
        "client_name": "Juan Carlos",
        "project": "Cocina",
        "date": "31.03.2026",
        "delivery_days": "30 dias",
        "material_name": "SILESTONE BLANCO NORTE",
        "material_type": "silestone",
        "material_m2": m2,
        "material_price_base": base_price,
        "material_price_unit": unit_price,
        "material_currency": "USD",
        "material_total": material_total,
        "discount_pct": 0,
        "discount_amount": 0,
        "merma": {
            "aplica": False,
            "desperdicio": 0.80,
            "sobrante_m2": 0,
            "motivo": "Desperdicio < 1.0 m²",
        },
        "piece_details": [
            {"description": "Mesada", "largo": 2.0, "dim2": 0.60, "m2": 1.2, "quantity": 1},
            {"description": "Zocalo", "largo": 2.0, "dim2": 0.05, "m2": 0.1, "quantity": 1},
        ],
        "mo_items": [
            {
                "description": "Agujero y pegado pileta",
                "quantity": 1,
                "unit_price": mo_unit_pileta,
                "base_price": mo_base_pileta,
                "total": round(1 * mo_unit_pileta),
            },
            {
                "description": "Colocacion",
                "quantity": 1.30,
                "unit_price": mo_unit_coloc,
                "base_price": mo_base_coloc,
                "total": round(1.30 * mo_unit_coloc),
            },
            {
                "description": "Flete + toma medidas Rosario",
                "quantity": 1,
                "unit_price": mo_unit_flete,
                "base_price": mo_base_flete,
                "total": round(1 * mo_unit_flete),
            },
        ],
        "sinks": [{"name": "Johnson Quadra Q71A", "quantity": 1, "unit_price": 350000}],
        "sectors": [{"label": "COCINA", "pieces": ["2.00 X 0.60", "ZOCALO 2.00 X 0.05"]}],
        "colocacion": True,
        "pileta": "empotrada_johnson",
        "anafe": False,
        "frentin": False,
        "inglete": False,
        "pulido": False,
        "localidad": "Rosario",
        "total_ars": 245458,
        "total_usd": material_total,
    }


# ── TestIVAConsistency ──────────────────────────────────────────────────────


class TestIVAMaterial:
    def test_valid_usd_iva(self):
        qdata = _valid_qdata()
        errors, warnings = _check_iva_material(qdata)
        assert errors == []

    def test_invalid_usd_iva(self):
        qdata = _valid_qdata()
        qdata["material_price_unit"] = 999  # Wrong
        errors, warnings = _check_iva_material(qdata)
        assert len(errors) == 1
        assert "IVA material inconsistente" in errors[0]

    def test_valid_ars_iva(self):
        qdata = _valid_qdata()
        qdata["material_currency"] = "ARS"
        base = 275958
        qdata["material_price_base"] = base
        qdata["material_price_unit"] = round(base * IVA)
        errors, warnings = _check_iva_material(qdata)
        assert errors == []

    def test_missing_base_price_warns(self):
        qdata = _valid_qdata()
        del qdata["material_price_base"]
        errors, warnings = _check_iva_material(qdata)
        assert errors == []
        assert len(warnings) == 1
        assert "material_price_base" in warnings[0]


class TestIVAMO:
    def test_valid_mo_iva(self):
        qdata = _valid_qdata()
        errors, warnings = _check_iva_mo(qdata)
        assert errors == []

    def test_mo_iva_mismatch(self):
        qdata = _valid_qdata()
        qdata["mo_items"][0]["unit_price"] = 99999  # Wrong
        errors, warnings = _check_iva_mo(qdata)
        assert len(errors) == 1
        assert "IVA MO inconsistente" in errors[0]

    def test_mo_without_base_skips(self):
        qdata = _valid_qdata()
        for mo in qdata["mo_items"]:
            del mo["base_price"]
        errors, warnings = _check_iva_mo(qdata)
        assert errors == []
        assert warnings == []


# ── TestMaterialTotal ───────────────────────────────────────────────────────


class TestMaterialTotal:
    def test_valid_total(self):
        qdata = _valid_qdata()
        errors, warnings = _check_material_total(qdata)
        assert errors == []

    def test_total_mismatch(self):
        qdata = _valid_qdata()
        qdata["material_total"] = 999
        errors, warnings = _check_material_total(qdata)
        assert len(errors) == 1
        assert "Total material inconsistente" in errors[0]

    def test_total_with_discount(self):
        qdata = _valid_qdata()
        gross = round(qdata["material_m2"] * qdata["material_price_unit"])
        qdata["discount_pct"] = 5
        qdata["discount_amount"] = round(gross * 5 / 100)
        qdata["material_total"] = gross - qdata["discount_amount"]
        errors, warnings = _check_material_total(qdata)
        assert errors == []


# ── TestMermaRules ──────────────────────────────────────────────────────────


class TestMermaRules:
    def test_negro_brasil_no_merma_passes(self):
        qdata = _valid_qdata()
        qdata["material_name"] = "GRANITO NEGRO BRASIL"
        qdata["material_type"] = "granito"
        qdata["merma"] = {"aplica": False, "desperdicio": 0, "sobrante_m2": 0, "motivo": ""}
        errors, warnings = _check_merma_rules(qdata)
        assert errors == []

    def test_negro_brasil_with_merma_errors(self):
        qdata = _valid_qdata()
        qdata["material_name"] = "GRANITO NEGRO BRASIL"
        qdata["material_type"] = "granito"
        qdata["merma"] = {"aplica": True, "desperdicio": 1.5, "sobrante_m2": 0.75, "motivo": ""}
        errors, warnings = _check_merma_rules(qdata)
        assert len(errors) == 1
        assert "Negro Brasil" in errors[0]

    def test_synthetic_without_merma_warns_if_high_waste(self):
        qdata = _valid_qdata()
        qdata["merma"] = {"aplica": False, "desperdicio": 1.5, "sobrante_m2": 0, "motivo": ""}
        errors, warnings = _check_merma_rules(qdata)
        assert len(warnings) == 1
        assert "sintético" in warnings[0].lower() or "merma" in warnings[0].lower()

    def test_synthetic_without_merma_ok_if_low_waste(self):
        qdata = _valid_qdata()
        # desperdicio < 1.0 → no merma is correct
        qdata["merma"] = {"aplica": False, "desperdicio": 0.5, "sobrante_m2": 0, "motivo": ""}
        errors, warnings = _check_merma_rules(qdata)
        assert errors == []
        assert warnings == []

    def test_natural_stone_no_merma_passes(self):
        qdata = _valid_qdata()
        qdata["material_name"] = "GRANITO AMADEUS"
        qdata["material_type"] = "granito"
        qdata["merma"] = {"aplica": False}
        errors, warnings = _check_merma_rules(qdata)
        assert errors == []
        assert warnings == []

    def test_natural_stone_with_merma_warns(self):
        qdata = _valid_qdata()
        qdata["material_name"] = "GRANITO AMADEUS"
        qdata["material_type"] = "granito"
        qdata["merma"] = {"aplica": True, "desperdicio": 1.0, "sobrante_m2": 0.5, "motivo": ""}
        errors, warnings = _check_merma_rules(qdata)
        assert len(warnings) == 1
        assert "natural" in warnings[0].lower()


# ── TestPegadoPileta ────────────────────────────────────────────────────────


class TestPegadoPileta:
    def test_one_sink_one_mo_passes(self):
        qdata = _valid_qdata()
        errors, warnings = _check_pegadopileta(qdata)
        assert errors == []

    def test_empotrada_missing_mo_errors(self):
        qdata = _valid_qdata()
        # Remove pileta MO item
        qdata["mo_items"] = [m for m in qdata["mo_items"] if "pileta" not in m["description"].lower()]
        errors, warnings = _check_pegadopileta(qdata)
        assert len(errors) == 1
        assert "pileta" in errors[0].lower()

    def test_no_pileta_skips(self):
        qdata = _valid_qdata()
        qdata["pileta"] = None
        errors, warnings = _check_pegadopileta(qdata)
        assert errors == []
        assert warnings == []

    def test_multiple_pileta_mo_warns(self):
        qdata = _valid_qdata()
        # Duplicate the pileta MO item
        pileta_mo = next(m for m in qdata["mo_items"] if "pileta" in m["description"].lower())
        qdata["mo_items"].append(copy.deepcopy(pileta_mo))
        errors, warnings = _check_pegadopileta(qdata)
        assert len(warnings) == 1
        assert "2" in warnings[0]


# ── TestPieceM2 ─────────────────────────────────────────────────────────────


class TestPieceM2:
    def test_valid_pieces(self):
        qdata = _valid_qdata()
        errors, warnings = _check_piece_m2(qdata)
        assert errors == []

    def test_m2_sum_mismatch(self):
        qdata = _valid_qdata()
        qdata["material_m2"] = 5.0  # Wrong sum
        errors, warnings = _check_piece_m2(qdata)
        assert len(errors) == 1
        assert "material_m2" in errors[0]

    def test_piece_m2_calc_wrong(self):
        qdata = _valid_qdata()
        qdata["piece_details"][0]["m2"] = 9.99  # Should be 1.2
        errors, warnings = _check_piece_m2(qdata)
        assert any("m2=" in e for e in errors)

    def test_no_piece_details_skips(self):
        qdata = _valid_qdata()
        del qdata["piece_details"]
        errors, warnings = _check_piece_m2(qdata)
        assert errors == []


# ── TestMOTotals ────────────────────────────────────────────────────────────


class TestMOTotals:
    def test_valid_totals(self):
        qdata = _valid_qdata()
        errors, warnings = _check_mo_item_totals(qdata)
        assert warnings == []

    def test_total_mismatch_warns(self):
        qdata = _valid_qdata()
        qdata["mo_items"][0]["total"] = 1  # Wrong
        errors, warnings = _check_mo_item_totals(qdata)
        assert len(warnings) == 1


# ── TestColocacion ──────────────────────────────────────────────────────────


class TestColocacion:
    def test_valid_colocacion_qty(self):
        qdata = _valid_qdata()
        errors, warnings = _check_colocacion_qty(qdata)
        assert warnings == []

    def test_wrong_colocacion_qty_warns(self):
        qdata = _valid_qdata()
        # Set wrong qty
        for mo in qdata["mo_items"]:
            if "colocaci" in mo["description"].lower():
                mo["quantity"] = 99.0
        errors, warnings = _check_colocacion_qty(qdata)
        assert len(warnings) == 1
        assert "Colocación" in warnings[0] or "colocaci" in warnings[0].lower()

    def test_colocacion_min_1(self):
        qdata = _valid_qdata()
        qdata["material_m2"] = 0.5
        for mo in qdata["mo_items"]:
            if "colocaci" in mo["description"].lower():
                mo["quantity"] = 1.0  # max(0.5, 1.0) = 1.0
        errors, warnings = _check_colocacion_qty(qdata)
        assert warnings == []

    def test_no_colocacion_skips(self):
        qdata = _valid_qdata()
        qdata["colocacion"] = False
        errors, warnings = _check_colocacion_qty(qdata)
        assert errors == []
        assert warnings == []


# ── TestFullValidation ──────────────────────────────────────────────────────


class TestFullValidation:
    def test_fully_valid_passes(self):
        result = validate_despiece(_valid_qdata())
        assert result.ok is True
        assert result.errors == []

    def test_multiple_errors_all_reported(self):
        qdata = _valid_qdata()
        qdata["material_price_unit"] = 999  # IVA error
        qdata["material_total"] = 1  # Total error
        qdata["material_name"] = "GRANITO NEGRO BRASIL"  # Keep merma.aplica=False so no error there
        qdata["merma"]["aplica"] = True  # Negro Brasil + merma = error
        result = validate_despiece(qdata)
        assert result.ok is False
        assert len(result.errors) >= 3

    def test_only_warnings_still_ok(self):
        qdata = _valid_qdata()
        # Trigger only a warning: synthetic without merma but low desperdicio is fine
        # Trigger colocacion qty warning instead
        for mo in qdata["mo_items"]:
            if "colocaci" in mo["description"].lower():
                mo["quantity"] = 99.0
        result = validate_despiece(qdata)
        assert result.ok is True
        assert len(result.warnings) >= 1
