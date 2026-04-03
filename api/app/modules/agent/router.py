from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
import uuid

# File upload constants
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5

from app.core.database import get_db
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.agent.schemas import (
    QuoteListResponse,
    QuoteDetailResponse,
    QuoteCompareItem,
    QuoteCompareResponse,
    QuoteStatusUpdate,
)

router = APIRouter(tags=["agent"])
agent_service = AgentService()


# ── LIST QUOTES ──────────────────────────────────────────────────────────────

@router.get("/quotes", response_model=list[QuoteListResponse])
async def list_quotes(
    limit: int = 100,
    offset: int = 0,
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
    await db.execute(
        update(Quote)
        .where(Quote.id == quote_id)
        .values(status=body.status)
    )
    await db.commit()
    return {"ok": True}


# ── PATCH QUOTE (admin) ──────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}")
async def patch_quote(
    quote_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    allowed = {"client_name", "project", "material", "parent_quote_id"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    await db.execute(update(Quote).where(Quote.id == quote_id).values(**updates))
    await db.commit()
    return {"ok": True, "updated": list(updates.keys())}


# ── MARK QUOTE AS READ ───────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}/read")
async def mark_as_read(quote_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


# ── DELETE QUOTE ──────────────────────────────────────────────────────────────

@router.delete("/quotes/{quote_id}")
async def delete_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Delete Drive file if exists
    if quote.drive_file_id:
        from app.modules.agent.tools.drive_tool import delete_drive_file
        await delete_drive_file(quote.drive_file_id)

    # Delete local files
    import shutil
    from app.core.static import OUTPUT_DIR
    output_dir = OUTPUT_DIR / quote_id
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)

    await db.delete(quote)
    await db.commit()
    return {"ok": True}


# ── CREATE QUOTE (new chat) ───────────────────────────────────────────────────

@router.post("/quotes")
async def create_quote(db: AsyncSession = Depends(get_db)):
    # Opportunistic cleanup of old empty drafts
    from app.core.database import cleanup_empty_drafts
    import asyncio
    asyncio.create_task(cleanup_empty_drafts())

    quote = Quote(
        id=str(uuid.uuid4()),
        client_name="",
        project="",
        messages=[],
        status=QuoteStatus.DRAFT,
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

    # Use first file for Claude (primary plan) — all saved as source_files
    plan_bytes = validated_files[0][0] if validated_files else None
    plan_filename = validated_files[0][1] if validated_files else None

    async def event_stream():
        full_response = ""
        try:
            async for chunk in agent_service.stream_chat(
                quote_id=quote_id,
                messages=quote.messages,
                user_message=message,
                plan_bytes=plan_bytes,
                plan_filename=plan_filename,
                db=db,
            ):
                if chunk["type"] == "text":
                    full_response += chunk["content"]
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "action":
                    # Tool use event (generating docs, uploading, etc.)
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "done":
                    yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            logging.error(f"SSE stream error for quote {quote_id}: {e}", exc_info=True)
            error_chunk = {"type": "action", "content": f"⚠️ Error inesperado: {str(e)[:200]}. Intentá de nuevo."}
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
