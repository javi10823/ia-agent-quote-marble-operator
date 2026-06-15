"""Tests · `GET /api/quotes/{id}` denormaliza `client_name` desde el breakdown.

Bug: el wizard (brief → contexto → despiece) guarda el cliente extraído SOLO
dentro de `quote_breakdown`, nunca en la columna `Quote.client_name`. El header
y el dashboard leen la columna → mostraban "Presupuesto {uuid}" y el draft
quedaba oculto del listado (que filtra `client_name != ""`).

Fix: `get_quote` copia el nombre del breakdown a la columna (lazy, una vez) con
la MISMA precedencia que el adapter del frontend
(`web/src/lib/api/adapters/context-from-breakdown.ts`).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.quote import Quote, QuoteStatus


async def _seed(db_session, quote_id: str, *, client_name: str = "", breakdown=None):
    db_session.add(
        Quote(
            id=quote_id,
            client_name=client_name,
            project="",
            messages=[],
            status=QuoteStatus.DRAFT,
            quote_breakdown=breakdown,
        )
    )
    await db_session.commit()


def _bd_with(field_value=None, *, raw_client=None, bucket="data_known", analysis_key="context_analysis_pending"):
    """Construye un breakdown con shape REAL del backend."""
    analysis: dict = {}
    if field_value is not None:
        analysis[bucket] = [{"field": "Cliente", "value": field_value, "source": "brief"}]
    if raw_client is not None:
        analysis["_brief_analysis_raw"] = {"client_name": raw_client}
    return {analysis_key: analysis}


@pytest.mark.asyncio
async def test_denormaliza_desde_data_known_pending(client, db_session):
    qid = str(uuid.uuid4())
    await _seed(db_session, qid, client_name="", breakdown=_bd_with("Juan Pérez"))

    resp = await client.get(f"/api/quotes/{qid}")
    assert resp.status_code == 200
    assert resp.json()["client_name"] == "Juan Pérez"

    # Persistido en la fila (dashboard ahora lo incluye/agrupa).
    refreshed = await db_session.get(Quote, qid)
    await db_session.refresh(refreshed)
    assert refreshed.client_name == "Juan Pérez"


@pytest.mark.asyncio
async def test_verified_tiene_precedencia_sobre_pending(client, db_session):
    qid = str(uuid.uuid4())
    bd = {
        "verified_context_analysis": {
            "data_known": [{"field": "Cliente", "value": "Cliente Verificado", "source": "brief"}],
        },
        "context_analysis_pending": {
            "data_known": [{"field": "Cliente", "value": "Cliente Pending", "source": "brief"}],
        },
    }
    await _seed(db_session, qid, client_name="", breakdown=bd)

    resp = await client.get(f"/api/quotes/{qid}")
    assert resp.json()["client_name"] == "Cliente Verificado"


@pytest.mark.asyncio
async def test_fallback_a_brief_analysis_raw(client, db_session):
    qid = str(uuid.uuid4())
    # Sin entry "Cliente" → cae al _brief_analysis_raw.client_name.
    await _seed(db_session, qid, client_name="", breakdown=_bd_with(None, raw_client="Erica Bernardi"))

    resp = await client.get(f"/api/quotes/{qid}")
    assert resp.json()["client_name"] == "Erica Bernardi"


@pytest.mark.asyncio
async def test_no_pisa_client_name_existente(client, db_session):
    qid = str(uuid.uuid4())
    # La columna ya tiene un valor → NO se sobrescribe con el breakdown.
    await _seed(db_session, qid, client_name="Nombre Canónico", breakdown=_bd_with("Otro Nombre"))

    resp = await client.get(f"/api/quotes/{qid}")
    assert resp.json()["client_name"] == "Nombre Canónico"


@pytest.mark.asyncio
async def test_sin_breakdown_no_crashea_queda_vacio(client, db_session):
    qid = str(uuid.uuid4())
    await _seed(db_session, qid, client_name="", breakdown=None)

    resp = await client.get(f"/api/quotes/{qid}")
    assert resp.status_code == 200
    assert resp.json()["client_name"] == ""


@pytest.mark.asyncio
async def test_breakdown_sin_cliente_queda_vacio(client, db_session):
    qid = str(uuid.uuid4())
    # Breakdown existe pero sin "Cliente" ni raw.client_name.
    bd = {"context_analysis_pending": {"data_known": [{"field": "Material", "value": "Granito", "source": "brief"}]}}
    await _seed(db_session, qid, client_name="", breakdown=bd)

    resp = await client.get(f"/api/quotes/{qid}")
    assert resp.status_code == 200
    assert resp.json()["client_name"] == ""
