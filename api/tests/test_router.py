"""Integration tests for API endpoints."""

import pytest


# ── POST /api/quotes — create ────────────────────────────────────────────────

class TestCreateQuote:
    @pytest.mark.asyncio
    async def test_create_returns_id(self, client):
        resp = await client.post("/api/quotes")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert len(data["id"]) > 10  # UUID format

    @pytest.mark.asyncio
    async def test_create_without_status_defaults_to_draft(self, client):
        resp = await client.post("/api/quotes")
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_with_status_draft(self, client):
        resp = await client.post("/api/quotes", json={"status": "draft"})
        assert resp.status_code == 200
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_with_status_pending(self, client):
        resp = await client.post("/api/quotes", json={"status": "pending"})
        assert resp.status_code == 200
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_with_empty_body(self, client):
        """Empty JSON body should behave like no body — default to draft."""
        resp = await client.post("/api/quotes", json={})
        assert resp.status_code == 200
        quote_id = resp.json()["id"]
        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "draft"


# ── GET /api/quotes — list ───────────────────────────────────────────────────

class TestListQuotes:
    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        resp = await client.get("/api/quotes")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_after_create(self, client):
        # Create quotes with client_name so they appear in listing
        # (empty drafts are hidden from list_quotes)
        r1 = await client.post("/api/quotes")
        r2 = await client.post("/api/quotes")
        q1_id = r1.json()["id"]
        q2_id = r2.json()["id"]
        await client.patch(f"/api/quotes/{q1_id}", json={"client_name": "Test 1"})
        await client.patch(f"/api/quotes/{q2_id}", json={"client_name": "Test 2"})
        resp = await client.get("/api/quotes")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── GET /api/quotes/:id — detail ─────────────────────────────────────────────

