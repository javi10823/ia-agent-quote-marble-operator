"""Tests for sink_type field — acceptance, persistence, API response."""

import pytest
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus


class TestSinkTypePost:
    """POST /api/v1/quote with sink_type."""

    @pytest.mark.asyncio
    async def test_create_quote_with_sink_type(self, client):
        """sink_type should be persisted when creating a quote."""
        from unittest.mock import patch
        with patch("app.modules.quote_engine.router.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            resp = await client.post("/api/v1/quote", json={
                "client_name": "Test Sink",
                "project": "Cocina",
                "material": "Silestone Blanco Norte",
                "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
                "localidad": "Rosario",
                "plazo": "30 dias",
                "pileta": "empotrada_johnson",
                "sink_type": {"basin_count": "simple", "mount_type": "abajo"},
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        qid = data["quotes"][0]["quote_id"]

        # Verify persisted in DB via detail endpoint
        detail = await client.get(f"/api/quotes/{qid}")
        assert detail.status_code == 200
        q = detail.json()
        assert q["sink_type"] is not None
        assert q["sink_type"]["basin_count"] == "simple"
        assert q["sink_type"]["mount_type"] == "abajo"

    @pytest.mark.asyncio
    async def test_create_quote_with_sink_type_doble(self, client):
        """basin_count=doble (caso Bernardi: pileta con 2 bachas) se persiste."""
        from unittest.mock import patch
        with patch("app.modules.quote_engine.router.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            resp = await client.post("/api/v1/quote", json={
                "client_name": "Érica Bernardi",
                "project": "Cocina",
                "material": "Silestone Blanco Norte",
                "pieces": [{"description": "Mesada", "largo": 2.05, "prof": 0.60}],
                "localidad": "Rosario",
                "plazo": "30 dias",
                "pileta": "empotrada_cliente",
                "sink_type": {"basin_count": "doble", "mount_type": "abajo"},
            })

        assert resp.status_code == 200
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["sink_type"]["basin_count"] == "doble"

    @pytest.mark.asyncio
    async def test_create_quote_without_sink_type(self, client):
        """Omitting sink_type should not break anything."""
        from unittest.mock import patch
        with patch("app.modules.quote_engine.router.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            resp = await client.post("/api/v1/quote", json={
                "client_name": "Test No Sink",
                "project": "Cocina",
                "material": "Silestone Blanco Norte",
                "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
                "localidad": "Rosario",
                "plazo": "30 dias",
            })

        assert resp.status_code == 200
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = await client.get(f"/api/quotes/{qid}")
        assert detail.json()["sink_type"] is None

    @pytest.mark.asyncio
    async def test_create_quote_no_pieces_with_sink_type(self, client):
        """Quote without pieces (pending review) should also persist sink_type."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test Pending",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "pileta": "empotrada_johnson",
            "sink_type": {"basin_count": "doble", "mount_type": "arriba"},
            "notes": "Mesada cocina con bacha doble",
        })

        assert resp.status_code == 200
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = await client.get(f"/api/quotes/{qid}")
        q = detail.json()
        assert q["sink_type"]["basin_count"] == "doble"
        assert q["sink_type"]["mount_type"] == "arriba"

    @pytest.mark.asyncio
    async def test_invalid_sink_type_rejected(self, client):
        """Invalid basin_count or mount_type should be rejected by schema."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test Invalid",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "sink_type": {"basin_count": "triple", "mount_type": "abajo"},
        })
        assert resp.status_code == 422


class TestSinkTypePatch:
    """PATCH /api/quotes/{id} with sink_type."""

    @pytest.mark.asyncio
    async def test_patch_adds_sink_type(self, client):
        """PATCH should add sink_type to existing quote."""
        resp = await client.post("/api/quotes")
        qid = resp.json()["id"]

        resp = await client.patch(f"/api/quotes/{qid}", json={
            "sink_type": {"basin_count": "simple", "mount_type": "abajo"},
        })
        assert resp.status_code == 200

        detail = await client.get(f"/api/quotes/{qid}")
        q = detail.json()
        assert q["sink_type"]["basin_count"] == "simple"
        assert q["sink_type"]["mount_type"] == "abajo"

    @pytest.mark.asyncio
    async def test_patch_updates_sink_type(self, client):
        """PATCH should update existing sink_type."""
        resp = await client.post("/api/quotes")
        qid = resp.json()["id"]

        # Set initial
        await client.patch(f"/api/quotes/{qid}", json={
            "sink_type": {"basin_count": "simple", "mount_type": "arriba"},
        })

        # Update
        await client.patch(f"/api/quotes/{qid}", json={
            "sink_type": {"basin_count": "doble", "mount_type": "abajo"},
        })

        detail = await client.get(f"/api/quotes/{qid}")
        q = detail.json()
        assert q["sink_type"]["basin_count"] == "doble"
        assert q["sink_type"]["mount_type"] == "abajo"

    @pytest.mark.asyncio
    async def test_patch_invalid_sink_type_rejected(self, client):
        """PATCH with invalid sink_type should be rejected."""
        resp = await client.post("/api/quotes")
        qid = resp.json()["id"]

        resp = await client.patch(f"/api/quotes/{qid}", json={
            "sink_type": {"basin_count": "cuadruple", "mount_type": "abajo"},
        })
        assert resp.status_code == 422


class TestSinkTypeListResponse:
    """GET /api/quotes should include sink_type."""

    @pytest.mark.asyncio
    async def test_list_includes_sink_type(self, client):
        resp = await client.post("/api/quotes")
        qid = resp.json()["id"]

        await client.patch(f"/api/quotes/{qid}", json={
            "client_name": "Test List",
            "sink_type": {"basin_count": "doble", "mount_type": "arriba"},
        })

        resp = await client.get("/api/quotes")
        quotes = resp.json()
        matched = [q for q in quotes if q["id"] == qid]
        assert len(matched) == 1
        assert matched[0]["sink_type"]["basin_count"] == "doble"
