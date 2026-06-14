"""Tests de los endpoints de listado/lectura de catálogos · sub-PR 22.2.b.

Cubre los gaps que NO tocaba test_import_endpoints.py (que cubre import +
backups): GET /api/catalog/ (lista con metadata), GET /api/catalog/{name}
(200 + 404) y PUT /api/catalog/{name} (403 catálogo no permitido).

DB de test vacía → _load_from_db cae a los JSON reales de api/catalog/.
"""
from __future__ import annotations

import pytest


class TestListCatalogs:
    @pytest.mark.asyncio
    async def test_list_returns_metadata_per_catalog(self, client):
        r = await client.get("/api/catalog/")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        for entry in data:
            assert set(entry.keys()) >= {"name", "item_count", "last_updated"}
            assert isinstance(entry["item_count"], int)

    @pytest.mark.asyncio
    async def test_list_includes_known_catalogs(self, client):
        r = await client.get("/api/catalog/")
        names = {e["name"] for e in r.json()}
        # Catálogos seedeados desde archivo
        assert "labor" in names
        assert "materials-silestone" in names


class TestGetCatalog:
    @pytest.mark.asyncio
    async def test_get_existing_catalog_returns_content(self, client):
        r = await client.get("/api/catalog/labor")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_get_unknown_catalog_returns_404(self, client):
        r = await client.get("/api/catalog/no-existe-este-catalogo")
        assert r.status_code == 404


class TestUpdateCatalogGuard:
    @pytest.mark.asyncio
    async def test_put_disallowed_catalog_returns_403(self, client):
        r = await client.put(
            "/api/catalog/catalogo-prohibido",
            json={"content": [{"sku": "X", "price_ars": 1}]},
        )
        assert r.status_code == 403
