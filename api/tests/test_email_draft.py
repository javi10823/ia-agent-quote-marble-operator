"""Tests for the AI-generated email draft endpoint.

LLM calls are mocked — we assert the orchestration layer (validator, stale
detection, cache, prompt safety) without burning tokens.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.tools.email_draft_tool import (
    is_email_stale,
    validate_email_amounts,
    _parse_amount,
    generate_email_draft,
)


# ─────────────────────────────────────────────────────────────────────────
# Unit tests — pure functions (no DB, no LLM)
# ─────────────────────────────────────────────────────────────────────────

def test_parse_amount_dot_thousands():
    assert _parse_amount("28.301") == 28301
    assert _parse_amount("2.708.376") == 2708376


def test_parse_amount_with_decimal():
    assert _parse_amount("28.301,50") == 28301
    assert _parse_amount("1.200,99") == 1200


def test_parse_amount_plain_int():
    assert _parse_amount("500") == 500


def test_parse_amount_invalid():
    assert _parse_amount("") is None
    assert _parse_amount("abc") is None
    assert _parse_amount("1.2.x") is None


def _mk_ctx(totals_list: list[dict]) -> dict:
    return {
        "quotes": [{"totals": t} for t in totals_list],
        "grand_total_ars": sum(t.get("total_ars", 0) for t in totals_list),
        "grand_total_usd": sum(t.get("total_usd", 0) for t in totals_list),
    }


def test_validator_accepts_exact_amounts():
    ctx = _mk_ctx([{"total_ars": 2708376, "total_usd": 19467}])
    body = (
        "Los montos son $2.708.376 mano de obra y USD 19.467 material."
    )
    assert validate_email_amounts(body, ctx) == []


def test_validator_tolerates_rounding():
    ctx = _mk_ctx([{"total_ars": 2708376, "total_usd": 28301}])
    # ±5 tolerance allows 28.300 ↔ 28.301
    body = "USD 28.300 vs contexto USD 28.301"
    assert validate_email_amounts(body, ctx) == []


def test_validator_catches_hallucinated_usd():
    ctx = _mk_ctx([{"total_ars": 2708376, "total_usd": 19467}])
    body = "Total: USD 99.999 (hallucinated)"
    errors = validate_email_amounts(body, ctx)
    assert errors and "99.999" in errors[0]


def test_validator_catches_hallucinated_ars():
    ctx = _mk_ctx([{"total_ars": 2708376, "total_usd": 19467}])
    body = "Entregamos a cambio de $5.000.000 ahora"
    errors = validate_email_amounts(body, ctx)
    assert errors


def test_validator_ignores_small_numbers():
    """Small numbers (zip codes, counts, dates) must not trip the validator."""
    ctx = _mk_ctx([{"total_ars": 2708376, "total_usd": 28301}])
    body = (
        "Recibimos el 4 de abril $2.708.376 por USD 28.301. "
        "Código 2000, 25 piletas, 5 fletes."
    )
    assert validate_email_amounts(body, ctx) == []


def test_validator_empty_body_is_ok():
    ctx = _mk_ctx([{"total_ars": 100}])
    assert validate_email_amounts("", ctx) == []


# ── Stale detection ──────────────────────────────────────────────────────

def _mk_snapshot_ctx(anchor_ts: str, sibs: dict[str, str], resumen_ts=None):
    return {
        "anchor_updated_at": anchor_ts,
        "sibling_updated_at_snapshots": sibs,
        "resumen_generated_at_snapshot": resumen_ts,
    }


def test_stale_none_draft_is_stale():
    assert is_email_stale(None, _mk_snapshot_ctx("2026-04-14", {}, None)) is True


def test_stale_anchor_timestamp_advanced():
    draft = {
        "quote_updated_at_snapshot": "2026-04-14T10:00:00",
        "sibling_updated_at_snapshots": {"a": "2026-04-14"},
        "resumen_updated_at_snapshot": None,
    }
    ctx = _mk_snapshot_ctx(
        "2026-04-14T11:00:00", {"a": "2026-04-14"}, None
    )
    assert is_email_stale(draft, ctx) is True


def test_stale_sibling_added():
    draft = {
        "quote_updated_at_snapshot": "T",
        "sibling_updated_at_snapshots": {"a": "T"},
        "resumen_updated_at_snapshot": None,
    }
    ctx = _mk_snapshot_ctx("T", {"a": "T", "b": "T"}, None)
    assert is_email_stale(draft, ctx) is True


def test_stale_resumen_regenerated():
    draft = {
        "quote_updated_at_snapshot": "T",
        "sibling_updated_at_snapshots": {"a": "T"},
        "resumen_updated_at_snapshot": "2026-04-10",
    }
    ctx = _mk_snapshot_ctx("T", {"a": "T"}, "2026-04-14")
    assert is_email_stale(draft, ctx) is True


def test_fresh_when_all_snapshots_match():
    draft = {
        "quote_updated_at_snapshot": "T",
        "sibling_updated_at_snapshots": {"a": "T"},
        "resumen_updated_at_snapshot": "2026-04-10",
    }
    ctx = _mk_snapshot_ctx("T", {"a": "T"}, "2026-04-10")
    assert is_email_stale(draft, ctx) is False


# ─────────────────────────────────────────────────────────────────────────
# Integration tests — orchestrator with mocked LLM
# ─────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def validated_quote(db_session):
    q = Quote(
        id=str(uuid.uuid4()),
        client_name="Estudio 72",
        project="Fideicomiso Ventus",
        material="SILESTONE BLANCO NORTE",
        total_ars=2_708_376,
        total_usd=28_301,
        status=QuoteStatus.VALIDATED,
        quote_breakdown={
            "material_name": "SILESTONE BLANCO NORTE",
            "material_m2": 66.5,
            "material_price_unit": 519,
            "material_currency": "USD",
            "discount_pct": 18,
        },
        messages=[],
    )
    db_session.add(q)
    await db_session.commit()
    return q


async def _mock_llm_response(subject: str, body: str):
    async def _inner(context, prior_error=None):
        return {"subject": subject, "body": body}
    return _inner


# PR #22 — el flow ya no usa LLM, es plantilla fija (Agostina). Los
# tests de mock _call_llm fueron reemplazados por verificación del
# template. Validator retry tampoco aplica (el body fijo no inventa
# números — los detalles van en los PDFs adjuntos).

@pytest.mark.asyncio
async def test_generate_template_email_ok(client, validated_quote):
    r = await client.get(f"/api/quotes/{validated_quote.id}/email-draft")
    assert r.status_code == 200, r.text
    body = r.json()
    # Template Agostina — strings clave que siempre deben estar.
    assert "Buenas tardes" in body["body"]
    assert "Confirmar recepción" in body["body"]
    assert "Agostina" in body["body"]
    assert "Marmolería D'Angelo" in body["body"]
    assert "3413 082996" in body["body"]
    assert "San Nicolas 1160" in body["body"]
    assert body["validated"] is True


@pytest.mark.asyncio
async def test_template_email_does_not_hallucinate_amounts(
    client, validated_quote
):
    """Plantilla fija no incluye montos en el body — los detalles van
    en los PDFs adjuntos. Evita inconsistencias de la IA anterior."""
    r = await client.get(f"/api/quotes/{validated_quote.id}/email-draft")
    body = r.json()["body"]
    # No debe haber dígitos de montos típicos
    assert "$" not in body
    assert "USD" not in body


@pytest.mark.asyncio
async def test_cache_hit_on_second_call(client, validated_quote):
    """Cache sigue funcionando con el template (no se regenera si no hay
    cambios)."""
    r1 = await client.get(f"/api/quotes/{validated_quote.id}/email-draft")
    assert r1.status_code == 200
    first_generated_at = r1.json()["generated_at"]
    r2 = await client.get(f"/api/quotes/{validated_quote.id}/email-draft")
    assert r2.status_code == 200
    # generated_at debe ser exactamente el mismo (no se regeneró).
    assert r2.json()["generated_at"] == first_generated_at


@pytest.mark.asyncio
async def test_regenerate_endpoint_ignores_cache(client, validated_quote):
    """POST /regenerate fuerza nuevo timestamp aunque el contenido sea idéntico."""
    r1 = await client.get(f"/api/quotes/{validated_quote.id}/email-draft")
    first_generated_at = r1.json()["generated_at"]
    r2 = await client.post(
        f"/api/quotes/{validated_quote.id}/email-draft/regenerate"
    )
    assert r2.status_code == 200
    # Forced regeneration → timestamp distinto
    assert r2.json()["generated_at"] != first_generated_at
    assert r2.json()["validated"] is True


# PR #22 — tests obsoletos de validator/notes-injection/LLM-error fueron
# eliminados porque el flow ya no usa LLM. Quedan los tests de template +
# cache + 404.

@pytest.mark.asyncio
async def test_unknown_quote_returns_404(client):
    r = await client.get(f"/api/quotes/{uuid.uuid4()}/email-draft")
    assert r.status_code == 404
