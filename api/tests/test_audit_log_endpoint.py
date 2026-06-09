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

    # ── Fix-up sprint-4/audit-log-content-fix · Bug 1 (regresión) ──────────
    # En prod, `Quote.messages[].content` viene como lista de bloques
    # multimodales Anthropic, NO como string plano (los fixtures previos
    # usaban string → no atraparon el bug). Estos tests cubren el shape real.

    @pytest.mark.asyncio
    async def test_audit_log_with_multimodal_content(self, client, db_session):
        await _seed_quote_with_audit(
            db_session,
            "q-multimodal",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Mesada de 2 x 0,60 en purastone venatino",
                        }
                    ],
                },
                {"role": "assistant", "content": "Listo."},
            ],
        )
        r = await client.get("/api/quotes/q-multimodal/audit-log")
        assert r.status_code == 200
        data = r.json()
        assert data["input_message"] == "Mesada de 2 x 0,60 en purastone venatino"

    @pytest.mark.asyncio
    async def test_audit_log_handles_mixed_content_blocks(self, client, db_session):
        await _seed_quote_with_audit(
            db_session,
            "q-mixed-blocks",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Mesada"},
                        {"type": "image", "source": {"type": "base64", "data": "..."}},
                        {"type": "text", "text": "de 2x0.60"},
                    ],
                }
            ],
        )
        r = await client.get("/api/quotes/q-mixed-blocks/audit-log")
        assert r.status_code == 200
        data = r.json()
        # Solo los bloques `text`, concatenados con espacio · el bloque image se omite.
        assert data["input_message"] == "Mesada de 2x0.60"

    @pytest.mark.asyncio
    async def test_audit_log_with_string_content(self, client, db_session):
        # Compat retroactiva · content como string plano sigue funcionando.
        await _seed_quote_with_audit(
            db_session,
            "q-string-content",
            messages=[{"role": "user", "content": "brief en string plano"}],
        )
        r = await client.get("/api/quotes/q-string-content/audit-log")
        assert r.status_code == 200
        assert r.json()["input_message"] == "brief en string plano"


# ── Fix-up sprint-4/audit-log-content-fix · Bug 2 (CORS en 5xx) ────────────
class TestUnhandledExceptionCors:
    """El handler global de Exception reinyecta headers CORS en los 500 para
    que el browser lea el status real en vez de un 'CORS error' opaco.

    Se testea el handler directamente (no vía TestClient) porque el
    ServerErrorMiddleware de Starlette re-raise la excepción tras emitir la
    respuesta, lo que el cliente de test propagaría — testear la función
    aísla la lógica de reinyección de CORS sin ese ruido."""

    def _make_request(self, origin: str | None):
        from starlette.requests import Request

        headers = [(b"origin", origin.encode())] if origin else []
        return Request({"type": "http", "method": "GET", "path": "/x", "headers": headers})

    @pytest.mark.asyncio
    async def test_5xx_returns_cors_headers_for_allowed_origin(self):
        from app.main import unhandled_exception_handler
        from app.core.config import settings

        allowed = settings.CORS_ORIGINS[0]  # garantizado en la allow-list
        resp = await unhandled_exception_handler(
            self._make_request(allowed), RuntimeError("boom")
        )
        assert resp.status_code == 500
        assert resp.headers.get("access-control-allow-origin") == allowed
        assert resp.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_5xx_no_cors_headers_for_disallowed_origin(self):
        from app.main import unhandled_exception_handler

        resp = await unhandled_exception_handler(
            self._make_request("https://no-permitido.example"), RuntimeError("boom")
        )
        assert resp.status_code == 500
        assert resp.headers.get("access-control-allow-origin") is None


# ── Sprint 4 audit-text-only-instrumentation · Bug 2 fix ──────────────────
# Verifica que los nuevos event_types emitidos por agent.py (text-only +
# dual_read paths) son persistidos correctamente y aparecen en el response
# del endpoint sin filtros. Tests aislados: NO ejecutan agent.chat()
# (requiere LLM mocking), seedean directamente con shape canon.

