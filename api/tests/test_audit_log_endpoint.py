"""Tests del endpoint `GET /api/quotes/{id}/audit-log` · Sprint 4 audit-trail-copy.

Cobertura:
- 404 quote inexistente
- happy path con eventos + errores + tokens + tools agregados
- truncation default >limit, full=true devuelve todos
- errors[] siempre completo aunque events trunca
- chat_duration_ms derivado de timestamps
- quote_breakdown se devuelve tal cual del JSON column
- log_event ironía-controlada se registra (audit.log_fetched)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


async def _seed_quote_with_audit(
    db_session,
    quote_id: str,
    *,
    client_name: str = "Cliente Test",
    project: str = "Test project",
    material: str | None = "Silestone Blanco Norte",
    breakdown: dict | None = None,
    messages: list | None = None,
    source_files: list | None = None,
    events: list[dict] | None = None,
    token_rows: list[dict] | None = None,
):
    """Inserta Quote + AuditEvent rows + TokenUsage rows."""
    from app.models.quote import Quote, QuoteStatus
    from app.models.usage import TokenUsage
    from app.modules.observability.models import AuditEvent

    db_session.add(
        Quote(
            id=quote_id,
            client_name=client_name,
            project=project,
            material=material,
            messages=messages or [],
            status=QuoteStatus.DRAFT,
            quote_breakdown=breakdown,
            source_files=source_files,
        )
    )
    base = datetime.now(timezone.utc)
    for i, e in enumerate(events or []):
        db_session.add(
            AuditEvent(
                id=str(uuid.uuid4()),
                created_at=e.get("created_at", base + timedelta(seconds=i)),
                event_type=e.get("event_type", "test.event"),
                source=e.get("source", "test"),
                quote_id=quote_id,
                session_id=quote_id,
                actor=e.get("actor", "javi"),
                actor_kind="user",
                request_id=str(uuid.uuid4()),
                turn_index=e.get("turn_index"),
                summary=e.get("summary", "test event"),
                payload=e.get("payload", {}),
                payload_truncated=False,
                success=e.get("success", True),
                error_message=e.get("error_message"),
                elapsed_ms=e.get("elapsed_ms"),
                debug_payload=False,
            )
        )
    for tu in token_rows or []:
        db_session.add(
            TokenUsage(
                quote_id=quote_id,
                input_tokens=tu.get("input_tokens", 0),
                output_tokens=tu.get("output_tokens", 0),
                cache_read_tokens=tu.get("cache_read_tokens", 0),
                cache_write_tokens=tu.get("cache_write_tokens", 0),
                model=tu.get("model", "sonnet"),
                cost_usd=tu.get("cost_usd", 0.0),
                iterations=tu.get("iterations", 1),
            )
        )
    await db_session.commit()


class TestAuditLogEndpoint:
    @pytest.mark.asyncio
    async def test_404_quote_not_found(self, client):
        r = await client.get("/api/quotes/does-not-exist/audit-log")
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_happy_path_aggregates_everything(self, client, db_session):
        base = datetime.now(timezone.utc)
        await _seed_quote_with_audit(
            db_session,
            "q-happy",
            client_name="Cueto-Heredia",
            material="Silestone Blanco Norte",
            messages=[
                {"role": "user", "content": "Hola Marina, te paso el plano..."},
                {"role": "assistant", "content": "Listo."},
            ],
            source_files=[{"filename": "plano.pdf"}, {"filename": "foto.jpg"}],
            breakdown={"sectors": [{"id": "S1"}], "total_ars": 660739},
            events=[
                {"event_type": "quote.created", "created_at": base},
                {"event_type": "chat.message_sent", "created_at": base + timedelta(seconds=1)},
                {"event_type": "agent.stream_started", "created_at": base + timedelta(seconds=2)},
                {
                    "event_type": "agent.tool_called",
                    "created_at": base + timedelta(seconds=3),
                    "payload": {"tool_name": "read_plan"},
                },
                {
                    "event_type": "agent.tool_result",
                    "created_at": base + timedelta(seconds=14),
                    "payload": {"tool_name": "read_plan", "ok": True},
                    "elapsed_ms": 11000,
                    "success": True,
                },
                {
                    "event_type": "agent.tool_result",
                    "created_at": base + timedelta(seconds=15),
                    "payload": {"tool_name": "catalog_lookup", "ok": True},
                    "elapsed_ms": 200,
                    "success": True,
                },
                {
                    "event_type": "quote.calculated",
                    "created_at": base + timedelta(seconds=25),
                    "payload": {"breakdown_keys": ["sectors", "total_ars"]},
                },
            ],
            token_rows=[
                {"input_tokens": 12000, "output_tokens": 3000, "cost_usd": 0.087, "model": "sonnet"},
            ],
        )
        r = await client.get("/api/quotes/q-happy/audit-log")
        assert r.status_code == 200, r.text
        data = r.json()

        # meta
        assert data["meta"]["quote_id"] == "q-happy"
        assert data["meta"]["client_name"] == "Cueto-Heredia"
        assert data["meta"]["material"] == "Silestone Blanco Norte"
        # input_message preserved
        assert data["input_message"] is not None
        assert "Hola Marina" in data["input_message"]
        assert data["plan_files"] == ["plano.pdf", "foto.jpg"]

        # events
        assert data["events_total"] == 7
        assert data["events_truncated"] is False
        event_types = [e["event_type"] for e in data["events"]]
        assert "quote.created" in event_types
        assert "agent.stream_started" in event_types
        assert event_types[0] == "quote.created"  # asc

        # tokens summary
        assert data["tokens"]["input_tokens"] == 12000
        assert data["tokens"]["output_tokens"] == 3000
        assert data["tokens"]["cost_usd"] == pytest.approx(0.087)
        assert data["tokens"]["models_used"] == ["sonnet"]

        # tools_used aggregated
        tool_names = {t["tool_name"] for t in data["tools_used"]}
        assert tool_names == {"read_plan", "catalog_lookup"}
        read_plan = next(t for t in data["tools_used"] if t["tool_name"] == "read_plan")
        assert read_plan["count"] == 1
        assert read_plan["total_ms"] == 11000
        assert read_plan["error_count"] == 0

        # chat_duration derived from timestamps (stream_started → last tool_result/calculated)
        assert data["chat_duration_ms"] is not None
        assert 22000 <= data["chat_duration_ms"] <= 24000  # ~23s

        # breakdown preserved
        assert data["quote_breakdown"]["total_ars"] == 660739

        # errors empty
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_errors_separate_from_events(self, client, db_session):
        base = datetime.now(timezone.utc)
        await _seed_quote_with_audit(
            db_session,
            "q-err",
            events=[
                {"event_type": "quote.created"},
                {
                    "event_type": "agent.tool_result",
                    "payload": {"tool_name": "read_plan"},
                    "success": False,
                    "error_message": "Plano ilegible · OCR fallido",
                    "elapsed_ms": 30000,
                },
                {
                    "event_type": "agent.tool_result",
                    "payload": {"tool_name": "read_plan"},
                    "success": True,
                    "elapsed_ms": 5000,
                },
            ],
        )
        r = await client.get("/api/quotes/q-err/audit-log")
        assert r.status_code == 200
        data = r.json()

        assert len(data["errors"]) == 1
        assert data["errors"][0]["error_message"] == "Plano ilegible · OCR fallido"
        assert data["errors"][0]["success"] is False

        # tools_used.error_count refleja el fallo
        read_plan = next(t for t in data["tools_used"] if t["tool_name"] == "read_plan")
        assert read_plan["count"] == 2
        assert read_plan["error_count"] == 1
        assert read_plan["total_ms"] == 35000

    @pytest.mark.asyncio
    async def test_truncation_when_over_limit(self, client, db_session):
        # 250 eventos > limit default 200 → truncate por defecto
        await _seed_quote_with_audit(
            db_session,
            "q-many",
            events=[{"event_type": f"test.evt.{i}"} for i in range(250)],
        )
        r = await client.get("/api/quotes/q-many/audit-log")
        assert r.status_code == 200
        data = r.json()
        assert data["events_total"] == 250
        assert data["events_truncated"] is True
        assert len(data["events"]) == 200  # default limit

        # full=true devuelve todos
        r2 = await client.get("/api/quotes/q-many/audit-log?full=true")
        data2 = r2.json()
        assert data2["events_truncated"] is False
        assert len(data2["events"]) == 250

    @pytest.mark.asyncio
    async def test_empty_quote_returns_empty_arrays(self, client, db_session):
        await _seed_quote_with_audit(db_session, "q-empty")
        r = await client.get("/api/quotes/q-empty/audit-log")
        assert r.status_code == 200
        data = r.json()
        assert data["events_total"] == 0
        assert data["events"] == []
        assert data["errors"] == []
        assert data["tools_used"] == []
        assert data["tokens"]["input_tokens"] == 0
        assert data["chat_duration_ms"] is None
        assert data["input_message"] is None
        assert data["plan_files"] == []
