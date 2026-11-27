"""El total general tiene que cerrar con el detalle (misma fórmula que el calculador)."""
import copy

import pytest

from app.modules.agent.tools.validation_tool import _check_grand_total, validate_despiece
from app.modules.quote_engine.calculator import calculate_quote

_PIECES = [
    {"description": "Mesada tramo 1", "largo": 2.4, "prof": 0.6},
    {"description": "Mesada tramo 2", "largo": 1.8, "prof": 0.6},
    {"description": "Zócalo", "largo": 4.2, "alto": 0.07},
]


def _calc(**over):
    base = {
        "client_name": "Cliente Test", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": copy.deepcopy(_PIECES), "localidad": "rosario", "colocacion": True,
        "pileta": "empotrada_cliente", "anafe": True, "plazo": "30 dias",
    }
    base.update(over)
    r = calculate_quote(base)
    assert r["ok"], r
    return r


ESCENARIOS = {
    "base": {},
    "descuento_material": {"discount_pct": 10},
    "descuento_mo": {"mo_discount_pct": 5},
    "edificio": {"is_edificio": True},
    "sin_colocacion": {"colocacion": False},
    "granito": {"material": "Granito Gris Mara"},
    "otra_localidad": {"localidad": "funes"},
}


@pytest.mark.parametrize("nombre", ESCENARIOS)
def test_salida_real_del_calculador_cierra(nombre):
    calc = _calc(**ESCENARIOS[nombre])
    errors, _ = _check_grand_total(calc)
    assert errors == [], (nombre, errors)
    assert validate_despiece(calc).ok or not any("Total" in e for e in validate_despiece(calc).errors)


def test_total_ars_adulterado_falla():
    calc = _calc()
    calc["total_ars"] += 1000
    errors, _ = _check_grand_total(calc)
    assert errors and "Total ARS" in errors[0]


def test_total_usd_adulterado_falla():
    calc = _calc()
    calc["total_usd"] -= 50
    errors, _ = _check_grand_total(calc)
    assert errors and "Total USD" in errors[0]


def test_mo_item_borrado_falla():
    calc = _calc()
    calc["mo_items"] = calc["mo_items"][1:]  # el total ya no cierra
    errors, _ = _check_grand_total(calc)
    assert errors


def test_descuento_mo_ignorado_falla():
    calc = _calc(mo_discount_pct=5)
    assert calc["mo_discount_amount"] > 0
    calc["mo_discount_amount"] = 0
    errors, _ = _check_grand_total(calc)
    assert errors


def test_validate_despiece_incluye_el_chequeo():
    calc = _calc()
    calc["total_ars"] += 5000
    res = validate_despiece(calc)
    assert not res.ok and any("Total ARS" in e for e in res.errors)


def test_sin_datos_suficientes_no_bloquea():
    assert _check_grand_total({"total_ars": 100}) == ([], [])
    assert _check_grand_total({}) == ([], [])


def test_solo_producto():
    calc = {
        "_quote_mode": "products_only", "total_ars": 90,
        "sinks": [{"unit_price": 50, "quantity": 2}], "discount_amount": 10,
    }
    assert _check_grand_total(calc) == ([], [])
    calc["total_ars"] = 100
    errors, _ = _check_grand_total(calc)
    assert errors


def test_material_en_ars_suma_material_y_sobrante():
    calc = {
        "total_ars": 1000 + 500 + 200 + 50, "material_currency": "ARS",
        "mo_items": [{"total": 1000}], "sinks": [{"unit_price": 500, "quantity": 1}],
        "material_total": 200, "sobrante_total": 50,
    }
    assert _check_grand_total(calc) == ([], [])
    calc["total_ars"] -= 50
    assert _check_grand_total(calc)[0]


def test_mo_sin_base_price_avisa():
    from app.modules.agent.tools.validation_tool import _check_iva_mo
    errors, warnings = _check_iva_mo({"mo_items": [{"description": "X", "unit_price": 10}]})
    assert errors == [] and any("base_price" in w for w in warnings)
