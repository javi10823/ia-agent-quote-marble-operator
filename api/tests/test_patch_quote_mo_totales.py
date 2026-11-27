"""patch_quote_mo recalcula con la MISMA fórmula que calculate_quote."""
import uuid

import pytest
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.quote_engine.calculator import calculate_quote, compute_mo_totals

_PIECES = [
    {"description": "Mesada tramo 1", "largo": 2.4, "prof": 0.6},
    {"description": "Mesada tramo 2", "largo": 1.8, "prof": 0.6},
    {"description": "Zócalo", "largo": 4.2, "alto": 0.07},
]


def _calc(**over):
    base = {
        "client_name": "Cliente Test", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": [dict(p) for p in _PIECES], "localidad": "rosario", "colocacion": True,
        "pileta": "empotrada_cliente", "anafe": True, "plazo": "30 dias",
    }
    base.update(over)
    r = calculate_quote(base)
    assert r["ok"], r
    return r


async def _seed(db_session, bd):
    qid = f"test-{uuid.uuid4()}"
    db_session.add(Quote(
        id=qid, client_name="Cliente Test", project="Cocina", messages=[],
        status=QuoteStatus.DRAFT, quote_breakdown=bd,
        total_ars=bd["total_ars"], total_usd=bd["total_usd"],
    ))
    await db_session.commit()
    return qid


async def _patch(db_session, qid, **inputs):
    return await AgentService()._execute_tool(
        "patch_quote_mo", inputs, quote_id=qid, db=db_session
    )


async def _reload(db_session, qid):
    db_session.expire_all()
    return (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()


def test_compute_mo_totals_coincide_con_calculate_quote():
    for over in ({}, {"mo_discount_pct": 5}, {"discount_pct": 10}, {"is_edificio": True}):
        c = _calc(**over)
        t = compute_mo_totals(
            c["mo_items"], c.get("sinks") or [], c.get("mo_discount_pct") or 0,
            c["material_currency"], c["material_total"], c.get("sobrante_total") or 0,
        )
        assert t["total_ars"] == c["total_ars"], over
        assert t["total_usd"] == c["total_usd"], over
        assert t["mo_discount_amount"] == c["mo_discount_amount"], over


@pytest.mark.asyncio
async def test_parche_que_no_cambia_nada_no_mueve_el_total(db_session):
    """Con descuento de MO y sobrante, un parche vacío dejaba otro total."""
    c = _calc(mo_discount_pct=5)
    assert c["mo_discount_amount"] > 0
    qid = await _seed(db_session, c)
    res = await _patch(db_session, qid, remove_items=["zzz-no-existe"])
    assert res["ok"] is True, res
    q = await _reload(db_session, qid)
    assert q.total_ars == c["total_ars"]
    assert q.total_usd == c["total_usd"]
    assert q.quote_breakdown["mo_discount_amount"] == c["mo_discount_amount"]


@pytest.mark.asyncio
async def test_sacar_colocacion_recalcula_el_descuento_de_mo(db_session):
    c = _calc(mo_discount_pct=5)
    qid = await _seed(db_session, c)
    res = await _patch(db_session, qid, remove_items=["colocaci"])
    assert res["ok"] is True, res
    q = await _reload(db_session, qid)
    bd = q.quote_breakdown
    expected = compute_mo_totals(
        bd["mo_items"], bd.get("sinks") or [], 5, bd["material_currency"],
        bd["material_total"], bd.get("sobrante_total") or 0,
    )
    assert q.total_ars == expected["total_ars"]
    assert bd["mo_discount_amount"] == expected["mo_discount_amount"]
    assert bd["mo_discount_amount"] < c["mo_discount_amount"]  # el descuento bajó con la MO


@pytest.mark.asyncio
async def test_colocacion_en_edificio_se_rechaza(db_session):
    c = _calc(is_edificio=True)
    qid = await _seed(db_session, c)
    res = await _patch(db_session, qid, add_colocacion=True)
    assert res["ok"] is False and "edificio" in res["error"].lower()
    q = await _reload(db_session, qid)
    assert q.total_ars == c["total_ars"]


@pytest.mark.asyncio
async def test_flete_con_iva_incluido_conserva_el_flag(db_session):
    from app.modules.quote_engine.calculator import _find_flete
    r = _find_flete("Piñero")
    if not r.get("found") or not r.get("price_includes_vat"):
        pytest.skip("la zona Piñero no está marcada price_includes_vat en este catálogo")
    c = _calc()
    qid = await _seed(db_session, c)
    res = await _patch(db_session, qid, add_flete="Piñero", flete_qty=2)
    assert res["ok"] is True, res
    flete = [m for m in (await _reload(db_session, qid)).quote_breakdown["mo_items"]
             if "flete" in m["description"].lower()]
    assert len(flete) == 1 and flete[0].get("price_includes_vat") is True
    assert flete[0]["total"] == round(flete[0]["unit_price"] * 2)


@pytest.mark.asyncio
async def test_solo_producto_se_rechaza(db_session):
    bd = {"_quote_mode": "products_only", "mo_items": [], "total_ars": 100, "total_usd": 0}
    qid = await _seed(db_session, bd)
    res = await _patch(db_session, qid, remove_items=["x"])
    assert res["ok"] is False
