"""Errores de validación visibles en el Paso 2 y 'confirmo pero cambiá X' no confirma."""
import copy

import pytest

from app.modules.agent.agent import _user_intent
from app.modules.quote_engine.calculator import build_deterministic_paso2, calculate_quote


def _calc():
    r = calculate_quote({
        "client_name": "Cliente Test", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": [{"description": "Mesada", "largo": 2.4, "prof": 0.6}],
        "localidad": "rosario", "colocacion": True, "plazo": "30 dias",
    })
    assert r["ok"]
    return copy.deepcopy(r)


def test_paso2_sin_errores_pide_confirmacion():
    txt = build_deterministic_paso2(_calc())
    assert "¿Confirmás para generar PDF y Excel?" in txt
    assert "Error de validación" not in txt


def test_paso2_con_errores_los_muestra_y_no_ofrece_confirmar():
    calc = _calc()
    calc["_validation_errors"] = ["Total ARS no cierra con el detalle: esperado=1, actual=2"]
    txt = build_deterministic_paso2(calc)
    assert "⛔ Error de validación: Total ARS no cierra" in txt
    assert "¿Confirmás" not in txt
    assert "No se puede generar el PDF" in txt


@pytest.mark.parametrize("msg", [
    "dale pero sacá el flete",
    "perfecto, quitá la colocación",
    "ok, cambiá el material",
    "confirmo, aunque el descuento no aplica",
    "listo, agregá una pileta",
])
def test_confirmar_con_cambio_es_modify(msg):
    assert _user_intent(msg) == "modify"


@pytest.mark.parametrize("msg", [
    "dale", "confirmo", "perfecto", "ok generá el presupuesto", "todo bien, generá el PDF",
    "listo, imprimí",
])
def test_confirmacion_pura_sigue_siendo_confirm(msg):
    assert _user_intent(msg) == "confirm"


def test_modificacion_y_otros_sin_cambios():
    assert _user_intent("sacá el flete") == "modify"
    assert _user_intent("hola, ¿cómo va?") == "other"
    assert _user_intent("") == "other"
