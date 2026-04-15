"""Condiciones de Contratación PDF — anexo del presupuesto edificio.

Renderiza el template fijo de `config.condiciones_edificio` con el cliente,
la obra, la fecha y el plazo (variable). El resto del texto NO cambia.

Se dispara automáticamente cuando se generan documentos de un presupuesto
edificio (is_edificio=True). Persiste el record en `Quote.condiciones_pdf`
y el frontend lo muestra como una card en el detalle del presupuesto.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.company_config import get as cfg
from app.core.static import OUTPUT_DIR
from app.models.quote import Quote


def _safe_filename(client_name: str, project: str) -> str:
    base = f"{client_name} - {project} - Condiciones".strip()
    safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in base)
    return f"{safe}.pdf"


def _render_condiciones_pdf(pdf_path: Path, data: dict) -> None:
    """Render Condiciones de Contratación as a clean A4 PDF (fpdf2)."""
    from app.modules.agent.tools.document_tool import _make_safe_fpdf, TEMPLATES_DIR

    FPDF = _make_safe_fpdf()
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Top bar
    pdf.set_fill_color(26, 47, 94)
    pdf.rect(0, 0, 210, 4, "F")

    # Logo
    logo_path = TEMPLATES_DIR / "logo-dangelo.png"
    if logo_path.exists():
        pdf.image(str(logo_path), x=10, y=10, w=55)
        pdf.set_y(35)
    else:
        pdf.set_y(15)

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, data["title"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Header line (cliente / obra / fecha)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, data["header_line"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Items numerados
    pdf.set_font("Helvetica", "", 10)
    for idx, item in enumerate(data["items"], start=1):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(8, 6, f"{idx}-")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, item, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    pdf.output(str(pdf_path))


def _build_data(quote: Quote, plazo_override: str | None = None) -> dict:
    """Build the render-ready dict from quote + config."""
    title = cfg("condiciones_edificio.title", "CONDICIONES CONTRATACIÓN MARMOLERIA")
    header_tpl = cfg(
        "condiciones_edificio.header_line",
        "Cliente: {cliente} - {obra} - {fecha}",
    )
    items_tpl: list = cfg("condiciones_edificio.items", []) or []
    default_plazo = cfg(
        "condiciones_edificio.default_plazo",
        "60 DIAS HÁBILES DESDE LA TOMA DE MEDIDAS EN OBRA",
    )

    cliente = (quote.client_name or "Cliente").strip()
    obra = (quote.project or "Obra").strip()
    fecha = datetime.now().strftime("%d/%m/%Y")
    plazo = (plazo_override or "").strip() or default_plazo

    def _fmt(s: str) -> str:
        return s.format(cliente=cliente, obra=obra, fecha=fecha, plazo=plazo)

    return {
        "title": title,
        "header_line": _fmt(header_tpl),
        "items": [_fmt(it) for it in items_tpl],
        "plazo": plazo,
    }


async def generate_condiciones_pdf(
    db: AsyncSession,
    quote_id: str,
    plazo_override: str | None = None,
) -> dict:
    """Generate, persist and (best-effort) upload to Drive.

    Returns the record dict (also persisted on Quote.condiciones_pdf).
    Idempotente: regenera siempre — cada quote tiene un único PDF de
    condiciones y se sobreescribe si cambia el cliente/obra/fecha/plazo.
    """
    from sqlalchemy import select as _sqsel
    res = await db.execute(_sqsel(Quote).where(Quote.id == quote_id))
    quote = res.scalar_one_or_none()
    if not quote:
        raise ValueError(f"Quote {quote_id} not found")

    data = _build_data(quote, plazo_override=plazo_override)

    out_dir = OUTPUT_DIR / quote_id
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(data["header_line"].split(" - ")[0].replace("Cliente:", "").strip(), quote.project or "")
    pdf_path = out_dir / filename

    await asyncio.to_thread(_render_condiciones_pdf, pdf_path, data)

    # Best-effort Drive upload (mismo helper que usa resumen_obra)
    drive_url = None
    drive_file_id = None
    try:
        from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
        drive_info = await asyncio.to_thread(
            upload_single_file_to_drive,
            str(pdf_path),
            quote.client_name or "Sin cliente",
        )
        if drive_info and drive_info.get("ok"):
            drive_url = drive_info.get("drive_url")
            drive_file_id = drive_info.get("file_id")
    except Exception as e:
        logging.warning(f"[condiciones] Drive upload failed for {quote_id}: {e}")

    record = {
        "pdf_url": f"/files/{quote_id}/{filename}",
        "drive_url": drive_url,
        "drive_file_id": drive_file_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plazo": data["plazo"],
    }

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(condiciones_pdf=record)
    )
    await db.commit()

    return record
