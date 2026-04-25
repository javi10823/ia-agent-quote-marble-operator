"""Tests para PR #398 — `GET /api/v1/business-rules`.

Subset v0 (acordado con operador, 2026-04-24):
  1. cocina_requires_capture — anti-Fabiana.
  2. ownership_options — cliente / dangelo.
  3. mount_options — abajo / arriba (levantado de SinkTypeInput).
  4. material families — levantadas de _FAMILY_CATALOGS (post-#396).

Endpoint público sin auth — el bot web lo fetchea al construir su
system prompt sin credenciales. Cache-Control + ETag para revalidación.
"""
from __future__ import annotations

from datetime import date

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Smoke: 200 con shape correcto
# ═══════════════════════════════════════════════════════════════════════


class TestBusinessRulesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_shape(self, client_no_auth):
        """Endpoint público — accesible sin cookie ni X-API-Key."""
        resp = await client_no_auth.get("/api/v1/business-rules")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "version" in body
        assert "sink" in body
        assert "materials" in body

    @pytest.mark.asyncio
    async def test_version_parses_as_iso_date(self, client_no_auth):
        """`version` debe ser ISO YYYY-MM-DD (parseable como fecha)."""
        resp = await client_no_auth.get("/api/v1/business-rules")
        v = resp.json()["version"]
        # Validación: fromisoformat acepta YYYY-MM-DD.
        parsed = date.fromisoformat(v)
        assert parsed.year >= 2025  # sanity: no es una fecha basura.

    @pytest.mark.asyncio
    async def test_sink_fields_typed_correctly(self, client_no_auth):
        body = (await client_no_auth.get("/api/v1/business-rules")).json()
        sink = body["sink"]

        assert isinstance(sink["cocina_requires_capture"], bool)
        assert sink["cocina_requires_capture"] is True

        assert isinstance(sink["ownership_options"], list)
        assert sink["ownership_options"] == ["cliente", "dangelo"]

        assert isinstance(sink["mount_options"], list)
        # Orden no importa, contenido sí.
        assert set(sink["mount_options"]) == {"abajo", "arriba"}

    @pytest.mark.asyncio
    async def test_materials_families_match_internal_catalog(self, client_no_auth):
        """Las familias expuestas DEBEN coincidir con el matcher interno
        post-#396. Si alguien renombra `_FAMILY_CATALOGS`, este test
        detecta drift."""
        from app.modules.quote_engine.calculator import _FAMILY_CATALOGS

        body = (await client_no_auth.get("/api/v1/business-rules")).json()
        families = body["materials"]["families"]

        assert isinstance(families, list)
        assert all(isinstance(f, str) for f in families)
        assert set(families) == set(_FAMILY_CATALOGS.keys())
        # v0 debe incluir las 8 conocidas.
        for expected in (
            "puraprima", "purastone", "silestone", "dekton",
            "neolith", "laminatto", "granito", "marmol",
        ):
            assert expected in families, f"missing family: {expected}"


# ═══════════════════════════════════════════════════════════════════════
# Acceso público (sin auth)
# ═══════════════════════════════════════════════════════════════════════


class TestPublicAccess:
    @pytest.mark.asyncio
    async def test_no_jwt_cookie_required(self, client_no_auth):
        """Sin cookie de sesión → no 401."""
        resp = await client_no_auth.get("/api/v1/business-rules")
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_no_x_api_key_required(self, client_no_auth):
        """Sin X-API-Key → no 401. El bot web lo fetchea sin
        credenciales."""
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={},  # explícitamente sin headers
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Cache-Control + ETag
# ═══════════════════════════════════════════════════════════════════════


