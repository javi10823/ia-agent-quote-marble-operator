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

    # ── PR #383 — Corte de historial al reopen ──────────────────────────

    @pytest.mark.asyncio
    async def test_reopen_truncates_chat_from_dual_read(self, client, db_session):
        """Post-reopen el historial queda cortado desde __DUAL_READ__
        (inclusive) y la card se regenera con las medidas editadas.
        Brief + card de contexto + [CONTEXT_CONFIRMED] se preservan;
        todo lo posterior (Paso 2 markdown, preguntas, confirmación) se
        descarta."""
        import json as _json
        from app.models.quote import Quote
        from sqlalchemy import update

        qid = await self._make_paso2_quote(client, db_session)
        # Simular historial Bernardi-style con Paso 2 ya calculado
        legacy_msgs = [
            {"role": "user", "content": "cotizar cocina + isla"},
            {"role": "assistant", "content": '__CONTEXT_ANALYSIS__{"data_known":[]}'},
            {"role": "user", "content": '[CONTEXT_CONFIRMED]{"answers":[]}'},
            {"role": "assistant", "content": '__DUAL_READ__{"sectores":[{"id":"cocina","tramos":[{"largo_m":{"valor":1.60}}]}]}'},
            {"role": "user", "content": '[DUAL_READ_CONFIRMED]{"sectores":[]}'},
            {"role": "assistant", "content": "## PASO 2 — Validación\nTotal: $797.177"},
            {"role": "user", "content": "Confirmo"},
        ]
        # verified_measurements con las medidas editadas — estas deben
        # aparecer en la card regenerada.
        bd_extra = {
            "verified_measurements": {
                "sectores": [{"id": "cocina", "tramos": [{"largo_m": {"valor": 2.05}}]}],
            },
        }
        existing = (await client.get(f"/api/quotes/{qid}")).json()["quote_breakdown"]
        existing.update(bd_extra)
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                messages=legacy_msgs, quote_breakdown=existing,
            )
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 200, resp.text

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        msgs = detail["messages"]
        # brief + ctx_analysis + ctx_confirmed + card regenerada = 4
        assert len(msgs) == 4, msgs
        assert msgs[0]["content"] == "cotizar cocina + isla"
        assert msgs[1]["content"].startswith("__CONTEXT_ANALYSIS__")
        assert msgs[2]["content"].startswith("[CONTEXT_CONFIRMED]")
        # Card regenerada con verified_measurements (editadas)
        assert msgs[3]["content"].startswith("__DUAL_READ__")
        parsed = _json.loads(msgs[3]["content"].replace("__DUAL_READ__", "", 1))
        assert parsed["sectores"][0]["tramos"][0]["largo_m"]["valor"] == 2.05

    @pytest.mark.asyncio
    async def test_reopen_promotes_verified_to_dual_read_in_breakdown(
        self, client, db_session,
    ):
        """verified_measurements → dual_read_result en el breakdown post-reopen,
        para que la card regenerada refleje los edits del operador."""
        import json as _json
        from app.models.quote import Quote
        from sqlalchemy import update

        qid = await self._make_paso2_quote(client, db_session)
        existing = (await client.get(f"/api/quotes/{qid}")).json()["quote_breakdown"]
        existing["verified_measurements"] = {
            "sectores": [{"id": "cocina", "tramos": [{"largo_m": {"valor": 2.05}}]}],
        }
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(quote_breakdown=existing)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 200

        bd = resp.json()["quote_breakdown"]
        assert bd["dual_read_result"]["sectores"][0]["tramos"][0]["largo_m"]["valor"] == 2.05
        assert "verified_measurements" not in bd  # limpiada en el reset

    @pytest.mark.asyncio
    async def test_reopen_preserves_brief_when_no_card_in_history(
        self, client, db_session,
    ):
        """Si el historial no tiene __DUAL_READ__ por alguna razón
        (historial corrupto, edge case), el reopen limpia el breakdown
        igual pero no rompe el chat — queda intacto."""
        from app.models.quote import Quote
        from sqlalchemy import update

        qid = await self._make_paso2_quote(client, db_session)
        sparse_msgs = [
            {"role": "user", "content": "cotizar"},
            {"role": "assistant", "content": "Mando el plano por favor."},
        ]
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(messages=sparse_msgs)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-measurements")
        assert resp.status_code == 200

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        # Chat sin cambios (no había card que cortar)
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["content"] == "cotizar"


# ═══════════════════════════════════════════════════════════════════════
# PR #383 — Endpoint reopen-context (editar card de análisis de contexto)
# ═══════════════════════════════════════════════════════════════════════


