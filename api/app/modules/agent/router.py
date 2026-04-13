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
MAX_FILES = 10

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
    DeriveMaterialRequest,
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
async def serve_file(file_path: str, db: AsyncSession = Depends(get_db)):
    """Serve files with Drive-first fallback for ephemeral filesystems.

    Resolution order:
    1. If local file exists → serve it
    2. If not local, search files_v2 metadata for Drive URL → redirect 302
    3. If parent has files_v2 for this file → redirect 302
    4. Nothing found → 404
    """
    from app.core.static import OUTPUT_DIR
    from starlette.responses import RedirectResponse
    import mimetypes, urllib.parse

    # 1. Try local filesystem first
    full_path = (OUTPUT_DIR / file_path).resolve()
    if full_path.is_relative_to(OUTPUT_DIR.resolve()) and full_path.exists() and full_path.is_file():
        media_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
        return FileResponse(full_path, media_type=media_type)

    # 2. File not local — try Drive fallback via files_v2
    # Extract quote_id from path: "{quote_id}/filename"
    parts = file_path.split("/", 1)
    if len(parts) == 2:
        req_quote_id, req_filename = parts[0], urllib.parse.unquote(parts[1])

        # Search in the quote itself
        drive_url = await _find_drive_url_in_files_v2(db, req_quote_id, req_filename)
        if drive_url:
            return RedirectResponse(url=drive_url, status_code=302)

        # If this is a child, search in parent
        try:
            quote_result = await db.execute(select(Quote).where(Quote.id == req_quote_id))
            quote = quote_result.scalar_one_or_none()
            if quote and quote.parent_quote_id:
                drive_url = await _find_drive_url_in_files_v2(db, quote.parent_quote_id, req_filename)
                if drive_url:
                    return RedirectResponse(url=drive_url, status_code=302)
            # If this is a parent, search children (files might be stored under parent ID)
            if quote and quote.quote_kind == "building_parent":
                drive_url = await _find_drive_url_in_files_v2(db, req_quote_id, req_filename)
                if drive_url:
                    return RedirectResponse(url=drive_url, status_code=302)
        except Exception as e:
            logging.warning(f"files_v2 lookup failed: {e}")

    raise HTTPException(status_code=404, detail="Archivo no encontrado")


