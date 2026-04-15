"""Contract tests for POST /api/quotes/resumen-obra.

Drive uploads are mocked to fail-quiet — we assert the endpoint never depends
on Drive being reachable. Local PDF generation is the single source of truth.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus


def _mk_breakdown(material: str, m2: float, price: float) -> dict:
    return {
        "material_name": material,
        "material_m2": m2,
        "material_price_unit": price,
        "material_currency": "USD",
        "discount_pct": 18,
        "mo_items": [
            {"description": "Agujero y pegado pileta", "quantity": 25,
             "unit_price": 62045, "total": 1551125},
            {"description": "Flete", "quantity": 5,
             "unit_price": 52000, "total": 260000},
        ],
        "mo_total": 1811125,
    }


@pytest_asyncio.fixture
async def validated_quote_factory(db_session):
    """Factory that creates a validated quote and returns its id."""
    async def _make(
        client_name: str = "Estudio 72",
        project: str = "Fideicomiso Ventus",
        material: str = "SILESTONE BLANCO NORTE",
        m2: float = 66.5,
        price: float = 519,
        total_ars: float = 2_708_376,
        total_usd: float = 28_301,
        status: QuoteStatus = QuoteStatus.VALIDATED,
    ) -> str:
        q = Quote(
            id=str(uuid.uuid4()),
            client_name=client_name,
            project=project,
            material=material,
            total_ars=total_ars,
            total_usd=total_usd,
            status=status,
            quote_breakdown=_mk_breakdown(material, m2, price),
            messages=[],
        )
        db_session.add(q)
        await db_session.commit()
        return q.id
    return _make


# ─────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_single_quote_ok(client, validated_quote_factory):
    qid = await validated_quote_factory()
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid], "notes": "Coordinar con obra civil."},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quote_ids"] == [qid]
    assert body["client_name"] == "Estudio 72"
    assert body["pdf_url"].startswith("/files/")
    assert body["notes"] == "Coordinar con obra civil."
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_generate_multi_quote_same_client_ok(
    client, validated_quote_factory, db_session
):
    qid1 = await validated_quote_factory(material="SILESTONE BLANCO NORTE")
    qid2 = await validated_quote_factory(material="GRANITO CEARA", price=357)
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={"drive_url": "https://drive/x", "file_id": "x"},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid1, qid2]},
        )
    assert r.status_code == 200
    body = r.json()
    assert set(body["quote_ids"]) == {qid1, qid2}
    assert body["drive_url"] == "https://drive/x"
    # Both quotes get the same resumen record
    db_session.expire_all()
    for qid in (qid1, qid2):
        row = (await db_session.execute(
            select(Quote).where(Quote.id == qid)
        )).scalar_one()
        assert row.resumen_obra is not None
        assert row.resumen_obra["drive_url"] == "https://drive/x"


async def test_resumen_obra_normalizes_client_name_in_db(
    client, validated_quote_factory, db_session
):
    """PR #18 — tras generar el resumen, todos los presupuestos del grupo
    quedan con el mismo client_name canónico (el más corto). Cubre el caso
    Estudio 72 donde el dashboard mostraba 'Estudio 72' y
    'Estudio 72 — Fideicomiso Ventus' mezclados."""
    from sqlalchemy import update as _upd
    qid1 = await validated_quote_factory(material="SILESTONE BLANCO NORTE")
    qid2 = await validated_quote_factory(material="GRANITO CEARA", price=357)
    # Set names so they match fuzzy but differ in length.
    await db_session.execute(
        _upd(Quote).where(Quote.id == qid1).values(client_name="Estudio 72 — Fideicomiso Ventus")
    )
    await db_session.execute(
        _upd(Quote).where(Quote.id == qid2).values(client_name="Estudio 72")
    )
    await db_session.commit()

    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={"drive_url": "https://drive/x", "file_id": "x"},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid1, qid2], "force_same_client": True},
        )
    assert r.status_code == 200, r.text
    # Ambos quotes quedan con el canónico (el más corto).
    db_session.expire_all()
    for qid in (qid1, qid2):
        row = (await db_session.execute(
            select(Quote).where(Quote.id == qid)
        )).scalar_one()
        assert row.client_name == "Estudio 72", (
            f"Expected canonical client_name='Estudio 72', got {row.client_name!r}"
        )


async def test_quote_detail_exposes_resumen_obra(
    client, validated_quote_factory
):
    """PR #18 — GET /api/quotes/:id debe devolver resumen_obra y
    email_draft para que ResumenObraCard/EmailDraftCard rendericen."""
    qid = await validated_quote_factory(material="SILESTONE BLANCO NORTE")
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={"drive_url": "https://drive/y", "file_id": "y"},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid]},
        )
    assert r.status_code == 200, r.text
    detail = (await client.get(f"/api/quotes/{qid}")).json()
    # El campo debe existir en la respuesta JSON (antes se persistía en DB
    # pero el endpoint lo omitía → frontend no renderizaba ResumenObraCard).
    assert "resumen_obra" in detail
    assert detail["resumen_obra"] is not None
    assert detail["resumen_obra"]["drive_url"] == "https://drive/y"
    # email_draft también debe estar presente (aunque sea None)
    assert "email_draft" in detail


# ─────────────────────────────────────────────────────────────────────────
# Validation rejections
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_empty_quote_ids(client):
    r = await client.post("/api/quotes/resumen-obra", json={"quote_ids": []})
    assert r.status_code == 400
    assert "vac" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reject_too_many_quote_ids(client, validated_quote_factory):
    ids = [await validated_quote_factory() for _ in range(21)]
    r = await client.post("/api/quotes/resumen-obra", json={"quote_ids": ids})
    assert r.status_code == 400
    assert "20" in r.json()["detail"] or "Máximo" in r.json()["detail"]


@pytest.mark.asyncio
async def test_reject_nonexistent_quote_id(client, validated_quote_factory):
    qid_real = await validated_quote_factory()
    fake = str(uuid.uuid4())
    r = await client.post(
        "/api/quotes/resumen-obra",
        json={"quote_ids": [qid_real, fake]},
    )
    assert r.status_code == 404
    assert fake in r.json()["detail"]


@pytest.mark.asyncio
async def test_reject_non_validated_quote(client, validated_quote_factory):
    qid_ok = await validated_quote_factory()
    qid_draft = await validated_quote_factory(status=QuoteStatus.DRAFT)
    r = await client.post(
        "/api/quotes/resumen-obra",
        json={"quote_ids": [qid_ok, qid_draft]},
    )
    assert r.status_code == 400
    assert qid_draft in r.json()["detail"]


@pytest.mark.asyncio
async def test_reject_mixed_clients(client, validated_quote_factory):
    qa = await validated_quote_factory(client_name="Estudio 72")
    qb = await validated_quote_factory(client_name="Juan Perez")
    r = await client.post(
        "/api/quotes/resumen-obra",
        json={"quote_ids": [qa, qb]},
    )
    assert r.status_code == 400
    assert "mismo cliente" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_same_client_different_casing_accepted(
    client, validated_quote_factory
):
    qa = await validated_quote_factory(client_name="Estudio 72")
    qb = await validated_quote_factory(client_name="  ESTUDIO 72  ")
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qa, qb]},
        )
    assert r.status_code == 200, r.text


# ─────────────────────────────────────────────────────────────────────────
# Notes sanitization
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notes_max_length(client, validated_quote_factory):
    qid = await validated_quote_factory()
    r = await client.post(
        "/api/quotes/resumen-obra",
        json={"quote_ids": [qid], "notes": "x" * 1001},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_notes_control_chars_stripped(
    client, validated_quote_factory, db_session
):
    qid = await validated_quote_factory()
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid], "notes": "Hola\x00\x07 mundo"},
        )
    assert r.status_code == 200
    assert "\x00" not in r.json()["notes"]
    assert "\x07" not in r.json()["notes"]


# ─────────────────────────────────────────────────────────────────────────
# Idempotency / overwrite
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overwrite_existing_resumen(
    client, validated_quote_factory, db_session
):
    qid = await validated_quote_factory()
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r1 = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid], "notes": "first"},
        )
        assert r1.status_code == 200
        first_ts = r1.json()["generated_at"]
        r2 = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid], "notes": "second"},
        )
    assert r2.status_code == 200
    second_ts = r2.json()["generated_at"]
    assert r2.json()["notes"] == "second"
    assert second_ts >= first_ts
    # DB reflects the latest
    db_session.expire_all()
    row = (await db_session.execute(
        select(Quote).where(Quote.id == qid)
    )).scalar_one()
    assert row.resumen_obra["notes"] == "second"


@pytest.mark.asyncio
async def test_dedup_same_id(client, validated_quote_factory):
    qid = await validated_quote_factory()
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid, qid, qid]},
        )
    assert r.status_code == 200
    assert r.json()["quote_ids"] == [qid]


# ─────────────────────────────────────────────────────────────────────────
# Email draft invalidation
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidates_email_draft(
    client, validated_quote_factory, db_session
):
    qid = await validated_quote_factory()
    # Pre-seed email_draft
    q = (await db_session.execute(
        select(Quote).where(Quote.id == qid)
    )).scalar_one()
    q.email_draft = {"subject": "x", "body": "y"}
    await db_session.commit()

    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        return_value={},
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid]},
        )
    assert r.status_code == 200
    # Expire session cache so we re-read from DB instead of the pre-commit state
    db_session.expire_all()
    row = (await db_session.execute(
        select(Quote).where(Quote.id == qid)
    )).scalar_one()
    assert row.email_draft is None


# ─────────────────────────────────────────────────────────────────────────
# Resilience: Drive failure does not break PDF generation
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_drive_failure_does_not_break_generation(
    client, validated_quote_factory, db_session
):
    qid = await validated_quote_factory()
    with patch(
        "app.modules.agent.tools.resumen_obra_tool._upload_to_drive_safe",
        side_effect=Exception("Drive down"),
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid]},
        )
    # Drive failure must NOT cascade — endpoint returns 500 because the
    # wrapper re-raises. To confirm the non-fatal path, patch the wrapper
    # itself to simulate the real 'return {}' behavior:
    assert r.status_code == 500  # sanity: uncaught side_effect surfaces


@pytest.mark.asyncio
async def test_drive_failure_wrapped_returns_200(
    client, validated_quote_factory, db_session
):
    qid = await validated_quote_factory()
    # Patch the underlying drive upload to fail; _upload_to_drive_safe swallows it
    with patch(
        "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
        side_effect=Exception("Drive down"),
    ):
        r = await client.post(
            "/api/quotes/resumen-obra",
            json={"quote_ids": [qid]},
        )
    assert r.status_code == 200, r.text
    assert r.json()["drive_url"] is None
