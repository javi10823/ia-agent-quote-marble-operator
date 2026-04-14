"""Tests for the fuzzy-match + merge-client endpoints.

Covers:
  - /quotes/client-match-check (preview: exact / fuzzy / ambiguous)
  - /quotes/merge-client       (rename to canonical)
  - /quotes/resumen-obra       (force_same_client override)
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus


@pytest_asyncio.fixture
async def mk_quote(db_session):
    async def _mk(client_name: str, status=QuoteStatus.VALIDATED) -> str:
        q = Quote(
            id=str(uuid.uuid4()),
            client_name=client_name,
            project="Proyecto",
            material="SILESTONE BLANCO NORTE",
            total_ars=1000,
            total_usd=100,
            status=status,
            quote_breakdown={
                "material_name": "SILESTONE BLANCO NORTE",
                "material_m2": 1.0,
                "material_price_unit": 500,
                "material_currency": "USD",
            },
            messages=[],
        )
        db_session.add(q)
        await db_session.commit()
        return q.id
    return _mk


# ─────────────────────────────────────────────────────────────────────────
# client-match-check
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_check_exact(client, mk_quote):
    a = await mk_quote("Estudio Munge")
    b = await mk_quote("Estudio Munge")
    r = await client.post("/api/quotes/client-match-check", json={"quote_ids": [a, b]})
    assert r.status_code == 200
    body = r.json()
    assert body["same"] is True
    assert body["reason"] == "exact"


@pytest.mark.asyncio
async def test_match_check_fuzzy(client, mk_quote):
    a = await mk_quote("Estudio Munge")
    b = await mk_quote("Munge")
    r = await client.post("/api/quotes/client-match-check", json={"quote_ids": [a, b]})
    assert r.status_code == 200
    body = r.json()
    assert body["same"] is True
    assert body["reason"] == "fuzzy"
    assert set(body["distinct_names"]) == {"Estudio Munge", "Munge"}


@pytest.mark.asyncio
async def test_match_check_ambiguous(client, mk_quote):
    a = await mk_quote("Estudio Munge")
    b = await mk_quote("Juan Pérez")
    r = await client.post("/api/quotes/client-match-check", json={"quote_ids": [a, b]})
    assert r.status_code == 200
    assert r.json()["same"] is False
    assert r.json()["reason"] == "ambiguous"


@pytest.mark.asyncio
async def test_match_check_missing_ids(client):
    r = await client.post(
        "/api/quotes/client-match-check",
        json={"quote_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_match_check_empty(client):
    r = await client.post("/api/quotes/client-match-check", json={"quote_ids": []})
    assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────
# merge-client
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_client_renames_all(client, mk_quote, db_session):
    a = await mk_quote("Estudio Munge")
    b = await mk_quote("Munge")
    r = await client.post(
        "/api/quotes/merge-client",
        json={
            "quote_ids": [a, b],
            "canonical_client_name": "Estudio MUNGE",
        },
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    rows = (
        await db_session.execute(select(Quote).where(Quote.id.in_([a, b])))
    ).scalars().all()
    assert all(q.client_name == "Estudio MUNGE" for q in rows)


@pytest.mark.asyncio
async def test_merge_client_invalidates_email_draft(client, mk_quote, db_session):
    qid = await mk_quote("Munge")
    q = (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()
    q.email_draft = {"subject": "x", "body": "y"}
    await db_session.commit()
    r = await client.post(
        "/api/quotes/merge-client",
        json={"quote_ids": [qid], "canonical_client_name": "Estudio Munge"},
    )
    assert r.status_code == 200
    db_session.expire_all()
    q2 = (await db_session.execute(select(Quote).where(Quote.id == qid))).scalar_one()
    assert q2.email_draft is None


@pytest.mark.asyncio
async def test_merge_client_rejects_empty_name(client, mk_quote):
    qid = await mk_quote("Estudio Munge")
    r = await client.post(
        "/api/quotes/merge-client",
        json={"quote_ids": [qid], "canonical_client_name": "   "},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_merge_client_rejects_too_long(client, mk_quote):
    qid = await mk_quote("Estudio Munge")
    r = await client.post(
        "/api/quotes/merge-client",
        json={"quote_ids": [qid], "canonical_client_name": "x" * 501},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_merge_client_missing_id(client, mk_quote):
    real = await mk_quote("Estudio Munge")
    fake = str(uuid.uuid4())
    r = await client.post(
        "/api/quotes/merge-client",
        json={"quote_ids": [real, fake], "canonical_client_name": "X"},
    )
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# resumen-obra — fuzzy + override
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resumen_accepts_fuzzy_variants(client, mk_quote):
    a = await mk_quote("Estudio Munge")
    b = await mk_quote("Munge")
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [a, b]},
        )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_resumen_ambiguous_requires_force(client, mk_quote):
    a = await mk_quote("Estudio Munge")
    b = await mk_quote("Juan Pérez")
    # Without force → rejected
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r1 = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [a, b]},
        )
    assert r1.status_code == 400
    # With force → accepted
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r2 = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [a, b], "force_same_client": True},
        )
    assert r2.status_code == 200, r2.text