async def _find_drive_url_in_files_v2(db: AsyncSession, quote_id: str, filename: str) -> str | None:
    """Search files_v2 in a quote's breakdown for a matching file. Returns drive_download_url or None."""
    try:
        result = await db.execute(select(Quote).where(Quote.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote or not quote.quote_breakdown:
            return None
        # Check files_v2 in breakdown
        files_v2 = quote.quote_breakdown.get("files_v2", {}) if quote.quote_breakdown else {}
        for item in files_v2.get("items", []):
            item_filename = urllib.parse.unquote(item.get("filename", ""))
            if item_filename == filename or item.get("local_url", "").endswith(filename):
                return item.get("drive_download_url") or item.get("drive_url")

        # Also check source_files (for source/plan files with drive info)
        for sf in (quote.source_files or []):
            if sf.get("filename") == filename or (sf.get("url") or "").endswith(filename):
                drive_dl = sf.get("drive_download_url") or sf.get("drive_url")
                if drive_dl:
                    return drive_dl
    except Exception:
        pass
    return None


# ── LIST QUOTES ──────────────────────────────────────────────────────────────

def _extract_drive_urls(quote) -> dict:
    """Extract drive_pdf_url and drive_excel_url from files_v2 in breakdown."""
    bd = quote.quote_breakdown if quote.quote_breakdown else {}
    files_v2 = bd.get("files_v2", {})
    result = {"drive_pdf_url": None, "drive_excel_url": None}
    for item in files_v2.get("items", []):
        kind = item.get("kind", "")
        url = item.get("drive_url") or item.get("drive_download_url")
        if kind == "pdf" and url and not result["drive_pdf_url"]:
            result["drive_pdf_url"] = url
        elif kind == "excel" and url and not result["drive_excel_url"]:
            result["drive_excel_url"] = url
        elif kind == "summary_pdf" and url and not result["drive_pdf_url"]:
            result["drive_pdf_url"] = url
        elif kind == "summary_excel" and url and not result["drive_excel_url"]:
            result["drive_excel_url"] = url
    return result


@router.get("/quotes")
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
            ),
            # Exclude building children — they live inside their parent
            or_(Quote.quote_kind != "building_child_material", Quote.quote_kind.is_(None)),
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

@router.get("/quotes/{quote_id}")
async def get_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # For building_parent, include children in the response
    response = QuoteDetailResponse.model_validate(quote)
    if quote.quote_kind == "building_parent":
        children_result = await db.execute(
            select(Quote)
            .where(Quote.parent_quote_id == quote_id, Quote.quote_kind == "building_child_material")
            .order_by(Quote.created_at)
        )
        children = children_result.scalars().all()
        response_dict = response.model_dump()
        response_dict["children"] = [QuoteListResponse.model_validate(c).model_dump() for c in children]
        return response_dict

    return response


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

    # Use complete breakdown as source of truth — it contains all fields
    # that generate_documents needs (sectors, mo_items, material_total,
    # merma, piece_details, sinks, discount_amount, etc.)
    # Only fill fallbacks for fields that might be missing in legacy breakdowns.
    doc_data = dict(bd)
    doc_data.setdefault("client_name", quote.client_name)
    doc_data.setdefault("project", quote.project)
    doc_data.setdefault("material_name", quote.material)
    doc_data.setdefault("total_ars", quote.total_ars)
    doc_data.setdefault("total_usd", quote.total_usd)
    doc_data.setdefault("discount_pct", 0)
    doc_data.setdefault("sectors", [])
    doc_data.setdefault("mo_items", [])

    doc_result = await generate_documents(quote_id, doc_data)
    pdf_url = doc_result.get("pdf_url") if doc_result.get("ok") else None
    excel_url = doc_result.get("excel_url") if doc_result.get("ok") else None

    # Preserve existing drive_url if new upload fails
    existing_drive_url = quote.drive_url
    existing_drive_file_id = quote.drive_file_id

    drive_url = None
    drive_file_id = None
    if doc_result.get("ok"):
        # Delete old Drive file before uploading new one
        if existing_drive_file_id:
            from app.modules.agent.tools.drive_tool import delete_drive_file
            await delete_drive_file(existing_drive_file_id)

        drive_result = await upload_to_drive(
            quote_id,
            doc_data["client_name"],
            doc_data["material_name"],
            doc_data.get("date"),
        )
        if drive_result.get("ok"):
            drive_url = drive_result.get("drive_url")
            drive_file_id = drive_result.get("drive_file_id")

    # If upload failed, preserve existing drive_url
    final_drive_url = drive_url or existing_drive_url
    final_drive_file_id = drive_file_id or existing_drive_file_id

    update_values = {
        "status": QuoteStatus.VALIDATED,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
    }
    # Only update drive fields if we have new values (don't overwrite with None)
    if drive_url:
        update_values["drive_url"] = drive_url
        update_values["drive_file_id"] = drive_file_id

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(**update_values)
    )
    await db.commit()

    return {
        "ok": True,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "drive_url": final_drive_url,
    }


# ── DERIVE MATERIAL — create new quote with different material ───────────────

