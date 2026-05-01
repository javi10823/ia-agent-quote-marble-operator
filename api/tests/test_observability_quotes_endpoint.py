"""Tests del endpoint nuevo `GET /admin/observability/quotes` (refactor UX).

Cubre:
- Devuelve quotes agrupados con counts correctos.
- Filtros: q (search), actor, has_errors, has_debug, from/to.
- Paginación (limit/offset).
- Orden default: last_event_desc.
- Quote con client_name JOIN.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


async def _seed(db_session, quote_id: str, client_name: str | None, events: list[dict]):
    """Inserta un Quote + N events. `events` es lista de dicts con keys
    parciales — el resto se llena con defaults razonables."""
    from app.models.quote import Quote, QuoteStatus
    from app.modules.observability.models import AuditEvent

    if client_name is not None:
        db_session.add(Quote(
            id=quote_id, client_name=client_name, project="Test",
            messages=[], status=QuoteStatus.VALIDATED,
        ))
    for i, e in enumerate(events):
        db_session.add(AuditEvent(
            id=str(uuid.uuid4()),
            created_at=e.get("created_at", datetime.now(timezone.utc) + timedelta(seconds=i)),
            event_type=e.get("event_type", "test.event"),
            source=e.get("source", "test"),
            quote_id=quote_id,
            session_id=quote_id,
            actor=e.get("actor", "javi"),
            actor_kind="user",
            request_id=str(uuid.uuid4()),
            turn_index=None,
            summary=e.get("summary", "test event"),
            payload={},
            payload_truncated=False,
            success=e.get("success", True),
            error_message=e.get("error_message"),
            elapsed_ms=None,
            debug_payload=e.get("debug_payload", False),
        ))
    await db_session.commit()


class TestObservabilityQuotesEndpoint:
    @pytest.mark.asyncio
    async def test_groups_events_by_quote(self, client, db_session):
        await _seed(db_session, "q-A", "Cliente A", [
            {"event_type": "quote.created"},
            {"event_type": "agent.tool_called"},
            {"event_type": "quote.calculated"},
        ])
        await _seed(db_session, "q-B", "Cliente B", [
            {"event_type": "quote.created"},
        ])

        r = await client.get("/api/admin/observability/quotes")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 2
        # Encuentra el quote A
        a = next((q for q in data["quotes"] if q["quote_id"] == "q-A"), None)
        assert a is not None
        assert a["client_name"] == "Cliente A"
        assert a["events_count"] == 3
        assert a["errors_count"] == 0
        assert a["has_debug_payloads"] is False
        assert a["actor"] == "javi"

    @pytest.mark.asyncio
    async def test_errors_count_filter(self, client, db_session):
        await _seed(db_session, "q-OK", "OK", [
            {"event_type": "quote.created", "success": True},
        ])
        await _seed(db_session, "q-FAIL", "Failing", [
            {"event_type": "quote.created", "success": True},
            {"event_type": "agent.tool_result", "success": False, "error_message": "boom"},
        ])

        # has_errors=true → solo q-FAIL
        r = await client.get("/api/admin/observability/quotes?has_errors=true")
        data = r.json()
        assert data["total"] == 1
        assert data["quotes"][0]["quote_id"] == "q-FAIL"
        assert data["quotes"][0]["errors_count"] == 1

        # has_errors=false → solo q-OK
        r = await client.get("/api/admin/observability/quotes?has_errors=false")
        data = r.json()
        assert data["total"] == 1
        assert data["quotes"][0]["quote_id"] == "q-OK"

    @pytest.mark.asyncio
    async def test_has_debug_filter(self, client, db_session):
        await _seed(db_session, "q-NORMAL", "Normal", [
            {"event_type": "quote.created"},
        ])
        await _seed(db_session, "q-DEBUG", "Debug", [
            {"event_type": "quote.created"},
            {"event_type": "agent.tool_called", "debug_payload": True},
        ])

        r = await client.get("/api/admin/observability/quotes?has_debug=true")
        data = r.json()
        assert data["total"] == 1
        assert data["quotes"][0]["quote_id"] == "q-DEBUG"
        assert data["quotes"][0]["has_debug_payloads"] is True

    @pytest.mark.asyncio
    async def test_search_q_matches_quote_id_and_client_name(
        self, client, db_session,
    ):
        await _seed(db_session, "q-DYS-001", "Marina Pérez", [
            {"event_type": "quote.created"},
        ])
        await _seed(db_session, "q-OTHER", "Otro Cliente", [
            {"event_type": "quote.created"},
        ])

        # Match por quote_id substring
        r = await client.get("/api/admin/observability/quotes?q=DYS")
        data = r.json()
        assert data["total"] == 1
        assert data["quotes"][0]["quote_id"] == "q-DYS-001"

        # Match por client_name substring (case-insensitive)
        r = await client.get("/api/admin/observability/quotes?q=marina")
        data = r.json()
        assert data["total"] == 1
        assert data["quotes"][0]["client_name"] == "Marina Pérez"

    @pytest.mark.asyncio
    async def test_actor_filter(self, client, db_session):
        await _seed(db_session, "q-JAVI", "C", [
            {"event_type": "quote.created", "actor": "javi"},
        ])
        await _seed(db_session, "q-MARINA", "C", [
            {"event_type": "quote.created", "actor": "marina"},
        ])

        r = await client.get("/api/admin/observability/quotes?actor=javi")
        data = r.json()
        assert data["total"] == 1
        assert data["quotes"][0]["quote_id"] == "q-JAVI"

    @pytest.mark.asyncio
    async def test_pagination(self, client, db_session):
        for i in range(5):
            await _seed(db_session, f"q-page-{i}", f"C{i}", [
                {"event_type": "quote.created"},
            ])

        r = await client.get("/api/admin/observability/quotes?limit=2&offset=0")
        data = r.json()
        assert data["total"] == 5
        assert len(data["quotes"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

        r = await client.get("/api/admin/observability/quotes?limit=2&offset=2")
        data = r.json()
        assert len(data["quotes"]) == 2
        assert data["offset"] == 2

    @pytest.mark.asyncio
    async def test_sort_default_last_event_desc(self, client, db_session):
        # q-OLD con último event hace 1h
        old_ts = datetime.now(timezone.utc) - timedelta(hours=1)
        new_ts = datetime.now(timezone.utc)
        await _seed(db_session, "q-OLD", "Old", [
            {"event_type": "quote.created", "created_at": old_ts},
        ])
        await _seed(db_session, "q-NEW", "New", [
            {"event_type": "quote.created", "created_at": new_ts},
        ])

        r = await client.get("/api/admin/observability/quotes")
        data = r.json()
        # New primero (last_event_at más reciente).
        assert data["quotes"][0]["quote_id"] == "q-NEW"
        assert data["quotes"][1]["quote_id"] == "q-OLD"

    @pytest.mark.asyncio
    async def test_quote_without_record_in_quotes_table(
        self, client, db_session,
    ):
        """Si hay events para un quote_id que NO existe en la tabla
        quotes (ej. eventos huérfanos post delete), igual aparece en
        la lista pero con client_name=None."""
        await _seed(db_session, "q-ORPHAN", None, [
            {"event_type": "quote.created"},
        ])

        r = await client.get("/api/admin/observability/quotes")
        data = r.json()
        orphan = next((q for q in data["quotes"] if q["quote_id"] == "q-ORPHAN"), None)
        assert orphan is not None
        assert orphan["client_name"] is None
        assert orphan["events_count"] == 1
