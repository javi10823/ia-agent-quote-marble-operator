"""Tests para PR #443 — `patch_quote_mo` acepta `flete_qty` y es
idempotente al reemplazar flete.

**Bug observado en producción (29/04/2026, quote DYSCON 26c73a89):**

Operador escribió "modificá flete a 4 fletes". Resultado: el flete
DESAPARECIÓ de la tabla MO. Total: $11.962.988 (= original
$12.262.988 - $300.000 = sin flete). Sonnet declaró en el chat
"Flete: 3 fletes → 4 fletes" pero el handler eliminó el flete y
nunca lo agregó de vuelta.

**Tres bugs raíz en el handler `patch_quote_mo`:**

1. No exponía `flete_qty` en el schema → Sonnet no podía pasar 4.
2. `add_flete` hardcodeaba `quantity: 1`.
3. Si ya había flete, `add_flete` skipeaba (no reemplazaba con qty
   nueva). Sonnet "limpiaba" con `remove_items: ['flete']` antes,
   pero si el `add_flete` posterior fallaba o tenía qty=1, el
   resultado era inconsistente.

**Fix en este PR:**

- Schema: `flete_qty: int` parámetro nuevo (default 1).
- Handler: respeta `flete_qty` (quantity + total).
- Handler idempotente: `add_flete` REEMPLAZA flete existente sin
  necesidad de `remove_items`. Si `remove_items` incluye flete +
  `add_flete` viene → el remove se skipea (deduplicación; el add
  ya hace el reemplazo).
- Localidad inválida → error ruidoso (antes: skipeo silencioso →
  flete eliminado del breakdown sin reemplazo).

**Tests:**

1. **Caso DYSCON exacto**: breakdown con flete qty=3 → patch con
   `add_flete + flete_qty=4` → flete con qty=4, total = 4×price.
2. Idempotencia: `add_flete` solo (sin remove) reemplaza si ya hay.
3. Default: `add_flete` sin `flete_qty` → quantity=1 (regression).
4. `remove_items + add_flete` → solo se aplica el reemplazo (no
   doble eliminación).
5. Localidad inválida → error ruidoso.
6. Drift guard del schema: `flete_qty` está expuesto.
"""
from __future__ import annotations

import uuid

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Drift guard del schema
# ═══════════════════════════════════════════════════════════════════════


class TestSchemaDriftGuard:
    def test_patch_quote_mo_schema_includes_flete_qty(self):
        """Si alguien borra `flete_qty` del schema, Sonnet vuelve a
        no saber cómo pasar la cantidad → bug DYSCON re-aparece."""
        from app.modules.agent.agent import TOOLS
        tool = next((t for t in TOOLS if t.get("name") == "patch_quote_mo"), None)
        assert tool is not None
        properties = tool["input_schema"]["properties"]
        assert "flete_qty" in properties, (
            "Tool `patch_quote_mo` debe exponer `flete_qty` (PR #443). "
            "Sin esto Sonnet no puede pasar la cantidad de fletes y "
            "el handler queda en quantity=1 hardcoded → bug DYSCON."
        )
        assert properties["flete_qty"]["type"] == "integer"


# ═══════════════════════════════════════════════════════════════════════
# Helper para crear quote con breakdown que ya tiene flete
# ═══════════════════════════════════════════════════════════════════════


async def _create_quote_with_flete(db_session, flete_qty=3, flete_unit_price=100000):
    from app.models.quote import Quote, QuoteStatus
    qid = f"test-flete-{uuid.uuid4()}"
    breakdown = {
        "client_name": "DYSCON S.A.",
        "project": "Unidad Penal N°8",
        "delivery_days": "30 días",
        "material_name": "GRANITO GRIS MARA EXTRA 2 ESP",
        "material_m2": 45.55,
        "material_price_unit": 224825,
        "material_price_base": 185806,
        "material_currency": "ARS",
        "material_total": 10240678,
        "discount_pct": 12,
        "discount_amount": 1228881,
        "sectors": [{"label": "Cocina", "pieces": ["Mesada"]}],
        "mo_items": [
            {
                "description": "Agujero y pegado pileta",
                "quantity": 32,
                "unit_price": 62045,
                "base_price": 51276,
                "total": 1985440,
            },
            {
                "description": "Mano de obra regrueso x ml",
                "quantity": 60.68,
                "unit_price": 15914,
                "base_price": 13152,
                "total": 965662,
            },
            {
                "description": "Flete + toma medidas Piñero",
                "quantity": flete_qty,
                "unit_price": flete_unit_price,
                "base_price": flete_unit_price,  # zone with price_includes_vat
                "total": flete_unit_price * flete_qty,
            },
        ],
        "sinks": [],
        "total_ars": 12262988,  # exactly the value before bug
        "total_usd": 0,
    }
    quote = Quote(
        id=qid,
        client_name="DYSCON S.A.",
        project="Unidad Penal N°8",
        material="GRANITO GRIS MARA EXTRA 2 ESP",
        total_ars=12262988,
        total_usd=0,
        status=QuoteStatus.VALIDATED,
        quote_breakdown=breakdown,
        messages=[],
    )
    db_session.add(quote)
    await db_session.commit()
    return qid