@router.post("/quotes/{quote_id}/derive-material")
async def derive_material(
    quote_id: str,
    body: DeriveMaterialRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a NEW quote derived from an existing one, replacing only the material.

    Copies client data, pieces, and options from the original.
    Recalculates everything from scratch via calculate_quote.
    The new quote is born in DRAFT status with no documents.

    Traceability: new quote's parent_quote_id points to the original.
    conversation_id is NOT copied — the derived quote starts its own chat.
    """
    import uuid as _uuid
    from app.modules.quote_engine.calculator import calculate_quote

    # Load original
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Presupuesto original no encontrado")

    # ── Source of truth for pieces ──
    # Priority: quote.pieces (raw input) > breakdown.piece_details (calculated)
    # If neither exists, reject — we need a reliable base to recalculate.
    pieces = None
    if original.pieces:
        # Raw pieces saved at creation — best source
        pieces = original.pieces
    elif original.quote_breakdown and original.quote_breakdown.get("piece_details"):
        # Fallback: reconstruct from breakdown's piece_details
        pieces = []
        for pd in original.quote_breakdown["piece_details"]:
            piece = {"description": pd["description"], "largo": pd["largo"]}
            if pd.get("dim2"):
                # dim2 is prof for mesadas, alto for zócalos
                desc_lower = pd["description"].lower()
                if "zócalo" in desc_lower or "zocalo" in desc_lower:
                    piece["alto"] = pd["dim2"]
                else:
                    piece["prof"] = pd["dim2"]
            pieces.append(piece)
        logging.info(f"[derive] Reconstructed {len(pieces)} pieces from breakdown for {quote_id}")
    if not pieces:
        raise HTTPException(status_code=400, detail="El presupuesto original no tiene piezas. No se puede derivar.")

    # ── Plazo: from breakdown or config default ──
    plazo = None
    if original.quote_breakdown:
        plazo = original.quote_breakdown.get("delivery_days")
    if not plazo:
        try:
            from app.core.company_config import get as _cfg
            plazo = _cfg("delivery_days.display", "40 dias desde la toma de medidas")
        except Exception:
            plazo = "40 dias desde la toma de medidas"

    # ── Build calculate_quote input ──
    calc_input = {
        "client_name": original.client_name or "",
        "project": original.project or "",
        "material": body.material,
        "pieces": pieces,
        "localidad": original.localidad or "rosario",
        "colocacion": original.colocacion if original.colocacion is not None else True,
        "pileta": original.pileta,
        "anafe": original.anafe or False,
        "plazo": plazo,
        "skip_flete": original.quote_breakdown.get("skip_flete", False) if original.quote_breakdown else False,
    }
    # Carry over frentin/inglete/pulido from original breakdown if they existed
    if original.quote_breakdown:
        for key in ("frentin", "frentin_ml", "inglete", "pulido", "discount_pct", "is_edificio"):
            val = original.quote_breakdown.get(key)
            if val:
                calc_input[key] = val

    # ── Calculate ──
    calc_result = calculate_quote(calc_input)
    if not calc_result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Error al calcular con material '{body.material}': {calc_result.get('error', 'desconocido')}"
        )

    # ── Create new quote ──
    new_id = str(_uuid.uuid4())
    new_quote = Quote(
        id=new_id,
        client_name=original.client_name,
        project=original.project,
        material=calc_result.get("material_name", body.material),
        total_ars=calc_result.get("total_ars"),
        total_usd=calc_result.get("total_usd"),
        quote_breakdown=calc_result,
        status=QuoteStatus.DRAFT,
        source=original.source,
        is_read=True,
        # Client contact
        client_phone=original.client_phone,
        client_email=original.client_email,
        # Quote options (copied from original)
        localidad=original.localidad,
        colocacion=original.colocacion,
        pileta=original.pileta,
        anafe=original.anafe,
        sink_type=original.sink_type,
        pieces=pieces,
        notes=original.notes,
        # Traceability
        parent_quote_id=original.parent_quote_id or original.id,
        # Fresh state — no docs, no chat, no history
        messages=[],
        change_history=[],
        # conversation_id intentionally NOT copied:
        # the derived quote starts its own chat context.
    )
    db.add(new_quote)
    await db.commit()

    logging.info(
        f"[derive-material] {quote_id} → {new_id} | "
        f"material: {original.material} → {body.material} | "
        f"total_ars: {original.total_ars} → {calc_result.get('total_ars')} | "
        f"total_usd: {original.total_usd} → {calc_result.get('total_usd')}"
    )

    return {
        "ok": True,
        "quote_id": new_id,
        "material": calc_result.get("material_name"),
        "total_ars": calc_result.get("total_ars"),
        "total_usd": calc_result.get("total_usd"),
        "derived_from": quote_id,
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

    # Serialize sink_type to dict for JSON column
    if "sink_type" in updates and body.sink_type is not None:
        updates["sink_type"] = body.sink_type.model_dump()

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


# ── ADMIN: Backfill Drive URLs for existing quotes ───────────────────────────

@router.post("/admin/backfill-drive")
async def backfill_drive(db: AsyncSession = Depends(get_db)):
    """Regenerate PDF/Excel and upload to Drive for quotes missing drive_pdf_url.

    Safe: reads from existing quote_breakdown, regenerates docs, uploads to Drive.
    Does NOT recalculate anything. Idempotent — skips quotes that already have Drive URLs.
    """
    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
    from app.core.static import OUTPUT_DIR

    # Find quotes that are validated but missing Drive URLs
    from sqlalchemy import or_ as _or
    result = await db.execute(
        select(Quote).where(
            Quote.status.in_(["validated", "sent"]),
            Quote.drive_pdf_url.is_(None),
            Quote.quote_breakdown.isnot(None),
            # Skip building children — they get handled via parent
            _or(Quote.quote_kind != "building_child_material", Quote.quote_kind.is_(None)),
        )
    )
    quotes = result.scalars().all()
    logging.info(f"[backfill-drive] Found {len(quotes)} quotes to backfill")

    results = []
    for q in quotes:
        bd = q.quote_breakdown
        if not bd or not bd.get("ok", True):
            results.append({"id": q.id, "status": "skipped", "reason": "no valid breakdown"})
            continue

        try:
            # Regenerate docs from breakdown
            doc_result = await generate_documents(q.id, bd)
            if not doc_result.get("ok"):
                results.append({"id": q.id, "status": "error", "reason": f"generate failed: {doc_result.get('error', '')[:100]}"})
                continue

            # Upload each file to Drive
            drive_pdf = None
            drive_excel = None
            subfolder = q.client_name or ""

            for url_key, kind in [("pdf_url", "pdf"), ("excel_url", "excel")]:
                local_url = doc_result.get(url_key)
                if not local_url:
                    continue
                local_path = str(OUTPUT_DIR / local_url.replace("/files/", "", 1))
                try:
                    dr = await upload_single_file_to_drive(local_path, subfolder)
                    if dr.get("ok"):
                        if kind == "pdf":
                            drive_pdf = dr["drive_url"]
                        else:
                            drive_excel = dr["drive_url"]
                except Exception as e:
                    logging.warning(f"[backfill] Drive upload failed for {q.id} {kind}: {e}")

            # Update quote
            update_vals = {
                "pdf_url": doc_result.get("pdf_url"),
                "excel_url": doc_result.get("excel_url"),
            }
            if drive_pdf:
                update_vals["drive_pdf_url"] = drive_pdf
                update_vals["drive_url"] = drive_pdf
            if drive_excel:
                update_vals["drive_excel_url"] = drive_excel

            # Build files_v2
            files_v2_items = []
            mat_label = (q.material or "").replace(" ", "_").lower()[:30]
            for kind, url in [("pdf", doc_result.get("pdf_url")), ("excel", doc_result.get("excel_url"))]:
                if url:
                    item = {
                        "kind": kind,
                        "scope": "self",
                        "owner_quote_id": q.id,
                        "file_key": f"{mat_label}:{kind}",
                        "filename": url.split("/")[-1],
                        "local_url": url,
                        "local_path": str(OUTPUT_DIR / url.replace("/files/", "", 1)),
                    }
                    if kind == "pdf" and drive_pdf:
                        item["drive_url"] = drive_pdf
                        item["drive_download_url"] = drive_pdf.replace("/view", "/export?format=pdf") if "/view" in drive_pdf else drive_pdf
                    elif kind == "excel" and drive_excel:
                        item["drive_url"] = drive_excel
                        item["drive_download_url"] = drive_excel
                    files_v2_items.append(item)

            if files_v2_items:
                bd_copy = dict(bd)
                bd_copy["files_v2"] = {"items": files_v2_items}
                update_vals["quote_breakdown"] = bd_copy

            await db.execute(update(Quote).where(Quote.id == q.id).values(**update_vals))
            await db.commit()

            results.append({
                "id": q.id,
                "client": q.client_name,
                "material": q.material,
                "status": "ok",
                "drive_pdf": bool(drive_pdf),
                "drive_excel": bool(drive_excel),
            })
            logging.info(f"[backfill] {q.id} ({q.client_name} / {q.material}): pdf={bool(drive_pdf)}, excel={bool(drive_excel)}")

        except Exception as e:
            logging.error(f"[backfill] Failed for {q.id}: {e}", exc_info=True)
            results.append({"id": q.id, "status": "error", "reason": str(e)[:200]})

    return {"total": len(quotes), "results": results}


# ── ZONE SELECT — operator draws rectangle on plan page ───────────────────────

from pydantic import BaseModel as _BaseModel


class ZoneSelectRequest(_BaseModel):
    bbox_normalized: dict  # {x1, y1, x2, y2} in 0-1 range
    page_num: int = 1


@router.post("/quotes/{quote_id}/zone-select")
async def zone_select(
    quote_id: str,
    body: ZoneSelectRequest,
    db: AsyncSession = Depends(get_db),
):
    """Receive operator's rectangle selection on a plan page.

    Converts normalized bbox to pixels, persists as selected_zone
    and zone_default for subsequent pages.
    """
    import logging
    from PIL import Image as _PILImage
    from app.modules.quote_engine.visual_quote_builder import normalize_bbox_to_pixels

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    bd = quote.quote_breakdown or {}

    # Read real image dimensions from disk
    from app.core.static import OUTPUT_DIR
    img_path = OUTPUT_DIR / quote_id / f"page_{body.page_num}.jpg"
    if img_path.exists():
        with _PILImage.open(img_path) as img:
            real_w, real_h = img.size
    else:
        logging.warning(f"[zone-select] Image not found at {img_path}, using fallback 1200x1200")
        real_w, real_h = 1200, 1200

    bbox_px = normalize_bbox_to_pixels(body.bbox_normalized, real_w, real_h)
    logging.info(f"[zone-select] Quote {quote_id}: bbox_normalized={body.bbox_normalized} → bbox_px={bbox_px} (image {real_w}×{real_h})")

    # Persist as selected zone + zone_default
    page_key = str(body.page_num)
    page_data = bd.get("page_data", {})
    pd = page_data.get(page_key, {})
    pd["selected_zone"] = {
        "name": "OPERADOR_SELECTION",
        "bbox": bbox_px,
        "view_type": "top_view",
        "confidence": 1.0,
        "source": "operator_rectangle",
    }
    page_data[page_key] = pd
    bd["page_data"] = page_data
    bd["zone_default"] = "OPERADOR_SELECTION"
    bd["zone_default_bbox"] = bbox_px
    bd["building_step"] = f"visual_page_{body.page_num}"

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(quote_breakdown=bd)
    )
    await db.commit()

    return {"ok": True, "bbox_px": bbox_px, "image_size": [real_w, real_h]}


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

    # Budget check — read DIRECTLY from DB (not cached config — multi-worker cache stale)
    try:
        from sqlalchemy import text as sql_text
        monthly_limit = 300
        hard_limit = True
        _budget_result = await db.execute(sql_text("SELECT content FROM catalogs WHERE name = 'config'"))
        _budget_row = _budget_result.first()
        if _budget_row and _budget_row[0]:
            import json as _budget_json
            _budget_val = _budget_row[0]
            _budget_cfg = _budget_json.loads(_budget_val) if isinstance(_budget_val, str) else _budget_val
            _budget_ai = _budget_cfg.get("ai_engine", {})
            monthly_limit = _budget_ai.get("monthly_budget_usd", 300)
            hard_limit = _budget_ai.get("enable_hard_limit", True)
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

        # Upload source file to Drive for durable storage
        source_drive_info = {}
        try:
            from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
            local_source_path = str(sources_dir / safe_filename)
            dr = await upload_single_file_to_drive(local_source_path, "Archivos Origen")
            if dr.get("ok"):
                source_drive_info = {
                    "drive_file_id": dr["file_id"],
                    "drive_url": dr["drive_url"],
                    "drive_download_url": dr["drive_download_url"],
                }
        except Exception as e:
            logging.warning(f"Drive upload of source file failed: {e}")

        # Update DB with source file metadata
        existing_files = quote.source_files or []
        if not any(f["filename"] == safe_filename for f in existing_files):
            existing_files.append({
                "filename": safe_filename,
                "type": content_type,
                "size": len(file_bytes),
                "url": f"/files/{quote_id}/sources/{safe_filename}",
                "uploaded_at": datetime.now().isoformat(),
                **source_drive_info,
            })
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(source_files=existing_files)
            )

            # Also persist in files_v2 for Drive-first resolution
            bd = quote.quote_breakdown or {}
            fv2 = bd.get("files_v2", {"items": []})
            fv2["items"].append({
                "kind": "source",
                "scope": "parent",
                "file_key": "parent:source",
                "filename": safe_filename,
                "local_path": str(sources_dir / safe_filename),
                "local_url": f"/files/{quote_id}/sources/{safe_filename}",
                **({f"drive_{k}": v for k, v in source_drive_info.items()} if source_drive_info else {}),
            })
            bd["files_v2"] = fv2
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=bd)
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
                elif chunk["type"] == "zone_selector":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "done":
                    logging.info(f"[SSE] Sending done for quote {quote_id}")
                    yield f"data: {json.dumps(chunk)}\n\n"
                else:
                    logging.warning(f"[SSE] Unknown chunk type: {chunk.get('type')} for quote {quote_id}")
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
