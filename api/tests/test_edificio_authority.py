"""is_edificio lo decide el operador, no el LLM."""
import uuid

import pytest

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.agent.edificio_authority import authorize_is_edificio, operator_says_edificio


@pytest.mark.parametrize("texto,esperado", [
    ("cotizá el edificio de Corrientes 123", True),
    ("son 40 departamentos, torre A", True),
    ("es una obra de consorcio", True),
    ("cocina con isla, adjunto los planos, 3 unidades", False),   # señales débiles
    ("mesada de 2,40 con 2 cocinas", False),
    ("", False),
])
def test_senales_fuertes(texto, esperado):
    assert operator_says_edificio(texto) is esperado


def test_llm_promueve_sin_evidencia_se_rechaza():
    v, w = authorize_is_edificio(True, "cocina para la casa de Juan, silestone", persisted=False)
    assert v is False and w and "particular" in w


def test_llm_con_evidencia_del_operador_se_acepta():
    assert authorize_is_edificio(True, "edificio de 20 departamentos", False) == (True, None)


def test_ya_marcado_en_el_calculo_guardado_se_acepta():
    assert authorize_is_edificio(True, "recalculá", persisted=True) == (True, None)


def test_orden_explicita_del_operador_promueve():
    assert authorize_is_edificio(False, "tratalo como edificio", False) == (True, None)
    assert authorize_is_edificio(None, "es edificio", False) == (True, None)


def test_llm_false_no_se_promueve_por_palabra_suelta():
    assert authorize_is_edificio(False, "hay 3 departamentos en el plano", False) == (False, None)


def test_ambiguo_edificio_y_particular_no_promueve():
    v, w = authorize_is_edificio(True, "edificio... no, es particular", False)
    assert v is False and w


# ── camino completo ─────────────────────────────────────────────────────────

def _inputs(**extra):
    base = {
        "client_name": "Cliente X", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": [{"description": "Mesada", "largo": 6.0, "prof": 0.6, "quantity": 6}],
        "localidad": "rosario", "plazo": "30 días", "colocacion": False,
    }
    base.update(extra)
    return base


async def _quote(db_session, **cols):
    qid = f"test-{uuid.uuid4()}"
    db_session.add(Quote(id=qid, client_name="Cliente X", project="Cocina", messages=[],
                         status=QuoteStatus.DRAFT, **cols))
    await db_session.commit()
    return qid


async def _calc(db_session, qid, inputs, msg="", history=None):
    return await AgentService()._execute_tool(
        "calculate_quote", inputs, quote_id=qid, db=db_session,
        conversation_history=history or [], current_user_message=msg,
    )


@pytest.mark.asyncio
async def test_edificio_inventado_no_cambia_el_precio(db_session):
    qid = await _quote(db_session)
    r = await _calc(db_session, qid, _inputs(is_edificio=True), msg="cotizá esta cocina")
    assert r["ok"] and not r.get("is_edificio") and r["discount_pct"] != 18  # 5 % = tier por cantidad
    assert any("obra particular" in w for w in r.get("warnings", []))


@pytest.mark.asyncio
async def test_edificio_declarado_aplica_el_18(db_session):
    qid = await _quote(db_session)
    r = await _calc(db_session, qid, _inputs(is_edificio=True), msg="es un edificio de 6 departamentos")
    assert r["ok"] and r["is_edificio"] and r["discount_pct"] == 18


@pytest.mark.asyncio
async def test_edificio_ya_guardado_se_mantiene_al_recalcular(db_session):
    qid = await _quote(db_session, is_building=True)
    r = await _calc(db_session, qid, _inputs(is_edificio=True), msg="sacá el flete")
    assert r["ok"] and r["is_edificio"]
