"""Los descuentos los decide el operador, no el LLM."""
import uuid

import pytest

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.agent.discount_authority import (
    authorize_discounts,
    stated_percentages,
    wants_discount_removed,
)


# ── función pura ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("Descuento 10% sobre material", {10.0}),
    ("hacele un 15% de descuento", {15.0}),
    ("dto 5 %", {5.0}),
    ("descuento del 12 por ciento", {12.0}),
    ("descuento 7,5%", {7.5}),
    ("Descuento 18% sobre material. Además 5% sobre MO descuento", {18.0, 5.0}),
    ("la mesada mide 10% más que la otra", set()),   # % sin la palabra descuento
    ("", set()),
])
def test_porcentajes_declarados(texto, esperado):
    assert stated_percentages(texto) == esperado


@pytest.mark.parametrize("msg,esperado", [
    ("sacá el descuento", True), ("quitale el descuento", True),
    ("sin descuento", True), ("no lleva descuento", True),
    ("eliminá el dto", True),
    ("poné 10% de descuento", False), ("el descuento es de 10%", False), ("", False),
])
def test_pedido_de_sacar_descuento(msg, esperado):
    assert wants_discount_removed(msg) is esperado


def test_llm_inventa_descuento_se_rechaza():
    d = authorize_discounts(15, 0, "cocina silestone 2.4 x 0.6", "calculá")
    assert d.discount_pct == 0 and len(d.rejected) == 1
    assert "15" in d.warnings()[0]


def test_descuento_pedido_por_el_operador_se_acepta():
    d = authorize_discounts(10, 0, "Hacele 10% de descuento", "dale")
    assert d.discount_pct == 10 and d.rejected == []


def test_llm_cambia_el_porcentaje_se_rechaza():
    d = authorize_discounts(20, 0, "descuento 10%", "dale")
    assert d.discount_pct == 0 and d.rejected[0][1] == 20


def test_fuera_de_rango_se_rechaza_aunque_figure():
    d = authorize_discounts(60, 0, "descuento 60%", "dale")
    assert d.discount_pct == 0 and "rango" in d.rejected[0][2]


def test_mo_discount_se_valida_igual():
    assert authorize_discounts(0, 5, "5% de descuento sobre MO", "x").mo_discount_pct == 5
    d = authorize_discounts(0, 5, "sin pedidos", "x")
    assert d.mo_discount_pct == 0 and d.rejected


def test_valor_ya_guardado_cuenta_como_evidencia():
    d = authorize_discounts(10, 0, "", "recalculá", persisted={10.0})
    assert d.discount_pct == 10


def test_sacar_el_descuento_anula_todo():
    d = authorize_discounts(10, 5, "descuento 10% descuento 5% sobre mo", "sacá el descuento")
    assert d.removed and d.discount_pct == 0 and d.mo_discount_pct == 0


# ── camino completo por calculate_quote ─────────────────────────────────────

def _inputs(**extra):
    base = {
        "client_name": "Cliente Sin Descuento", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        "localidad": "rosario", "plazo": "30 días", "colocacion": True,
    }
    base.update(extra)
    return base


async def _quote(db_session, breakdown=None):
    qid = f"test-{uuid.uuid4()}"
    db_session.add(Quote(
        id=qid, client_name="Cliente Sin Descuento", project="Cocina", messages=[],
        status=QuoteStatus.DRAFT, quote_breakdown=breakdown,
    ))
    await db_session.commit()
    return qid


async def _calc(db_session, qid, inputs, history=None, msg=""):
    return await AgentService()._execute_tool(
        "calculate_quote", inputs, quote_id=qid, db=db_session,
        conversation_history=history or [], current_user_message=msg,
    )


@pytest.mark.asyncio
async def test_descuento_inventado_no_llega_al_precio(db_session):
    qid = await _quote(db_session)
    base = await _calc(db_session, qid, _inputs(), msg="cotizá la cocina")
    qid2 = await _quote(db_session)
    inv = await _calc(db_session, qid2, _inputs(discount_pct=15), msg="cotizá la cocina")
    assert inv["ok"] and base["ok"]
    assert inv["discount_pct"] == 0
    assert inv["total_usd"] == base["total_usd"]
    assert any("No se aplicó" in w for w in inv.get("warnings", []))


@pytest.mark.asyncio
async def test_descuento_pedido_si_se_aplica(db_session):
    qid = await _quote(db_session)
    hist = [{"role": "user", "content": "cocina silestone, hacele 10% de descuento sobre material"}]
    r = await _calc(db_session, qid, _inputs(discount_pct=10), history=hist, msg="dale")
    assert r["ok"] and r["discount_pct"] == 10 and r["discount_amount"] > 0


@pytest.mark.asyncio
async def test_sacar_el_descuento_no_vuelve_por_el_historial(db_session):
    qid = await _quote(db_session)
    hist = [{"role": "user", "content": "Descuento 10% sobre material"}]
    con = await _calc(db_session, qid, _inputs(), history=hist, msg="dale")
    assert con["discount_pct"] == 10  # la regex del brief lo toma
    qid2 = await _quote(db_session)
    sin = await _calc(db_session, qid2, _inputs(discount_pct=10), history=hist, msg="sacá el descuento")
    assert sin["ok"] and sin["discount_pct"] == 0 and sin["discount_amount"] == 0


@pytest.mark.asyncio
async def test_descuentos_automaticos_siguen_funcionando(db_session):
    """Edificio ≥ 15 m² → 18 % automático, sin que lo pase el LLM."""
    qid = await _quote(db_session)
    r = await _calc(
        db_session, qid,
        _inputs(is_edificio=True, colocacion=False,
                pieces=[{"description": "Mesada", "largo": 6.0, "prof": 0.6, "quantity": 6}]),
        msg="edificio",
    )
    assert r["ok"] and r["discount_pct"] == 18
