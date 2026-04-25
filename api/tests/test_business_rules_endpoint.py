"""Tests para `GET /api/v1/business-rules` v0 (PR #399 rework de #398).

Shape prescriptivo (copy-paste-into-prompt). Auth con `X-API-Key`
(mismo esquema que `/api/v1/quote`).

Cobertura:
  - 401 sin api-key.
  - 401 con api-key inválida.
  - 200 con api-key válida.
  - Shape correcto (rules.bacha.question, payload_mapping, etc.).
  - Endpoint NO requiere cookie/sesión del operador (X-API-Key alcanza).
  - Cache-Control + ETag + If-None-Match → 304.
  - Anti-leak: no precios, no SKUs internos.
"""
from __future__ import annotations

import pytest

from app.core import auth as _auth_mod
from app.modules.quote_engine import router as _qe_router_mod


_TEST_API_KEY = "test-marble-api-key-396"


@pytest.fixture
def with_api_key(monkeypatch):
    """Setea `QUOTE_API_KEY` en ambos lugares donde se lee desde
    `settings`: el del agent middleware (auth.py) y el del verify_api_key
    del quote_engine router. Sin esto, el check se skipea (dev mode)."""
    monkeypatch.setattr(_auth_mod.settings, "QUOTE_API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(_qe_router_mod.settings, "QUOTE_API_KEY", _TEST_API_KEY)
    return _TEST_API_KEY


# ═══════════════════════════════════════════════════════════════════════
# Auth con X-API-Key
# ═══════════════════════════════════════════════════════════════════════


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_401(self, client_no_auth, with_api_key):
        """Sin header X-API-Key → 401 con mensaje del verify_api_key."""
        resp = await client_no_auth.get("/api/v1/business-rules")
        assert resp.status_code == 401
        # Mensaje del helper (ver quote_engine/router.py::verify_api_key).
        assert "API key" in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_wrong_api_key_returns_401(self, client_no_auth, with_api_key):
        """Con X-API-Key incorrecta → 401."""
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": "wrong-key-xyz"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_returns_200(self, client_no_auth, with_api_key):
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_no_cookie_session_required(self, client_no_auth, with_api_key):
        """El endpoint NO requiere cookie del operador. Con X-API-Key
        sola alcanza, sin importar que el cliente no tenga JWT."""
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_lowercase_header_accepted(self, client_no_auth, with_api_key):
        """`x-api-key` lowercase también — los headers HTTP son
        case-insensitive."""
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"x-api-key": _TEST_API_KEY},
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Shape del payload
# ═══════════════════════════════════════════════════════════════════════


