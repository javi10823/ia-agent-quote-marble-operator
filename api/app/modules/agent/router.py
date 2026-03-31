from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
import json
import uuid

from app.core.database import get_db
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


# ── DELETE QUOTE ──────────────────────────────────────────────────────────────

@router.delete("/quotes/{quote_id}")
async def delete_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
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
    plan_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Read plan file if provided
    plan_bytes = None
    plan_filename = None
    if plan_file:
        plan_bytes = await plan_file.read()
        plan_filename = plan_file.filename

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
