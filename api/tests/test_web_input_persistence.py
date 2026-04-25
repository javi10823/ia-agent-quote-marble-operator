"""Tests para persistencia de `web_input` (PR #400).

Cuando el bot externo hace `POST /api/v1/quote`, el body crudo se
guarda en `Quote.web_input` para que el operador pueda auditar
exactamente qué llegó vs qué derivó el backend (resolve_pileta,
parse_measurements, fuzzy material correction).

Cubre:
  - Path con-pieces: el body se persiste cuando hay pieces.
  - Path sin-pieces (DRAFT/PENDING): el body se persiste igual.
  - Schema response: `GET /api/quotes/:id` expone `web_input`.
  - Enum serialization: `pileta` (PiletaType) sale como string, no
    como `PiletaType.EMPOTRADA_JOHNSON` (sino el JSON column rompe).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.quote import Quote


# ═══════════════════════════════════════════════════════════════════════
# POST /api/v1/quote → web_input persistido en DB
# ═══════════════════════════════════════════════════════════════════════


class TestWebInputPersistedOnPost:
    @pytest.mark.asyncio
    async def test_with_pieces_persists_body(self, client, db_session):
        """Path con-pieces: body crudo se guarda en quote.web_input."""
        body = {
            "client_name": "Perdomo Fabiana",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.30, "prof": 0.60},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
            "sink_type": {"basin_count": "simple", "mount_type": "abajo"},
            "pileta_sku": "JOHNSON-LAVANDA",
            "notes": "Compra la bacha en D'Angelo",
        }
        with patch(
            "app.modules.quote_engine.router.upload_to_drive",
            return_value={"ok": True, "drive_url": "https://drive.test"},
        ):
            resp = await client.post("/api/v1/quote", json=body)
        assert resp.status_code == 200, resp.text

        quote_id = resp.json()["quotes"][0]["quote_id"]
        result = await db_session.execute(select(Quote).where(Quote.id == quote_id))
        quote = result.scalar_one()
        assert quote.web_input is not None, "web_input debería persistirse"
        # Campos clave del body llegan literal (no derivados).
        assert quote.web_input["client_name"] == "Perdomo Fabiana"
        assert quote.web_input["pileta_sku"] == "JOHNSON-LAVANDA"
        assert quote.web_input["notes"] == "Compra la bacha en D'Angelo"
        assert quote.web_input["sink_type"] == {
            "basin_count": "simple",
            "mount_type": "abajo",
        }
        # Drift guard: si alguien rompe model_dump(mode="json") y los
        # enums vuelven como objetos, el JSON column tira al insertar.
        # Acá ya pasó la persistencia → si llegamos hasta acá, está OK.

    @pytest.mark.asyncio
    async def test_without_pieces_persists_body(self, client, db_session):
        """Path sin-pieces (PENDING/DRAFT): body crudo igual se guarda.
        Este es el path crítico — sin pieces es donde más data hay que
        capturar (notas, sink_type, conversation, etc.)."""
        body = {
            "client_name": "Cliente Sin Piezas",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "plazo": "30 días",
            "notes": "Mesada de 2 metros aprox, todavía no tengo plano",
            "sink_type": {"basin_count": "doble", "mount_type": "arriba"},
        }
        with patch(
            "app.modules.quote_engine.text_parser.parse_measurements",
            return_value=None,  # forzar path sin pieces
        ):
            resp = await client.post("/api/v1/quote", json=body)
        assert resp.status_code == 200, resp.text

        quote_id = resp.json()["quotes"][0]["quote_id"]
        result = await db_session.execute(select(Quote).where(Quote.id == quote_id))
        quote = result.scalar_one()
        assert quote.web_input is not None
        assert quote.web_input["client_name"] == "Cliente Sin Piezas"
        assert quote.web_input["notes"].startswith("Mesada de 2 metros")
        assert quote.web_input["sink_type"]["basin_count"] == "doble"

    @pytest.mark.asyncio
    async def test_pileta_enum_serializes_to_string(self, client, db_session):
        """`pileta` (PiletaType enum) debe serializar como string en
        web_input. Si `model_dump()` sin mode="json" se cuela, los
        enums quedan como objetos no JSON-serializables y rompe el
        INSERT en SQLite/Postgres."""
        body = {
            "client_name": "Test Enum",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "plazo": "30 días",
            "pileta": "empotrada_johnson",
        }
        with patch(
            "app.modules.quote_engine.router.upload_to_drive",
            return_value={"ok": True, "drive_url": "https://drive.test"},
        ):
            resp = await client.post("/api/v1/quote", json=body)
        assert resp.status_code == 200, resp.text

        quote_id = resp.json()["quotes"][0]["quote_id"]
        result = await db_session.execute(select(Quote).where(Quote.id == quote_id))
        quote = result.scalar_one()
        # Si el enum no serializó bien, web_input sería None o
        # contendría algo como `"pileta": "PiletaType.EMPOTRADA_JOHNSON"`.
        assert quote.web_input is not None
        assert quote.web_input["pileta"] == "empotrada_johnson"


# ═══════════════════════════════════════════════════════════════════════
# GET /api/quotes/:id expone web_input
# ═══════════════════════════════════════════════════════════════════════


class TestQuoteDetailExposesWebInput:
    @pytest.mark.asyncio
    async def test_response_includes_web_input(self, client):
        """El detalle del quote debe traer web_input para que el
        frontend lo use en el botón 'Copiar solicitud'."""
        # Crear quote vía POST /api/v1/quote.
        body = {
            "client_name": "Detail Test",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "plazo": "30 días",
            "notes": "Notita",
        }
        with patch(
            "app.modules.quote_engine.router.upload_to_drive",
            return_value={"ok": True, "drive_url": "https://drive.test"},
        ):
            create_resp = await client.post("/api/v1/quote", json=body)
        quote_id = create_resp.json()["quotes"][0]["quote_id"]

        # Leer el detalle.
        detail_resp = await client.get(f"/api/quotes/{quote_id}")
        assert detail_resp.status_code == 200
        data = detail_resp.json()
        assert "web_input" in data, "QuoteDetailResponse debe incluir web_input"
        assert data["web_input"] is not None
        assert data["web_input"]["client_name"] == "Detail Test"
        assert data["web_input"]["notes"] == "Notita"

    @pytest.mark.asyncio
    async def test_operator_quote_has_null_web_input(self, client):
        """Quotes creados por el operador (no por el bot web) no tienen
        web_input — solo el path POST /v1/quote lo persiste."""
        # Crear quote vía operator endpoint.
        create_resp = await client.post("/api/quotes")
        assert create_resp.status_code == 200
        quote_id = create_resp.json()["id"]

        detail_resp = await client.get(f"/api/quotes/{quote_id}")
        assert detail_resp.status_code == 200
        data = detail_resp.json()
        # web_input debe estar presente en el schema pero null para operator.
        assert data.get("web_input") is None
