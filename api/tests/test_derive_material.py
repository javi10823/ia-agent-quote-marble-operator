"""Tests for POST /quotes/{id}/derive-material — create new quote with different material."""

import pytest
from app.modules.quote_engine.calculator import calculate_quote


def _make_original_breakdown():
    """Build a realistic breakdown for the original quote."""
    return calculate_quote({
        "client_name": "Alvaro Torres",
        "project": "Cocina",
        "material": "Silestone Blanco Norte",
        "pieces": [
            {"description": "Mesada tramo 1", "largo": 4.10, "prof": 0.65},
            {"description": "Mesada tramo 2", "largo": 2.80, "prof": 0.65},
            {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
        ],
        "localidad": "puerto san martin",
        "colocacion": True,
        "pileta": "empotrada_cliente",
        "anafe": True,
        "plazo": "30 dias desde la toma de medidas",
    })


async def _create_original(client):
    """Create and populate an original quote for deriving."""
    resp = await client.post("/api/quotes")
    qid = resp.json()["id"]

    bd = _make_original_breakdown()
    assert bd["ok"]

    from app.core.database import get_db
    from app.main import app
    from sqlalchemy import update as sql_update
    from app.models.quote import Quote

    async for db in app.dependency_overrides[get_db]():
        await db.execute(
            sql_update(Quote).where(Quote.id == qid).values(
                client_name="Alvaro Torres",
                client_phone="341-1234567",
                client_email="alvaro@test.com",
                project="Cocina",
                material="SILESTONE BLANCO NORTE",
                localidad="puerto san martin",
                colocacion=True,
                pileta="empotrada_cliente",
                anafe=True,
                sink_type={"basin_count": "simple", "mount_type": "abajo"},
                pieces=[
                    {"description": "Mesada tramo 1", "largo": 4.10, "prof": 0.65},
                    {"description": "Mesada tramo 2", "largo": 2.80, "prof": 0.65},
                    {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
                ],
                notes="Con anafe y pileta empotrada",
                quote_breakdown=bd,
                total_ars=bd["total_ars"],
                total_usd=bd["total_usd"],
                source="web",
            )
        )
        await db.commit()

    return qid


class TestDeriveMaterial:

    @pytest.mark.asyncio
    async def test_creates_new_quote(self, client):
        """Derive must create a new quote, not modify the original."""
        qid = await _create_original(client)

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"]
        assert data["quote_id"] != qid
        assert data["derived_from"] == qid

    @pytest.mark.asyncio
    async def test_new_material_in_breakdown(self, client):
        """New quote must have the NEW material, not the original."""
        qid = await _create_original(client)

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        new_id = resp.json()["quote_id"]

        detail = await client.get(f"/api/quotes/{new_id}")
        q = detail.json()
        assert "PALOMA" in q["material"].upper()
        assert q["quote_breakdown"]["material_name"] != "SILESTONE BLANCO NORTE"

    @pytest.mark.asyncio
    async def test_copies_client_data(self, client):
        """New quote must have same client, project, localidad, options."""
        qid = await _create_original(client)

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        new_id = resp.json()["quote_id"]

        detail = await client.get(f"/api/quotes/{new_id}")
        q = detail.json()
        assert q["client_name"] == "Alvaro Torres"
        assert q["project"] == "Cocina"
        # sink_type should be copied
        assert q["sink_type"]["basin_count"] == "simple"
        assert q["sink_type"]["mount_type"] == "abajo"

    @pytest.mark.asyncio
    async def test_clears_docs_and_status(self, client):
        """New quote must have no docs and DRAFT status."""
        qid = await _create_original(client)

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        new_id = resp.json()["quote_id"]

        detail = await client.get(f"/api/quotes/{new_id}")
        q = detail.json()
        assert q["status"] == "draft"
        assert q["pdf_url"] is None
        assert q["excel_url"] is None
        assert q["drive_url"] is None

    @pytest.mark.asyncio
    async def test_recalculates_totals(self, client):
        """New quote must have recalculated totals for the new material."""
        qid = await _create_original(client)

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        data = resp.json()

        # Original was Silestone — different price/currency than Purastone
        original = await client.get(f"/api/quotes/{qid}")
        orig_data = original.json()

        # Totals should be different (different material = different price)
        assert data["total_usd"] != orig_data["total_usd"] or data["total_ars"] != orig_data["total_ars"]

    @pytest.mark.asyncio
    async def test_sets_parent_quote_id(self, client):
        """New quote must point to original via parent_quote_id."""
        qid = await _create_original(client)

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        new_id = resp.json()["quote_id"]

        detail = await client.get(f"/api/quotes/{new_id}")
        q = detail.json()
        assert q["parent_quote_id"] == qid

    @pytest.mark.asyncio
    async def test_invalid_material_returns_400(self, client):
        """Nonexistent material must fail with 400, not create a quote."""
        qid = await _create_original(client)

        # Count quotes before
        before = await client.get("/api/quotes")
        count_before = len(before.json())

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Material Inventado XYZ",
        })
        assert resp.status_code == 400

        # Count should not change
        after = await client.get("/api/quotes")
        assert len(after.json()) == count_before

    @pytest.mark.asyncio
    async def test_no_pieces_returns_400(self, client):
        """Quote without pieces must reject derive."""
        resp = await client.post("/api/quotes")
        qid = resp.json()["id"]
        # Empty quote — no pieces, no breakdown

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Silestone Blanco Norte",
        })
        assert resp.status_code == 400
        assert "piezas" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_original_unchanged(self, client):
        """Original quote must remain completely untouched."""
        qid = await _create_original(client)
        original_before = await client.get(f"/api/quotes/{qid}")
        orig = original_before.json()

        await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })

        original_after = await client.get(f"/api/quotes/{qid}")
        orig_after = original_after.json()

        assert orig_after["material"] == orig["material"]
        assert orig_after["total_ars"] == orig["total_ars"]
        assert orig_after["total_usd"] == orig["total_usd"]
        assert orig_after["quote_breakdown"] == orig["quote_breakdown"]

    @pytest.mark.asyncio
    async def test_pieces_from_breakdown_fallback(self, client):
        """If quote.pieces is None, derive from breakdown.piece_details."""
        resp = await client.post("/api/quotes")
        qid = resp.json()["id"]

        # Set breakdown with piece_details but NO quote.pieces
        bd = _make_original_breakdown()
        from app.core.database import get_db
        from app.main import app
        from sqlalchemy import update as sql_update
        from app.models.quote import Quote

        async for db in app.dependency_overrides[get_db]():
            await db.execute(
                sql_update(Quote).where(Quote.id == qid).values(
                    client_name="Test Fallback",
                    project="Cocina",  # Required since PR #15
                    material="SILESTONE BLANCO NORTE",
                    localidad="rosario",
                    quote_breakdown=bd,
                    pieces=None,  # No raw pieces
                )
            )
            await db.commit()

        resp = await client.post(f"/api/quotes/{qid}/derive-material", json={
            "material": "Blanco Paloma",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"]
        assert "PALOMA" in data["material"].upper()