class TestReopenContext:
    """Endpoint que reabre la edición del contexto (card
    __CONTEXT_ANALYSIS__). Gemelo de /reopen-measurements pero para el
    paso anterior del flujo."""

    async def _make_context_confirmed_quote(self, client, db_session) -> str:
        """Quote con verified_context_analysis (contexto confirmado) +
        historial completo con ambas cards."""
        from app.models.quote import Quote
        from sqlalchemy import update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        bd = {
            "dual_read_result": {"sectores": [{"id": "cocina", "tramos": []}]},
            "context_analysis_pending": {
                "data_known": [{"field": "Material", "value": "PURASTONE"}],
                "assumptions": [],
                "pending_questions": [],
            },
            "verified_context_analysis": {"answers": [{"q": 1, "a": "x"}]},
            "verified_context": "[MEDIDAS VERIFICADAS...]",
            "verified_measurements": {"sectores": [{"tramos": [{"largo_m": {"valor": 2.05}}]}]},
            "material_name": "PURASTONE",
            "total_ars": 797177,
            "total_usd": 4128,
            "mo_items": [{"description": "Colocación"}],
        }
        msgs = [
            {"role": "user", "content": "cotizar cocina"},
            {"role": "assistant", "content": '__CONTEXT_ANALYSIS__{"data_known":[]}'},
            {"role": "user", "content": '[CONTEXT_CONFIRMED]{"answers":[]}'},
            {"role": "assistant", "content": '__DUAL_READ__{"sectores":[]}'},
            {"role": "user", "content": '[DUAL_READ_CONFIRMED]{"sectores":[]}'},
            {"role": "assistant", "content": "## PASO 2 — Total $797.177"},
            {"role": "user", "content": "Confirmo"},
        ]
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                quote_breakdown=bd,
                messages=msgs,
                total_ars=797177,
                total_usd=4128,
            )
        )
        await db_session.commit()
        return qid

    @pytest.mark.asyncio
    async def test_reopen_context_clears_paso2_and_context_confirmation(
        self, client, db_session,
    ):
        qid = await self._make_context_confirmed_quote(client, db_session)
        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 200, resp.text

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        bd = detail["quote_breakdown"] or {}
        # Contexto + Paso 2 limpios
        assert "verified_context_analysis" not in bd
        assert "verified_context" not in bd
        assert "material_name" not in bd
        assert "mo_items" not in bd
        # context_analysis_pending preservado (fuente para regenerar card)
        assert bd.get("context_analysis_pending", {}).get("data_known")
        # Totales de la tabla también limpios
        assert detail["total_ars"] is None
        assert detail["total_usd"] is None

    @pytest.mark.asyncio
    async def test_reopen_context_truncates_chat_from_context_card(
        self, client, db_session,
    ):
        """Post-reopen el chat queda cortado desde __CONTEXT_ANALYSIS__
        (inclusive). Solo el brief (y cualquier turn previo a la card de
        contexto) se preserva."""
        qid = await self._make_context_confirmed_quote(client, db_session)
        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 200

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        msgs = detail["messages"]
        # Solo el brief + card regenerada = 2 turns
        assert len(msgs) == 2, msgs
        assert msgs[0]["content"] == "cotizar cocina"
        # Card regenerada con context_analysis_pending preservado
        assert msgs[1]["content"].startswith("__CONTEXT_ANALYSIS__")

    @pytest.mark.asyncio
    async def test_reopen_context_404_for_nonexistent_quote(self, client):
        resp = await client.post(
            "/api/quotes/00000000-0000-0000-0000-000000000000/reopen-context"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reopen_context_400_when_no_context_confirmed(self, client):
        """Quote sin verified_context_analysis → 400."""
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 400
        assert "contexto" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reopen_context_409_when_validated(self, client, db_session):
        from app.models.quote import Quote, QuoteStatus
        from sqlalchemy import update
        qid = await self._make_context_confirmed_quote(client, db_session)
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(status=QuoteStatus.VALIDATED)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_reopen_context_409_when_sent(self, client, db_session):
        from app.models.quote import Quote, QuoteStatus
        from sqlalchemy import update
        qid = await self._make_context_confirmed_quote(client, db_session)
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(status=QuoteStatus.SENT)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_reopen_context_idempotent_second_call_returns_400(
        self, client, db_session,
    ):
        """El primer reopen borra verified_context_analysis → el segundo
        responde 400 (nada que reabrir)."""
        qid = await self._make_context_confirmed_quote(client, db_session)
        r1 = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert r1.status_code == 200
        r2 = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_reopen_context_clears_alzada_derived_tramos(
        self, client, db_session,
    ):
        """PR #388 — reopen-context debe quitar tramos `_derived_kind='alzada'`
        además de los de patas. Una alzada con distinto alto después
        requiere regenerar desde cero con la nueva respuesta."""
        from app.models.quote import Quote
        from sqlalchemy import update
        qid = await self._make_context_confirmed_quote(client, db_session)
        existing = (await client.get(f"/api/quotes/{qid}")).json()["quote_breakdown"]
        existing["dual_read_result"] = {
            "sectores": [
                {"id": "cocina", "tipo": "cocina", "tramos": [
                    {"id": "c1", "descripcion": "Cocina",
                     "largo_m": {"valor": 2.05}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.23}},
                    {"id": "derived_alzada_cocina", "descripcion": "Alzada cocina",
                     "largo_m": {"valor": 2.05}, "ancho_m": {"valor": 0.10}, "m2": {"valor": 0.21},
                     "zocalos": [], "_derived": True, "_derived_kind": "alzada"},
                ]},
            ],
        }
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(quote_breakdown=existing)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 200, resp.text

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        cocina = detail["quote_breakdown"]["dual_read_result"]["sectores"][0]
        # Solo la mesada original queda — la alzada derivada se limpió
        assert len(cocina["tramos"]) == 1
        assert cocina["tramos"][0]["descripcion"] == "Cocina"
        assert not any(t.get("_derived") for t in cocina["tramos"])

    @pytest.mark.asyncio
    async def test_reopen_context_clears_derived_pieces_from_isla(
        self, client, db_session,
    ):
        """PR #386 — reopen-context debe quitar los tramos `_derived:true`
        del sector isla. La re-confirmación del contexto los regenera
        según las nuevas respuestas (quizá diferentes)."""
        from app.models.quote import Quote
        from sqlalchemy import update
        qid = await self._make_context_confirmed_quote(client, db_session)
        # Inyectar un dual_read con patas derivadas ya materializadas
        # (como quedaría post-#386 después de CONTEXT_CONFIRMED).
        existing = (await client.get(f"/api/quotes/{qid}")).json()["quote_breakdown"]
        existing["dual_read_result"] = {
            "sectores": [
                {"id": "isla", "tipo": "isla", "tramos": [
                    {"id": "i1", "descripcion": "Mesada isla",
                     "largo_m": {"valor": 2.03}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.22}},
                    {"id": "derived_pata_frontal_isla", "descripcion": "Pata frontal isla",
                     "largo_m": {"valor": 2.03}, "ancho_m": {"valor": 0.90}, "m2": {"valor": 1.83},
                     "zocalos": [], "_derived": True,
                     "_derived_source": "derived_from_operator_answers"},
                    {"id": "derived_pata_lateral_izq", "descripcion": "Pata lateral isla izq",
                     "largo_m": {"valor": 0.60}, "ancho_m": {"valor": 0.90}, "m2": {"valor": 0.54},
                     "zocalos": [], "_derived": True,
                     "_derived_source": "derived_from_operator_answers"},
                ]},
            ],
        }
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(quote_breakdown=existing)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/reopen-context")
        assert resp.status_code == 200, resp.text

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        isla = detail["quote_breakdown"]["dual_read_result"]["sectores"][0]
        # Solo la mesada queda (tramo sin `_derived`)
        assert len(isla["tramos"]) == 1
        assert isla["tramos"][0]["descripcion"] == "Mesada isla"
        # Ningún tramo tiene `_derived:true`
        assert not any(t.get("_derived") for t in isla["tramos"])

    @pytest.mark.asyncio
    async def test_reopen_context_preserves_dual_read_and_brief(
        self, client, db_session,
    ):
        """dual_read_result se preserva — el despiece detectado sigue
        siendo útil post-edit de contexto. Brief del operador intacto."""
        qid = await self._make_context_confirmed_quote(client, db_session)
        await client.post(f"/api/quotes/{qid}/reopen-context")

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        bd = detail["quote_breakdown"]
        # El operador puede haber editado medidas — `verified_measurements`
        # se promueve a `dual_read_result` igual que en /reopen-measurements.
        assert "dual_read_result" in bd
        # Brief en el chat intacto
        assert detail["messages"][0]["content"] == "cotizar cocina"


