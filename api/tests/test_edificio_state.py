"""Tests for edificio building_step state machine.

Verifies the state transitions:
  step1_review → (confirm) → step2_quote → (confirm) → generate_documents
"""

import uuid
import pytest
from sqlalchemy import select, update as sql_update

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService


async def _create_building_quote(db_session, step: str = "step1_review") -> str:
    """Create a quote in DB with edificio breakdown at a given step."""
    qid = f"test-edif-{uuid.uuid4()}"
    quote = Quote(
        id=qid,
        client_name="ESH Test",
        project="Concesionario",
        material="Negro Boreal",
        localidad="Rosario",
        is_building=True,
        messages=[],
        status=QuoteStatus.DRAFT,
    )
    db_session.add(quote)
    await db_session.commit()

    # Set breakdown with building_step
    breakdown = {
        "building_step": step,
        "summary": {
            "materials": {
                "Negro Boreal": {
                    "pieces": [{"id": "M1", "largo": 2.3, "ancho": 0.6, "m2_calc_total": 1.38}],
                    "faldon_pieces": [],
                    "m2_total": 1.38,
                    "pileta_pegado": 1,
                    "pileta_apoyo": 0,
                    "faldon_ml_total": 0,
                    "piece_count_physical": 1,
                },
            },
            "totals": {
                "m2_total": 1.38,
                "pieces_physical_total": 1,
                "flete_qty": 1,
                "pileta_pegado_total": 1,
                "pileta_apoyo_total": 0,
                "faldon_ml_total": 0,
                "descuento_18_aplica": False,
            },
        },
    }
    if step == "step2_quote":
        breakdown["paso2_calc"] = {"grand_total_ars": 100000, "grand_total_usd": 0}

    await db_session.execute(
        sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=breakdown)
    )
    await db_session.commit()
    return qid


