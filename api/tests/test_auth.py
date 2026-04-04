"""Tests for auth endpoints — create-user protection, username strip."""

import pytest
from app.core.auth import create_token, COOKIE_NAME


class TestCreateUserProtection:
    @pytest.mark.asyncio
    async def test_initial_setup_allowed_without_auth(self, client_no_auth):
        """First user creation should work without auth cookie."""
        res = await client_no_auth.post("/api/auth/create-user", json={
            "username": "admin",
            "password": "password123",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_second_user_blocked_without_auth(self, client_no_auth):
        """After first user exists, creating another without auth should fail."""
        # Create first user
        res1 = await client_no_auth.post("/api/auth/create-user", json={
            "username": "admin",
            "password": "password123",
        })
        assert res1.status_code == 200

        # Try creating second user without auth — should be blocked
        res2 = await client_no_auth.post("/api/auth/create-user", json={
            "username": "attacker",
            "password": "password123",
        })
        assert res2.status_code == 401

    @pytest.mark.asyncio
    async def test_second_user_allowed_with_auth(self, client):
        """After first user exists, creating another WITH auth should work."""
        # Create first user (via authenticated client)
        res1 = await client.post("/api/auth/create-user", json={
            "username": "admin",
            "password": "password123",
        })
        assert res1.status_code == 200

        # Create second user — should work since we have valid cookie
        res2 = await client.post("/api/auth/create-user", json={
            "username": "operator",
            "password": "password123",
        })
        assert res2.status_code == 200


class TestLoginUsernameStrip:
    @pytest.mark.asyncio
    async def test_login_strips_whitespace(self, client_no_auth):
        """Username should be stripped of whitespace before validation."""
        # Create user
        await client_no_auth.post("/api/auth/create-user", json={
            "username": "admin",
            "password": "password123",
        })
        # Login with extra spaces
        res = await client_no_auth.post("/api/auth/login", json={
            "username": "  admin  ",
            "password": "password123",
        })
        assert res.status_code == 200


class TestStatusTransitions:
    @pytest.mark.asyncio
    async def test_valid_transition_draft_to_validated(self, client):
        # Create quote
        create_res = await client.post("/api/quotes")
        quote_id = create_res.json()["id"]
        # Transition to validated
        res = await client.patch(f"/api/quotes/{quote_id}/status", json={"status": "validated"})
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_transition_draft_to_sent(self, client):
        # Create quote
        create_res = await client.post("/api/quotes")
        quote_id = create_res.json()["id"]
        # Try invalid transition
        res = await client.patch(f"/api/quotes/{quote_id}/status", json={"status": "sent"})
        assert res.status_code == 400
        assert "Transición inválida" in res.json()["detail"]


class TestPaginatedQuotes:
    @pytest.mark.asyncio
    async def test_list_with_limit(self, client):
        res = await client.get("/api/quotes?limit=10&offset=0")
        assert res.status_code == 200
        assert isinstance(res.json(), list)


class TestTypedPatch:
    @pytest.mark.asyncio
    async def test_patch_with_valid_fields(self, client):
        create_res = await client.post("/api/quotes")
        quote_id = create_res.json()["id"]
        res = await client.patch(f"/api/quotes/{quote_id}", json={"client_name": "Test Client"})
        assert res.status_code == 200
        assert "client_name" in res.json()["updated"]

    @pytest.mark.asyncio
    async def test_patch_rejects_long_client_name(self, client):
        create_res = await client.post("/api/quotes")
        quote_id = create_res.json()["id"]
        res = await client.patch(f"/api/quotes/{quote_id}", json={"client_name": "A" * 501})
        assert res.status_code == 422
