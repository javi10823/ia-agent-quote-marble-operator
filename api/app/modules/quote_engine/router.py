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
from app.modules.quote_engine.schemas import QuoteInput, QuoteResponse, QuoteResultItem, MOItemOutput, MermaOutput, DiscountOutput, PieceInput, PiletaType
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

    # Default plazo from config.json if not provided
    if not body.plazo:
        try:
            import json
            from pathlib import Path as _P
            _cfg = json.loads((_P(__file__).parent.parent.parent / "catalog" / "config.json").read_text())
            body.plazo = _cfg.get("delivery_days", {}).get("display", "40 dias")
        except Exception:
            body.plazo = "40 dias"

    # If no pieces provided, try to parse from notes using Claude
    if not body.pieces:
        if body.notes:
            try:
                from app.modules.quote_engine.text_parser import parse_measurements
                parsed = await parse_measurements(body.notes, materials[0], body.project)
                if parsed and parsed.get("pieces"):
                    body.pieces = [PieceInput(**{k: v for k, v in p.items() if k in ("description", "largo", "prof", "alto")}) for p in parsed["pieces"]]
                    if parsed.get("pileta") and not body.pileta:
                        try:
                            body.pileta = PiletaType(parsed["pileta"])
                        except ValueError:
                            pass
                    if parsed.get("anafe"):
                        body.anafe = True
                    if parsed.get("frentin"):
                        body.frentin = True
                    if parsed.get("colocacion") is False:
                        body.colocacion = False
                    logging.info(f"Parsed {len(body.pieces)} pieces from notes for {body.client_name}")
                    body._parsed_from_notes = True  # type: ignore[attr-defined]
            except Exception as e:
                logging.error(f"Failed to parse notes for {body.client_name}: {e}")
                # Fall through to empty draft

        # If still no pieces (no notes, or parse failed) → create quote
        # PENDING if there are notes (operator has data to work with), DRAFT if empty
        if not body.pieces:
            quote_id = f"web-{uuid.uuid4()}"
            has_notes = bool(body.notes and body.notes.strip())
            quote = Quote(
                id=quote_id,
                client_name=body.client_name,
                project=body.project,
                material=materials[0],
                messages=body.conversation or [],
                status=QuoteStatus.PENDING if has_notes else QuoteStatus.DRAFT,
                source="web",
                is_read=False,
                notes=body.notes,
                localidad=body.localidad,
                colocacion=body.colocacion,
                pileta=body.pileta.value if body.pileta else None,
                anafe=body.anafe,
            )
            db.add(quote)
            await db.commit()
            merma_msg = "Pendiente revision por operador" if has_notes else "Pendiente medidas"
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
                    merma=MermaOutput(aplica=False, motivo=merma_msg),
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
            status=QuoteStatus.PENDING,
            source="web",
            is_read=False,
            notes=body.notes,
            localidad=body.localidad,
            colocacion=body.colocacion,
            pileta=body.pileta.value if body.pileta else None,
            anafe=body.anafe,
            pieces=[p.model_dump() for p in body.pieces] if body.pieces else None,
        )
        db.add(quote)
        await db.commit()

        # No doc generation here — operator validates via POST /quotes/{id}/validate

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
            pdf_url=None,
            excel_url=None,
            drive_url=None,
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
        from app.core.static import OUTPUT_DIR
        sources_dir = OUTPUT_DIR / quote_id / "sources"
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

    # If quote has no breakdown yet and we just saved files, trigger agent processing
    # in the background so the API responds immediately to the chatbot
    if saved and not quote.quote_breakdown:
        import asyncio

        async def _process_plan_background(qid: str, q: Quote, first_file: dict):
            """Run Valentina in background to read plan, extract pieces, calculate quote."""
            try:
                from app.modules.agent.agent import AgentService
                from app.core.database import AsyncSessionLocal

                # Build context message from quote data
                parts = []
                if q.client_name:
                    parts.append(f"Cliente: {q.client_name}")
                if q.project:
                    parts.append(f"Proyecto: {q.project}")
                if q.material:
                    parts.append(f"Material: {q.material}")
                localidad = getattr(q, "localidad", None)
                if localidad:
                    parts.append(f"Localidad: {localidad}")
                colocacion = getattr(q, "colocacion", None)
                if colocacion is not None:
                    parts.append(f"{'Con' if colocacion else 'Sin'} colocación")
                pileta_val = getattr(q, "pileta", None)
                if pileta_val:
                    parts.append(f"Pileta: {pileta_val}")
                anafe_val = getattr(q, "anafe", None)
                if anafe_val:
                    parts.append(f"Con anafe")
                if q.notes:
                    parts.append(f"Notas del cliente: {q.notes}")
                parts.append("Adjunto el plano. Es un procesamiento automático — calculá el presupuesto completo y guardá el breakdown. NO generar documentos (PDF/Excel/Drive). NO pedir confirmación. Solo calcular y guardar.")

                auto_message = "\n".join(parts)

                # Read file from disk
                from app.core.static import OUTPUT_DIR as _OUTDIR
                file_path = _OUTDIR / qid / "sources" / first_file["filename"]
                plan_data = file_path.read_bytes() if file_path.exists() else None

                agent = AgentService()
                async with AsyncSessionLocal() as bg_db:
                    async for _ in agent.stream_chat(
                        quote_id=qid,
                        messages=q.messages or [],
                        user_message=auto_message,
                        plan_bytes=plan_data,
                        plan_filename=first_file["filename"] if plan_data else None,
                        db=bg_db,
                    ):
                        pass  # Consume stream — only care about side effects (DB updates)

                logging.info(f"Auto-processed plan for web quote {qid}")
            except Exception as e:
                logging.error(f"Failed to auto-process plan for {qid}: {e}", exc_info=True)

        asyncio.create_task(_process_plan_background(quote_id, quote, saved[0]))

    return {"ok": True, "saved": len(saved), "errors": errors, "files": existing}