class TestPayloadShape:
    async def _get(self, client, with_api_key):
        resp = await client.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        assert resp.status_code == 200
        return resp.json()

    @pytest.mark.asyncio
    async def test_top_level_has_version_and_rules(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        assert set(body.keys()) == {"version", "rules"}

    @pytest.mark.asyncio
    async def test_version_format(self, client_no_auth, with_api_key):
        """`version` con formato `YYYY-MM-DD-vN`."""
        import re
        body = await self._get(client_no_auth, with_api_key)
        v = body["version"]
        assert re.match(r"^\d{4}-\d{2}-\d{2}-v\d+$", v), f"version inválida: {v!r}"

    # ── Bacha ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rules_bacha_question_present(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        bacha = body["rules"]["bacha"]
        assert isinstance(bacha["question"], str)
        # El copy literal debe incluir las opciones del cliente.
        assert "tenés" in bacha["question"] or "tienes" in bacha["question"]
        assert "comprás" in bacha["question"] or "compras" in bacha["question"]

    @pytest.mark.asyncio
    async def test_rules_bacha_requires_clarification_when_mentioned(
        self, client_no_auth, with_api_key,
    ):
        body = await self._get(client_no_auth, with_api_key)
        assert body["rules"]["bacha"]["requires_clarification_when_mentioned"] is True

    @pytest.mark.asyncio
    async def test_rules_bacha_do_not_ask(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        do_not_ask = body["rules"]["bacha"]["do_not_ask"]
        assert isinstance(do_not_ask, list)
        # Topics que el bot NO debe preguntar (regla del operador).
        assert "simple/doble" in do_not_ask
        assert "arriba/abajo" in do_not_ask

    @pytest.mark.asyncio
    async def test_rules_bacha_payload_mapping(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        mapping = body["rules"]["bacha"]["payload_mapping"]
        # Mapping de la respuesta del cliente al enum `pileta` de
        # POST /api/v1/quote (#397).
        assert mapping == {
            "propia": "empotrada_cliente",
            "dangelo": "empotrada_johnson",
            "apoyo": "apoyo",
        }

    @pytest.mark.asyncio
    async def test_rules_bacha_notes_non_empty(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        notes = body["rules"]["bacha"]["notes"]
        assert isinstance(notes, list)
        assert len(notes) >= 1
        # Cada nota es un string de prompt.
        assert all(isinstance(n, str) and n for n in notes)
        # Al menos una nota cubre el escenario clave (anti-Fabiana).
        joined = " ".join(notes).lower()
        assert "pileta" in joined or "bacha" in joined
        assert "d'angelo" in joined or "dangelo" in joined.replace("'", "")

    # ── Materials ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rules_materials_flags(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        m = body["rules"]["materials"]
        assert m["marble_not_recommended_for_kitchen"] is True
        assert m["silestone_purastone_not_for_exterior"] is True

    @pytest.mark.asyncio
    async def test_rules_materials_families_present(self, client_no_auth, with_api_key):
        """`families` queda subordinado al shape `rules.materials.*` —
        no como endpoint paralelo. Levantado de _FAMILY_CATALOGS."""
        from app.modules.quote_engine.calculator import _FAMILY_CATALOGS

        body = await self._get(client_no_auth, with_api_key)
        families = body["rules"]["materials"]["families"]
        assert isinstance(families, list)
        assert set(families) == set(_FAMILY_CATALOGS.keys())

    # ── Naming ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rules_naming_flags(self, client_no_auth, with_api_key):
        body = await self._get(client_no_auth, with_api_key)
        n = body["rules"]["naming"]
        assert n["purastone_one_word"] is True
        assert n["puraprima_one_word"] is True


# ═══════════════════════════════════════════════════════════════════════
# Cache-Control + ETag
# ═══════════════════════════════════════════════════════════════════════


class TestCachingHeaders:
    @pytest.mark.asyncio
    async def test_cache_control(self, client_no_auth, with_api_key):
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        cc = resp.headers.get("cache-control") or resp.headers.get("Cache-Control")
        assert cc is not None
        assert "max-age=3600" in cc

    @pytest.mark.asyncio
    async def test_etag_stable(self, client_no_auth, with_api_key):
        h = {"X-API-Key": _TEST_API_KEY}
        r1 = await client_no_auth.get("/api/v1/business-rules", headers=h)
        r2 = await client_no_auth.get("/api/v1/business-rules", headers=h)
        e1 = r1.headers.get("etag") or r1.headers.get("ETag")
        e2 = r2.headers.get("etag") or r2.headers.get("ETag")
        assert e1 and e2 and e1 == e2

    @pytest.mark.asyncio
    async def test_if_none_match_returns_304(self, client_no_auth, with_api_key):
        h = {"X-API-Key": _TEST_API_KEY}
        first = await client_no_auth.get("/api/v1/business-rules", headers=h)
        etag = first.headers.get("etag") or first.headers.get("ETag")
        revalidate = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={**h, "If-None-Match": etag},
        )
        assert revalidate.status_code == 304


# ═══════════════════════════════════════════════════════════════════════
# Anti-leak — no expone data sensible
# ═══════════════════════════════════════════════════════════════════════


class TestNoSensitiveLeak:
    @pytest.mark.asyncio
    async def test_no_price_tokens(self, client_no_auth, with_api_key):
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        blob = str(resp.json()).lower()
        for forbidden in (
            "price", "precio", "ars", "usd", "iva", "discount", "merma",
            "margen", "$",
        ):
            assert forbidden not in blob, f"token sensible: {forbidden!r}"

    @pytest.mark.asyncio
    async def test_no_internal_skus(self, client_no_auth, with_api_key):
        """Ningún SKU interno (PEGADOPILETA, PURAGREY, LUXOR, etc.)
        debe filtrarse al payload del bot web.

        Nota sobre 'JOHNSON': el string aparece intencionalmente como
        parte de `empotrada_johnson` — valor del enum `PiletaType` que
        es **contrato público** de POST /api/v1/quote (el bot lo manda
        de vuelta en `pileta`). Por eso no se chequea acá: no es un
        SKU interno, es vocabulario de la API."""
        resp = await client_no_auth.get(
            "/api/v1/business-rules",
            headers={"X-API-Key": _TEST_API_KEY},
        )
        blob = str(resp.json()).upper()
        for forbidden in (
            "PURAGREY", "PEGADOPILETA", "LUXOR", "QUADRA",
            "SILVER GREY", "BLANCO NORTE", "ENKEL",
        ):
            assert forbidden not in blob, f"SKU interno filtrado: {forbidden!r}"


# ═══════════════════════════════════════════════════════════════════════
# build_rules() puro — drift guards
# ═══════════════════════════════════════════════════════════════════════


class TestBuildRulesPure:
    def test_returns_pydantic_model(self):
        from app.modules.business_rules.rules import build_rules
        from app.modules.business_rules.schema import BusinessRulesV0

        rules = build_rules()
        assert isinstance(rules, BusinessRulesV0)

    def test_families_lifted_from_calculator(self):
        from app.modules.business_rules.rules import build_rules
        from app.modules.quote_engine.calculator import _FAMILY_CATALOGS

        rules = build_rules()
        assert rules.rules.materials.families == list(_FAMILY_CATALOGS.keys())

    def test_payload_mapping_keys_match_quote_input_enum(self):
        """El mapping `payload_mapping` debe tener las 3 keys canónicas
        que el bot web envía. Los valores deben ser parseables como
        `PiletaType` enum del POST /api/v1/quote."""
        from app.modules.business_rules.rules import build_rules
        from app.modules.quote_engine.schemas import PiletaType

        rules = build_rules()
        mapping = rules.rules.bacha.payload_mapping
        assert set(mapping.keys()) == {"propia", "dangelo", "apoyo"}
        for v in mapping.values():
            # Si el valor no es parseable como PiletaType, esto rompe
            # (drift guard contra renombre del enum).
            PiletaType(v)
