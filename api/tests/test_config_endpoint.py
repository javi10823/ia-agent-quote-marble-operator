"""Tests del endpoint `GET/PUT /api/catalog/config` · Sprint 4 sub-PR
22.2.a config-ui-page.

Cobertura:
- GET devuelve las 4 keys nuevas del scope 22.2.a
- GET muestra default_zocalo_height = 0.05 (BUG PROD FIX · master Regla 10)
- PUT con dict válido persiste + invalida cache + GET subsecuente devuelve cambios
- PUT con body inválido (content=null) rechaza 422
- Fixtures con shape REAL del config.json (lección #60)
"""
from __future__ import annotations

import pytest


class TestConfigEndpointGet:
    @pytest.mark.asyncio
    async def test_get_config_contains_new_keys_from_22_2_a(self, client):
        """Verifica que las 4 keys agregadas en este sub-PR aparezcan en GET."""
        r = await client.get("/api/catalog/config")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)
        assert "measurements" in data
        # Bug fix prod · default zócalo alineado al master (era 0.07)
        assert data["measurements"]["default_zocalo_height"] == 0.05
        # NUEVO · default alzada
        assert data["measurements"]["default_alzada_height"] == 0.6
        # NUEVO bloque defaults operativos
        assert "defaults" in data
        assert data["defaults"]["colocacion_particulares"] is True
        assert data["defaults"]["delivery_zone_sku"] == "ENVIOROS"
        assert data["defaults"]["forma_pago"] == "Contado"

    @pytest.mark.asyncio
    async def test_get_config_preserves_existing_keys(self, client):
        """Regresión · los bloques previos (iva, delivery_days, discount,
        company, conditions, etc.) NO se rompen al agregar `defaults`."""
        r = await client.get("/api/catalog/config")
        assert r.status_code == 200
        data = r.json()
        assert data["iva"]["multiplier"] == 1.21
        assert data["delivery_days"]["default"] == 30
        assert "company" in data
        assert "conditions" in data
        assert "ai_engine" in data


class TestConfigEndpointPut:
    @pytest.mark.asyncio
    async def test_put_config_persists_and_get_returns_updated(self, client):
        """PUT con dict válido persiste a DB. GET subsecuente devuelve la
        versión nueva (incluye invalidación de cache module-level)."""
        # GET inicial
        r0 = await client.get("/api/catalog/config")
        original = r0.json()
        # Modificamos un field editable del scope 22.2.a
        new_config = {**original}
        new_config["measurements"] = {
            **original["measurements"],
            "default_alzada_height": 0.75,  # cambiamos 0.6 → 0.75
        }
        # PUT
        r1 = await client.put(
            "/api/catalog/config",
            json={"content": new_config},
        )
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body == {"ok": True, "catalog": "config"}
        # GET subsecuente refleja el cambio
        r2 = await client.get("/api/catalog/config")
        assert r2.json()["measurements"]["default_alzada_height"] == 0.75

    @pytest.mark.asyncio
    async def test_put_config_null_content_rejected(self, client):
        """Pydantic rechaza body con content=null (preserva validator
        existente · regresión)."""
        r = await client.put(
            "/api/catalog/config",
            json={"content": None},
        )
        assert r.status_code == 422


class TestConfigEndpointCacheInvalidation:
    @pytest.mark.asyncio
    async def test_put_config_invokes_cache_invalidation_handlers(self, client, monkeypatch):
        """Verifica que el endpoint invoca las 3 funciones de cache
        invalidation (catalog_tool + document_tool + company_config) al
        recibir PUT sobre `config`.

        Razón del approach: en multi-worker prod, los caches son
        module-level por proceso. El endpoint llama 3 invalidates pero solo
        afectan al worker actual. UI debe decir "puede tardar unos segundos
        en producción" (caveat documentado en bundle FASE 1 punto 6).

        El test NO verifica propagación real (requeriría multi-process
        coordination) · verifica que las llamadas SE HACEN. Suficiente
        para regresión-guard del wire.
        """
        calls = {"catalog": False, "company": False, "config": False}

        def _spy_catalog(name):
            calls["catalog"] = True

        def _spy_company():
            calls["company"] = True

        def _spy_config():
            calls["config"] = True

        # Patch las 3 funciones que el router llama tras PUT
        monkeypatch.setattr(
            "app.modules.catalog.router.invalidate_catalog_cache", _spy_catalog
        )
        monkeypatch.setattr(
            "app.modules.catalog.router.invalidate_company_config_cache", _spy_company
        )
        monkeypatch.setattr(
            "app.core.company_config.invalidate_config_cache", _spy_config
        )

        r = await client.put(
            "/api/catalog/config",
            json={"content": {"measurements": {"default_zocalo_height": 0.05}}},
        )
        assert r.status_code == 200

        assert calls["catalog"], "invalidate_catalog_cache no fue invocado"
        assert calls["company"], "invalidate_company_config_cache no fue invocado"
        assert calls["config"], "invalidate_config_cache no fue invocado"