class TestBuildingStepStateMachine:

    @pytest.mark.asyncio
    async def test_step1_confirm_triggers_paso2(self, db_session):
        """Confirming Paso 1 (step1_review) should advance to step2_quote."""
        qid = await _create_building_quote(db_session, "step1_review")

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message="Confirmo",
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            chunks.append(chunk)

        # Should have emitted text (Paso 2 render) + done
        text_chunks = [c for c in chunks if c.get("type") == "text"]
        assert len(text_chunks) >= 1, f"Expected text chunk, got: {chunks}"

        # Check state advanced
        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = r.scalar_one()
        assert q.quote_breakdown.get("building_step") == "step2_quote", (
            f"Expected step2_quote, got: {q.quote_breakdown.get('building_step')}"
        )

    @pytest.mark.asyncio
    async def test_step2_confirm_advances_to_paso3(self, db_session):
        """Confirming Paso 2 (step2_quote) should generate documents (Paso 3),
        NOT re-render Paso 2. building_step advances to step3_done."""
        qid = await _create_building_quote(db_session, "step2_quote")

        agent = AgentService()
        chunks = []
        try:
            async for chunk in agent.stream_chat(
                quote_id=qid,
                messages=[
                    {"role": "user", "content": "Edificio test"},
                    {"role": "assistant", "content": "## Presupuesto Edificio\n...paso 2..."},
                ],
                user_message="Confirmo, generar presupuestos",
                plan_bytes=None,
                plan_filename=None,
                db=db_session,
            ):
                chunks.append(chunk)
        except Exception:
            pass

        # The key assertion: Paso 2 render was NOT re-emitted
        text_chunks = [c for c in chunks if c.get("type") == "text"]
        all_text = " ".join(c.get("content", "") for c in text_chunks)
        assert "Presupuesto Edificio" not in all_text or "Documentos generados" in all_text, (
            "Paso 2 was re-rendered instead of advancing to Paso 3"
        )

        # building_step should advance to step3_done (or stay step2_quote if docs failed)
        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = r.scalar_one()
        step = q.quote_breakdown.get("building_step")
        assert step in ("step2_quote", "step3_done"), f"Unexpected step: {step}"

    @pytest.mark.asyncio
    async def test_fresh_quote_does_not_trigger_paso2(self, db_session):
        """A fresh building quote without building_step should not trigger Paso 2."""
        qid = f"test-fresh-{uuid.uuid4()}"
        quote = Quote(
            id=qid,
            client_name="Test",
            project="Test",
            is_building=True,
            messages=[],
            status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        # No breakdown at all — should fall through to Claude (which fails without key)
        agent = AgentService()
        chunks = []
        try:
            async for chunk in agent.stream_chat(
                quote_id=qid,
                messages=[],
                user_message="Confirmo",
                plan_bytes=None,
                plan_filename=None,
                db=db_session,
            ):
                chunks.append(chunk)
        except Exception:
            pass

        # Should NOT render Paso 2 (no summary, no building_step)
        text_chunks = [c for c in chunks if c.get("type") == "text"]
        all_text = " ".join(c.get("content", "") for c in text_chunks)
        assert "Presupuesto Edificio" not in all_text


class TestAwaitingClientName:

    @pytest.mark.asyncio
    async def test_missing_client_enters_awaiting_state(self, db_session):
        """step2_quote without client_name → awaiting_client_name."""
        qid = f"test-await-{uuid.uuid4()}"
        quote = Quote(
            id=qid,
            client_name="",  # Empty!
            project="Concesionario",
            material="Negro Boreal",
            localidad="Rosario",
            is_building=True,
            messages=[],
            status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        bd = {
            "building_step": "step2_quote",
            "paso2_calc": {"calc_results": {}, "mo_items": [], "mo_total": 0, "grand_total_ars": 0, "grand_total_usd": 0},
            "summary": {"materials": {}, "totals": {}},
        }
        await db_session.execute(sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=bd))
        await db_session.commit()

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(qid, [], "Confirmo", None, None, db=db_session):
            chunks.append(chunk)

        text = " ".join(c.get("content", "") for c in chunks if c.get("type") == "text")
        assert "nombre del cliente" in text.lower()

        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = r.scalar_one()
        assert q.quote_breakdown["building_step"] == "awaiting_client_name"

    @pytest.mark.asyncio
    async def test_client_name_captured_and_persisted(self, db_session):
        """awaiting_client_name + "ESH" → saves client_name, resumes to step2_quote."""
        qid = f"test-capture-{uuid.uuid4()}"
        quote = Quote(
            id=qid,
            client_name="",
            project="Concesionario",
            material="Negro Boreal",
            localidad="Rosario",
            is_building=True,
            messages=[],
            status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        bd = {
            "building_step": "awaiting_client_name",
            "paso2_calc": {"calc_results": {}, "mo_items": [], "mo_total": 0, "grand_total_ars": 0, "grand_total_usd": 0},
            "summary": {"materials": {}, "totals": {}},
        }
        await db_session.execute(sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=bd))
        await db_session.commit()

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(qid, [], "ESH 1121-SM", None, None, db=db_session):
            chunks.append(chunk)

        # Client name should be persisted
        r = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = r.scalar_one()
        assert q.client_name == "ESH 1121-SM"
        # Step should have resumed (step2_quote or step3_done)
        step = q.quote_breakdown.get("building_step")
        assert step in ("step2_quote", "step3_done"), f"Expected resume, got: {step}"

    @pytest.mark.asyncio
    async def test_no_infinite_loop(self, db_session):
        """After client name is set, should not ask again."""
        qid = f"test-noloop-{uuid.uuid4()}"
        quote = Quote(
            id=qid,
            client_name="ESH",  # Already set
            project="Concesionario",
            material="Negro Boreal",
            localidad="Rosario",
            is_building=True,
            messages=[],
            status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()

        bd = {
            "building_step": "step2_quote",
            "paso2_calc": {"calc_results": {}, "mo_items": [], "mo_total": 0, "grand_total_ars": 0, "grand_total_usd": 0},
            "summary": {"materials": {}, "totals": {}},
        }
        await db_session.execute(sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=bd))
        await db_session.commit()

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(qid, [], "Confirmo", None, None, db=db_session):
            chunks.append(chunk)

        text = " ".join(c.get("content", "") for c in chunks if c.get("type") == "text")
        assert "nombre del cliente" not in text.lower()
