"""Tests para PR #437 (P1.2) — endpoint `PATCH /quotes/{id}` acepta
`delivery_days` y lo persiste en `quote_breakdown` JSON.

**Por qué este PR (análisis de modificabilidad, plan Fase 1):**

PR #436 agregó `delivery_days` al tool `update_quote` (chat de
Sonnet). PERO el endpoint REST `PATCH /quotes/{id}` no lo aceptaba
en su schema (`QuotePatchRequest`). Si el frontend agregaba un
EditableField de demora, no funcionaba — el `model_dump(exclude_none=True)`
descartaba el campo.

Además, `delivery_days` NO existe como columna de Quote — solo en
`quote_breakdown.delivery_days` (JSON). El handler debe extraerlo
antes del `update(Quote).values(...)` y mergearlo en el breakdown.

Sin este PR, P2.1 (EditableField de demora en frontend) está
bloqueado.

**Tests cubren:**

1. Schema: `QuotePatchRequest` acepta `delivery_days` (drift guard).
2. Handler: PATCH con solo `delivery_days` → persiste en breakdown.
3. Handler: PATCH con `delivery_days` + otro campo → ambos OK.
4. Breakdown vacío previo → crea uno mínimo con delivery_days.
5. delivery_days null/empty → respeta `exclude_none`.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ═══════════════════════════════════════════════════════════════════════
# Schema drift guard
# ═══════════════════════════════════════════════════════════════════════


class TestSchemaDriftGuard:
    def test_quote_patch_request_includes_delivery_days(self):
        """Drift guard: si alguien borra `delivery_days` del schema,
        el endpoint vuelve al estado pre-PR #437 → frontend
        EditableField de demora rompe silenciosamente."""
        from app.modules.agent.schemas import QuotePatchRequest
        # Pydantic v2 — model_fields contiene los campos.
        assert "delivery_days" in QuotePatchRequest.model_fields, (
            "QuotePatchRequest debe tener `delivery_days` (PR #437). "
            "Sin ese campo, frontend no puede editar la demora vía REST."
        )
        field = QuotePatchRequest.model_fields["delivery_days"]
        # Es Optional[str] — el annotation incluye str y None.
        assert "str" in str(field.annotation), (
            f"delivery_days debe ser Optional[str], vi {field.annotation}"
        )

    def test_quote_patch_request_validates_delivery_days_type(self):
        """Acepta string, rechaza cosas raras."""
        from app.modules.agent.schemas import QuotePatchRequest
        # Acepta string.
        req = QuotePatchRequest(delivery_days="30 días")
        assert req.delivery_days == "30 días"
        # Acepta None (Optional).
        req2 = QuotePatchRequest(delivery_days=None)
        assert req2.delivery_days is None
        # Rechaza int (max_length=200 implica string).
        with pytest.raises(Exception):
            QuotePatchRequest(delivery_days=123)


# ═══════════════════════════════════════════════════════════════════════
# Handler integration — PATCH /quotes/{id}
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestPatchQuoteDeliveryDays:
    async def _create_quote(self, db_session, breakdown=None) -> str:
        from app.models.quote import Quote, QuoteStatus
        qid = str(uuid.uuid4())
        quote = Quote(
            id=qid,
            client_name="Test",
            project="Test",
            status=QuoteStatus.DRAFT,
            quote_breakdown=breakdown,
        )
        db_session.add(quote)
        await db_session.commit()
        return qid

    async def test_patch_only_delivery_days_persists_in_breakdown(
        self, client: AsyncClient, db_session,
    ):
        """**Caso clave**: solo delivery_days (campo breakdown-only)
        → handler extrae del dict de columnas y mergea al JSON."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await self._create_quote(
            db_session,
            breakdown={"delivery_days": "A confirmar", "client_name": "Test"},
        )
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"delivery_days": "30 días"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert "delivery_days" in body["updated"]

        # Persistencia en breakdown.
        await db_session.commit()  # async session refresh
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.quote_breakdown["delivery_days"] == "30 días"

    async def test_patch_delivery_days_with_other_field(
        self, client: AsyncClient, db_session,
    ):
        """delivery_days + client_name → ambos persisten correctamente."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await self._create_quote(
            db_session,
            breakdown={"delivery_days": "A confirmar"},
        )
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={
                "delivery_days": "60 días",
                "client_name": "Cliente Nuevo",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "delivery_days" in body["updated"]
        assert "client_name" in body["updated"]

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.client_name == "Cliente Nuevo"
        assert q.quote_breakdown["delivery_days"] == "60 días"

    async def test_patch_delivery_days_no_breakdown_creates_minimal(
        self, client: AsyncClient, db_session,
    ):
        """Quote sin breakdown previo (raro pero posible) → handler
        crea breakdown mínimo con el delivery_days."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await self._create_quote(db_session, breakdown=None)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"delivery_days": "45 días"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.quote_breakdown is not None
        assert q.quote_breakdown["delivery_days"] == "45 días"

    async def test_patch_delivery_days_preserves_existing_breakdown_fields(
        self, client: AsyncClient, db_session,
    ):
        """Cambiar delivery_days NO debe perder otros campos del
        breakdown (sectors, mo_items, totals, etc.)."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await self._create_quote(
            db_session,
            breakdown={
                "delivery_days": "A confirmar",
                "client_name": "Test",
                "material_name": "GRANITO",
                "material_m2": 5.0,
                "sectors": [{"label": "Cocina", "pieces": ["Mesada 2x0.6"]}],
                "mo_items": [{"description": "Colocación", "quantity": 5, "unit_price": 50000, "total": 250000}],
                "total_ars": 1000000,
            },
        )
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"delivery_days": "30 días"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        bd = q.quote_breakdown
        assert bd["delivery_days"] == "30 días"
        # Campos viejos preservados.
        assert bd["material_name"] == "GRANITO"
        assert bd["material_m2"] == 5.0
        assert len(bd["sectors"]) == 1
        assert len(bd["mo_items"]) == 1
        assert bd["total_ars"] == 1000000

    async def test_patch_empty_body_rejected(
        self, client: AsyncClient, db_session,
    ):
        """Body vacío → 400 (mismo comportamiento de antes, no
        regresión)."""
        qid = await self._create_quote(db_session)
        resp = await client.patch(f"/api/quotes/{qid}", json={})
        assert resp.status_code == 400

    async def test_patch_only_none_values_rejected(
        self, client: AsyncClient, db_session,
    ):
        """delivery_days=None + nada más → 400 (model_dump
        exclude_none deja el dict vacío)."""
        qid = await self._create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"delivery_days": None},
        )
        assert resp.status_code == 400

    async def test_patch_delivery_days_quote_not_found(
        self, client: AsyncClient,
    ):
        """Quote inexistente → 404."""
        resp = await client.patch(
            "/api/quotes/00000000-0000-0000-0000-000000000000",
            json={"delivery_days": "30 días"},
        )
        assert resp.status_code == 404
