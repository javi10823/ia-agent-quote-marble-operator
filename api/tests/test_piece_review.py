"""Piezas que el operador debe verificar: medidas sin respaldo en el plano."""
import uuid

import pytest

from app.modules.agent.router import _serialize_dual_read_to_pieces
from app.modules.quote_engine.piece_review import (
    NO_TEXT_WARNING,
    plan_warnings,
    tramo_review_reason,
)


def _fv(v, status="CONFIRMADO", **extra):
    return {"valor": v, "status": status, **extra}


def _tramo(largo_status="CONFIRMADO", **extra):
    return {
        "id": "t1", "descripcion": "Mesada",
        "largo_m": _fv(2.15, largo_status, unanchored_reason="2.15m no está en las cotas del plano"),
        "ancho_m": _fv(0.6), **extra,
    }


def test_confirmado_no_se_marca():
    assert tramo_review_reason(_tramo()) is None


@pytest.mark.parametrize("status", ["UNANCHORED", "CONFLICTO", "DUDOSO"])
def test_sin_respaldo_se_marca(status):
    assert tramo_review_reason(_tramo(status))


def test_editado_por_el_operador_se_da_por_verificado():
    assert tramo_review_reason(_tramo("UNANCHORED", _manual=True)) is None


def test_del_brief_no_cuenta_como_editado():
    assert tramo_review_reason(_tramo("UNANCHORED", _manual=True, _from_text=True))


def test_serializador_expone_needs_review_y_motivo():
    dr = {"sectores": [{"tramos": [_tramo("UNANCHORED", zocalos=[
        {"lado": "trasero", "ml": 2.15, "alto_m": 0.05, "status": "UNANCHORED"},
        {"lado": "lateral", "ml": 0.6, "alto_m": 0.05},
    ])]}]}
    pieces = _serialize_dual_read_to_pieces(dr)
    assert [p["needs_review"] for p in pieces] == [True, True, False]
    assert "no está en las cotas" in pieces[0]["review_reason"]


def test_aviso_de_plano_sin_texto():
    assert plan_warnings({"sin_texto_en_plano": True}) == [NO_TEXT_WARNING]
    assert plan_warnings({}) == [] and plan_warnings(None) == []


@pytest.mark.asyncio
async def test_endpoint_devuelve_aviso_y_marcas(client, db_session):
    from app.models.quote import Quote, QuoteStatus
    qid = str(uuid.uuid4())
    db_session.add(Quote(
        id=qid, client_name="T", project="P", material="Silestone", status=QuoteStatus.DRAFT,
        quote_breakdown={"dual_read_result": {
            "sin_texto_en_plano": True,
            "sectores": [{"tramos": [_tramo("CONFLICTO")]}],
        }},
    ))
    await db_session.commit()
    data = (await client.get(f"/api/quotes/{qid}/pieces")).json()
    assert data["warnings"] == [NO_TEXT_WARNING]
    assert data["pieces"][0]["needs_review"] is True
