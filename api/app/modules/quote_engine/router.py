"""Public API endpoint for quote generation — no LLM, pure calculation."""

import uuid
import logging
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Header
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key for public quote endpoints. Skips if QUOTE_API_KEY is empty (dev mode)."""
    if not settings.QUOTE_API_KEY:
        return  # No API key configured — skip check (dev backward compat)
    if not x_api_key or x_api_key != settings.QUOTE_API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida o faltante")
from app.models.quote import Quote, QuoteStatus
from app.modules.quote_engine.schemas import QuoteInput, QuoteResponse, QuoteResultItem, MOItemOutput, MermaOutput, DiscountOutput
from app.modules.quote_engine.calculator import calculate_quote
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive

router = APIRouter(tags=["quote-engine"])


@router.post("/v1/quote", response_model=QuoteResponse, dependencies=[Depends(verify_api_key)])
async def create_quote_api(body: QuoteInput, db: AsyncSession = Depends(get_db)):
    """
    Generate one or more quotes from complete input data.
    No LLM involved — pure Python calculation.
    Returns quotes with PDF/Excel links.
    """
    # Normalize material to list
    materials = body.material if isinstance(body.material, list) else [body.material]

    # If no pieces provided, create a draft quote for the operator to complete
    if not body.pieces:
        quote_id = f"web-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id,
            client_name=body.client_name,
            project=body.project,
            material=materials[0],
            messages=body.conversation or [],
            status=QuoteStatus.DRAFT,
            source="web",
            is_read=False,
            notes=body.notes,
        )
        db.add(quote)
        await db.commit()
        return QuoteResponse(
            ok=True,
            quotes=[QuoteResultItem(
                quote_id=quote_id,
                material=materials[0],
                material_m2=0,
                material_price_unit=0,
                material_currency="USD",
                material_total=0,
                mo_items=[],
                total_ars=0,
                total_usd=0,
                merma=MermaOutput(aplica=False, motivo="Pendiente medidas"),
                discount=DiscountOutput(aplica=False),
            )],
        )

    results = []
    for material_name in materials:
        # Build input for calculator
        calc_input = {
            "client_name": body.client_name,
            "project": body.project,
            "material": material_name,
            "pieces": [p.model_dump() for p in body.pieces],
            "localidad": body.localidad,
            "colocacion": body.colocacion,
            "pileta": body.pileta.value if body.pileta else None,
            "anafe": body.anafe,
            "frentin": body.frentin,
            "pulido": body.pulido,
            "plazo": body.plazo,
            "discount_pct": body.discount_pct,
            "date": body.date,
        }

        calc_result = calculate_quote(calc_input)

        if not calc_result.get("ok"):
            return QuoteResponse(ok=False, error=calc_result.get("error"))

        # Create quote record in DB
        quote_id = f"web-{uuid.uuid4()}"
        quote = Quote(
            id=quote_id,
            client_name=calc_result["client_name"],
            project=calc_result["project"],
            material=calc_result["material_name"],
            total_ars=calc_result["total_ars"],
            total_usd=calc_result["total_usd"],
            quote_breakdown=calc_result,
            messages=body.conversation or [],
            status=QuoteStatus.VALIDATED,
            source="web",
            is_read=False,
            notes=body.notes,
        )
        db.add(quote)
        await db.commit()

        # Generate PDF/Excel — WEB_ prefix only in filename, not content
        doc_data = {
            "client_name": calc_result["client_name"],
            "project": calc_result["project"],
            "date": calc_result["date"],
            "delivery_days": calc_result["delivery_days"],
            "material_name": calc_result["material_name"],
            "filename_prefix": "WEB_",
            "material_m2": calc_result["material_m2"],
            "material_price_unit": calc_result["material_price_unit"],
            "material_currency": calc_result["material_currency"],
            "discount_pct": calc_result["discount_pct"],
            "sectors": calc_result["sectors"],
            "sinks": calc_result["sinks"],
            "mo_items": calc_result["mo_items"],
            "total_ars": calc_result["total_ars"],
            "total_usd": calc_result["total_usd"],
        }

        doc_result = await generate_documents(quote_id, doc_data)
        pdf_url = doc_result.get("pdf_url") if doc_result.get("ok") else None
        excel_url = doc_result.get("excel_url") if doc_result.get("ok") else None

        # Upload to Drive
        drive_url = None
        if doc_result.get("ok"):
            drive_result = await upload_to_drive(
                quote_id,
                calc_result["client_name"],
                calc_result["material_name"],
                calc_result["date"],
            )
            if drive_result.get("ok"):
                drive_url = drive_result.get("drive_url")

            # Update DB with file URLs + Drive file ID
            from sqlalchemy import update
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(
                    pdf_url=pdf_url,
                    excel_url=excel_url,
                    drive_url=drive_url,
                    drive_file_id=drive_result.get("drive_file_id") if drive_result.get("ok") else None,
                )
            )
            await db.commit()

        merma = calc_result["merma"]
        results.append(QuoteResultItem(
            quote_id=quote_id,
            material=calc_result["material_name"],
            material_m2=calc_result["material_m2"],
            material_price_unit=calc_result["material_price_unit"],
            material_currency=calc_result["material_currency"],
            material_total=calc_result["material_total"],
            mo_items=[MOItemOutput(**mo) for mo in calc_result["mo_items"]],
            total_ars=calc_result["total_ars"],
            total_usd=calc_result["total_usd"],
            merma=MermaOutput(
                aplica=merma["aplica"],
                desperdicio=merma["desperdicio"],
                sobrante_m2=merma.get("sobrante_m2", 0),
                motivo=merma["motivo"],
            ),
            discount=DiscountOutput(
                aplica=calc_result["discount_pct"] > 0,
                porcentaje=calc_result["discount_pct"],
                monto=calc_result.get("discount_amount", 0),
            ),
            pdf_url=pdf_url,
            excel_url=excel_url,
            drive_url=drive_url,
        ))

    return QuoteResponse(ok=True, quotes=results)


@router.post("/v1/quote/{quote_id}/files", dependencies=[Depends(verify_api_key)])
async def upload_source_files(
    quote_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload source files (plans, images) to an existing quote."""
    from sqlalchemy import select as sel
    from pathlib import Path
    from datetime import datetime

    ALLOWED = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    MAX_SIZE = 10 * 1024 * 1024
    MAX_COUNT = 5

    result = await db.execute(sel(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        return {"ok": False, "error": "Quote not found"}

    if len(files) > MAX_COUNT:
        return {"ok": False, "error": f"Maximum {MAX_COUNT} files per request"}

    saved = []
    errors = []

    for f in files:
        if not f.filename:
            continue
        # Sanitize filename — strip directory traversal
        safe_name = Path(f.filename).name
        if not safe_name:
            continue
        ct = f.content_type or ""
        if ct not in ALLOWED:
            errors.append(f"'{safe_name}' — unsupported type ({ct})")
            continue
        data = await f.read()
        if len(data) > MAX_SIZE:
            errors.append(f"'{safe_name}' — exceeds 10MB")
            continue

        # Save to disk
        sources_dir = Path(__file__).parent.parent.parent.parent / "output" / quote_id / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / safe_name).write_bytes(data)

        saved.append({
            "filename": safe_name,
            "type": ct,
            "size": len(data),
            "url": f"/files/{quote_id}/sources/{safe_name}",
            "uploaded_at": datetime.now().isoformat(),
        })

    # Update DB
    existing = quote.source_files or []
    for s in saved:
        if not any(e["filename"] == s["filename"] for e in existing):
            existing.append(s)

    from sqlalchemy import update as upd
    await db.execute(upd(Quote).where(Quote.id == quote_id).values(source_files=existing))
    await db.commit()

    return {"ok": True, "saved": len(saved), "errors": errors, "files": existing}
