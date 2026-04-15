"""PR #19 — exponer is_building en list/detail responses para badge OBRA."""
import pytest
from sqlalchemy import update
from app.models.quote import Quote


@pytest.mark.asyncio
async def test_list_response_includes_is_building(client, db_session):
    """GET /api/quotes debe incluir is_building en cada item."""
    # Create a quote and mark it as building
    resp = await client.post("/api/quotes")
    qid = resp.json()["id"]
    await db_session.execute(
        update(Quote).where(Quote.id == qid).values(
            client_name="Test Edificio",
            project="Obra X",
            is_building=True,
        )
    )
    await db_session.commit()

    items = (await client.get("/api/quotes")).json()
    target = next((q for q in items if q["id"] == qid), None)
    assert target is not None
    assert "is_building" in target
    assert target["is_building"] is True


@pytest.mark.asyncio
async def test_list_response_residential_is_building_false(client, db_session):
    """Residencial → is_building False (no badge OBRA)."""
    resp = await client.post("/api/quotes")
    qid = resp.json()["id"]
    await db_session.execute(
        update(Quote).where(Quote.id == qid).values(
            client_name="Casa Pérez",
            project="Cocina",
            is_building=False,
        )
    )
    await db_session.commit()

    items = (await client.get("/api/quotes")).json()
    target = next((q for q in items if q["id"] == qid), None)
    assert target is not None
    assert target.get("is_building") is False
