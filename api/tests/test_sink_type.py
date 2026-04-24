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


# ═══════════════════════════════════════════════════════════════════════
# PR #397 — Defaults de pileta desde sink_type / pileta_sku
# ═══════════════════════════════════════════════════════════════════════
#
# Regla acordada con operador (2026-04-24):
#   1. body.pileta seteado → respetar.
#   2. body.pileta_sku presente → pileta=empotrada_johnson.
#   3. body.sink_type presente:
#        - mount_type=arriba → apoyo.
#        - mount_type=abajo  → empotrada_cliente.
#   4. Nada → None (comportamiento actual).
# basin_count NO multiplica pileta_qty (1 PEGADOPILETA, siempre).


class TestSinkTypeDefaultsPileta:
    """Sin body.pileta explícito, el router debe inferirlo desde
    sink_type / pileta_sku, y el calculator cotiza MO de pileta según."""

    async def _post_and_get_breakdown(self, client, **body_fields):
        """Helper: POST /api/v1/quote con los campos pedidos + un
        despiece mínimo. Retorna `quote_breakdown` del quote creado."""
        from unittest.mock import patch
        payload = {
            "client_name": "Test Pileta Resolver",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "plazo": "30 dias",
            **body_fields,
        }
        with patch(
            "app.modules.quote_engine.router.upload_to_drive",
            return_value={"ok": True, "drive_url": "https://drive.test"},
        ):
            resp = await client.post("/api/v1/quote", json=payload)
        assert resp.status_code == 200, resp.text
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = await client.get(f"/api/quotes/{qid}")
        return detail.json(), resp.json()["quotes"][0]

    @pytest.mark.asyncio
    async def test_sink_type_abajo_without_pileta_defaults_to_empotrada_cliente(
        self, client,
    ):
        """sink_type.mount_type=abajo sin pileta → empotrada_cliente.
        El calculator agrega PEGADOPILETA qty=1."""
        q, item = await self._post_and_get_breakdown(
            client,
            sink_type={"basin_count": "simple", "mount_type": "abajo"},
        )
        assert q["pileta"] == "empotrada_cliente"
        mo_descs = [mo["description"].lower() for mo in item["mo_items"]]
        assert any("pegado pileta" in d for d in mo_descs)

    @pytest.mark.asyncio
    async def test_sink_type_arriba_without_pileta_defaults_to_apoyo(
        self, client,
    ):
        """sink_type.mount_type=arriba sin pileta → apoyo.
        El calculator agrega AGUJERO PILETA APOYO (no PEGADOPILETA)."""
        q, item = await self._post_and_get_breakdown(
            client,
            sink_type={"basin_count": "simple", "mount_type": "arriba"},
        )
        assert q["pileta"] == "apoyo"
        mo_descs = [mo["description"].lower() for mo in item["mo_items"]]
        assert any("pileta apoyo" in d for d in mo_descs)

    @pytest.mark.asyncio
    async def test_pileta_sku_without_enum_defaults_to_empotrada_johnson(
        self, client,
    ):
        """pileta_sku sin pileta enum → empotrada_johnson.
        La bacha entra como producto si el SKU matchea sinks.json."""
        q, item = await self._post_and_get_breakdown(
            client,
            pileta_sku="Z52",  # existe en sinks.json
        )
        assert q["pileta"] == "empotrada_johnson"
        # El item físico pileta entra al breakdown via sinks[]
        assert q["quote_breakdown"].get("sinks"), (
            "esperaba que la bacha entre como producto cuando pileta_sku matchea"
        )
        sinks = q["quote_breakdown"]["sinks"]
        assert any("JOHNSON" in (s.get("name") or "").upper() for s in sinks)
        # MO de PEGADOPILETA también presente.
        mo_descs = [mo["description"].lower() for mo in item["mo_items"]]
        assert any("pegado pileta" in d for d in mo_descs)

    @pytest.mark.asyncio
    async def test_pileta_sku_with_explicit_pileta_respects_explicit(
        self, client,
    ):
        """Si el cliente manda ambos, body.pileta gana sobre la
        inferencia por sku (prioridad 1 de la regla)."""
        q, item = await self._post_and_get_breakdown(
            client,
            pileta="apoyo",  # explícito
            pileta_sku="Z52",
        )
        assert q["pileta"] == "apoyo"
        # Nota: con pileta=apoyo el calculator NO agrega sink product
        # (la rama de sinks[] requiere empotrada_johnson).
        mo_descs = [mo["description"].lower() for mo in item["mo_items"]]
        assert any("pileta apoyo" in d for d in mo_descs)

    @pytest.mark.asyncio
    async def test_basin_count_doble_does_not_multiply_qty(self, client):
        """Regla del operador: doble sigue siendo 1 PEGADOPILETA, no 2.
        basin_count es dato comercial/contextual, no multiplicador."""
        q, item = await self._post_and_get_breakdown(
            client,
            sink_type={"basin_count": "doble", "mount_type": "abajo"},
        )
        # Un solo item de pegado pileta (no 2).
        pegado_items = [
            mo for mo in item["mo_items"]
            if "pegado pileta" in mo["description"].lower()
        ]
        assert len(pegado_items) == 1
        assert pegado_items[0]["quantity"] == 1

    @pytest.mark.asyncio
    async def test_no_pileta_no_sink_type_no_mo(self, client):
        """Sin pileta, sin sink_type, sin pileta_sku → comportamiento
        actual: el calculator no cotiza MO de pileta."""
        q, item = await self._post_and_get_breakdown(client)
        assert q["pileta"] is None
        mo_descs = [mo["description"].lower() for mo in item["mo_items"]]
        assert not any("pileta" in d for d in mo_descs)

    @pytest.mark.asyncio
    async def test_explicit_pileta_respected_over_sink_type(self, client):
        """body.pileta explícito (apoyo) + sink_type.mount_type=abajo
        (que inferiría empotrada_cliente) → gana el explícito."""
        q, item = await self._post_and_get_breakdown(
            client,
            pileta="apoyo",
            sink_type={"basin_count": "simple", "mount_type": "abajo"},
        )
        assert q["pileta"] == "apoyo"

    @pytest.mark.asyncio
    async def test_pileta_sku_not_found_still_adds_mo(self, client):
        """Si pileta_sku se envía pero no existe en sinks.json → MO
        PEGADOPILETA sí entra (regla #5: 'si no hay pileta_sku, igual
        tiene que entrar la MO correspondiente')."""
        q, item = await self._post_and_get_breakdown(
            client,
            pileta_sku="INEXISTENTE_XYZ123",
        )
        assert q["pileta"] == "empotrada_johnson"
        mo_descs = [mo["description"].lower() for mo in item["mo_items"]]
        assert any("pegado pileta" in d for d in mo_descs), (
            "MO debe entrar aunque el SKU del producto no matchee"
        )


class TestSinkTypeDefaultsNoPiecesPath:
    """Path no-pieces: el default se aplica antes de persistir el
    quote DRAFT/PENDING. La DB refleja el pileta resuelto."""

    @pytest.mark.asyncio
    async def test_no_pieces_sink_type_resolves_pileta(self, client):
        """Sin pieces + sink_type abajo sin pileta → persiste
        empotrada_cliente en Quote.pileta (para que el operador vea el
        estado correcto al abrir el quote)."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Web No Pieces",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "sink_type": {"basin_count": "simple", "mount_type": "abajo"},
            "notes": "Mesada con bacha simple",
        })
        assert resp.status_code == 200
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["pileta"] == "empotrada_cliente"

    @pytest.mark.asyncio
    async def test_no_pieces_pileta_sku_defaults_johnson(self, client):
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Web SKU",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "pileta_sku": "LUXOR171",
            "notes": "Cliente pidió Johnson",
        })
        assert resp.status_code == 200
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["pileta"] == "empotrada_johnson"
