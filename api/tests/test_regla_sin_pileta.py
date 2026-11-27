"""Regla configurable: "sin pileta" ¿sigue cobrando el agujero (cliente la trae) o no cobra nada?"""
import uuid

import pytest

import app.modules.agent.agent as agent_mod
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService

KEY = "defaults.sin_pileta_cobra_agujero"


def _inputs():
    return {
        "client_name": "Cliente Pileta", "project": "Cocina", "material": "Silestone Blanco Norte",
        "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        "localidad": "rosario", "plazo": "30 días", "colocacion": True,
        "pileta": "empotrada_cliente",   # lo que suele mandar el LLM
    }


async def _calc(db_session, history_text, monkeypatch, cobra=None):
    if cobra is not None:
        real = agent_mod._cfg
        monkeypatch.setattr(agent_mod, "_cfg", lambda k, d=None: cobra if k == KEY else real(k, d))
    qid = f"test-{uuid.uuid4()}"
    db_session.add(Quote(id=qid, client_name="Cliente Pileta", project="Cocina", messages=[],
                         status=QuoteStatus.DRAFT))
    await db_session.commit()
    return await AgentService()._execute_tool(
        "calculate_quote", _inputs(), quote_id=qid, db=db_session,
        conversation_history=[{"role": "user", "content": history_text}],
        current_user_message="calculá",
    )


def _pileta_mo(r):
    return [m for m in r["mo_items"] if "pileta" in m["description"].lower()]


@pytest.mark.asyncio
async def test_default_sin_pileta_sigue_cobrando_el_agujero(db_session, monkeypatch):
    """Comportamiento histórico (regla = true)."""
    r = await _calc(db_session, "cocina silestone, sin pileta", monkeypatch)
    assert r["ok"] and _pileta_mo(r)


@pytest.mark.asyncio
async def test_regla_apagada_sin_pileta_no_cobra_nada(db_session, monkeypatch):
    r = await _calc(db_session, "cocina silestone, sin pileta", monkeypatch, cobra=False)
    assert r["ok"] and not _pileta_mo(r) and not r.get("sinks")


@pytest.mark.asyncio
async def test_regla_apagada_pero_cliente_trae_la_pileta_si_cobra(db_session, monkeypatch):
    r = await _calc(db_session, "cocina silestone, sin producto de pileta, el cliente trae la pileta",
                    monkeypatch, cobra=False)
    assert r["ok"] and _pileta_mo(r)


@pytest.mark.asyncio
async def test_regla_apagada_sin_mencionar_sin_pileta_no_cambia(db_session, monkeypatch):
    r = await _calc(db_session, "cocina silestone con bacha empotrada", monkeypatch, cobra=False)
    assert r["ok"] and _pileta_mo(r)


def test_la_regla_esta_en_config_json_con_default_historico():
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).resolve().parent.parent / "catalog" / "config.json").read_text(encoding="utf-8"))
    assert cfg["defaults"]["sin_pileta_cobra_agujero"] is True
