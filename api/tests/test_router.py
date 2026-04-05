"""Integration tests for API endpoints."""

import pytest


# ── POST /api/quotes — create ────────────────────────────────────────────────

class TestCreateQuote:
    @pytest.mark.asyncio
    async def test_create_returns_id(self, client):
        resp = await client.post("/api/quotes")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert len(data["id"]) > 10  # UUID format

    @pytest.mark.asyncio
    async def test_create_without_status_defaults_to_draft(self, client):
        resp = await client.post("/api/quotes")
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_with_status_draft(self, client):
        resp = await client.post("/api/quotes", json={"status": "draft"})
        assert resp.status_code == 200
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_with_status_pending(self, client):
        resp = await client.post("/api/quotes", json={"status": "pending"})
        assert resp.status_code == 200
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_with_empty_body(self, client):
        """Empty JSON body should behave like no body — default to draft."""
        resp = await client.post("/api/quotes", json={})
        assert resp.status_code == 200
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "draft"


# ── GET /api/quotes — list ───────────────────────────────────────────────────

class TestListQuotes:
    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        resp = await client.get("/api/quotes")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_after_create(self, client):
        # Create quotes with client_name so they appear in listing
        # (empty drafts are hidden from list_quotes)
        r1 = await client.post("/api/quotes")
        r2 = await client.post("/api/quotes")
        q1_id = r1.json()["id"]
        q2_id = r2.json()["id"]
        await client.patch(f"/api/quotes/{q1_id}", json={"client_name": "Test 1"})
        await client.patch(f"/api/quotes/{q2_id}", json={"client_name": "Test 2"})
        resp = await client.get("/api/quotes")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── GET /api/quotes/:id — detail ─────────────────────────────────────────────

class TestGetQuote:
    @pytest.mark.asyncio
    async def test_get_existing(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        resp = await client.get(f"/api/quotes/{quote_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == quote_id
        assert data["status"] == "draft"
        assert "messages" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_404(self, client):
        resp = await client.get("/api/quotes/nonexistent-id-12345")
        assert resp.status_code == 404


# ── DELETE /api/quotes/:id ───────────────────────────────────────────────────

class TestDeleteQuote:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/quotes/{quote_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["ok"] is True

        # Should be gone
        get_resp = await client.get(f"/api/quotes/{quote_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_404(self, client):
        resp = await client.delete("/api/quotes/nonexistent-id-12345")
        assert resp.status_code == 404


# ── PATCH /api/quotes/:id/status ─────────────────────────────────────────────

class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_draft_to_validated(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/quotes/{quote_id}/status",
            json={"status": "validated"},
        )
        assert resp.status_code == 200

        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "validated"

    @pytest.mark.asyncio
    async def test_validated_to_sent(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        await client.patch(f"/api/quotes/{quote_id}/status", json={"status": "validated"})
        await client.patch(f"/api/quotes/{quote_id}/status", json={"status": "sent"})

        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "sent"
