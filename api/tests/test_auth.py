"""Tests for auth endpoints — create-user protection, username strip."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.auth import (
    create_token,
    COOKIE_NAME,
    ALGORITHM,
    TOKEN_EXPIRY_HOURS,
    REFRESH_THRESHOLD_HOURS,
)
from app.core.config import settings


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


class TestAuthHeaderFallback:
    """
    Auth vía `Authorization: Bearer <jwt>` header — fallback para clientes
    que no pueden usar cookies cross-origin (iOS Safari con ITP).

    El backend acepta el token desde dos fuentes:
    1. Cookie `auth_token` (primary — desktop).
    2. Header `Authorization: Bearer <token>` (fallback — mobile).

    Cookie tiene precedencia si ambos están presentes (ver
    `test_cookie_precedence_over_header`).
    """

    @pytest.mark.asyncio
    async def test_login_returns_token_in_body(self, client_no_auth):
        """Login debe devolver el JWT en el body además de setear la cookie.

        Esto es lo que permite al cliente guardarlo en localStorage y mandarlo
        por header en requests subsecuentes cuando la cookie no viaja.
        """
        await client_no_auth.post("/api/auth/create-user", json={
            "username": "admin",
            "password": "password123",
        })
        res = await client_no_auth.post("/api/auth/login", json={
            "username": "admin",
            "password": "password123",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["username"] == "admin"
        # Nuevo: token emitido en el body.
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 20  # JWTs son largos

        # Sanity: además de en el body, también debe estar en la cookie (el
        # cliente desktop sigue usando ese path sin cambios).
        assert COOKIE_NAME in res.cookies

    @pytest.mark.asyncio
    async def test_header_auth_accepted(self, client_no_auth):
        """Request con Authorization: Bearer <token> y sin cookie debe pasar."""
        token = create_token("test@test.com")
        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Si el header funcionó, el middleware lo deja pasar → no es 401.
        # (puede ser 200 con [] si no hay quotes — depende de fixtures — pero
        # definitivamente no 401).
        assert res.status_code != 401

    @pytest.mark.asyncio
    async def test_header_auth_case_insensitive_scheme(self, client_no_auth):
        """Scheme 'bearer' (lowercase) también debe ser aceptado."""
        token = create_token("test@test.com")
        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"bearer {token}"},
        )
        assert res.status_code != 401

    @pytest.mark.asyncio
    async def test_header_auth_with_invalid_token(self, client_no_auth):
        """Authorization con JWT inválido debe devolver 401."""
        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_header_auth_malformed_no_bearer_prefix(self, client_no_auth):
        """Header sin prefijo 'Bearer ' no se toma como token válido."""
        token = create_token("test@test.com")
        # Token sin prefijo → no matchea, cae a fallback → 401.
        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": token},
        )
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_cookie_precedence_over_header(self, client_no_auth):
        """Si cookie y header están presentes, prevalece la cookie.

        Caso raro pero posible: cliente que deja el header por sticky config
        mientras recibe una nueva cookie. Si son distintos, el backend usa
        la cookie (la fuente más reciente / más segura — httpOnly).
        """
        valid_cookie_token = create_token("cookie@test.com")
        valid_header_token = create_token("header@test.com")

        # Cookie válida + header con token CORRUPTO → si el middleware usara
        # el header por error, fallaría. Si usa la cookie, pasa.
        res_cookie_wins = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": "Bearer bogus.token.value"},
            cookies={COOKIE_NAME: valid_cookie_token},
        )
        assert res_cookie_wins.status_code != 401, (
            "Cookie válida debe ganar sobre header inválido"
        )

        # Sanity inversa: cookie corrupta + header válido → 401 (cookie gana,
        # pero está rota → no cae al header como fallback).
        res_cookie_loses = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {valid_header_token}"},
            cookies={COOKIE_NAME: "not-a-jwt"},
        )
        assert res_cookie_loses.status_code == 401, (
            "Cookie corrupta toma precedencia aunque header sea válido "
            "(evita que un header stale enmascare una sesión inválida)"
        )

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, client_no_auth):
        """Sin cookie ni header → 401 claro."""
        res = await client_no_auth.get("/api/quotes")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_x_api_key_fallback_still_works(self, client_no_auth, monkeypatch):
        """El fallback X-API-Key (web chatbot público) sigue funcionando
        después de agregar el Authorization header fallback."""
        # Set QUOTE_API_KEY en settings
        from app.core import auth as auth_mod
        monkeypatch.setattr(auth_mod.settings, "QUOTE_API_KEY", "test-api-key-xyz")

        res = await client_no_auth.get(
            "/api/quotes",
            headers={"x-api-key": "test-api-key-xyz"},
        )
        assert res.status_code != 401

    @pytest.mark.asyncio
    async def test_create_user_accepts_header_auth(self, client_no_auth):
        """El endpoint create-user también debe aceptar Authorization header
        (además de cookie), ya que usa el mismo helper."""
        # Crear primer user sin auth (initial setup).
        res1 = await client_no_auth.post("/api/auth/create-user", json={
            "username": "admin",
            "password": "password123",
        })
        assert res1.status_code == 200

        # Segundo user: usar token por header (sin cookie).
        token = create_token("admin")
        res2 = await client_no_auth.post(
            "/api/auth/create-user",
            json={"username": "operator", "password": "password123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 200


class TestExtractTokenHelper:
    """
    Unit tests del helper extract_token_from_request — aislado del resto del
    middleware para documentar claramente las reglas de parsing.
    """

    def _make_request(self, cookies=None, headers=None):
        """Construye un Request-like object mínimo para el helper."""
        from starlette.requests import Request

        headers_list = []
        if headers:
            for k, v in headers.items():
                headers_list.append((k.lower().encode(), v.encode()))
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers_list.append((b"cookie", cookie_str.encode()))

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers_list,
        }
        return Request(scope)

    def test_cookie_only(self):
        from app.core.auth import extract_token_from_request
        req = self._make_request(cookies={COOKIE_NAME: "cookie-token-abc"})
        assert extract_token_from_request(req) == "cookie-token-abc"

    def test_header_only(self):
        from app.core.auth import extract_token_from_request
        req = self._make_request(headers={"authorization": "Bearer header-token-xyz"})
        assert extract_token_from_request(req) == "header-token-xyz"

    def test_cookie_wins_over_header(self):
        from app.core.auth import extract_token_from_request
        req = self._make_request(
            cookies={COOKIE_NAME: "cookie-token"},
            headers={"authorization": "Bearer header-token"},
        )
        assert extract_token_from_request(req) == "cookie-token"

    def test_empty_returns_none(self):
        from app.core.auth import extract_token_from_request
        req = self._make_request()
        assert extract_token_from_request(req) is None

    def test_malformed_header_returns_none(self):
        from app.core.auth import extract_token_from_request
        # "Basic foo" → no es Bearer → ignorar.
        req = self._make_request(headers={"authorization": "Basic dXNlcjpwYXNz"})
        assert extract_token_from_request(req) is None

    def test_bearer_without_token_returns_none(self):
        from app.core.auth import extract_token_from_request
        # "Bearer " sin token → ignorar.
        req = self._make_request(headers={"authorization": "Bearer "})
        assert extract_token_from_request(req) is None

    def test_bearer_case_insensitive(self):
        from app.core.auth import extract_token_from_request
        # "bearer", "BEARER", "Bearer" todos válidos.
        for scheme in ("bearer", "BEARER", "Bearer", "BeArEr"):
            req = self._make_request(headers={"authorization": f"{scheme} tok123"})
            assert extract_token_from_request(req) == "tok123", scheme


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


# ═══════════════════════════════════════════════════════════════════════
# PR #389 — Sliding session refresh
# ═══════════════════════════════════════════════════════════════════════
#
# Al token activo le quedan <24h de vida → la siguiente request
# autenticada emite un token nuevo (cookie + header `X-Refreshed-Token`).
# Al activo le quedan >=24h → no se emite refresh (evita spam).
#
# Helpers para simular tokens con `exp` arbitrario sin tener que esperar
# días reales ni monkeypatchear `datetime.now` global.


def _make_token_with_remaining(email: str, remaining_hours: float) -> str:
    """Emite un JWT con `exp = now + remaining_hours`. Usado para simular
    tokens cerca/lejos de vencer sin tocar el reloj."""
    exp = datetime.now(timezone.utc) + timedelta(hours=remaining_hours)
    payload = {
        "sub": email,
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _decode_exp_hours(token: str) -> float:
    """Calcula horas restantes hasta `exp` del JWT."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    exp_dt = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    return (exp_dt - datetime.now(timezone.utc)).total_seconds() / 3600


