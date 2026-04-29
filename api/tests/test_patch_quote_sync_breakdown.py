"""Tests para PR #438 (P1.1) — `PATCH /quotes/{id}` sincroniza al
breakdown los campos con mirror en ambas capas.

**Plan Fase 1 — P1.1** del análisis de modificabilidad (29/04/2026).

**Bug latente (no visible hoy pero a 1 paso):**

`QuotePatchRequest` acepta `localidad`, `colocacion`, `pileta`,
`anafe`, `client_name`, `project`, `material`. El handler los
escribía SOLO a la columna de Quote. PERO esos campos también
viven en `quote_breakdown` (JSON) y los renderers del PDF/Paso 2
+ frontend detail view leen del breakdown.

Resultado: si frontend agrega `EditableField` para localidad y
llama `PATCH /quotes/{id}`:
- Columna `localidad` ✓ actualizada.
- `quote_breakdown.localidad` ❌ vieja.
- Detail view (lee del breakdown) ❌ no se ve cambio.
- PDF re-generado (lee del breakdown) ❌ usa la vieja.
- Paso 2 markdown ❌ idem.

Con este PR, el handler hace mirror automático: cualquier campo
del map `_BREAKDOWN_MIRROR_FIELDS` que viene en el patch se
escribe en columna Y en breakdown.

**Casos cubiertos:**

- localidad, colocacion, pileta, anafe → columna + breakdown.
- material (col) → breakdown.material_name (rename histórico).
- client_name, project → ambos lados (antes faltaba mirror).
- Combinaciones: varios campos juntos.
- Campos sin mirror (notes, status, sink_type) → solo columna.
- Drift guard del map: si alguien borra una entrada, el test
  rompe y obliga a actualizar la cobertura.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ═══════════════════════════════════════════════════════════════════════
# Setup helper
# ═══════════════════════════════════════════════════════════════════════


async def _create_quote(db_session, breakdown=None) -> str:
    from app.models.quote import Quote, QuoteStatus
    qid = str(uuid.uuid4())
    quote = Quote(
        id=qid,
        client_name="Original Cliente",
        project="Original Proyecto",
        material="GRANITO ORIGINAL",
        localidad="rosario",
        colocacion=True,
        pileta="empotrada_johnson",
        anafe=False,
        status=QuoteStatus.DRAFT,
        quote_breakdown=breakdown or {
            "client_name": "Original Cliente",
            "project": "Original Proyecto",
            "material_name": "GRANITO ORIGINAL",
            "localidad": "rosario",
            "colocacion": True,
            "pileta": "empotrada_johnson",
            "anafe": False,
            "delivery_days": "30 días",
        },
    )
    db_session.add(quote)
    await db_session.commit()
    return qid


# ═══════════════════════════════════════════════════════════════════════
# Drift guard del map de mirror fields
# ═══════════════════════════════════════════════════════════════════════


class TestMirrorMapDriftGuard:
    def test_breakdown_mirror_map_has_known_fields(self):
        """**Drift guard**: si alguien edita el handler y borra una
        entrada del `_BREAKDOWN_MIRROR_FIELDS`, este test rompe y
        obliga a actualizar el handler + tests.

        Lectura via `inspect.getsource` para no depender de export."""
        import inspect
        from app.modules.agent import router as router_mod
        src = inspect.getsource(router_mod.patch_quote)
        # Cada campo crítico debe aparecer en el map.
        for col_key in (
            "client_name", "project", "localidad",
            "colocacion", "pileta", "anafe", "material",
        ):
            assert f'"{col_key}":' in src, (
                f"`{col_key}` no aparece en _BREAKDOWN_MIRROR_FIELDS del "
                f"handler patch_quote (PR #438). Si alguien lo sacó, "
                f"edición REST de ese campo deja de propagar al breakdown "
                f"→ PDF/Paso2 muestran valor viejo."
            )
        # Material → material_name (rename histórico).
        assert '"material_name"' in src, (
            "El mapping `material → material_name` falta. Sin esto, "
            "PATCH material rompe la sincro con breakdown."
        )


# ═══════════════════════════════════════════════════════════════════════
# Mirror per field
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestPatchSyncBreakdown:
    async def test_localidad_mirrors_to_breakdown(
        self, client: AsyncClient, db_session,
    ):
        """**Caso del análisis**: PATCH localidad debe actualizar
        columna Y breakdown."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"localidad": "Piñero"},
        )
        assert resp.status_code == 200, resp.text

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.localidad == "Piñero"
        assert q.quote_breakdown["localidad"] == "Piñero", (
            f"breakdown.localidad NO sincronizado: {q.quote_breakdown}"
        )

    async def test_colocacion_mirrors_to_breakdown(
        self, client: AsyncClient, db_session,
    ):
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"colocacion": False},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.colocacion is False
        assert q.quote_breakdown["colocacion"] is False

    async def test_pileta_mirrors_to_breakdown(
        self, client: AsyncClient, db_session,
    ):
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"pileta": "empotrada_cliente"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.pileta == "empotrada_cliente"
        assert q.quote_breakdown["pileta"] == "empotrada_cliente"

    async def test_anafe_mirrors_to_breakdown(
        self, client: AsyncClient, db_session,
    ):
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"anafe": True},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.anafe is True
        assert q.quote_breakdown["anafe"] is True

    async def test_material_mirrors_to_breakdown_with_rename(
        self, client: AsyncClient, db_session,
    ):
        """**Rename crítico**: `material` (columna) → `material_name`
        (breakdown). Si el mapping se rompe, el frontend detail view
        muestra el material viejo aunque la columna se haya cambiado."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"material": "SILESTONE BLANCO NORTE"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.material == "SILESTONE BLANCO NORTE"
        assert q.quote_breakdown["material_name"] == "SILESTONE BLANCO NORTE"

    async def test_client_name_and_project_mirror(
        self, client: AsyncClient, db_session,
    ):
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"client_name": "DYSCON S.A.", "project": "Unidad Penal N°8"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.client_name == "DYSCON S.A."
        assert q.project == "Unidad Penal N°8"
        assert q.quote_breakdown["client_name"] == "DYSCON S.A."
        assert q.quote_breakdown["project"] == "Unidad Penal N°8"

    async def test_combined_fields_all_mirror(
        self, client: AsyncClient, db_session,
    ):
        """Varios campos en un solo PATCH → todos sincronizados."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={
                "localidad": "Piñero",
                "colocacion": False,
                "pileta": "apoyo",
                "anafe": True,
                "material": "DEKTON KAIROS",
                "delivery_days": "60 días",
            },
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        # Columnas.
        assert q.localidad == "Piñero"
        assert q.colocacion is False
        assert q.pileta == "apoyo"
        assert q.anafe is True
        assert q.material == "DEKTON KAIROS"
        # Breakdown.
        bd = q.quote_breakdown
        assert bd["localidad"] == "Piñero"
        assert bd["colocacion"] is False
        assert bd["pileta"] == "apoyo"
        assert bd["anafe"] is True
        assert bd["material_name"] == "DEKTON KAIROS"
        assert bd["delivery_days"] == "60 días"

    async def test_preserves_other_breakdown_fields(
        self, client: AsyncClient, db_session,
    ):
        """**Anti-clobber**: cambiar `localidad` NO debe perder
        sectors, mo_items, totals, etc. del breakdown."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(
            db_session,
            breakdown={
                "client_name": "Test",
                "localidad": "rosario",
                "material_name": "GRANITO",
                "material_m2": 10.5,
                "sectors": [{"label": "Cocina", "pieces": ["Mesada"]}],
                "mo_items": [{"description": "Colocación", "total": 250000}],
                "total_ars": 5000000,
                "delivery_days": "30 días",
            },
        )
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"localidad": "Cañada de Gómez"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        bd = q.quote_breakdown
        assert bd["localidad"] == "Cañada de Gómez"
        # Otros campos intactos.
        assert bd["material_name"] == "GRANITO"
        assert bd["material_m2"] == 10.5
        assert len(bd["sectors"]) == 1
        assert len(bd["mo_items"]) == 1
        assert bd["total_ars"] == 5000000
        assert bd["delivery_days"] == "30 días"

    async def test_fields_without_mirror_only_column(
        self, client: AsyncClient, db_session,
    ):
        """**Regression**: campos SIN mirror (notes, status,
        sink_type) deben seguir actualizando solo la columna, NO
        meterse en el breakdown."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session)
        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"notes": "Cliente prefiere mañana", "status": "validated"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.notes == "Cliente prefiere mañana"
        assert q.status.value == "validated"
        # Breakdown NO debe tener notes (no es mirror).
        assert "notes" not in q.quote_breakdown

    async def test_no_breakdown_previo_creates_minimal(
        self, client: AsyncClient, db_session,
    ):
        """Edge case: quote sin breakdown previo + PATCH localidad
        → handler crea breakdown con solo ese campo."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote(db_session, breakdown=None)
        # forzar breakdown a None
        await db_session.execute(
            __import__("sqlalchemy").update(Quote)
            .where(Quote.id == qid)
            .values(quote_breakdown=None)
        )
        await db_session.commit()

        resp = await client.patch(
            f"/api/quotes/{qid}",
            json={"localidad": "Piñero"},
        )
        assert resp.status_code == 200

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.quote_breakdown is not None
        assert q.quote_breakdown["localidad"] == "Piñero"
