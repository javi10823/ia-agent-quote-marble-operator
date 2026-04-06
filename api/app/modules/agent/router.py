from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
import uuid

logger = logging.getLogger(__name__)

# File upload constants
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5

from app.core.database import get_db
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.agent.schemas import (
    CreateQuoteRequest,
    QuoteListResponse,
    QuoteDetailResponse,
    QuoteCompareItem,
    QuoteCompareResponse,
    QuoteStatusUpdate,
    QuotePatchRequest,
)

router = APIRouter(tags=["agent"])
agent_service = AgentService()

# Valid status transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"validated", "pending"},
    "pending": {"validated", "draft"},
    "validated": {"sent", "draft"},
    "sent": {"validated"},
}


# ── AUTHENTICATED FILE SERVING ───────────────────────────────────────────────
# Separate router mounted at /files (not /api/files) to match existing URLs in DB

files_router = APIRouter(tags=["files"])

@files_router.get("/files/{file_path:path}")
async def serve_file(file_path: str):
    """Serve generated files (PDFs, Excel, sources) with auth protection."""
    from app.core.static import OUTPUT_DIR
    import mimetypes
    full_path = (OUTPUT_DIR / file_path).resolve()
    if not full_path.is_relative_to(OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    media_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
    return FileResponse(full_path, media_type=media_type)


# ── LIST QUOTES ──────────────────────────────────────────────────────────────

@router.get("/quotes", response_model=list[QuoteListResponse])
async def list_quotes(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import defer
    from sqlalchemy import or_, and_
    result = await db.execute(
        select(Quote)
        .options(defer(Quote.messages), defer(Quote.quote_breakdown), defer(Quote.source_files))
        .where(
            # Exclude empty drafts (no client_name) — only show drafts with real data
            or_(
                Quote.status != "draft",
                and_(Quote.status == "draft", Quote.client_name != "", Quote.client_name.isnot(None)),
            )
        )
        .order_by(Quote.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


# ── CHECK FOR CHANGES (lightweight polling) ─────────────────────────────────

@router.get("/quotes/check")
async def check_quotes(db: AsyncSession = Depends(get_db)):
    """Lightweight check: returns count + last update timestamp for smart polling."""
    from sqlalchemy import func, or_, and_
    result = await db.execute(
        select(
            func.count(Quote.id),
            func.max(Quote.updated_at),
        ).where(
            or_(
                Quote.status != "draft",
                and_(Quote.status == "draft", Quote.client_name != "", Quote.client_name.isnot(None)),
            )
        )
    )
    row = result.one()
    return {
        "count": row[0],
        "last_updated_at": row[1].isoformat() if row[1] else None,
    }


# ── GET QUOTE DETAIL ─────────────────────────────────────────────────────────

@router.get("/quotes/{quote_id}", response_model=QuoteDetailResponse)
async def get_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return quote


# ── COMPARE QUOTES ───────────────────────────────────────────────────────────

@router.get("/quotes/{quote_id}/compare", response_model=QuoteCompareResponse)
async def compare_quotes(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Return all related quotes (parent + children) for side-by-side comparison."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    root_id = quote.parent_quote_id or quote.id

    # Load root quote
    if root_id != quote.id:
        root_result = await db.execute(select(Quote).where(Quote.id == root_id))
        root = root_result.scalar_one_or_none()
        if not root:
            raise HTTPException(status_code=404, detail="Presupuesto padre no encontrado")
    else:
        root = quote

    # Load all children
    children_result = await db.execute(
        select(Quote)
        .where(Quote.parent_quote_id == root_id)
        .order_by(Quote.created_at)
    )
    children = children_result.scalars().all()

    all_quotes = [root] + list(children)
    if len(all_quotes) < 2:
        raise HTTPException(status_code=404, detail="No hay variantes para comparar")

    return QuoteCompareResponse(
        parent_id=root_id,
        client_name=root.client_name,
        project=root.project,
        quotes=[QuoteCompareItem.model_validate(q) for q in all_quotes],
    )


@router.get("/quotes/{quote_id}/compare/pdf")
async def compare_pdf(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Generate and return a comparison PDF for all related quotes."""
    from fastapi.responses import FileResponse
    from app.modules.agent.tools.document_tool import generate_comparison_pdf, OUTPUT_DIR

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    root_id = quote.parent_quote_id or quote.id

    if root_id != quote.id:
        root_result = await db.execute(select(Quote).where(Quote.id == root_id))
        root = root_result.scalar_one_or_none()
        if not root:
            raise HTTPException(status_code=404, detail="Presupuesto padre no encontrado")
    else:
        root = quote

    children_result = await db.execute(
        select(Quote)
        .where(Quote.parent_quote_id == root_id)
        .order_by(Quote.created_at)
    )
    children = children_result.scalars().all()
    all_quotes = [root] + list(children)

    if len(all_quotes) < 2:
        raise HTTPException(status_code=404, detail="No hay variantes para comparar")

    quotes_data = []
    for q in all_quotes:
        bd = q.quote_breakdown or {}
        bd["_total_ars"] = q.total_ars or bd.get("total_ars", 0)
        bd["_total_usd"] = q.total_usd or bd.get("total_usd", 0)
        bd["_material"] = q.material or bd.get("material_name", "")
        quotes_data.append(bd)

    pdf_dir = OUTPUT_DIR / root_id
    pdf_dir.mkdir(exist_ok=True)
    pdf_path = pdf_dir / "comparativo.pdf"

    import asyncio
    await asyncio.to_thread(
        generate_comparison_pdf, pdf_path, root.client_name, root.project, quotes_data
    )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"Comparativo - {root.client_name}.pdf",
    )


# ── UPDATE QUOTE STATUS ───────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}/status")
async def update_status(
    quote_id: str,
    body: QuoteStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    current = quote.status.value if hasattr(quote.status, "value") else quote.status
    target = body.status.value if hasattr(body.status, "value") else body.status
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(status_code=400, detail=f"Transición inválida: {current} → {target}")

    await db.execute(
        update(Quote)
        .where(Quote.id == quote_id)
        .values(status=body.status)
    )
    await db.commit()
    return {"ok": True}


# ── VALIDATE QUOTE (generate docs + change status) ──────────────────────────

@router.post("/quotes/{quote_id}/validate")
async def validate_quote(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate PDF/Excel/Drive from existing breakdown and set status to validated."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    bd = quote.quote_breakdown
    if not bd:
        raise HTTPException(status_code=400, detail="El presupuesto no tiene desglose calculado")

    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_to_drive

    doc_data = {
        "client_name": bd.get("client_name", quote.client_name),
        "project": bd.get("project", quote.project),
        "date": bd.get("date"),
        "delivery_days": bd.get("delivery_days"),
        "material_name": bd.get("material_name", quote.material),
        "material_m2": bd.get("material_m2"),
        "material_price_unit": bd.get("material_price_unit"),
        "material_currency": bd.get("material_currency"),
        "discount_pct": bd.get("discount_pct", 0),
        "sectors": bd.get("sectors", []),
        "sinks": bd.get("sinks", []),
        "mo_items": bd.get("mo_items", []),
        "total_ars": bd.get("total_ars", quote.total_ars),
        "total_usd": bd.get("total_usd", quote.total_usd),
    }

    doc_result = await generate_documents(quote_id, doc_data)
    pdf_url = doc_result.get("pdf_url") if doc_result.get("ok") else None
    excel_url = doc_result.get("excel_url") if doc_result.get("ok") else None

    drive_url = None
    drive_file_id = None
    if doc_result.get("ok"):
        drive_result = await upload_to_drive(
            quote_id,
            doc_data["client_name"],
            doc_data["material_name"],
            doc_data.get("date"),
        )
        if drive_result.get("ok"):
            drive_url = drive_result.get("drive_url")
            drive_file_id = drive_result.get("drive_file_id")

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(
            status=QuoteStatus.VALIDATED,
            pdf_url=pdf_url,
            excel_url=excel_url,
            drive_url=drive_url,
            drive_file_id=drive_file_id,
        )
    )
    await db.commit()

    return {
        "ok": True,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "drive_url": drive_url,
    }


# ── PATCH QUOTE (admin) ──────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}")
async def patch_quote(
    quote_id: str,
    body: QuotePatchRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify quote exists
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Quote not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Map origin -> source
    if "origin" in updates:
        updates["source"] = updates.pop("origin")

    # Serialize material array to comma-separated string
    if "material" in updates and isinstance(updates["material"], list):
        updates["material"] = ", ".join(updates["material"])

    # Serialize pieces to list of dicts for JSON column
    if "pieces" in updates and updates["pieces"] is not None:
        updates["pieces"] = [p.model_dump() for p in body.pieces]

    await db.execute(update(Quote).where(Quote.id == quote_id).values(**updates))
    await db.commit()

    logger.info("[patch] Quote %s updated: %s", quote_id, list(updates.keys()))
    return {"ok": True, "updated": list(updates.keys())}


# ── MARK QUOTE AS READ ───────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}/read")
async def mark_as_read(quote_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


# ── GENERATE DOCUMENTS (for web quotes without docs) ─────────────────────────

@router.post("/quotes/{quote_id}/generate")
async def generate_quote_documents(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Generate PDF/Excel/Drive for a quote that has quote_breakdown but no documents yet."""
    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_to_drive

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    bd = quote.quote_breakdown
    if not bd:
        raise HTTPException(status_code=400, detail="Este presupuesto no tiene datos de cálculo (quote_breakdown)")

    # Build doc_data from breakdown (same structure as quote_engine/router.py)
    doc_data = {
        "client_name": bd.get("client_name", quote.client_name),
        "project": bd.get("project", quote.project),
        "date": bd.get("date", ""),
        "delivery_days": bd.get("delivery_days", ""),
        "material_name": bd.get("material_name", quote.material or ""),
        "material_m2": bd.get("material_m2", 0),
        "material_price_unit": bd.get("material_price_unit", 0),
        "material_currency": bd.get("material_currency", "USD"),
        "discount_pct": bd.get("discount_pct", 0),
        "sectors": bd.get("sectors", []),
        "sinks": bd.get("sinks", []),
        "mo_items": bd.get("mo_items", []),
        "total_ars": bd.get("total_ars", 0),
        "total_usd": bd.get("total_usd", 0),
    }

    # Generate PDF + Excel
    doc_result = await generate_documents(quote_id, doc_data)
    if not doc_result.get("ok"):
        raise HTTPException(status_code=500, detail=doc_result.get("error", "Error generando documentos"))

    pdf_url = doc_result.get("pdf_url")
    excel_url = doc_result.get("excel_url")

    # Upload to Drive
    drive_url = None
    drive_file_id = None
    drive_result = await upload_to_drive(
        quote_id,
        doc_data["client_name"],
        doc_data["material_name"],
        doc_data["date"],
    )
    if drive_result.get("ok"):
        drive_url = drive_result.get("drive_url")
        drive_file_id = drive_result.get("drive_file_id")

    # Update quote with file URLs + status
    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(
            pdf_url=pdf_url,
            excel_url=excel_url,
            drive_url=drive_url,
            drive_file_id=drive_file_id,
            status=QuoteStatus.VALIDATED.value,
        )
    )
    await db.commit()

    logging.info(f"Generated documents for quote {quote_id}: pdf={pdf_url}, drive={drive_url}")

    return {
        "ok": True,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "drive_url": drive_url,
    }


# ── DELETE QUOTE ──────────────────────────────────────────────────────────────

@router.delete("/quotes/{quote_id}")
async def delete_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Resolve the family root and collect all related quotes
    root_id = quote.parent_quote_id or quote.id
    family_result = await db.execute(
        select(Quote).where(
            (Quote.id == root_id) | (Quote.parent_quote_id == root_id)
        )
    )
    family = list(family_result.scalars().all())

    logging.info(
        f"Cascade-deleting quote family root={root_id}: "
        f"{[q.id for q in family]} (triggered by {quote_id})"
    )

    import shutil
    from app.core.static import OUTPUT_DIR

    for q in family:
        # Delete Drive file if exists (best-effort)
        if q.drive_file_id:
            try:
                from app.modules.agent.tools.drive_tool import delete_drive_file
                await delete_drive_file(q.drive_file_id)
            except Exception as e:
                logging.warning(f"Failed to delete Drive file {q.drive_file_id}: {e}")

        # Delete local files
        output_dir = OUTPUT_DIR / q.id
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
            except Exception as e:
                logging.warning(f"Failed to delete local files for {q.id}: {e}")

        await db.delete(q)

    await db.commit()
    return {"ok": True, "deleted": [q.id for q in family]}


# ── CREATE QUOTE (new chat) ───────────────────────────────────────────────────

@router.post("/quotes")
async def create_quote(
    db: AsyncSession = Depends(get_db),
    body: Optional[CreateQuoteRequest] = None,
):
    # Opportunistic cleanup of old empty drafts
    from app.core.database import cleanup_empty_drafts
    import asyncio
    asyncio.create_task(cleanup_empty_drafts())

    quote = Quote(
        id=str(uuid.uuid4()),
        client_name="",
        project="",
        messages=[],
        status=body.status if body and body.status else QuoteStatus.DRAFT,
    )
    db.add(quote)
    await db.commit()
    return {"id": quote.id}


# ── CHAT — SSE STREAMING ──────────────────────────────────────────────────────

@router.post("/quotes/{quote_id}/chat")
async def chat(
    quote_id: str,
    message: str = Form(...),
    plan_files: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_db),
):
    from app.main import touch_chat_activity
    touch_chat_activity()

    # Budget check — block if monthly limit exceeded
    try:
        from sqlalchemy import text as sql_text
        from app.modules.agent.tools.catalog_tool import get_ai_config
        ai_cfg = get_ai_config()
        budget_cfg = ai_cfg if "monthly_budget_usd" in ai_cfg else {}
        monthly_limit = budget_cfg.get("monthly_budget_usd", 50)
        hard_limit = budget_cfg.get("enable_hard_limit", True)
        if hard_limit and monthly_limit > 0:
            month_start = __import__("datetime").datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            spent_result = await db.execute(
                sql_text("SELECT COALESCE(SUM(cost_usd), 0) FROM token_usage WHERE created_at >= :start"),
                {"start": month_start},
            )
            spent = spent_result.scalar() or 0
            if spent >= monthly_limit:
                raise HTTPException(status_code=429, detail=f"Límite mensual de API alcanzado (${spent:.2f} de ${monthly_limit:.2f}). Contactá al administrador.")
    except HTTPException:
        raise
    except Exception as e:
        logging.warning(f"Budget check failed: {e}")

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Validate and read uploaded files
    from pathlib import Path
    from datetime import datetime
    from app.modules.agent.tools.plan_tool import save_plan_to_temp

    validated_files: list[tuple[bytes, str]] = []  # (bytes, filename)
    errors: list[str] = []

    if len(plan_files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_FILES} archivos por mensaje")

    for pf in plan_files:
        if not pf.filename:
            continue
        # Sanitize filename — strip directory traversal (../ etc.)
        safe_filename = Path(pf.filename).name
        if not safe_filename:
            continue
        # Validate MIME type
        content_type = pf.content_type or ""
        if content_type not in ALLOWED_MIME_TYPES:
            errors.append(f"'{safe_filename}' — tipo no soportado ({content_type}). Solo PDF, JPG, PNG, WEBP.")
            continue
        # Read and validate size
        file_bytes = await pf.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            errors.append(f"'{safe_filename}' — excede 10MB ({len(file_bytes) / 1048576:.1f}MB)")
            continue
        validated_files.append((file_bytes, safe_filename))

        # Save to temp for read_plan tool
        save_plan_to_temp(safe_filename, file_bytes)

        # Persist source file for download
        from app.core.static import OUTPUT_DIR as _OUT
        sources_dir = _OUT / quote_id / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / safe_filename).write_bytes(file_bytes)

        # Update DB with source file metadata
        existing_files = quote.source_files or []
        if not any(f["filename"] == safe_filename for f in existing_files):
            existing_files.append({
                "filename": safe_filename,
                "type": content_type,
                "size": len(file_bytes),
                "url": f"/files/{quote_id}/sources/{safe_filename}",
                "uploaded_at": datetime.now().isoformat(),
            })
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(source_files=existing_files)
            )
            await db.commit()

    if errors:
        raise HTTPException(status_code=400, detail=" | ".join(errors))

    # Pass ALL files to Claude (not just the first one)
    plan_bytes = validated_files[0][0] if validated_files else None
    plan_filename = validated_files[0][1] if validated_files else None
    extra_files = validated_files[1:] if len(validated_files) > 1 else []

    async def event_stream():
        full_response = ""
        try:
            async for chunk in agent_service.stream_chat(
                quote_id=quote_id,
                messages=quote.messages,
                user_message=message,
                plan_bytes=plan_bytes,
                plan_filename=plan_filename,
                extra_files=extra_files,
                db=db,
            ):
                if chunk["type"] == "ping":
                    # SSE keepalive comment — prevents proxy timeout
                    yield ": keepalive\n\n"
                elif chunk["type"] == "text":
                    full_response += chunk["content"]
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "action":
                    # Tool use event (generating docs, uploading, etc.)
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "done":
                    yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            logging.error(f"SSE stream error for quote {quote_id}: {e}", exc_info=True)
            error_chunk = {"type": "error", "content": f"⚠️ Error inesperado: {str(e)[:200]}. Intentá de nuevo."}
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': '', 'error': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