class TestAuditLogTextOnlyInstrumentation:
    @pytest.mark.asyncio
    async def test_text_only_flow_events_appear_in_audit_log(self, client, db_session):
        """Simula los 4 events nuevos del text-only flow + 2 baseline previos."""
        base = datetime.now(timezone.utc)
        await _seed_quote_with_audit(
            db_session,
            "q-text-only",
            client_name="Familia Mansilla",
            material=None,
            messages=[
                {"role": "user", "content": "Mesada de 2 x 0,60 en purastone venatino"}
            ],
            events=[
                {"event_type": "quote.created", "created_at": base, "summary": "Quote created"},
                {
                    "event_type": "chat.message_sent",
                    "created_at": base + timedelta(milliseconds=12),
                    "summary": "Operator sent chat message",
                },
                {
                    "event_type": "text_parse.started",
                    "created_at": base + timedelta(milliseconds=120),
                    "summary": "Text-only brief parse started · msg_chars=43",
                    "payload": {"message_chars": 43},
                },
                {
                    "event_type": "text_parse.completed",
                    "created_at": base + timedelta(milliseconds=8456),
                    "summary": "Text-only brief parse completed · tramos=1",
                    "payload": {"ok": True, "sectores_count": 1},
                    "elapsed_ms": 8336,
                },
                {
                    "event_type": "context_analysis.started",
                    "created_at": base + timedelta(milliseconds=8500),
                    "summary": "Text-only context analysis started",
                    "payload": {"path": "text_only"},
                },
                {
                    "event_type": "quote_breakdown.mutated",
                    "created_at": base + timedelta(milliseconds=12100),
                    "summary": "Breakdown mutated (text-only)",
                    "payload": {
                        "path": "text_only",
                        "mutated_keys": ["dual_read_result", "context_analysis_pending"],
                    },
                },
                {
                    "event_type": "context_analysis.pending",
                    "created_at": base + timedelta(milliseconds=12150),
                    "summary": "Text-only context pending · 3 known · 2 assumptions · 1 questions",
                    "payload": {
                        "path": "text_only",
                        "data_known_count": 3,
                        "assumptions_count": 2,
                        "pending_questions_count": 1,
                    },
                    "elapsed_ms": 3600,
                },
            ],
        )
        r = await client.get("/api/quotes/q-text-only/audit-log")
        assert r.status_code == 200, r.text
        data = r.json()

        # Total events visible (7 baseline + new instrumentation)
        assert data["events_total"] == 7

        # Los 5 event_types NUEVOS aparecen sin filtro
        event_types = {e["event_type"] for e in data["events"]}
        expected_new = {
            "text_parse.started",
            "text_parse.completed",
            "context_analysis.started",
            "quote_breakdown.mutated",
            "context_analysis.pending",
        }
        assert expected_new.issubset(event_types), (
            f"Faltan event_types nuevos: {expected_new - event_types}"
        )

        # Payload del context_analysis.pending preserva data_known_count
        ctx = next(e for e in data["events"] if e["event_type"] == "context_analysis.pending")
        assert ctx["payload"]["data_known_count"] == 3
        assert ctx["payload"]["path"] == "text_only"
        assert ctx["elapsed_ms"] == 3600

    @pytest.mark.asyncio
    async def test_dual_read_flow_events_appear_in_audit_log(self, client, db_session):
        """Simula los 4 events nuevos del plan flow (_run_dual_read)."""
        base = datetime.now(timezone.utc)
        await _seed_quote_with_audit(
            db_session,
            "q-dual-read",
            messages=[{"role": "user", "content": "leé el plano"}],
            source_files=[{"filename": "plano.pdf"}],
            events=[
                {"event_type": "quote.created", "created_at": base},
                {"event_type": "chat.message_sent", "created_at": base + timedelta(milliseconds=10)},
                {
                    "event_type": "dual_read.started",
                    "created_at": base + timedelta(milliseconds=200),
                    "summary": "Dual-read started · crop=cocina · planilla_m2=6.5",
                    "payload": {"crop_label": "cocina", "planilla_m2": 6.5},
                },
                {
                    "event_type": "quote_breakdown.mutated",
                    "created_at": base + timedelta(seconds=15),
                    "payload": {
                        "path": "dual_read",
                        "mutated_keys": [
                            "dual_read_result",
                            "dual_read_plan_hash",
                            "context_analysis_pending",
                            "brief_analysis",
                        ],
                    },
                },
                {
                    "event_type": "context_analysis.pending",
                    "created_at": base + timedelta(seconds=15, milliseconds=200),
                    "summary": "Dual-read context pending",
                    "payload": {"path": "dual_read"},
                },
                {
                    "event_type": "dual_read.completed",
                    "created_at": base + timedelta(seconds=18),
                    "summary": "Dual-read completed",
                    "payload": {"path": "dual_read", "exit": "context_emitted"},
                    "elapsed_ms": 17800,
                },
            ],
        )
        r = await client.get("/api/quotes/q-dual-read/audit-log")
        assert r.status_code == 200
        data = r.json()

        event_types = [e["event_type"] for e in data["events"]]
        assert "dual_read.started" in event_types
        assert "dual_read.completed" in event_types
        # Orden ASC por created_at preservado
        assert event_types.index("dual_read.started") < event_types.index("dual_read.completed")

        # chat_duration_ms NO se computa desde dual_read.* (la lógica usa
        # agent.stream_started → último tool_result/quote.calculated). Sin
        # esos eventos seed, chat_duration_ms = None. Este test documenta
        # ese comportamiento esperado · regresión-guard.
        assert data["chat_duration_ms"] is None

    @pytest.mark.asyncio
    async def test_new_event_types_not_filtered_by_endpoint(self, client, db_session):
        """Verifica que el endpoint NO filtra los nuevos event_types por
        accidente (ej: una whitelist de event_types conocidos)."""
        base = datetime.now(timezone.utc)
        # Mix de eventos pre-existentes + nuevos
        novel_types = [
            "text_parse.started",
            "text_parse.completed",
            "context_analysis.started",
            "context_analysis.pending",
            "quote_breakdown.mutated",
            "dual_read.started",
            "dual_read.completed",
        ]
        events = [{"event_type": "quote.created", "created_at": base}] + [
            {
                "event_type": t,
                "created_at": base + timedelta(seconds=i + 1),
                "summary": f"{t} test",
            }
            for i, t in enumerate(novel_types)
        ]
        await _seed_quote_with_audit(db_session, "q-no-filter", events=events)
        r = await client.get("/api/quotes/q-no-filter/audit-log")
        assert r.status_code == 200
        data = r.json()
        returned_types = {e["event_type"] for e in data["events"]}
        for t in novel_types:
            assert t in returned_types, f"Endpoint filtró out event_type nuevo: {t}"
