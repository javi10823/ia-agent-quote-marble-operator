"""update_quote no puede escribir montos ni material: salen de calculate_quote."""

from app.modules.agent.agent import TOOLS, _check_update_quote_fields


def _schema_fields() -> set[str]:
    tool = next(t for t in TOOLS if t["name"] == "update_quote")
    return set(tool["input_schema"]["properties"]["updates"]["properties"])


def test_rechaza_montos_y_material():
    for campo, valor in (("total_ars", 1), ("total_usd", 1), ("material", "Otro")):
        err = _check_update_quote_fields({campo: valor})
        assert err is not None and err["ok"] is False, campo
        assert campo in err["error"]


def test_rechaza_aunque_venga_con_campos_validos():
    err = _check_update_quote_fields({"client_name": "X", "total_ars": 5})
    assert err is not None and "total_ars" in err["error"]


def test_campos_permitidos_pasan():
    assert _check_update_quote_fields({"client_name": "X", "project": "Y"}) is None
    assert _check_update_quote_fields({"delivery_days": "30 días"}) is None
    assert _check_update_quote_fields({"status": "sent"}) is None


def test_campo_desconocido_rechazado():
    err = _check_update_quote_fields({"pileta": "x"})
    assert err is not None and "pileta" in err["error"]


def test_none_se_ignora():
    assert _check_update_quote_fields({"total_ars": None, "project": "Y"}) is None


def test_schema_no_ofrece_montos_ni_material_al_llm():
    campos = _schema_fields()
    assert not campos & {"total_ars", "total_usd", "material"}
    assert {"client_name", "project", "status", "delivery_days"} <= campos