# ═══════════════════════════════════════════════════════════════════════
# Caso DYSCON real: modificar flete 3 → 4
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestDysconFleteModification:
    async def test_modify_flete_3_to_4_via_add_flete_with_qty(
        self, db_session,
    ):
        """**Caso DYSCON exacto**: quote con flete qty=3, operador
        pide qty=4. Sonnet llama
        `patch_quote_mo(add_flete='Piñero', flete_qty=4)`.

        Resultado esperado:
        - El flete sigue presente en mo_items (no se borra).
        - quantity = 4 (no 1, no 3).
        - total = 4 × $100.000 = $400.000.
        - Total ARS del breakdown actualizado consistentemente."""
        from app.modules.agent.agent import AgentService
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote_with_flete(db_session, flete_qty=3)
        agent = AgentService()
        result = await agent._execute_tool(
            "patch_quote_mo",
            {"add_flete": "Piñero", "flete_qty": 4},
            quote_id=qid,
            db=db_session,
        )
        assert result["ok"] is True, f"patch failed: {result}"

        await db_session.commit()
        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        bd = q.quote_breakdown
        flete_items = [m for m in bd["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete_items) == 1, f"Esperaba 1 flete, vi {flete_items}"
        flete = flete_items[0]
        assert flete["quantity"] == 4, f"qty debe ser 4, vi {flete['quantity']}"
        # Total = qty × unit_price.
        assert flete["total"] == flete["quantity"] * flete["unit_price"]

    async def test_flete_qty_default_is_1(self, db_session):
        """Regression: `add_flete` sin `flete_qty` → quantity=1
        (comportamiento anterior preservado)."""
        from app.modules.agent.agent import AgentService
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote_with_flete(db_session, flete_qty=3)
        agent = AgentService()
        result = await agent._execute_tool(
            "patch_quote_mo",
            {"add_flete": "Piñero"},  # sin flete_qty
            quote_id=qid,
            db=db_session,
        )
        assert result["ok"] is True

        await db_session.commit()
        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        flete = next(m for m in q.quote_breakdown["mo_items"] if "flete" in m["description"].lower())
        assert flete["quantity"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Idempotencia y reemplazo
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestIdempotency:
    async def test_add_flete_replaces_existing_no_duplicates(
        self, db_session,
    ):
        """Si ya hay flete en mo_items, `add_flete` debe REEMPLAZARLO
        (no duplicar). Sin esta idempotencia, pasarlo dos veces
        agregaba 2 fletes."""
        from app.modules.agent.agent import AgentService
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote_with_flete(db_session, flete_qty=3)
        agent = AgentService()
        result = await agent._execute_tool(
            "patch_quote_mo",
            {"add_flete": "Piñero", "flete_qty": 5},
            quote_id=qid,
            db=db_session,
        )
        assert result["ok"] is True

        await db_session.commit()
        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        flete_items = [m for m in q.quote_breakdown["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete_items) == 1, "Esperaba 1 flete tras reemplazo, no duplicado"
        assert flete_items[0]["quantity"] == 5

    async def test_remove_items_with_add_flete_no_double_processing(
        self, db_session,
    ):
        """**Caso DYSCON exacto que causó el bug**: Sonnet pasaba
        `remove_items: ['flete']` + `add_flete` esperando 'limpiar
        antes de agregar'. Antes del fix, ambos se ejecutaban: el
        remove eliminaba el flete viejo y el add NO se ejecutaba
        (porque `if not has_flete` después del remove → ya no había
        flete). Ahora: cuando viene `add_flete`, el remove se
        skipea para flete (lo reemplaza el add). Resultado: flete
        nuevo correcto."""
        from app.modules.agent.agent import AgentService
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote_with_flete(db_session, flete_qty=3)
        agent = AgentService()
        result = await agent._execute_tool(
            "patch_quote_mo",
            {
                "remove_items": ["flete"],  # ← Sonnet "limpia"
                "add_flete": "Piñero",      # ← y agrega nuevo
                "flete_qty": 4,             # ← con qty correcta
            },
            quote_id=qid,
            db=db_session,
        )
        assert result["ok"] is True

        await db_session.commit()
        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        flete_items = [m for m in q.quote_breakdown["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete_items) == 1, (
            f"Esperaba 1 flete después del replace combinado, vi {len(flete_items)}"
        )
        assert flete_items[0]["quantity"] == 4


# ═══════════════════════════════════════════════════════════════════════
# Regression — comportamiento original preservado
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestRegression:
    async def test_remove_items_alone_still_deletes(self, db_session):
        """Si el operador SÍ quiere eliminar el flete (no modificar),
        `remove_items: ['flete']` SIN `add_flete` lo elimina como
        antes."""
        from app.modules.agent.agent import AgentService
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_quote_with_flete(db_session, flete_qty=3)
        agent = AgentService()
        result = await agent._execute_tool(
            "patch_quote_mo",
            {"remove_items": ["flete"]},
            quote_id=qid,
            db=db_session,
        )
        assert result["ok"] is True

        await db_session.commit()
        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        flete_items = [m for m in q.quote_breakdown["mo_items"] if "flete" in m["description"].lower()]
        assert flete_items == [], "remove_items solo debería eliminar el flete"

    async def test_invalid_localidad_rejects_loud(self, db_session):
        """**Caso CRÍTICO**: localidad inválida → error ruidoso. Antes
        del fix, `_find_flete` devolvía `found: False` y el handler
        skipeaba silenciosamente. Sonnet creía que se aplicó. Ahora
        devuelve `ok: False` con error claro."""
        from app.modules.agent.agent import AgentService

        qid = await _create_quote_with_flete(db_session, flete_qty=3)
        agent = AgentService()
        result = await agent._execute_tool(
            "patch_quote_mo",
            {"add_flete": "ZONA_INEXISTENTE_XYZ", "flete_qty": 2},
            quote_id=qid,
            db=db_session,
        )
        assert result["ok"] is False
        assert "ZONA_INEXISTENTE_XYZ" in result["error"]