# ═══════════════════════════════════════════════════════════════════════
# PR #380 — Endpoint rehydrate-history
# ═══════════════════════════════════════════════════════════════════════

class TestRehydrateHistoryEndpoint:
    """Endpoint que limpia historial legacy usando el breakdown como
    fuente de verdad. Idempotente y no destructivo."""

    @pytest.mark.asyncio
    async def test_404_for_nonexistent_quote(self, client):
        resp = await client.post(
            "/api/quotes/00000000-0000-0000-0000-000000000000/rehydrate-history"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_200_changed_false_on_clean_quote(self, client, db_session):
        """Quote sin markers legacy → changed=False, no UPDATE."""
        from app.models.quote import Quote
        from sqlalchemy import update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        clean_msgs = [
            {"role": "user", "content": "cotizar cocina"},
            {"role": "assistant", "content": "## PASO 2"},
        ]
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(messages=clean_msgs)
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/rehydrate-history")
        assert resp.status_code == 200
        assert resp.json()["changed"] is False
        # Los messages no cambiaron
        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert len(detail["messages"]) == 2

    @pytest.mark.asyncio
    async def test_200_rehydrates_legacy_bernardi_shape(self, client, db_session):
        """Historial legacy con placeholders → se reconstruye usando el
        dual_read_result del breakdown."""
        from app.models.quote import Quote
        from sqlalchemy import update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        legacy_msgs = [
            {"role": "user", "content": "brief con [TEXTO EXTRAÍDO DEL PDF] dump"},
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
            {"role": "user", "content": "(contexto confirmado)"},
        ]
        bd = {"dual_read_result": {"sectores": [{"tipo": "cocina"}]}}
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                messages=legacy_msgs, quote_breakdown=bd,
            )
        )
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{qid}/rehydrate-history")
        assert resp.status_code == 200
        assert resp.json()["changed"] is True

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        msgs = detail["messages"]
        # Brief limpio
        brief = msgs[0]["content"]
        brief_text = brief if isinstance(brief, str) else "".join(
            b.get("text", "") for b in brief if b.get("type") == "text"
        )
        assert "TEXTO EXTRAÍDO" not in brief_text
        # Card de despiece reconstruida
        assert msgs[1]["content"].startswith("__DUAL_READ__")
        # Fake (contexto confirmado) descartado
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_idempotent_second_call(self, client, db_session):
        from app.models.quote import Quote
        from sqlalchemy import update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        legacy_msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        bd = {"dual_read_result": {"sectores": []}}
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                messages=legacy_msgs, quote_breakdown=bd,
            )
        )
        await db_session.commit()

        r1 = await client.post(f"/api/quotes/{qid}/rehydrate-history")
        assert r1.json()["changed"] is True
        r2 = await client.post(f"/api/quotes/{qid}/rehydrate-history")
        assert r2.json()["changed"] is False

    @pytest.mark.asyncio
    async def test_does_not_modify_breakdown_or_status(self, client, db_session):
        """Condición del PR: no toca cálculo. Verificamos que breakdown,
        total_ars, total_usd y status quedan intactos."""
        from app.models.quote import Quote
        from sqlalchemy import update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        legacy_msgs = [
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
        ]
        bd = {
            "dual_read_result": {"sectores": []},
            "material_name": "PURASTONE",
            "total_ars": 797177,
            "total_usd": 4128,
        }
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                messages=legacy_msgs,
                quote_breakdown=bd,
                total_ars=797177,
                total_usd=4128,
            )
        )
        await db_session.commit()

        await client.post(f"/api/quotes/{qid}/rehydrate-history")

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        assert detail["total_ars"] == 797177
        assert detail["total_usd"] == 4128
        assert detail["quote_breakdown"]["material_name"] == "PURASTONE"
        assert detail["quote_breakdown"]["total_ars"] == 797177

    @pytest.mark.asyncio
    async def test_preserves_clean_messages_between_legacy(self, client, db_session):
        """Si en el medio hay mensajes legítimos (ej: Paso 2 markdown),
        se preservan tal cual mientras los adyacentes se rehidratan."""
        from app.models.quote import Quote
        from sqlalchemy import update
        create = await client.post("/api/quotes")
        qid = create.json()["id"]
        legacy_msgs = [
            {"role": "user", "content": "brief"},
            {"role": "assistant", "content": "__DUAL_READ_CARD_SHOWN__"},
            {"role": "assistant", "content": "## PASO 2 — Validación\n\nmateriales y precios"},
            {"role": "user", "content": "Confirmo"},
        ]
        bd = {"dual_read_result": {"sectores": []}}
        await db_session.execute(
            update(Quote).where(Quote.id == qid).values(
                messages=legacy_msgs, quote_breakdown=bd,
            )
        )
        await db_session.commit()

        await client.post(f"/api/quotes/{qid}/rehydrate-history")

        detail = (await client.get(f"/api/quotes/{qid}")).json()
        msgs = detail["messages"]
        assert len(msgs) == 4
        assert msgs[1]["content"].startswith("__DUAL_READ__")
        assert msgs[2]["content"].startswith("## PASO 2")
        assert msgs[3]["content"] == "Confirmo"
