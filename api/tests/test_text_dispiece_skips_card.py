"""Tests para PR #402 + #404 — texto con despiece completo no debe
mutar tramos en `[CONTEXT_CONFIRMED]`, pero SÍ debe re-emitir el
chunk para que el frontend tenga el trigger de transición.

**Historia:**

PR #402 detectó que cuando el dual_read viene de texto
(`text_parser.parsed_pieces_to_card` → `dual_read_result.source="TEXT"`)
y el operador confirmaba contexto, el handler de `[CONTEXT_CONFIRMED]`
corría `apply_answers()` + los merges de patas/alzada sobre el dual
textual, corrompiendo los sectores. La card del frontend mostraba
"Regrueso 60,68 × 1" sola, sin los sectores originales.

PR #402 fixeó eso pero **fue demasiado agresivo**: además de skipear
apply_answers/merges, skipeaba también el emit del chunk. Eso
rompía un contrato implícito con el frontend — ese chunk no es solo
"render la card", es el trigger de la transición de fase
("ahora estás en estado: confirmar despiece"). Sin re-emit, el
operador queda en una UI muerta sin botón "Confirmar despiece"
activo (logs reales de Railway 28/04/2026 mostraron 7+ minutos de
polling sin avance tras `[CONTEXT_CONFIRMED]` en TEXT).

**PR #404** restaura el emit del chunk, manteniendo el resto del
fix de #402:
  1. Skip `apply_answers` (preserva tramos textuales). [#402]
  2. Skip merges de patas/alzada. [#402]
  3. Re-emit del chunk `dual_read_result` con sectores intactos. [#404]
  4. Persistir assistant turn `__DUAL_READ__` igual que en interactivo. [#404]

**Lo que NO toca este PR:**
  - El cálculo (calculator.py).
  - El path Dual Read interactivo (source != "TEXT") — comportamiento
    intacto.
  - `verified_context_analysis` se sigue persistiendo igual.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select, update as sql_update

from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _build_completed_dual(source: str) -> dict:
    """Dual read 'cerrado' — un sector con un tramo con todos los
    fields confirmed. Igual al output de parsed_pieces_to_card() o de
    una Dual Read confirmada, según el `source`."""
    return {
        "sectores": [
            {
                "id": "sector_1",
                "tipo": "cocina",
                "tramos": [
                    {
                        "id": "t1",
                        "descripcion": "Mesada",
                        "largo_m": {"opus": None, "sonnet": None, "valor": 2.30, "status": "CONFIRMADO"},
                        "ancho_m": {"opus": None, "sonnet": None, "valor": 0.60, "status": "CONFIRMADO"},
                        "m2": {"opus": None, "sonnet": None, "valor": 1.38, "status": "CONFIRMADO"},
                        "zocalos": [],
                        "frentin": [],
                        "regrueso": [],
                        "_manual": True,
                    },
                ],
                "m2_total": {"opus": None, "sonnet": None, "valor": 1.38, "status": "CONFIRMADO"},
                "ambiguedades": [],
                "_manual": True,
            },
        ],
        "requires_human_review": False,
        "conflict_fields": [],
        "source": source,
        "view_type": "texto" if source == "TEXT" else "plano",
        "view_type_reason": "test fixture",
        "m2_warning": None,
        "_retry": True,
    }


async def _create_quote_with_dual(db_session, source: str) -> str:
    """Crea un quote con un dual_read_result cerrado del `source` dado.
    El quote ya tiene el primer emit de la card (en messages) y un
    `context_analysis_pending` del paso anterior."""
    qid = f"test-text-dispiece-{uuid.uuid4()}"
    quote = Quote(
        id=qid,
        client_name="Cliente Texto",
        project="Cocina",
        material="Silestone Blanco Norte",
        localidad="Rosario",
        messages=[
            # Mensaje user con el brief.
            {"role": "user", "content": [{"type": "text", "text": "cocina 2.30 × 0.60"}]},
            # Mensaje assistant con la card original (primer emit).
            {
                "role": "assistant",
                "content": f"__DUAL_READ__{json.dumps(_build_completed_dual(source))}",
            },
            # Mensaje assistant con la card de contexto.
            {
                "role": "assistant",
                "content": '__CONTEXT_ANALYSIS__{"data_known":[],"assumptions":[],"pending_questions":[]}',
            },
        ],
        status=QuoteStatus.DRAFT,
    )
    db_session.add(quote)
    await db_session.commit()

    breakdown = {
        "dual_read_result": _build_completed_dual(source),
        # context_analysis_pending: gate del flow normal — el handler
        # de `[CONTEXT_CONFIRMED]` lo lee al cargar `_bd_ctx`.
        "context_analysis_pending": {
            "data_known": [],
            "assumptions": [],
            "pending_questions": [],
        },
    }
    await db_session.execute(
        sql_update(Quote).where(Quote.id == qid).values(quote_breakdown=breakdown)
    )
    await db_session.commit()
    return qid


# ─────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────


class TestTextDispiecePreservesSectors:
    """Path TEXT — apply_answers no debe correr; sectores intactos.
    Esta era la razón original del fix de #402 y sigue siendo crítica."""

    @pytest.mark.asyncio
    async def test_text_source_preserves_dual_read_in_db(self, db_session):
        """`source="TEXT"` debe preservar el dual_read_result en DB
        sin mutar los sectores. apply_answers no debe correr."""
        qid = await _create_quote_with_dual(db_session, source="TEXT")
        original_dual = _build_completed_dual("TEXT")

        agent = AgentService()
        async for _ in agent.stream_chat(
            quote_id=qid,
            messages=[],
            # Answers no triviales — si apply_answers corriera,
            # mutaría el dual.
            user_message='[CONTEXT_CONFIRMED]{"answers":[{"id":"regrueso","value":"5"}]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            pass

        # Re-leer el quote: el dual_read_result debe estar igual.
        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        quote = result.scalar_one()
        persisted_dual = quote.quote_breakdown.get("dual_read_result")

        # Sectores preservados (apply_answers NO corrió).
        assert persisted_dual["sectores"] == original_dual["sectores"], (
            "Regresión: apply_answers corrió sobre TEXT y mutó los sectores. "
            f"Esperaba {original_dual['sectores']}, "
            f"encontré {persisted_dual['sectores']}"
        )
        # source preservado.
        assert persisted_dual["source"] == "TEXT"

    @pytest.mark.asyncio
    async def test_text_source_persists_context_confirmed_user_turn(self, db_session):
        """El user turn `[CONTEXT_CONFIRMED]<json>` se persiste en
        messages para que el frontend lo renderice como pill verde."""
        qid = await _create_quote_with_dual(db_session, source="TEXT")

        agent = AgentService()
        async for _ in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message='[CONTEXT_CONFIRMED]{"answers":[]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            pass

        await db_session.commit()
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        quote = result.scalar_one()
        msg_texts = [
            m["content"][0]["text"] if isinstance(m.get("content"), list) else m.get("content")
            for m in (quote.messages or [])
        ]
        # Debe haber al menos un msg con `[CONTEXT_CONFIRMED]`.
        assert any(
            isinstance(t, str) and t.startswith("[CONTEXT_CONFIRMED]")
            for t in msg_texts
        ), f"Falta persistencia del user turn `[CONTEXT_CONFIRMED]`. Msgs: {msg_texts}"


class TestTextDispieceReemitsChunk:
    """PR #404 — el chunk `dual_read_result` SÍ se re-emite para que
    el frontend tenga el trigger de transición. Antes (#402) skipeaba
    el emit y dejaba el operador con UI muerta sin botón "Confirmar
    despiece" activo."""

    @pytest.mark.asyncio
    async def test_text_source_emits_dual_read_chunk(self, db_session):
        """`source="TEXT"` + `[CONTEXT_CONFIRMED]` → DEBE emitir el
        chunk `dual_read_result`. Es el trigger que el frontend usa
        para mostrar el botón "Confirmar despiece" activo y permitir
        avanzar al `[DUAL_READ_CONFIRMED]`."""
        qid = await _create_quote_with_dual(db_session, source="TEXT")

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message='[CONTEXT_CONFIRMED]{"answers":[]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            chunks.append(chunk)

        chunk_types = [c.get("type") for c in chunks]
        assert "dual_read_result" in chunk_types, (
            f"PR #404 regresión: TEXT debe re-emitir dual_read_result "
            f"para que el frontend pueda transicionar a 'confirmar "
            f"despiece'. Chunks emitidos: {chunk_types}"
        )
        assert "done" in chunk_types

    @pytest.mark.asyncio
    async def test_text_source_emit_preserves_original_sectors(self, db_session):
        """El chunk emitido debe llevar los sectores originales del
        texto, NO los pisados por merges. Esto une la garantía de
        #402 (no mutar) con el re-emit de #404 — la card que el
        operador ve post-confirmar-contexto = la card que vio al
        pegar el brief."""
        qid = await _create_quote_with_dual(db_session, source="TEXT")
        original_dual = _build_completed_dual("TEXT")

        agent = AgentService()
        emitted_chunk = None
        async for chunk in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message='[CONTEXT_CONFIRMED]{"answers":[{"id":"regrueso","value":"5"}]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            if chunk.get("type") == "dual_read_result":
                emitted_chunk = chunk

        assert emitted_chunk is not None, "Falta el chunk dual_read_result"
        emitted_dual = json.loads(emitted_chunk["content"])
        assert emitted_dual["sectores"] == original_dual["sectores"], (
            "Regresión PR #402: el chunk emitido tiene sectores mutados. "
            f"Esperaba {original_dual['sectores']}, "
            f"encontré {emitted_dual['sectores']}"
        )

    @pytest.mark.asyncio
    async def test_text_source_persists_assistant_dual_read(self, db_session):
        """PR #404: persistir el assistant turn `__DUAL_READ__` en
        messages igual que el path interactivo. Sin esto, al
        recargar el quote el frontend pierde la card."""
        qid = await _create_quote_with_dual(db_session, source="TEXT")

        # Snapshot inicial: 1 user + 1 assistant DUAL_READ + 1 assistant CONTEXT_ANALYSIS.
        result_pre = await db_session.execute(select(Quote).where(Quote.id == qid))
        msgs_pre = result_pre.scalar_one().messages or []
        assistant_dual_pre = sum(
            1 for m in msgs_pre
            if m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("__DUAL_READ__")
        )
        assert assistant_dual_pre == 1  # baseline

        agent = AgentService()
        async for _ in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message='[CONTEXT_CONFIRMED]{"answers":[]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            pass

        await db_session.commit()
        result_post = await db_session.execute(select(Quote).where(Quote.id == qid))
        msgs_post = result_post.scalar_one().messages or []
        assistant_dual_post = sum(
            1 for m in msgs_post
            if m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("__DUAL_READ__")
        )
        # Debe haber 2 ahora: la original (primer emit) + la del context-confirmed.
        assert assistant_dual_post == 2, (
            f"PR #404: TEXT debe persistir el assistant __DUAL_READ__ "
            f"post-context-confirm igual que el path interactivo. "
            f"Antes: {assistant_dual_pre}, después: {assistant_dual_post} "
            f"(esperaba 2)"
        )


class TestInteractiveDualReadStillEmits:
    """Path interactivo — el comportamiento del Dual Read del plano
    no se toca. Regresión guard."""

    @pytest.mark.asyncio
    async def test_non_text_source_emits_dual_read_chunk(self, db_session):
        """`source != "TEXT"` (Dual Read del plano) → DEBE emitir
        chunk `dual_read_result` como hoy."""
        qid = await _create_quote_with_dual(db_session, source="OPUS")

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message='[CONTEXT_CONFIRMED]{"answers":[]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            chunks.append(chunk)

        chunk_types = [c.get("type") for c in chunks]
        assert "dual_read_result" in chunk_types, (
            f"Regresión: Dual Read interactivo (source!=TEXT) debe seguir "
            f"emitiendo chunk dual_read_result. Chunks: {chunk_types}"
        )

    @pytest.mark.asyncio
    async def test_no_source_emits_dual_read_chunk(self, db_session):
        """Quote sin `source` definido (legacy / plano antiguo) →
        comportamiento default = emit (no skip)."""
        qid = f"test-no-source-{uuid.uuid4()}"
        quote = Quote(
            id=qid,
            client_name="Test Legacy",
            project="Cocina",
            material="Silestone Blanco Norte",
            localidad="Rosario",
            messages=[],
            status=QuoteStatus.DRAFT,
        )
        db_session.add(quote)
        await db_session.commit()
        # dual sin `source` field.
        dual_no_source = _build_completed_dual("OPUS")
        dual_no_source.pop("source")
        await db_session.execute(
            sql_update(Quote).where(Quote.id == qid).values(
                quote_breakdown={"dual_read_result": dual_no_source}
            )
        )
        await db_session.commit()

        agent = AgentService()
        chunks = []
        async for chunk in agent.stream_chat(
            quote_id=qid,
            messages=[],
            user_message='[CONTEXT_CONFIRMED]{"answers":[]}',
            plan_bytes=None,
            plan_filename=None,
            db=db_session,
        ):
            chunks.append(chunk)

        chunk_types = [c.get("type") for c in chunks]
        assert "dual_read_result" in chunk_types, (
            f"Regresión: dual sin `source` (legacy) debe emitir chunk. "
            f"Chunks: {chunk_types}"
        )
