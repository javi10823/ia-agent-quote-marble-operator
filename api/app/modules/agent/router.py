from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
import json
import uuid

# File upload constants
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5

import re

from app.core.database import get_db


def _safe_filename(name: str) -> str:
    """Strip path separators and dangerous characters from upload filenames."""
    # Take only the basename (no directory traversal)
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Remove any remaining dangerous characters
    name = re.sub(r'[^\w.\-() ]', '_', name)
    return name or "upload"
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.agent.schemas import (
    QuoteListResponse,
    QuoteDetailResponse,
    QuoteStatusUpdate,
)

router = APIRouter(tags=["agent"])
agent_service = AgentService()


# ── LIST QUOTES ──────────────────────────────────────────────────────────────

@router.get("/quotes", response_model=list[QuoteListResponse])
async def list_quotes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Quote).order_by(Quote.created_at.desc())
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
    from pathlib import Path
    output_dir = Path(__file__).parent.parent.parent.parent / "output" / quote_id
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)

    await db.delete(quote)
    await db.commit()
    return {"ok": True}


# ── CREATE QUOTE (new chat) ───────────────────────────────────────────────────

@router.post("/quotes")
async def create_quote(db: AsyncSession = Depends(get_db)):
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
        # Sanitize filename to prevent path traversal
        safe_name = _safe_filename(pf.filename)
        # Validate MIME type
        content_type = pf.content_type or ""
        if not any(content_type.startswith(t.split("/")[0]) and t.split("/")[1] in content_type for t in ALLOWED_MIME_TYPES) and content_type not in ALLOWED_MIME_TYPES:
            errors.append(f"'{safe_name}' — tipo no soportado ({content_type}). Solo PDF, JPG, PNG, WEBP.")
            continue
        # Read and validate size
        file_bytes = await pf.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            errors.append(f"'{safe_name}' — excede 10MB ({len(file_bytes) / 1048576:.1f}MB)")
            continue
        validated_files.append((file_bytes, safe_name))

        # Save to temp for read_plan tool
        save_plan_to_temp(safe_name, file_bytes)

        # Persist source file for download
        sources_dir = Path(__file__).parent.parent.parent.parent / "output" / quote_id / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / safe_name).write_bytes(file_bytes)

        # Update DB with source file metadata
        existing_files = quote.source_files or []
        if not any(f["filename"] == safe_name for f in existing_files):
            existing_files.append({
                "filename": safe_name,
                "type": content_type,
                "size": len(file_bytes),
                "url": f"/files/{quote_id}/sources/{safe_name}",
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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
