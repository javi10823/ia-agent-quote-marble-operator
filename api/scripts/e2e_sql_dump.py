"""Dump literal de queries SQL pedidas por el operador en los 6 tests E2E.

Corre contra Postgres con el schema aplicado. Inserta data sintética que
simula los flows pedidos y dumpea el output. Lo que sale acá es lo que
el operador puede ejecutar en staging después de un flow real con LLM.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


async def main():
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Importar el helper sin cargar el agent module pesado.
    from app.modules.observability import log_event

    class _State:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class _Req:
        def __init__(self, user_email):
            self.state = _State(
                user_email=user_email,
                request_id=str(uuid.uuid4()),
                session_id=None,
            )

    qid_happy = f"e2e-sqldump-happy-{uuid.uuid4().hex[:8]}"
    qid_err = f"e2e-sqldump-err-{uuid.uuid4().hex[:8]}"
    qid_pii = f"e2e-sqldump-pii-{uuid.uuid4().hex[:8]}"

    async with factory() as db:
        # --- Test #1: happy path ---
        r = _Req("javi")
        await log_event(db, event_type="quote.created", source="router",
                        summary="Quote created", request=r, quote_id=qid_happy,
                        payload={"status": "draft"})
        await log_event(db, event_type="chat.message_sent", source="router",
                        summary="Chat with brief 5-7 mesadas",
                        request=r, quote_id=qid_happy, turn_index=0,
                        payload={"message_chars": 412, "plan_files_count": 1})
        await log_event(db, event_type="agent.stream_started", source="agent",
                        summary="Agent stream started",
                        request=r, quote_id=qid_happy, turn_index=0,
                        payload={"prior_msgs": 0, "msg_chars": 412, "has_plan": True})
        for tool in ["catalog_lookup", "read_plan", "calculate_quote", "generate_documents"]:
            await log_event(db, event_type="agent.tool_called", source="agent",
                            summary=f"Tool: {tool}", request=r, quote_id=qid_happy,
                            payload={"tool": tool})
            await log_event(db, event_type="agent.tool_result", source="agent",
                            summary=f"Tool: {tool} ok", request=r, quote_id=qid_happy,
                            payload={"tool": tool}, success=True, elapsed_ms=120)
        await log_event(db, event_type="quote.calculated", source="calculator",
                        summary="Quote calculated SILESTONE BLANCO NORTE | ARS None→480000",
                        request=r, quote_id=qid_happy,
                        payload={
                            "material": "SILESTONE BLANCO NORTE",
                            "total_ars_after": 480000, "total_usd_after": 1200,
                            "validation_ok": True, "is_edificio": False,
                        })
        await log_event(db, event_type="docs.generated", source="docs",
                        summary="Documents generated (ok)",
                        request=r, quote_id=qid_happy,
                        payload={
                            "material": "SILESTONE BLANCO NORTE",
                            "pdf_url": "/files/abc.pdf",
                            "excel_url": "/files/abc.xlsx",
                            "drive_pdf_url": "https://drive.google.com/file/d/abc/view",
                            "drive_excel_url": "https://drive.google.com/file/d/xyz/view",
                            "drive_file_id": "abc",
                            "local_gen_ok": True, "drive_ok": True,
                        })

        # --- Test #2: patch_mo + regenerate ---
        await log_event(db, event_type="agent.tool_called", source="agent",
                        summary="Tool: patch_quote_mo (sacá el flete)",
                        request=r, quote_id=qid_happy,
                        payload={"tool": "patch_quote_mo"})
        await log_event(db, event_type="agent.tool_result", source="agent",
                        summary="Tool: patch_quote_mo ok",
                        request=r, quote_id=qid_happy,
                        payload={"tool": "patch_quote_mo"}, success=True, elapsed_ms=45)
        await log_event(db, event_type="quote.patched_mo", source="agent",
                        summary="MO patched (removed=['flete...'])",
                        request=r, quote_id=qid_happy,
                        payload={"removed": ["Flete + toma medidas Rosario"],
                                 "total_ars_after": 428000})
        await log_event(db, event_type="docs.regenerated", source="router",
                        summary="PDF + Excel regenerated",
                        request=r, quote_id=qid_happy,
                        payload={
                            "pdf_url_after": "/files/abc-v2.pdf",
                            "drive_pdf_url": "https://drive.google.com/file/d/abc2/view",
                            "drive_excel_url": "https://drive.google.com/file/d/xyz2/view",
                            "drive_file_id": "abc2", "drive_ok": True,
                        })

        # --- Test #3: error path ---
        await log_event(db, event_type="quote.created", source="router",
                        summary="Quote created", request=r, quote_id=qid_err)
        await log_event(db, event_type="agent.stream_started", source="agent",
                        summary="Agent stream started", request=r, quote_id=qid_err)
        await log_event(db, event_type="agent.tool_called", source="agent",
                        summary="Tool: calculate_quote", request=r, quote_id=qid_err,
                        payload={"tool": "calculate_quote"})
        await log_event(db, event_type="agent.tool_result", source="agent",
                        summary="Tool calculate_quote FAILED",
                        request=r, quote_id=qid_err,
                        payload={"tool": "calculate_quote"},
                        success=False,
                        error_message="Material 'INEXISTENTE-XYZ' not found in catalog",
                        elapsed_ms=95)
        # NO emitimos quote.calculated ni docs.generated → se rompió el flow.

        # --- Test #6: PII ---
        await log_event(db, event_type="quote.created", source="router",
                        summary="Quote with PII fields",
                        request=r, quote_id=qid_pii,
                        payload={
                            "client_name": "Juan Pérez",
                            "client_phone": "+54 9 341 1234567",
                            "client_email": "juan@example.com",
                            "billing_address": "Av. Pellegrini 1234, Rosario",
                            "telefono": "0341-456-7890",
                        })

        await db.commit()

        print("=" * 70)
        print("TEST E2E #1 — Happy path completo")
        print(f"  quote_id = {qid_happy}")
        print("=" * 70)
        print("SQL: SELECT event_type, actor, success, created_at FROM audit_events")
        print(f"     WHERE quote_id = '{qid_happy}' ORDER BY created_at ASC;")
        print()
        r1 = await db.execute(text(
            "SELECT event_type, actor, success, created_at "
            "FROM audit_events WHERE quote_id = :q ORDER BY created_at ASC"
        ), {"q": qid_happy})
        for row in r1:
            print(f"  {row.event_type:25} {row.actor:10} success={row.success}  {row.created_at.isoformat()}")

        print()
        print("=" * 70)
        print("TEST E2E #3 — Error path")
        print(f"  quote_id = {qid_err}")
        print("=" * 70)
        r3 = await db.execute(text(
            "SELECT event_type, actor, success, error_message FROM audit_events "
            "WHERE quote_id = :q ORDER BY created_at ASC"
        ), {"q": qid_err})
        for row in r3:
            err = row.error_message or "—"
            print(f"  {row.event_type:25} success={row.success}  err={err[:60]}")

        print()
        print("=" * 70)
        print("TEST E2E #4 — Drive consolidation in payload")
        print("=" * 70)
        r4 = await db.execute(text(
            "SELECT payload FROM audit_events "
            "WHERE event_type IN ('docs.generated', 'docs.regenerated') "
            "AND quote_id = :q"
        ), {"q": qid_happy})
        for row in r4:
            p = row.payload
            print(f"  drive_pdf_url    = {p.get('drive_pdf_url')}")
            print(f"  drive_excel_url  = {p.get('drive_excel_url')}")
            print(f"  drive_file_id    = {p.get('drive_file_id')}")
            print(f"  drive_ok         = {p.get('drive_ok')}")
            print()

        print("=" * 70)
        print("TEST E2E #5 — Actor distribution (no all-system, no all-api-key)")
        print("=" * 70)
        r5 = await db.execute(text(
            "SELECT event_type, actor, COUNT(*) AS c "
            "FROM audit_events WHERE quote_id LIKE 'e2e-sqldump-%' "
            "GROUP BY event_type, actor ORDER BY event_type, actor"
        ))
        for row in r5:
            print(f"  {row.event_type:25} {row.actor:10} count={row.c}")

        print()
        print("=" * 70)
        print("TEST E2E #6 — PII redaction check")
        print("=" * 70)
        for needle, label in [("341", "phone fragment"),
                              ("example.com", "email"),
                              ("Pellegrini", "address")]:
            r6 = await db.execute(text(
                "SELECT COUNT(*) FROM audit_events WHERE quote_id = :q "
                "AND payload::text LIKE :pat"
            ), {"q": qid_pii, "pat": f"%{needle}%"})
            count = r6.scalar()
            verdict = "❌ LEAK" if count > 0 else "✓ clean"
            print(f"  {label:20} pattern='{needle}'  rows={count}  {verdict}")

        # Mostrar el payload literal del PII test para confirmar
        # que `<redacted>` está en lugar de los valores reales.
        print()
        print("PII payload literal (verificá que aparezca '<redacted>'):")
        rp = await db.execute(text(
            "SELECT payload::text FROM audit_events WHERE quote_id = :q"
        ), {"q": qid_pii})
        print(f"  {rp.scalar()}")

        # Cleanup
        await db.execute(text(
            "DELETE FROM audit_events WHERE quote_id LIKE 'e2e-sqldump-%'"
        ))
        await db.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
