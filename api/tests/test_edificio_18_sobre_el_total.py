"""El 18 % de edificio se calcula sobre el total de m² de la obra (todos los materiales) y con > 15."""
import uuid

import pytest

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService, _other_edificio_calcs
from app.modules.quote_engine.calculator import calculate_quote


def _calc(m2_largo: float, **over):
    base = {
        "client_name": "Obra Test", "project": "Torre", "material": "Silestone Blanco Norte",
        "pieces": [{"description": "Mesada", "largo": m2_largo, "prof": 1.0}],
        "localidad": "rosario", "colocacion": False, "is_edificio": True, "plazo": "30 dias",
    }
    base.update(over)
    r = calculate_quote(base)
    assert r["ok"], r
    return r


def test_umbral_es_estricto_exactamente_15_no_descuenta():
    r = _calc(15.0)
    assert r["discount_pct"] != 18


def test_mas_de_15_si_descuenta():
    assert _calc(15.5)["discount_pct"] == 18


def test_un_material_chico_descuenta_si_la_obra_suma_mas_de_15():
    solo = _calc(10.0)
    assert solo["discount_pct"] != 18
    con_otros = _calc(10.0, edificio_otros_m2=8.0)
    assert con_otros["discount_pct"] == 18
    assert con_otros["edificio_total_m2"] == round(con_otros["material_m2"] + 8.0, 2)


def test_otros_m2_no_afectan_a_un_particular():
    r = _calc(10.0, is_edificio=False, edificio_otros_m2=50.0)
    assert r["discount_pct"] != 18 and "edificio_total_m2" not in r


def test_descuento_manual_gana_sobre_el_automatico():
    r = _calc(10.0, edificio_otros_m2=50.0, discount_pct=10)
    assert r["discount_pct"] == 10


# ── otros materiales de la obra ─────────────────────────────────────────────

def test_otros_calcs_excluye_el_mismo_material_y_los_que_no_son_edificio():
    a = {"material_name": "SILESTONE BLANCO NORTE", "is_edificio": True, "material_m2": 10}
    b = {"material_name": "DEKTON KELYA", "is_edificio": True, "material_m2": 6}
    c = {"material_name": "GRANITO GRIS MARA", "is_edificio": False, "material_m2": 4}
    cur = {**a, "_prior_calcs": [b, c]}
    otros = _other_edificio_calcs(cur, "Dekton Kelya")
    assert [o["material_name"] for o in otros] == ["SILESTONE BLANCO NORTE"]
    assert [o["material_name"] for o in _other_edificio_calcs(cur, "Puraprima X")] == [
        "SILESTONE BLANCO NORTE", "DEKTON KELYA"]
    assert _other_edificio_calcs(None, "x") == []


# ── camino completo: 2 materiales en la misma obra ──────────────────────────

async def _quote(db_session):
    qid = f"test-{uuid.uuid4()}"
    db_session.add(Quote(id=qid, client_name="Obra Test", project="Torre", messages=[],
                         status=QuoteStatus.DRAFT))
    await db_session.commit()
    return qid


def _inputs(material, largo):
    return {
        "client_name": "Obra Test", "project": "Torre", "material": material,
        "pieces": [{"description": "Mesada", "largo": largo, "prof": 1.0}],
        "localidad": "rosario", "colocacion": False, "is_edificio": True, "plazo": "30 días",
    }


async def _calc_tool(db_session, qid, inputs):
    return await AgentService()._execute_tool(
        "calculate_quote", inputs, quote_id=qid, db=db_session,
        conversation_history=[], current_user_message="es un edificio de departamentos",
    )


@pytest.mark.asyncio
async def test_segundo_material_suma_al_total_y_avisa_del_primero(db_session):
    qid = await _quote(db_session)
    r1 = await _calc_tool(db_session, qid, _inputs("Silestone Blanco Norte", 9.0))
    assert r1["ok"] and r1["discount_pct"] != 18       # 9 m² solo: no llega
    r2 = await _calc_tool(db_session, qid, _inputs("Dekton Kelya", 8.0))
    assert r2["ok"] and r2["discount_pct"] == 18       # 9 + 8 > 15
    assert any("recalculá" in w and "SILESTONE" in w.upper() for w in r2.get("warnings", []))
