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

    @pytest.mark.asyncio
    async def test_quote_becomes_visible_when_client_name_set(self, client):
        """PR #375 — regresión: un quote recién creado (empty draft)
        NO aparece en el listado. Apenas se setea `client_name`
        (ej: desde _run_dual_read al emitir la card de análisis), el
        quote se hace visible en el dashboard desde ese turno.

        Antes, con _extract_quote_info corriendo sólo al final del while
        loop de Claude (que nunca se alcanza cuando _run_dual_read hace
        return early con la card), la columna client_name quedaba vacía
        y el filtro del listado trataba el quote como empty draft aunque
        tuviera plano + mensajes + datos en el breakdown.
        """
        create = await client.post("/api/quotes")
        qid = create.json()["id"]

        # Paso 1: quote recién creado, todavía sin client_name → NO en lista.
        listing_before = await client.get("/api/quotes")
        assert listing_before.status_code == 200
        ids_before = {q["id"] for q in listing_before.json()}
        assert qid not in ids_before, (
            "Quote con client_name vacío debería estar oculto del listado"
        )

        # Paso 2: _run_dual_read simula setear client_name desde el brief.
        # Usamos PATCH como proxy — es la misma columna que updatearía el
        # helper _extract_column_updates_from_analysis.
        await client.patch(f"/api/quotes/{qid}", json={"client_name": "Erica Bernardi"})

        # Paso 3: ahora SÍ debe aparecer en el listado.
        listing_after = await client.get("/api/quotes")
        ids_after = {q["id"] for q in listing_after.json()}
        assert qid in ids_after, (
            "Quote con client_name seteado debe aparecer en el listado desde "
            "ese turno (no esperar a confirmación de medidas)"
        )


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
        body = del_resp.json()
        assert body["ok"] is True
        assert quote_id in body["deleted"]

        # Should be gone
        get_resp = await client.get(f"/api/quotes/{quote_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_parent_cascades_to_children(self, client):
        """Deleting a parent quote must also delete all its children."""
        parent = (await client.post("/api/quotes")).json()["id"]
        child = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{child}", json={"parent_quote_id": parent})

        del_resp = await client.delete(f"/api/quotes/{parent}")
        assert del_resp.status_code == 200
        body = del_resp.json()
        assert set(body["deleted"]) == {parent, child}

        assert (await client.get(f"/api/quotes/{parent}")).status_code == 404
        assert (await client.get(f"/api/quotes/{child}")).status_code == 404

    @pytest.mark.asyncio
    async def test_delete_child_cascades_to_family(self, client):
        """Deleting a child quote must also delete the parent and siblings."""
        parent = (await client.post("/api/quotes")).json()["id"]
        child1 = (await client.post("/api/quotes")).json()["id"]
        child2 = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{child1}", json={"parent_quote_id": parent})
        await client.patch(f"/api/quotes/{child2}", json={"parent_quote_id": parent})

        del_resp = await client.delete(f"/api/quotes/{child1}")
        assert del_resp.status_code == 200
        body = del_resp.json()
        assert set(body["deleted"]) == {parent, child1, child2}

        assert (await client.get(f"/api/quotes/{parent}")).status_code == 404
        assert (await client.get(f"/api/quotes/{child1}")).status_code == 404
        assert (await client.get(f"/api/quotes/{child2}")).status_code == 404

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

    @pytest.mark.asyncio
    async def test_patch_notes(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        notes = "Medir in situ antes del corte.\nCliente prefiere filo recto."
        resp = await client.patch(f"/api/quotes/{qid}", json={"notes": notes})
        assert resp.status_code == 200
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["notes"] == notes

    @pytest.mark.asyncio
    async def test_patch_project(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        resp = await client.patch(f"/api/quotes/{qid}", json={"project": "Cocina 1er piso"})
        assert resp.status_code == 200
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["project"] == "Cocina 1er piso"

    @pytest.mark.asyncio
    async def test_patch_client_name_max_length_exceeded(self, client):
        qid = (await client.post("/api/quotes")).json()["id"]
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"client_name": "x" * 501},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_empty_string_replaces_value(self, client):
        """Empty string is a valid write — operator can blank a field."""
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={"client_name": "Juan"})
        await client.patch(f"/api/quotes/{qid}", json={"client_name": ""})
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["client_name"] == ""

    @pytest.mark.asyncio
    async def test_patch_bool_false_writes(self, client):
        """Booleans set to False must persist (exclude_none=True must still include False)."""
        qid = (await client.post("/api/quotes")).json()["id"]
        await client.patch(f"/api/quotes/{qid}", json={"colocacion": True, "anafe": True})
        await client.patch(f"/api/quotes/{qid}", json={"colocacion": False, "anafe": False})
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["colocacion"] is False
        assert detail["anafe"] is False

    @pytest.mark.asyncio
    async def test_patch_all_editable_fields_together(self, client):
        """Operator can PATCH the full editable set in one request."""
        qid = (await client.post("/api/quotes")).json()["id"]
        payload = {
            "client_name": "Natalia",
            "project": "Echesortu",
            "material": "Granito Negro Boreal",
            "client_phone": "341-5555555",
            "client_email": "natalia@test.com",
            "localidad": "Rosario",
            "pileta": "empotrada_cliente",
            "colocacion": True,
            "anafe": False,
            "notes": "Edificio de 2 plantas",
        }
        resp = await client.patch(f"/api/quotes/{qid}", json=payload)
        assert resp.status_code == 200
        assert set(resp.json()["updated"]) == set(payload.keys())
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        for k, v in payload.items():
            assert detail[k] == v


# ── /regenerate helper: ediciones manuales pisan breakdown cacheado ─────────

class TestRegenerateDocDataBuild:
    """_build_regenerate_doc_data should override client_name/project/notes
    from the Quote column (manual edits via detail view) rather than trust
    the stale copies inside the cached breakdown."""

    def test_overrides_client_name_project_notes_from_quote(self):
        from app.modules.agent.router import _build_regenerate_doc_data
        from app.models.quote import Quote

        quote = Quote(
            id="q1",
            client_name="Natalia (editada)",
            project="Echesortu (editado)",
            material="Granito Negro Boreal",
            notes="Nota editada manualmente",
            total_ars=100000,
            total_usd=100,
        )
        stale_bd = {
            "client_name": "Nombre viejo",
            "project": "Proyecto viejo",
            "notes": "Nota vieja",
            "material_name": "Granito Negro Boreal",
            "sectors": [{"label": "cocina", "pieces": ["mesada"]}],
            "mo_items": [],
            "total_ars": 100000,
            "total_usd": 100,
        }

        data = _build_regenerate_doc_data(quote, stale_bd)

        assert data["client_name"] == "Natalia (editada)"
        assert data["project"] == "Echesortu (editado)"
        assert data["notes"] == "Nota editada manualmente"
        # El resto del breakdown queda intacto
        assert data["sectors"] == stale_bd["sectors"]
        assert data["material_name"] == "Granito Negro Boreal"
        assert data["total_ars"] == 100000

    def test_empty_notes_on_quote_clears_stale_notes(self):
        """Si el operador borra notas manualmente (notes=None o ''),
        no deben quedar las viejas del breakdown."""
        from app.modules.agent.router import _build_regenerate_doc_data
        from app.models.quote import Quote

        quote = Quote(id="q1", client_name="X", project="Y", notes=None)
        stale_bd = {"client_name": "A", "project": "B", "notes": "vieja"}

        data = _build_regenerate_doc_data(quote, stale_bd)
        assert data["notes"] is None

    def test_setdefault_fills_legacy_breakdowns_missing_keys(self):
        """Breakdowns viejos pueden no tener sectors/mo_items/totals — fallback."""
        from app.modules.agent.router import _build_regenerate_doc_data
        from app.models.quote import Quote

        quote = Quote(
            id="q1", client_name="X", project="Y",
            material="Silestone", total_ars=50000, total_usd=50, notes=None,
        )
        legacy_bd = {}

        data = _build_regenerate_doc_data(quote, legacy_bd)
        assert data["material_name"] == "Silestone"
        assert data["total_ars"] == 50000
        assert data["total_usd"] == 50
        assert data["discount_pct"] == 0
        assert data["sectors"] == []
        assert data["mo_items"] == []

    def test_normalize_alzada_labels_in_cached_sectors(self):
        """Quotes viejos tienen Alzadas con detalle + leyenda TRAMOS pegados
        en el label cacheado. Regenerate debe colapsarlos a '{L} × {D} Alzada'
        sin modificar mesadas ni otros labels."""
        from app.modules.agent.router import _build_regenerate_doc_data
        from app.models.quote import Quote

        quote = Quote(id="q1", client_name="X", project="Y", notes=None)
        bd = {
            "sectors": [{
                "label": "Cocina",
                "pieces": [
                    "0.38 × 0.60 Placa tramo izquierdo",
                    "2.03 × 0.60 Placa tramo derecho",
                    "3.01 × 0.60 Alzada corrida (fondo completo sin heladera) (SE REALIZA EN 2 TRAMOS)",
                    "4.10 × 0.65 Mesada tramo 1 (SE REALIZA EN 2 TRAMOS)",
                ],
            }],
        }

        data = _build_regenerate_doc_data(quote, bd)
        pieces = data["sectors"][0]["pieces"]
        assert pieces[0] == "0.38 × 0.60 Placa tramo izquierdo"
        assert pieces[1] == "2.03 × 0.60 Placa tramo derecho"
        assert pieces[2] == "3.01 × 0.60 Alzada"
        # Mesadas no se tocan — la leyenda 2 TRAMOS es válida para mesadas
        assert pieces[3] == "4.10 × 0.65 Mesada tramo 1 (SE REALIZA EN 2 TRAMOS)"

    def test_normalize_preserves_override_star_on_alzada(self):
        """Si el label tenía sufijo ' *' (override de m²), debe preservarse."""
        from app.modules.agent.router import _build_regenerate_doc_data
        from app.models.quote import Quote

        quote = Quote(id="q1", client_name="X", project="Y", notes=None)
        bd = {
            "sectors": [{
                "label": "Cocina",
                "pieces": ["3.01 × 0.60 Alzada corrida (SE REALIZA EN 2 TRAMOS) *"],
            }],
        }
        data = _build_regenerate_doc_data(quote, bd)
        assert data["sectors"][0]["pieces"][0] == "3.01 × 0.60 Alzada *"


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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
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
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "localidad": "Rosario",
            "notes": "test quote",
        })
        qid = resp.json()["quotes"][0]["quote_id"]
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["source"] == "web"