class TestGetQuote:
    @pytest.mark.asyncio
    async def test_get_existing(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        resp = await client.get(f"/api/quotes/{quote_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == quote_id
        assert data["status"] == "draft"
        assert "messages" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_404(self, client):
        resp = await client.get("/api/quotes/nonexistent-id-12345")
        assert resp.status_code == 404


# ── DELETE /api/quotes/:id ───────────────────────────────────────────────────

class TestDeleteQuote:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/quotes/{quote_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["ok"] is True

        # Should be gone
        get_resp = await client.get(f"/api/quotes/{quote_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_404(self, client):
        resp = await client.delete("/api/quotes/nonexistent-id-12345")
        assert resp.status_code == 404


# ── PATCH /api/quotes/:id/status ─────────────────────────────────────────────

class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_draft_to_validated(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/quotes/{quote_id}/status",
            json={"status": "validated"},
        )
        assert resp.status_code == 200

        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "validated"

    @pytest.mark.asyncio
    async def test_validated_to_sent(self, client):
        create_resp = await client.post("/api/quotes")
        quote_id = create_resp.json()["id"]

        await client.patch(f"/api/quotes/{quote_id}/status", json={"status": "validated"})
        await client.patch(f"/api/quotes/{quote_id}/status", json={"status": "sent"})

        detail = await client.get(f"/api/quotes/{quote_id}")
        assert detail.json()["status"] == "sent"


# ── PATCH /api/quotes/:id — partial update ──────────────────────────────────

class TestPatchQuote:
    @pytest.mark.asyncio
    async def test_patch_client_name(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        resp = await client.patch(f"/api/quotes/{qid}", json={"client_name": "Juan"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["client_name"] == "Juan"

    @pytest.mark.asyncio
    async def test_patch_client_contact(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={
            "client_phone": "341-1234567",
            "client_email": "juan@test.com",
        })
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["client_phone"] == "341-1234567"
        assert detail["client_email"] == "juan@test.com"

    @pytest.mark.asyncio
    async def test_patch_localidad_colocacion(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={
            "localidad": "Rosario",
            "colocacion": True,
        })
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["localidad"] == "Rosario"
        assert detail["colocacion"] is True

    @pytest.mark.asyncio
    async def test_patch_pileta_anafe(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={
            "pileta": "empotrada_cliente",
            "anafe": True,
        })
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["pileta"] == "empotrada_cliente"
        assert detail["anafe"] is True

    @pytest.mark.asyncio
    async def test_patch_conversation_id(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={
            "conversation_id": "DA-1712300000-ABCD",
        })
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["conversation_id"] == "DA-1712300000-ABCD"

    @pytest.mark.asyncio
    async def test_patch_origin_maps_to_source(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        resp = await client.patch(f"/api/quotes/{qid}", json={"origin": "web"})
        assert resp.status_code == 200
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["source"] == "web"

    @pytest.mark.asyncio
    async def test_patch_material_string(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={"material": "Silestone Blanco"})
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["material"] == "Silestone Blanco"

    @pytest.mark.asyncio
    async def test_patch_material_array(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={
            "material": ["Silestone Blanco", "Dekton Kelya"],
        })
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["material"] == "Silestone Blanco, Dekton Kelya"

    @pytest.mark.asyncio
    async def test_patch_pieces(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        pieces = [
            {"description": "Mesada cocina", "largo": 2.5, "prof": 0.6},
            {"description": "Zocalo", "largo": 2.5},
        ]
        await client.patch(f"/api/quotes/{qid}", json={"pieces": pieces})
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert len(detail["pieces"]) == 2
        assert detail["pieces"][0]["description"] == "Mesada cocina"
        assert detail["pieces"][0]["largo"] == 2.5
        assert detail["pieces"][0]["prof"] == 0.6
        assert detail["pieces"][1]["prof"] is None

    @pytest.mark.asyncio
    async def test_patch_status_free(self, client):
        """Status via PATCH sets freely without transition validation."""
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={"status": "sent"})
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["status"] == "sent"

    @pytest.mark.asyncio
    async def test_patch_accumulative(self, client):
        """Multiple PATCHes accumulate fields without overwriting others."""
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={"client_name": "Juan"})
        await client.patch(f"/api/quotes/{qid}", json={"project": "Cocina"})
        await client.patch(f"/api/quotes/{qid}", json={"material": "Silestone"})

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["client_name"] == "Juan"
        assert detail["project"] == "Cocina"
        assert detail["material"] == "Silestone"

    @pytest.mark.asyncio
    async def test_patch_nonexistent_404(self, client):
        resp = await client.patch(
            "/api/quotes/nonexistent-id-12345",
            json={"client_name": "Test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_empty_body_400(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        resp = await client.patch(f"/api/quotes/{qid}", json={})
        assert resp.status_code == 400


# ── X-API-Key auth fallback ─────────────────────────────────────────────────

class TestApiKeyAuth:
    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, client_no_auth):
        resp = await client_no_auth.get("/api/quotes")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_header_grants_access(self, client_no_auth, monkeypatch):
        monkeypatch.setenv("QUOTE_API_KEY", "test-key-123")
        # Reload settings to pick up env var
        from app.core.config import Settings
        import app.core.config
        app.core.config.settings = Settings()
        import app.core.auth
        # Also reload auth module's reference
        from importlib import reload
        reload(app.core.auth)

        resp = await client_no_auth.get(
            "/api/quotes",
            headers={"X-API-Key": "test-key-123"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_wrong_api_key_returns_401(self, client_no_auth, monkeypatch):
        monkeypatch.setenv("QUOTE_API_KEY", "correct-key")
        from app.core.config import Settings
        import app.core.config
        app.core.config.settings = Settings()

        resp = await client_no_auth.get(
            "/api/quotes",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_works_for_post_quotes(self, client_no_auth, monkeypatch):
        monkeypatch.setenv("QUOTE_API_KEY", "test-key-123")
        from app.core.config import Settings
        import app.core.config
        app.core.config.settings = Settings()

        resp = await client_no_auth.post(
            "/api/quotes",
            headers={"X-API-Key": "test-key-123"},
        )
        assert resp.status_code == 200
        assert "id" in resp.json()

    @pytest.mark.asyncio
    async def test_api_key_works_for_patch_quotes(self, client_no_auth, monkeypatch):
        monkeypatch.setenv("QUOTE_API_KEY", "test-key-123")
        from app.core.config import Settings
        import app.core.config
        app.core.config.settings = Settings()

        # Create quote first
        create_resp = await client_no_auth.post(
            "/api/quotes",
            headers={"X-API-Key": "test-key-123"},
        )
        qid = create_resp.json()["id"]

        # Patch it
        resp = await client_no_auth.patch(
            f"/api/quotes/{qid}",
            json={"client_name": "API Key User"},
            headers={"X-API-Key": "test-key-123"},
        )
        assert resp.status_code == 200


# ── POST /v1/quote — quote engine ──────────────────────────────────────────

class TestQuoteEngine:
    @pytest.mark.asyncio
    async def test_create_without_pieces_and_notes_is_draft(self, client):
        """No pieces, no notes → DRAFT."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        qid = data["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_with_notes_no_pieces_is_pending(self, client):
        """Notes present but no pieces → PENDING (operator has data)."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "notes": "Plano adjunto: Marmoleria.pdf. Zócalo de 5cm.",
        })
        assert resp.status_code == 200
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_with_notes_has_contextual_merma_message(self, client):
        """With notes → merma motivo should say 'revision por operador'."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "notes": "Plano adjunto",
        })
        merma = resp.json()["quotes"][0]["merma"]
        assert "operador" in merma["motivo"].lower()

    @pytest.mark.asyncio
    async def test_create_without_notes_has_medidas_message(self, client):
        """Without notes → merma motivo should say 'medidas'."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
        })
        merma = resp.json()["quotes"][0]["merma"]
        assert "medidas" in merma["motivo"].lower()

    @pytest.mark.asyncio
    async def test_plazo_optional_does_not_error(self, client):
        """Plazo not provided should not cause validation error."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "notes": "Solo un test",
        })
        # Should succeed (200) — plazo defaults from config.json
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_saves_localidad_colocacion_pileta(self, client):
        """New fields should be saved in quote creation."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "anafe": True,
            "notes": "Con anafe y pileta",
        })
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["localidad"] == "Rosario"
        assert detail["colocacion"] is True
        assert detail["pileta"] == "empotrada_cliente"
        assert detail["anafe"] is True

    @pytest.mark.asyncio
    async def test_fuzzy_material_match(self, client):
        """Fuzzy match should correct typos in material name."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Sileston Blanco Nort",  # typo
            "localidad": "Rosario",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Should have matched to the real material
        assert "BLANCO NORTE" in data["quotes"][0]["material"].upper()

    @pytest.mark.asyncio
    async def test_fuzzy_adds_correction_note(self, client):
        """Fuzzy match should add correction note to quote."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Sileston Blanco Nort",
            "localidad": "Rosario",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        })
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert "Material corregido" in (detail["notes"] or "")

    @pytest.mark.asyncio
    async def test_exact_match_no_fuzzy(self, client):
        """Exact match should not trigger fuzzy or add correction note."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        })
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert "corregido" not in (detail["notes"] or "").lower()

    @pytest.mark.asyncio
    async def test_web_quote_has_source_web(self, client):
        """Web quotes should have source=web."""
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "notes": "test quote",
        })
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["source"] == "web"
