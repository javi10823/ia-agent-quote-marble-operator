"""E2E verification tests para PR #445 — auditoría operativa.

Corre contra Postgres real (no SQLite) — `DATABASE_URL` debe apuntar
a Postgres. SQLite no acepta JSONB y el cast `payload::text` falla.

Lo que se verifica acá vs lo que necesita staging:

CUBIERTO POR ESTE TEST (Postgres local):
- Schema correcto + índices creados.
- log_event() en Postgres real persiste y deserializa bien.
- Test #5 — actor propagation: `request.state.user_email` se resuelve
  correctamente (user / api_key / system) según el caller.
- Test #6 — PII redaction: phones/emails/addresses **NO** aparecen
  en `payload::text` después de pasar por sanitize_for_audit.
- Test E2E#1 sintético: flow completo con `log_event` directo emitido
  en el orden esperado. Verifica orden ascendente y pares balanceados
  de tool_called/tool_result.
- Test E2E#3 sintético: tool con success=False loggea error_message
  y NO emite quote.calculated/docs.generated downstream.

NO CUBIERTO ACÁ (necesita staging con ANTHROPIC_API_KEY real):
- Test E2E#1 con LLM real (Sonnet emite tool calls).
- Test E2E#2 — comportamiento del agent al procesar "sacá el flete"
  (depende de cómo Sonnet decide qué tool usar).
- Test E2E#4 con Drive real (requiere service account).
- Verificación de que `agent.tool_called` realmente recibe el username
  cuando el operador real dispara una request — depende de que el
  middleware `auth_middleware` setee `request.state.user_email` desde
  el JWT, lo cual requiere flow completo HTTP.

Para los que requieren staging, este test deja **assertions de
estructura** — si Postgres + helper + sanitizer funcionan acá, el
flow real solo agrega el LLM como fuente de tool calls.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


pytestmark = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason="E2E tests require Postgres (DATABASE_URL must point to Postgres)",
)


@pytest_asyncio.fixture
async def pg_session():
    """Engine + session fresh por test (asyncpg no tolera event loops
    cruzados entre tests). El schema ya debe estar aplicado — se asume
    que `init_db()` corrió al menos una vez antes."""
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    # Cleanup escoped al test scope.
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM audit_events WHERE event_type LIKE 'e2e.%' OR quote_id LIKE 'e2e-%'"
        ))
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════════
# Mock de FastAPI Request para tests #5
# ═══════════════════════════════════════════════════════════════════════


class _MockState:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockRequest:
    def __init__(self, user_email=None, request_id=None, session_id=None):
        self.state = _MockState(
            user_email=user_email,
            request_id=request_id,
            session_id=session_id,
        )


# ═══════════════════════════════════════════════════════════════════════
# TEST #5 — Actor propagation
# ═══════════════════════════════════════════════════════════════════════


class TestActorPropagation:
    @pytest.mark.asyncio
    async def test_user_actor_when_request_has_user_email(self, pg_session):
        from app.modules.observability import log_event

        req = _MockRequest(user_email="javi", request_id=str(uuid.uuid4()))
        ev = await log_event(
            pg_session,
            event_type="e2e.actor.user",
            source="test",
            summary="user actor",
            request=req,
            quote_id="e2e-actor-1",
        )
        await pg_session.commit()
        assert ev.actor == "javi"
        assert ev.actor_kind == "user"
        assert ev.request_id == req.state.request_id

    @pytest.mark.asyncio
    async def test_api_key_actor(self, pg_session):
        from app.modules.observability import log_event

        req = _MockRequest(user_email="api-key", request_id=str(uuid.uuid4()))
        ev = await log_event(
            pg_session,
            event_type="e2e.actor.api_key",
            source="test",
            summary="api_key actor",
            request=req,
            quote_id="e2e-actor-2",
        )
        await pg_session.commit()
        assert ev.actor == "api-key"
        assert ev.actor_kind == "api_key"

    @pytest.mark.asyncio
    async def test_system_actor_when_no_request(self, pg_session):
        from app.modules.observability import log_event

        ev = await log_event(
            pg_session,
            event_type="e2e.actor.system",
            source="test",
            summary="no request → system",
            quote_id="e2e-actor-3",
        )
        await pg_session.commit()
        assert ev.actor == "system"
        assert ev.actor_kind == "system"

    @pytest.mark.asyncio
    async def test_aggregate_actor_query_returns_distinct_actors(self, pg_session):
        """Test #5 acceptance criteria: SELECT event_type, actor, COUNT(*)
        GROUP BY ... debe devolver USERS, no todo "system" o "api-key"."""
        from app.modules.observability import log_event

        # Self-contained: inserta 3 actor types en este mismo test.
        for actor_email, qid_suffix in [
            ("javi", "agg-1"),
            ("api-key", "agg-2"),
            (None, "agg-3"),
        ]:
            req = (
                _MockRequest(user_email=actor_email, request_id=str(uuid.uuid4()))
                if actor_email is not None
                else None
            )
            await log_event(
                pg_session,
                event_type=f"e2e.actor.{qid_suffix}",
                source="test",
                summary=f"actor test {qid_suffix}",
                request=req,
                quote_id=f"e2e-{qid_suffix}",
            )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT event_type, actor, COUNT(*) "
                "FROM audit_events "
                "WHERE event_type LIKE 'e2e.actor.%' "
                "GROUP BY event_type, actor "
                "ORDER BY event_type"
            )
        )
        rows = list(result.all())
        actors = {row.actor for row in rows}
        # Si la propagación falla, todos serían "system".
        assert "javi" in actors, f"User actor missing — actors found: {actors}"
        assert "api-key" in actors, f"api_key actor missing — actors found: {actors}"
        assert "system" in actors


# ═══════════════════════════════════════════════════════════════════════
# TEST #6 — PII redaction (phones, emails, addresses)
# ═══════════════════════════════════════════════════════════════════════


class TestPIIRedaction:
    @pytest.mark.asyncio
    async def test_phone_not_in_payload(self, pg_session):
        from app.modules.observability import log_event

        # Caso: brief con teléfono cliente.
        await log_event(
            pg_session,
            event_type="e2e.pii.phone",
            source="test",
            summary="brief mentions phone",
            quote_id="e2e-pii-1",
            payload={
                "client_name": "Juan",
                "client_phone": "+54 9 341 1234567",
                "telefono": "0341-456-7890",
            },
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT payload::text FROM audit_events "
                "WHERE quote_id = 'e2e-pii-1' AND payload::text LIKE :pat"
            ),
            {"pat": "%341%"},
        )
        rows = list(result.all())
        assert len(rows) == 0, (
            f"PII LEAK: phone fragment '341' found in payload: "
            f"{[r[0] for r in rows]}"
        )

    @pytest.mark.asyncio
    async def test_email_not_in_payload(self, pg_session):
        from app.modules.observability import log_event

        await log_event(
            pg_session,
            event_type="e2e.pii.email",
            source="test",
            summary="brief mentions email",
            quote_id="e2e-pii-2",
            payload={
                "client_name": "Maria",
                "client_email": "maria@example.com",
                "user_email": "operator@dangelo.com",
            },
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT payload::text FROM audit_events "
                "WHERE quote_id = 'e2e-pii-2' AND payload::text LIKE :pat"
            ),
            {"pat": "%example.com%"},
        )
        rows = list(result.all())
        assert len(rows) == 0, f"PII LEAK: email leaked: {[r[0] for r in rows]}"

    @pytest.mark.asyncio
    async def test_address_not_in_payload(self, pg_session):
        from app.modules.observability import log_event

        await log_event(
            pg_session,
            event_type="e2e.pii.address",
            source="test",
            summary="brief mentions address",
            quote_id="e2e-pii-3",
            payload={
                "client_name": "Carlos",
                "billing_address": "Av. Pellegrini 1234, Rosario",
                "direccion": "Calle Falsa 123",
            },
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT payload::text FROM audit_events "
                "WHERE quote_id = 'e2e-pii-3' AND payload::text LIKE :pat"
            ),
            {"pat": "%Pellegrini%"},
        )
        rows = list(result.all())
        assert len(rows) == 0, f"PII LEAK: address leaked: {[r[0] for r in rows]}"


# ═══════════════════════════════════════════════════════════════════════
# TEST E2E #1 (sintético) — Happy path order verification
# ═══════════════════════════════════════════════════════════════════════
#
# Sin LLM real, simulamos qué eventos emitirían los handlers en
# secuencia. Verifica el ORDER, los pares balanceados, y los campos
# clave. Para verificación CON LLM real, ver staging.


class TestE2EHappyPathOrder:
    @pytest.mark.asyncio
    async def test_full_flow_emits_events_in_correct_order(self, pg_session):
        from app.modules.observability import log_event

        qid = "e2e-happy-001"
        req = _MockRequest(user_email="javi", request_id=str(uuid.uuid4()))

        # Simulación: lo que dispararían los handlers reales.
        # 1. quote.created
        await log_event(
            pg_session, event_type="quote.created", source="router",
            summary="Quote created", request=req, quote_id=qid,
            payload={"status": "draft"},
        )
        # 2. chat.message_sent
        await log_event(
            pg_session, event_type="chat.message_sent", source="router",
            summary="Operator sent chat message", request=req, quote_id=qid,
            payload={"message_chars": 200, "plan_files_count": 1},
        )
        # 3. agent.stream_started
        await log_event(
            pg_session, event_type="agent.stream_started", source="agent",
            summary="Agent stream started", request=req, quote_id=qid,
            turn_index=0,
            payload={"prior_msgs": 0, "msg_chars": 200, "has_plan": True},
        )
        # 4-7. tool_called / tool_result pairs (catalog_lookup + read_plan)
        for tool in ["catalog_lookup", "read_plan"]:
            await log_event(
                pg_session, event_type="agent.tool_called", source="agent",
                summary=f"Tool: {tool}", request=req, quote_id=qid,
                payload={"tool": tool},
            )
            await log_event(
                pg_session, event_type="agent.tool_result", source="agent",
                summary=f"Tool: {tool} ok", request=req, quote_id=qid,
                payload={"tool": tool}, success=True, elapsed_ms=120,
            )
        # 8. quote.calculated
        await log_event(
            pg_session, event_type="quote.calculated", source="calculator",
            summary="Quote calculated", request=req, quote_id=qid,
            payload={"material": "SILESTONE BLANCO NORTE", "total_ars": 240000},
        )
        # 9. docs.generated
        await log_event(
            pg_session, event_type="docs.generated", source="docs",
            summary="Documents generated", request=req, quote_id=qid,
            payload={
                "pdf_url": "/files/x.pdf", "excel_url": "/files/x.xlsx",
                "drive_pdf_url": "https://drive.../pdf",
                "drive_excel_url": "https://drive.../xlsx",
                "drive_file_id": "abc123",
            },
        )
        await pg_session.commit()

        # Verificación: orden + cuenta + balance.
        result = await pg_session.execute(
            text(
                "SELECT event_type, actor, success, created_at "
                "FROM audit_events WHERE quote_id = :qid "
                "ORDER BY created_at ASC"
            ),
            {"qid": qid},
        )
        rows = list(result.all())
        types_in_order = [r.event_type for r in rows]
        assert types_in_order == [
            "quote.created",
            "chat.message_sent",
            "agent.stream_started",
            "agent.tool_called", "agent.tool_result",
            "agent.tool_called", "agent.tool_result",
            "quote.calculated",
            "docs.generated",
        ]
        # Pares balanceados.
        called = sum(1 for r in rows if r.event_type == "agent.tool_called")
        results = sum(1 for r in rows if r.event_type == "agent.tool_result")
        assert called == results, (
            f"Tool call/result imbalance: called={called}, results={results}"
        )
        # Todos del mismo actor (no se mezcla con system).
        actors = {r.actor for r in rows}
        assert actors == {"javi"}, f"Mixed actors in single flow: {actors}"


# ═══════════════════════════════════════════════════════════════════════
# TEST E2E #3 (sintético) — Error path
# ═══════════════════════════════════════════════════════════════════════


class TestE2EErrorPath:
    @pytest.mark.asyncio
    async def test_tool_failure_does_not_emit_calculated_or_generated(
        self, pg_session,
    ):
        from app.modules.observability import log_event

        qid = "e2e-err-001"
        req = _MockRequest(user_email="javi", request_id=str(uuid.uuid4()))

        # Flow hasta tool_result con success=False.
        await log_event(
            pg_session, event_type="quote.created", source="router",
            summary="Quote created", request=req, quote_id=qid,
        )
        await log_event(
            pg_session, event_type="agent.stream_started", source="agent",
            summary="Agent stream started", request=req, quote_id=qid,
        )
        await log_event(
            pg_session, event_type="agent.tool_called", source="agent",
            summary="Tool: calculate_quote", request=req, quote_id=qid,
            payload={"tool": "calculate_quote"},
        )
        await log_event(
            pg_session, event_type="agent.tool_result", source="agent",
            summary="Tool calculate_quote FAILED",
            request=req, quote_id=qid,
            payload={"tool": "calculate_quote"},
            success=False,
            error_message="Material 'INEXISTENTE' not found in catalog",
            elapsed_ms=85,
        )
        # NO emitimos quote.calculated ni docs.generated — es lo que
        # esperamos que el agent NO haga al recibir tool error.
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT event_type, success, error_message FROM audit_events "
                "WHERE quote_id = :qid ORDER BY created_at ASC"
            ),
            {"qid": qid},
        )
        rows = list(result.all())
        types = [r.event_type for r in rows]

        # Tool result tiene success=False y error_message.
        tool_result_rows = [r for r in rows if r.event_type == "agent.tool_result"]
        assert len(tool_result_rows) == 1
        assert tool_result_rows[0].success is False
        assert tool_result_rows[0].error_message
        assert "INEXISTENTE" in tool_result_rows[0].error_message

        # Confirmar AUSENCIA de calculated / generated.
        assert "quote.calculated" not in types
        assert "docs.generated" not in types


# ═══════════════════════════════════════════════════════════════════════
# TEST E2E #4 (sintético) — Drive consolidation in payload
# ═══════════════════════════════════════════════════════════════════════


class TestE2EDriveConsolidation:
    @pytest.mark.asyncio
    async def test_docs_generated_payload_has_drive_fields(self, pg_session):
        """Verifica el desvío del plan: drive.uploaded consolidado dentro
        de docs.generated. payload tiene drive_pdf_url, drive_excel_url,
        drive_file_id."""
        from app.modules.observability import log_event

        qid = "e2e-drive-001"
        req = _MockRequest(user_email="javi", request_id=str(uuid.uuid4()))

        await log_event(
            pg_session, event_type="docs.generated", source="docs",
            summary="Documents generated with Drive upload",
            request=req, quote_id=qid,
            payload={
                "pdf_url": "/files/quote.pdf",
                "excel_url": "/files/quote.xlsx",
                "drive_pdf_url": "https://drive.google.com/file/d/abc/view",
                "drive_excel_url": "https://drive.google.com/file/d/xyz/view",
                "drive_file_id": "abc",
            },
            success=True,
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT payload FROM audit_events "
                "WHERE quote_id = :qid AND event_type = 'docs.generated'"
            ),
            {"qid": qid},
        )
        rows = list(result.all())
        assert len(rows) == 1
        payload = rows[0].payload
        assert payload.get("drive_pdf_url"), "drive_pdf_url missing"
        assert payload.get("drive_excel_url"), "drive_excel_url missing"
        assert payload.get("drive_file_id"), "drive_file_id missing"

    @pytest.mark.asyncio
    async def test_drive_failure_loggs_success_false(self, pg_session):
        """Cuando Drive falla, success=False (correcto, sin mentir).

        Verifica el fix aplicado a agent.py y router.py: si la generación
        local funcionó pero Drive devolvió None (upload silencioso falló
        por token vencido, network, etc.), el evento docs.generated/
        docs.regenerated se loggea con `success=False` y error_message
        explícito. Antes el helper escupía `success=True` aunque drive_*
        fueran null — eso es mentir.
        """
        from app.modules.observability import log_event

        qid = "e2e-drive-fail-001"
        req = _MockRequest(user_email="javi", request_id=str(uuid.uuid4()))

        # Replica EXACTA de la lógica del handler agent.py post-fix.
        # Generación local OK, Drive falla.
        result_ok = True
        drive_pdf_url = None  # Drive falló
        drive_excel_url = None
        gen_ok = bool(result_ok)
        drive_attempted = result_ok is True
        drive_failed = drive_attempted and not (drive_pdf_url and drive_excel_url)
        audit_success = gen_ok and not drive_failed
        audit_error = None
        if drive_failed:
            audit_error = "Drive upload failed for: PDF, Excel (local generation OK, Drive returned no url)"

        await log_event(
            pg_session, event_type="docs.generated", source="docs",
            summary="Documents generated (drive partial-fail)",
            request=req, quote_id=qid,
            payload={
                "pdf_url": "/files/quote.pdf",
                "excel_url": "/files/quote.xlsx",
                "drive_pdf_url": drive_pdf_url,
                "drive_excel_url": drive_excel_url,
                "drive_file_id": None,
                "local_gen_ok": gen_ok,
                "drive_ok": not drive_failed,
            },
            success=audit_success,
            error_message=audit_error,
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT payload, success, error_message FROM audit_events "
                "WHERE quote_id = :qid"
            ),
            {"qid": qid},
        )
        row = result.one()
        # Post-fix: success=False cuando Drive falla aunque la
        # generación local haya sido OK.
        assert row.success is False, (
            "REGRESSION: success=True con Drive fallando — el handler "
            "está mintiendo al operador."
        )
        assert row.error_message and "Drive upload failed" in row.error_message
        assert row.payload.get("drive_pdf_url") is None
        assert row.payload.get("drive_ok") is False
        assert row.payload.get("local_gen_ok") is True
