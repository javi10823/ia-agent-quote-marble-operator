"""Tests para PR #402 — texto con despiece completo NO debe re-emitir
la card de Dual Read post-`[CONTEXT_CONFIRMED]`.

**Bug:** cuando el operador pega un brief con despiece textual completo
(`text_parser.parsed_pieces_to_card` → `dual_read_result.source="TEXT"`)
y después confirma contexto, el handler de `[CONTEXT_CONFIRMED]` corre
`apply_answers()` y los merges de patas/alzada sobre el dual textual,
corrompiendo los sectores. Al re-emitir el chunk, el frontend renderiza
una "card fantasma" con tramos pisados (típicamente "Regrueso 60,68 × 1"
solo, sin los sectores originales).

**Fix:** detectar `source == "TEXT"` en el handler y:
  1. Skip `apply_answers` (preserva tramos textuales).
  2. Skip merges de patas/alzada.
  3. Skip emit del chunk `dual_read_result`.
  4. Skip persistencia del assistant turn `__DUAL_READ__` (la card
     original ya está en messages del primer emit).

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


class TestTextDispieceSkipsCard:
    """Path TEXT — despiece textual cerrado, NO debe re-emitir card."""

    @pytest.mark.asyncio
    async def test_text_source_skips_dual_read_chunk(self, db_session):
        """`source="TEXT"` + `[CONTEXT_CONFIRMED]` → NO emit chunk
        `dual_read_result`. Solo emit `done`."""
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
        assert "dual_read_result" not in chunk_types, (
            f"Regresión: TEXT no debe re-emitir dual_read_result. "
            f"Chunks emitidos: {chunk_types}"
        )
        assert "done" in chunk_types, f"Falta el emit done. Chunks: {chunks}"

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

    @pytest.mark.asyncio
    async def test_text_source_does_not_persist_extra_dual_read_assistant(self, db_session):
        """En TEXT NO debe agregarse un assistant turn `__DUAL_READ__`
        nuevo — la card original ya está en messages del primer emit."""
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
        assert assistant_dual_post == 1, (
            f"Regresión: TEXT no debe agregar un assistant __DUAL_READ__ extra. "
            f"Antes: {assistant_dual_pre}, después: {assistant_dual_post}"
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