class TestSlidingSessionRefresh:
    @pytest.mark.asyncio
    async def test_refresh_fires_when_under_threshold(self, client_no_auth):
        """Token con <24h de vida → el middleware emite uno nuevo en la
        response (cookie + header `X-Refreshed-Token`)."""
        # Token a punto de vencer: 2h de vida (umbral: 24h → debe refrescar).
        old_token = _make_token_with_remaining("test@test.com", remaining_hours=2)

        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert res.status_code != 401
        # El header expuesto debe tener el token fresco.
        refreshed = res.headers.get("X-Refreshed-Token") or res.headers.get("x-refreshed-token")
        assert refreshed, "esperaba X-Refreshed-Token en la response"
        assert refreshed != old_token, "el token nuevo debe diferir del viejo"
        # Y debe tener ~72h de vida (TOKEN_EXPIRY_HOURS).
        remaining = _decode_exp_hours(refreshed)
        assert remaining > TOKEN_EXPIRY_HOURS - 1  # tolerancia 1h
        # La cookie también se re-emite.
        assert COOKIE_NAME in res.cookies

    @pytest.mark.asyncio
    async def test_no_refresh_when_above_threshold(self, client_no_auth):
        """Token fresco (ej: acabado de emitir, ~72h) → no refresh — evita
        spam de Set-Cookie/header en cada request cuando la sesión está
        lejos de vencer."""
        fresh_token = create_token("test@test.com")
        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {fresh_token}"},
        )
        assert res.status_code != 401
        assert res.headers.get("X-Refreshed-Token") is None
        assert res.headers.get("x-refreshed-token") is None

    @pytest.mark.asyncio
    async def test_expired_token_returns_401_no_refresh(self, client_no_auth):
        """Token ya vencido (remaining < 0) → 401 con 'Sesión expirada'.
        No refresh (no podemos re-emitir en un token que no es válido)."""
        expired = _make_token_with_remaining("test@test.com", remaining_hours=-1)
        res = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Sesión expirada"
        assert res.headers.get("X-Refreshed-Token") is None

    @pytest.mark.asyncio
    async def test_no_token_returns_401_no_authenticado(self, client_no_auth):
        """Sin token ni cookie → 401 con 'No autenticado'. El string es
        el contract que el frontend matchea para el redirect a /login."""
        res = await client_no_auth.get("/api/quotes")
        assert res.status_code == 401
        assert res.json()["detail"] == "No autenticado"

    @pytest.mark.asyncio
    async def test_refresh_at_threshold_boundary(self, client_no_auth):
        """Token con exactamente REFRESH_THRESHOLD_HOURS - 0.1h de vida
        (apenas bajo el umbral) → sí refresh.
        Token con exactamente REFRESH_THRESHOLD_HOURS + 0.1h → no refresh."""
        just_under = _make_token_with_remaining(
            "test@test.com",
            remaining_hours=REFRESH_THRESHOLD_HOURS - 0.1,
        )
        res1 = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {just_under}"},
        )
        assert res1.headers.get("X-Refreshed-Token"), "justo bajo umbral debe refrescar"

        just_over = _make_token_with_remaining(
            "test@test.com",
            remaining_hours=REFRESH_THRESHOLD_HOURS + 0.1,
        )
        res2 = await client_no_auth.get(
            "/api/quotes",
            headers={"Authorization": f"Bearer {just_over}"},
        )
        assert res2.headers.get("X-Refreshed-Token") is None, "justo sobre umbral NO debe refrescar"