class TestCachingHeaders:
    @pytest.mark.asyncio
    async def test_cache_control_max_age_3600(self, client_no_auth):
        resp = await client_no_auth.get("/api/v1/business-rules")
        cc = resp.headers.get("cache-control") or resp.headers.get("Cache-Control")
        assert cc is not None
        assert "max-age=3600" in cc

    @pytest.mark.asyncio
    async def test_etag_present_and_quoted(self, client_no_auth):
        """ETag debe venir con comillas dobles según RFC 7232."""
        resp = await client_no_auth.get("/api/v1/business-rules")
        etag = resp.headers.get("etag") or resp.headers.get("ETag")
        assert etag is not None
        assert etag.startswith('"') and etag.endswith('"')

    @pytest.mark.asyncio
    async def test_etag_stable_across_requests(self, client_no_auth):
        """Mismo payload → mismo ETag. Determinístico (sort_keys
        en el hash)."""
        r1 = await client_no_auth.get("/api/v1/business-rules")
        r2 = await client_no_auth.get("/api/v1/business-rules")
        e1 = r1.headers.get("etag") or r1.headers.get("ETag")
        e2 = r2.headers.get("etag") or r2.headers.get("ETag")
        assert e1 == e2

    @pytest.mark.asyncio
    async def test_if_none_match_returns_304(self, client_no_auth):
        """Cliente revalida con ETag actual → 304 Not Modified."""
        first = await client_no_auth.get("/api/v1/business-rules")
        etag = first.headers.get("etag") or first.headers.get("ETag")

        revalidate = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"If-None-Match": etag},
        )
        assert revalidate.status_code == 304

    @pytest.mark.asyncio
    async def test_if_none_match_mismatch_returns_200(self, client_no_auth):
        """ETag distinto al actual → 200 con body fresco."""
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"If-None-Match": '"stale-etag-xyz"'},
        )
        assert resp.status_code == 200
        # Body presente.
        assert "version" in resp.json()


# ═══════════════════════════════════════════════════════════════════════
# Anti-leak: no expone data sensible
# ═══════════════════════════════════════════════════════════════════════


class TestNoSensitiveLeak:
    """Garantía explícita: el payload NO contiene precios, SKUs
    internos, lógica comercial. Si alguien agrega un campo nuevo que
    rompa esto, los tests fallan."""

    @pytest.mark.asyncio
    async def test_payload_keys_are_only_v0_subset(self, client_no_auth):
        body = (await client_no_auth.get("/api/v1/business-rules")).json()
        assert set(body.keys()) == {"version", "sink", "materials"}

    @pytest.mark.asyncio
    async def test_no_price_fields_anywhere(self, client_no_auth):
        """Ninguna key del payload debe sonar a precio."""
        body = (await client_no_auth.get("/api/v1/business-rules")).json()
        blob = str(body).lower()
        for forbidden in ("price", "precio", "iva", "ars", "usd",
                          "discount", "descuento", "merma", "margen"):
            assert forbidden not in blob, (
                f"payload contiene token sensible: {forbidden!r}"
            )

    @pytest.mark.asyncio
    async def test_no_sku_fields(self, client_no_auth):
        """No exponer SKUs internos (ej: 'PURAGREY', 'LUXOR171',
        'PEGADOPILETA')."""
        body = (await client_no_auth.get("/api/v1/business-rules")).json()
        blob = str(body).upper()
        for forbidden in ("PURAGREY", "LUXOR", "PEGADOPILETA", "QUADRA",
                          "JOHNSON", "SILVER GREY", "BLANCO NORTE"):
            assert forbidden not in blob, (
                f"payload contiene SKU/marca: {forbidden!r}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Función pura `build_rules()`
# ═══════════════════════════════════════════════════════════════════════


class TestBuildRulesPure:
    """`build_rules()` es función pura — sin DB, sin LLM. Llamable
    desde tests sin fixtures."""

    def test_pure_function_returns_pydantic_model(self):
        from app.modules.business_rules.rules import build_rules
        from app.modules.business_rules.schema import BusinessRulesV0

        rules = build_rules()
        assert isinstance(rules, BusinessRulesV0)
        assert rules.sink.cocina_requires_capture is True
        assert rules.sink.ownership_options == ["cliente", "dangelo"]

    def test_mount_options_are_lifted_from_quote_input(self):
        """Drift guard: si alguien renombra el Literal en
        SinkTypeInput.mount_type, el endpoint refleja el cambio. Y si
        rompe el shape, este test falla en el import."""
        from app.modules.business_rules.rules import build_rules
        from app.modules.quote_engine.schemas import SinkTypeInput
        from typing import get_args

        rules = build_rules()
        expected = list(get_args(
            SinkTypeInput.model_fields["mount_type"].annotation
        ))
        assert rules.sink.mount_options == expected

    def test_families_lifted_from_calculator_constant(self):
        """Drift guard idem para `_FAMILY_CATALOGS`."""
        from app.modules.business_rules.rules import build_rules
        from app.modules.quote_engine.calculator import _FAMILY_CATALOGS

        rules = build_rules()
        assert rules.materials.families == list(_FAMILY_CATALOGS.keys())