# ═══════════════════════════════════════════════════════════════════════
# PR #378 — Endpoint POST /api/quotes/:id/reopen-measurements
# ═══════════════════════════════════════════════════════════════════════

class TestReopenMeasurements:
    """Endpoint que permite al operador reabrir edición después de haber
    confirmado medidas. Invalida el Paso 2 (material + MO + totales) y
    deja el quote en 'Paso 1 editable'."""

    async def _make_paso2_quote(self, client, db_session) -> str:
        """Helper: crea quote y lo pone en estado post-Paso 2 (con
        verified_context + material + totales)."""
        from app.models.quote import Quote
        from sqlalchemy import select, update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        # Parchear el breakdown directo en DB para simular Paso 2 completo.
        bd = {
            "dual_read_result": {"sectores": [{"tipo": "cocina"}]},
            "brief_analysis": {"client_name": "Erica Bernardi"},
            "verified_context": "[MEDIDAS VERIFICADAS...]",
            "verified_measurements": {"sectores": []},
            "verified_commercial_attrs": {"anafe_count": {"value": 1}},
            "material_name": "PURASTONE",
            "total_ars": 797177,
            "total_usd": 4128,
            "mo_items": [{"description": "Colocación"}],
            "sectors": [{"label": "COCINA"}],
        }
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                quote_breakdown=bd,
                total_ars=797177,
                total_usd=4128,
            )
        )
        await db_session.commit()
        return qid

    @pytest.mark.asyncio
    async def test_reopen_clears_paso2_state(self, client, db_session):
        """Post-reopen: verified_context, material, totales, mo_items desaparecen;
        dual_read_result y brief_analysis se preservan."""
        qid = await self._make_paso2_quote(client, db_session)

        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 200, resp.text

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        bd = detail["quote_breakdown"] or {}
        # Paso 2 limpio
        assert "verified_context" not in bd
        assert "verified_measurements" not in bd
        assert "verified_commercial_attrs" not in bd
        assert "material_name" not in bd
        assert "mo_items" not in bd
        assert "sectors" not in bd
        # Paso 1 preservado
        assert "dual_read_result" in bd
        assert bd.get("brief_analysis", {}).get("client_name") == "Erica Bernardi"
        # Totales de la tabla también limpios
        assert detail["total_ars"] is None
        assert detail["total_usd"] is None

    @pytest.mark.asyncio
    async def test_reopen_404_for_nonexistent_quote(self, client):
        resp = await client.post("/api/quotes/00000000-0000-0000-0000-000000000000/reopen-measurements")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reopen_400_when_no_confirmation_yet(self, client):
        """Quote nuevo (sin Paso 2) — no hay nada que reabrir → 400."""
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 400
        assert "confirmaci" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reopen_409_when_validated(self, client, db_session):
        """Status=validated → 409 (PDF ya generado, no se reabre)."""
        from app.models.quote import Quote, QuoteStatus
        from sqlalchemy import update
        qid = await self._make_paso2_quote(client, db_session)
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(status=QuoteStatus.VALIDATED)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 409
        assert "validated" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reopen_409_when_sent(self, client, db_session):
        from app.models.quote import Quote, QuoteStatus
        from sqlalchemy import update
        qid = await self._make_paso2_quote(client, db_session)
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(status=QuoteStatus.SENT)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_reopen_idempotent_second_call_returns_400(self, client, db_session):
        """Después del primer reopen el quote ya no tiene verified_context;
        el segundo reopen devuelve 400 (nada que reabrir)."""
        qid = await self._make_paso2_quote(client, db_session)
        r1 = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert r1.status_code == 200
        r2 = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_reopen_preserves_client_name_column(self, client, db_session):
        """La columna Quote.client_name NO se pisa — es trabajo real persistido
        y reabrir medidas no debería perderlo (el cliente sigue siendo el mismo)."""
        qid = await self._make_paso2_quote(client, db_session)
        from app.models.quote import Quote
        from sqlalchemy import update
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                client_name="Erica Bernardi",
            )
        )
        await db_session.commit()

        await client.post(f"/api/quotes/{qid}/reopen-measurements")
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["client_name"] == "Erica Bernardi"
