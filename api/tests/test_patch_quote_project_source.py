"""PATCH /quotes/{id} con `project` marca "edited" en lugar de "inferred" `project_source`
("inferred") del breakdown: la obra editada a mano deja de ser una
sugerencia. Otros campos no la tocan."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


def _inferred_breakdown() -> dict:
    return {
        "client_name": "Original Cliente",
        "project": "Juan - Silestone",
        "project_source": "inferred",
        "localidad": "rosario",
    }


async def _create_quote(db_session, breakdown=None) -> str:
    from app.models.quote import Quote, QuoteStatus
    qid = str(uuid.uuid4())
    quote = Quote(
        id=qid,
        client_name="Original Cliente",
        project="Juan - Silestone",
        material="GRANITO ORIGINAL",
        localidad="rosario",
        colocacion=True,
        pileta="empotrada_johnson",
        anafe=False,
        status=QuoteStatus.DRAFT,
        quote_breakdown=breakdown if breakdown is not None else _inferred_breakdown(),
    )
    db_session.add(quote)
    await db_session.commit()
    return qid


async def _reload(db_session, qid):
    from app.models.quote import Quote
    from sqlalchemy import select
    await db_session.commit()
    result = await db_session.execute(select(Quote).where(Quote.id == qid))
    return result.scalar_one()


@pytest.mark.asyncio
class TestPatchProjectSource:
    async def test_patch_project_removes_inferred_mark(
        self, client: AsyncClient, db_session,
    ):
        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}", json={"project": "Cocina Belgrano"},
        )
        assert resp.status_code == 200, resp.text
        q = await _reload(db_session, qid)
        assert q.project == "Cocina Belgrano"
        assert q.quote_breakdown["project"] == "Cocina Belgrano"
        assert q.quote_breakdown["project_source"] == "edited"

    async def test_patch_same_suggested_value_also_removes_mark(
        self, client: AsyncClient, db_session,
    ):
        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}", json={"project": "Juan - Silestone"},
        )
        assert resp.status_code == 200, resp.text
        q = await _reload(db_session, qid)
        assert q.quote_breakdown["project"] == "Juan - Silestone"
        assert q.quote_breakdown["project_source"] == "edited"

    async def test_patch_other_field_keeps_mark(
        self, client: AsyncClient, db_session,
    ):
        qid = await _create_quote(db_session)
        resp = await client.patch(f"/api/quotes/{qid}", json={"localidad": "X"})
        assert resp.status_code == 200, resp.text
        q = await _reload(db_session, qid)
        assert q.quote_breakdown["localidad"] == "X"
        assert q.quote_breakdown["project_source"] == "inferred"

    async def test_patch_project_without_mark_is_fine(
        self, client: AsyncClient, db_session,
    ):
        qid = await _create_quote(
            db_session, breakdown={"client_name": "Original Cliente"},
        )
        resp = await client.patch(
            f"/api/quotes/{qid}", json={"project": "Obra nueva"},
        )
        assert resp.status_code == 200, resp.text
        q = await _reload(db_session, qid)
        assert q.quote_breakdown["project"] == "Obra nueva"
        assert q.quote_breakdown["project_source"] == "edited"
