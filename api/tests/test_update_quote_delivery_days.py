"""Tests para PR #436 — `update_quote` acepta `delivery_days`.

**Bug observado en producción (29/04/2026):**

Operador escribe "cambiá la demora a 30 días" en un quote
products_only. Sonnet llama `update_quote(updates={"delivery_days":
"30 días"})`. El handler antiguo:

1. Filtraba con `allowed = {client_name, project, material,
   total_ars, total_usd, status}` → `delivery_days` quedaba fuera.
2. Si era el ÚNICO campo, `clean = {}` → retornaba "No hay campos
   válidos".
3. Sonnet leía el error pero respondía al operador "demora cambiada"
   (alucinación + Issue #422).

Resultado: la DB nunca se tocaba pero el operador veía la respuesta
"demora cambiada" y se quedaba con la demora vieja.

**Fix:** dos categorías de campos:
- `_COLUMN_FIELDS`: client_name, project, material, total_ars,
  total_usd, status (van a columnas de Quote).
- `_BREAKDOWN_ONLY_FIELDS`: delivery_days (vive solo en JSON).

Cualquier otro campo → error LOUD (no silent drop). Sonnet recibe
el error real y NO puede mentirle al operador.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Helpers — reproducir el handler de update_quote sin todo el agent
# ═══════════════════════════════════════════════════════════════════════


async def _call_update_quote(quote_id: str, updates: dict, db_session) -> dict:
    """Invoca la lógica del handler `update_quote` directamente.

    Replica la lógica del handler para no tener que mockear todo el
    AgentService loop. La lógica es pura (SQL + JSON), no depende del
    LLM ni del stream.
    """
    from app.models.quote import Quote
    from sqlalchemy import select, update as sql_update

    _COLUMN_FIELDS = {"client_name", "project", "material", "total_ars", "total_usd", "status"}
    _BREAKDOWN_ONLY_FIELDS = {"delivery_days"}
    _ALL_ALLOWED = _COLUMN_FIELDS | _BREAKDOWN_ONLY_FIELDS

    _unknown = [k for k in updates if k not in _ALL_ALLOWED and updates[k] is not None]
    if _unknown:
        return {
            "ok": False,
            "error": (
                f"Campos no soportados por update_quote: {_unknown}. "
                f"Permitidos: {sorted(_ALL_ALLOWED)}. Para cambios "
                f"de despiece/MO usar calculate_quote o patch_quote_mo."
            ),
        }

    clean_columns = {
        k: v for k, v in updates.items()
        if k in _COLUMN_FIELDS and v is not None
    }
    clean_breakdown_only = {
        k: v for k, v in updates.items()
        if k in _BREAKDOWN_ONLY_FIELDS and v is not None
    }
    if not clean_columns and not clean_breakdown_only:
        return {"ok": False, "error": "No hay campos válidos para actualizar"}

    q_result = await db_session.execute(select(Quote).where(Quote.id == quote_id))
    q_obj = q_result.scalar_one_or_none()
    if q_obj and q_obj.quote_breakdown:
        bd = dict(q_obj.quote_breakdown)
        changed = False
        if "client_name" in clean_columns and bd.get("client_name") != clean_columns["client_name"]:
            bd["client_name"] = clean_columns["client_name"]
            changed = True
        if "project" in clean_columns and bd.get("project") != clean_columns["project"]:
            bd["project"] = clean_columns["project"]
            changed = True
        for k, v in clean_breakdown_only.items():
            if bd.get(k) != v:
                bd[k] = v
                changed = True
        if changed:
            clean_columns["quote_breakdown"] = bd
    elif clean_breakdown_only:
        clean_columns["quote_breakdown"] = dict(clean_breakdown_only)

    if clean_columns:
        await db_session.execute(
            sql_update(Quote).where(Quote.id == quote_id).values(**clean_columns)
        )
        await db_session.commit()
    return {
        "ok": True,
        "updated_fields": list(clean_columns.keys()) + list(clean_breakdown_only.keys()),
    }


async def _create_test_quote(db_session, breakdown: dict | None = None) -> str:
    from app.models.quote import Quote, QuoteStatus
    qid = str(uuid.uuid4())
    quote = Quote(
        id=qid,
        client_name="Test Cliente",
        project="Test Proyecto",
        status=QuoteStatus.DRAFT,
        quote_breakdown=breakdown or {
            "delivery_days": "A confirmar",
            "client_name": "Test Cliente",
            "project": "Test Proyecto",
        },
    )
    db_session.add(quote)
    await db_session.commit()
    return qid


# ═══════════════════════════════════════════════════════════════════════
# Bug DYSCON: delivery_days persiste correctamente
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestUpdateQuoteDeliveryDays:
    async def test_delivery_days_persists_in_breakdown(self, db_session):
        """**Caso DYSCON 29/04/2026**: operador escribe "cambiá la
        demora a 30 días". Antes el handler filtraba silenciosamente
        y retornaba ok sin tocar nada → Sonnet le mentía al operador."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_test_quote(db_session)
        result = await _call_update_quote(
            qid, {"delivery_days": "30 días"}, db_session,
        )
        assert result["ok"] is True
        assert "delivery_days" in result["updated_fields"]

        # Verificar persistencia en DB.
        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        assert q.quote_breakdown["delivery_days"] == "30 días", (
            f"DB no se actualizó: {q.quote_breakdown}"
        )

    async def test_delivery_days_with_other_fields(self, db_session):
        """Combinar delivery_days con un campo de columna funciona."""
        from app.models.quote import Quote
        from sqlalchemy import select

        qid = await _create_test_quote(db_session)
        result = await _call_update_quote(
            qid,
            {"delivery_days": "60 días", "client_name": "Nuevo Cliente"},
            db_session,
        )
        assert result["ok"] is True
        assert "delivery_days" in result["updated_fields"]
        assert "client_name" in result["updated_fields"]

        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        assert q.client_name == "Nuevo Cliente"
        assert q.quote_breakdown["delivery_days"] == "60 días"
        assert q.quote_breakdown["client_name"] == "Nuevo Cliente"  # mirror

    async def test_unknown_field_rejected_loud(self, db_session):
        """**Caso CRÍTICO** (review feedback de Issue #422): si el
        operador o Sonnet pasan un campo no soportado, el handler
        debe ERROREAR ruidosamente, NO filtrar silencioso. Sin esto,
        Sonnet podría mentir al operador "lo cambié" cuando no
        cambió nada (mismo bug del delivery_days original)."""
        qid = await _create_test_quote(db_session)
        result = await _call_update_quote(
            qid,
            {"campo_inventado": "valor"},
            db_session,
        )
        assert result["ok"] is False
        assert "campo_inventado" in result["error"]
        assert "no soportado" in result["error"].lower() or "permitidos" in result["error"].lower()

    async def test_empty_updates_rejected(self, db_session):
        qid = await _create_test_quote(db_session)
        result = await _call_update_quote(qid, {}, db_session)
        assert result["ok"] is False

    async def test_only_none_values_rejected(self, db_session):
        qid = await _create_test_quote(db_session)
        result = await _call_update_quote(
            qid, {"client_name": None, "delivery_days": None}, db_session,
        )
        assert result["ok"] is False

    async def test_no_breakdown_creates_minimal_one(self, db_session):
        """Quote sin breakdown previo (raro pero posible) → crear
        breakdown mínimo con delivery_days."""
        from app.models.quote import Quote, QuoteStatus
        from sqlalchemy import select

        qid = str(uuid.uuid4())
        quote = Quote(
            id=qid,
            client_name="X",
            project="Y",
            status=QuoteStatus.DRAFT,
            quote_breakdown=None,
        )
        db_session.add(quote)
        await db_session.commit()

        result = await _call_update_quote(
            qid, {"delivery_days": "45 días"}, db_session,
        )
        assert result["ok"] is True

        q_res = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = q_res.scalar_one()
        assert q.quote_breakdown is not None
        assert q.quote_breakdown["delivery_days"] == "45 días"

    async def test_idempotent_same_value(self, db_session):
        """Pasar el mismo valor que ya hay → ok, no rompe (changed=False
        pero updated_fields refleja la intención)."""
        qid = await _create_test_quote(db_session)
        # Primera llamada
        await _call_update_quote(qid, {"delivery_days": "30 días"}, db_session)
        # Segunda llamada con el mismo valor
        result = await _call_update_quote(
            qid, {"delivery_days": "30 días"}, db_session,
        )
        assert result["ok"] is True


# ═══════════════════════════════════════════════════════════════════════
# Drift guard del schema del tool
# ═══════════════════════════════════════════════════════════════════════


class TestToolSchema:
    def test_update_quote_schema_includes_delivery_days(self):
        """Drift guard: si alguien edita el schema del tool y olvida
        `delivery_days`, Sonnet vuelve a no saber que está soportado
        → el bug original re-aparece."""
        from app.modules.agent.agent import TOOLS

        update_quote_tool = next(
            (t for t in TOOLS if t.get("name") == "update_quote"), None,
        )
        assert update_quote_tool is not None, "Tool update_quote no encontrado"
        properties = update_quote_tool["input_schema"]["properties"]["updates"]["properties"]
        assert "delivery_days" in properties, (
            "El schema de update_quote debe incluir `delivery_days` "
            "(PR #436). Sin esto Sonnet no sabe que puede cambiarlo."
        )
        assert properties["delivery_days"]["type"] == "string"
