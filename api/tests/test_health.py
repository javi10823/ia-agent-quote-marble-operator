"""Tests for /health endpoint with DB check."""

import pytest


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["db"] == "connected"

    @pytest.mark.asyncio
    async def test_health_returns_service_name(self, client):
        res = await client.get("/health")
        data = res.json()
        assert data["service"] == "marble-operator-api"
