"""Tests for CORS configuration — preview URLs de Vercel.

Las preview URLs de Vercel tienen subdominios únicos por commit
(`<project>-git-<hash>-<team>.vercel.app`). No se pueden listar
estáticamente en `CORS_ORIGINS`, así que el backend usa
`allow_origin_regex` para permitirlas todas sin abrir la puerta a
dominios ajenos.

Estos tests verifican que:
- La regex del default matchea previews del team real.
- Rechaza orígenes externos (attacker.vercel.app, subdominios de otros teams).
- El endpoint real responde con header Access-Control-Allow-Origin correcto.
"""

import re
import pytest
from app.core.config import settings


class TestCorsRegexPattern:
    """Unit tests de la regex aislados — no dependen del servidor."""

    @pytest.fixture
    def pattern(self):
        return re.compile(settings.CORS_ORIGIN_REGEX)

    def test_matches_preview_url_git_branch(self, pattern):
        """Preview URL típica de rama: `<project>-git-<branch-hash>-<team>.vercel.app`."""
        url = "https://ia-agent-quote-marble-operator-git-c-d45cfe-javi10824s-projects.vercel.app"
        assert pattern.match(url) is not None

    def test_matches_preview_url_pr_hash(self, pattern):
        """Preview URL con hash de deploy (sin `git-` prefix)."""
        url = "https://ia-agent-quote-marble-operator-abc123xyz-javi10824s-projects.vercel.app"
        assert pattern.match(url) is not None

    def test_rejects_different_team(self, pattern):
        """Team distinto → no matchea. Previene CSRF desde otro proyecto Vercel."""
        url = "https://ia-agent-quote-marble-operator-git-main-attacker-team.vercel.app"
        assert pattern.match(url) is None

    def test_rejects_different_project(self, pattern):
        """Proyecto distinto con mismo team → no matchea."""
        url = "https://other-project-git-main-javi10824s-projects.vercel.app"
        assert pattern.match(url) is None

    def test_rejects_plain_vercel_app(self, pattern):
        """`vercel.app` solo → no matchea."""
        url = "https://vercel.app"
        assert pattern.match(url) is None

    def test_rejects_attacker_embedding_project_name(self, pattern):
        """Atacante que pone el nombre del proyecto como subdominio propio."""
        url = "https://ia-agent-quote-marble-operator.attacker.com"
        assert pattern.match(url) is None

    def test_rejects_http_scheme(self, pattern):
        """Requiere https — un atacante en HTTP no debe poder pasar."""
        url = "http://ia-agent-quote-marble-operator-x-javi10824s-projects.vercel.app"
        assert pattern.match(url) is None

    def test_rejects_trailing_path_as_origin(self, pattern):
        """El Origin header no trae path, pero por las dudas: con path no matchea."""
        url = "https://ia-agent-quote-marble-operator-x-javi10824s-projects.vercel.app/evil"
        assert pattern.match(url) is None


class TestCorsMiddlewareBehavior:
    """Tests end-to-end vía TestClient — verifica que CORSMiddleware está
    armado con la regex y que responde los headers correctos."""

    @pytest.mark.asyncio
    async def test_preview_origin_gets_cors_headers(self, client_no_auth):
        """Preflight OPTIONS desde una preview URL debe volver con
        Access-Control-Allow-Origin echoing el origin."""
        preview_origin = "https://ia-agent-quote-marble-operator-git-c-d45cfe-javi10824s-projects.vercel.app"
        res = await client_no_auth.options(
            "/api/quotes",
            headers={
                "Origin": preview_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORSMiddleware responde al preflight con 200 y los headers CORS
        assert res.headers.get("access-control-allow-origin") == preview_origin
        assert res.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_foreign_origin_gets_no_cors_headers(self, client_no_auth):
        """Origin de un team ajeno → sin header Access-Control-Allow-Origin.
        El browser bloquea la respuesta — que es lo que queremos."""
        res = await client_no_auth.options(
            "/api/quotes",
            headers={
                "Origin": "https://evil.attacker.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Sin allow-origin en la respuesta. (CORSMiddleware puede devolver
        # 400 o omitir el header según versión — ambos equivalen a bloqueo
        # desde la perspectiva del browser.)
        assert res.headers.get("access-control-allow-origin") != "https://evil.attacker.com"

    @pytest.mark.asyncio
    async def test_listed_origin_still_works(self, client_no_auth):
        """Las URLs listadas explícitamente en CORS_ORIGINS siguen funcionando —
        la regex es aditiva, no reemplaza."""
        # localhost:3000 está en el default de CORS_ORIGINS
        listed_origin = "http://localhost:3000"
        if listed_origin not in settings.CORS_ORIGINS:
            pytest.skip(f"{listed_origin} no está en CORS_ORIGINS de la config de test")
        res = await client_no_auth.options(
            "/api/quotes",
            headers={
                "Origin": listed_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.headers.get("access-control-allow-origin") == listed_origin
