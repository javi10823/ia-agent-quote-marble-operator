import math
import shutil
import logging
from pathlib import Path
from datetime import datetime
import asyncio

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

from app.core.static import OUTPUT_DIR


DELIVERY_SUFFIX = "días desde la toma de medidas"
from app.core.catalog_dir import CATALOG_DIR

_company_config_cache: dict | None = None


def _load_company_config() -> dict:
    """Load company + conditions from config.json. Cached in memory."""
    global _company_config_cache
    if _company_config_cache is not None:
        return _company_config_cache

    import json
    try:
        with open(CATALOG_DIR / "config.json") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    company = cfg.get("company", {})
    conditions = cfg.get("conditions", {})

    _company_config_cache = {
        "name": company.get("name", "D'ANGELO"),
        "subtitle": company.get("subtitle", "MARMOLERIA"),
        "address": company.get("address", "SAN NICOLAS 1160"),
        "phone": company.get("phone", "341-3082996"),
        "email": company.get("email", "marmoleriadangelo@gmail.com"),
        "conditions_general": conditions.get("general", ""),
        "conditions_payment": conditions.get("payment", ""),
    }
    return _company_config_cache


def invalidate_company_config_cache():
    """Clear cached company config so next call reloads from disk."""
    global _company_config_cache
    _company_config_cache = None


def _fmt_ars(value: float) -> str:
    """Format ARS price: $65.147,34 (dot thousands, comma decimal, 2 decimals)."""
    n = round(value, 2)
    # Format with 2 decimals, then swap separators for Argentine locale
    raw = f"{abs(n):,.2f}"  # "65,147.34"
    # Swap: comma→temp, dot→comma, temp→dot
    formatted = raw.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${formatted}" if n >= 0 else f"-${formatted}"


def _fmt_usd(value: float) -> str:
    """Format USD price: USD 1.937 (dot for thousands, no decimals)."""
    n = round(value)
    formatted = f"{abs(n):,}".replace(",", ".")
    return f"USD {formatted}" if n >= 0 else f"-USD {formatted}"


def _fmt_qty(value: float) -> str:
    """Format quantity Argentine style: 1,20 (comma for decimal)."""
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".replace(".", ",")


def _normalize_delivery(raw: str) -> str:
    """Ensure delivery text is complete, not just a number."""
    if not raw:
        return ""
    raw = raw.strip()
    # If it's just a number like "30", add the full text
    if raw.isdigit():
        return f"{raw} {DELIVERY_SUFFIX}"
    # If it has "dias" or "días" but not the full phrase, leave as is
    return raw


async def generate_documents(quote_id: str, quote_data: dict) -> dict:
    """Generate PDF and Excel for a quote."""
    try:
        client_name = quote_data["client_name"]
        material = quote_data.get("material_name", "")
        prefix = quote_data.get("filename_prefix", "")
        # Always use server date — never trust Claude's date
        date_str = datetime.now().strftime("%d.%m.%Y")
        # Sanitize filename: remove any remaining invalid characters
        filename_base = f"{prefix}{client_name} - {material} - {date_str}"
        filename_base = filename_base.replace("/", "-").replace("\\", "-")

        quote_dir = OUTPUT_DIR / quote_id
        quote_dir.mkdir(exist_ok=True)

        pdf_path = quote_dir / f"{filename_base}.pdf"
        excel_path = quote_dir / f"{filename_base}.xlsx"

        # Generate both in parallel — run blocking I/O in thread pool
        await asyncio.gather(
            asyncio.to_thread(_generate_excel, excel_path, quote_data),
            asyncio.to_thread(_generate_pdf, pdf_path, quote_data),
        )

        return {
            "ok": True,
            "pdf_url": f"/files/{quote_id}/{filename_base}.pdf",
            "excel_url": f"/files/{quote_id}/{filename_base}.xlsx",
            "filename_base": filename_base,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def generate_edificio_documents(
    quote_id: str,
    paso2_calc: dict,
    summary: dict,
    client_name: str = "",
    project: str = "",
    localidad: str = "Rosario",
) -> dict:
    """Generate 3 PDF+Excel for edificio using build_edificio_doc_context.

    Presentation model built by edificio_parser, not ad-hoc here.
    Uses _generate_pdf/_generate_excel (original D'Angelo template).
    """
    from app.modules.quote_engine.edificio_parser import build_edificio_doc_context

    date_str = datetime.now().strftime("%d.%m.%Y")
    quote_dir = OUTPUT_DIR / quote_id
    quote_dir.mkdir(exist_ok=True)

    contexts = build_edificio_doc_context(summary, paso2_calc, client_name, project)
    generated = []

    for ctx in contexts:
        mat_name = ctx.get("_mat_name_raw", "")
        cur = ctx.get("_currency", "ARS")

        safe_mat = (ctx.get("material_name") or mat_name).replace("/", "-").replace("\\", "-")
        base_name = f"{client_name} - {safe_mat} - {date_str}"
        pdf_path = quote_dir / f"{base_name}.pdf"
        excel_path = quote_dir / f"{base_name}.xlsx"

        # Use edificio-specific renderers that respect show_mo and grand_total_text
        await asyncio.gather(
            asyncio.to_thread(_generate_edificio_pdf, pdf_path, ctx),
            asyncio.to_thread(_generate_edificio_excel, excel_path, ctx),
        )

        generated.append({
            "material": mat_name or ctx.get("material_name", ""),
            "pdf_url": f"/files/{quote_id}/{base_name}.pdf",
            "excel_url": f"/files/{quote_id}/{base_name}.xlsx",
            "total_ars": ctx.get("total_ars", 0),
            "total_usd": ctx.get("total_usd", 0),
            "currency": cur,
        })

    # ── 4th document: Resumen General de Obra ──
    resumen_name = f"{client_name} - Resumen General de Obra - {date_str}"
    resumen_pdf = quote_dir / f"{resumen_name}.pdf"
    resumen_xlsx = quote_dir / f"{resumen_name}.xlsx"

    # Build material rows from paso2_calc (read-only, no recomputation)
    calc_results = paso2_calc.get("calc_results", {})
    mat_rows = []
    total_mat_ars = 0
    total_mat_usd = 0
    mat_display_names = []
    for mat_name_r, mr in calc_results.items():
        if not mr.get("ok"):
            continue
        cur = mr["currency"]
        net = mr["material_net"]
        mat_rows.append({
            "name": mr.get("catalog_name", mat_name_r),
            "m2": mr["m2"],
            "currency": cur,
            "price_unit": mr["price_unit"],
            "subtotal": mr["material_total"],
            "discount_pct": mr.get("discount_pct", 0),
            "discount_amount": mr.get("discount_amount", 0),
            "net": net,
        })
        mat_display_names.append(mr.get("catalog_name", mat_name_r))
        if cur == "ARS":
            total_mat_ars += net
        else:
            total_mat_usd += net

    resumen_data = {
        "client_name": client_name,
        "project": project,
        "materials": mat_rows,
        "mo_items": paso2_calc.get("mo_items", []),
        "mo_total": paso2_calc.get("mo_total", 0),
        "total_mat_ars": total_mat_ars,
        "total_mat_usd": total_mat_usd,
        "grand_total_ars": paso2_calc.get("grand_total_ars", 0),
        "grand_total_usd": paso2_calc.get("grand_total_usd", 0),
        "material_names": mat_display_names,
    }

    await asyncio.gather(
        asyncio.to_thread(_generate_resumen_obra_pdf, resumen_pdf, resumen_data),
        asyncio.to_thread(_generate_resumen_obra_excel, resumen_xlsx, resumen_data),
    )

    generated.append({
        "material": "Resumen General de Obra",
        "pdf_url": f"/files/{quote_id}/{resumen_name}.pdf",
        "excel_url": f"/files/{quote_id}/{resumen_name}.xlsx",
        "total_ars": paso2_calc.get("grand_total_ars", 0),
        "total_usd": paso2_calc.get("grand_total_usd", 0),
        "currency": "consolidado",
    })

    return {
        "ok": True,
        "generated": generated,
        "grand_total_ars": paso2_calc.get("grand_total_ars", 0),
        "grand_total_usd": paso2_calc.get("grand_total_usd", 0),
    }


def _generate_resumen_obra_pdf(pdf_path: Path, data: dict) -> None:
    """Generate consolidated project summary PDF — same D'Angelo look."""
    from fpdf import FPDF
    from app.modules.quote_engine.edificio_parser import _fmt_num

    co = _load_company_config()
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
        pdf.set_y(12)
        pdf.set_font("Helvetica", "B", 28)
        pdf.cell(0, 12, co["name"], new_x="LMARGIN", new_y="NEXT")

    # Header
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"{co['address']} | Tel: {co['phone']} | {co['email']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    col_w = 95
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 5, f"Cliente: {data['client_name']}")
    pdf.cell(col_w, 5, "Forma de pago", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(col_w, 5, "")
    pdf.cell(col_w, 5, "CONTADO EFVO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 5, f"Proyecto: {data['project']}")
    pdf.cell(col_w, 5, "Fecha de entrega", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(col_w, 5, "")
    pdf.cell(col_w, 5, "Segun cronograma de obra", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    pdf.ln(5)

    pdf.set_draw_color(26, 26, 26)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Title
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "RESUMEN GENERAL DE OBRA", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ── 1. Materials table ──
    pdf.set_font("Helvetica", "B", 8)
    mw = [52, 12, 12, 22, 24, 22, 24]  # widths
    headers = ["Material", "m2", "Mon", "Precio unit", "Subtotal", "Descuento", "Total neto"]
    for i, h in enumerate(headers):
        pdf.cell(mw[i], 5, h, align="R" if i > 0 else "L")
    pdf.ln()
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(1)

    pdf.set_font("Helvetica", "", 8)
    for m in data["materials"]:
        cur = m["currency"]
        sym = "USD " if cur == "USD" else "$"
        pdf.cell(mw[0], 5, m["name"][:30])
        pdf.cell(mw[1], 5, _fmt_num(m["m2"]), align="R")
        pdf.cell(mw[2], 5, cur, align="R")
        pdf.cell(mw[3], 5, f"{sym}{_fmt_num(m['price_unit'], 0)}", align="R")
        pdf.cell(mw[4], 5, f"{sym}{_fmt_num(m['subtotal'], 0)}", align="R")
        if m["discount_pct"]:
            pdf.cell(mw[5], 5, f"-{sym}{_fmt_num(m['discount_amount'], 0)}", align="R")
        else:
            pdf.cell(mw[5], 5, "-", align="R")
        pdf.cell(mw[6], 5, f"{sym}{_fmt_num(m['net'], 0)}", align="R")
        pdf.ln()

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    if data["total_mat_ars"]:
        pdf.cell(0, 5, f"Total materiales ARS: ${_fmt_num(data['total_mat_ars'], 0)}", new_x="LMARGIN", new_y="NEXT")
    if data["total_mat_usd"]:
        pdf.cell(0, 5, f"Total materiales USD: USD {_fmt_num(data['total_mat_usd'], 0)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── 2. MO table ──
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "MANO DE OBRA GLOBAL", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    ow = [80, 25, 35, 35]
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(ow[0], 5, "Concepto")
    pdf.cell(ow[1], 5, "Cantidad", align="R")
    pdf.cell(ow[2], 5, "Precio c/IVA", align="R")
    pdf.cell(ow[3], 5, "Total", align="R")
    pdf.ln()
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(1)

    pdf.set_font("Helvetica", "", 8)
    for mo in data["mo_items"]:
        qty = mo.get("qty", 1)
        qty_str = _fmt_num(qty, 2) if isinstance(qty, float) else str(qty)
        pdf.cell(ow[0], 5, mo.get("desc", ""))
        pdf.cell(ow[1], 5, qty_str, align="R")
        pdf.cell(ow[2], 5, f"${_fmt_num(mo.get('price', 0), 0)}", align="R")
        pdf.cell(ow[3], 5, f"${_fmt_num(mo.get('total', 0), 0)}", align="R")
        pdf.ln()

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, f"Total mano de obra ARS: ${_fmt_num(data['mo_total'], 0)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── 3. Grand totals ──
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "TOTALES GENERALES DEL PROYECTO", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 9)
    if data["total_mat_ars"]:
        pdf.cell(0, 5, f"Total materiales ARS: ${_fmt_num(data['total_mat_ars'], 0)}", new_x="LMARGIN", new_y="NEXT")
    if data["total_mat_usd"]:
        pdf.cell(0, 5, f"Total materiales USD: USD {_fmt_num(data['total_mat_usd'], 0)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Total mano de obra ARS: ${_fmt_num(data['mo_total'], 0)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, f"TOTAL FINAL ARS: ${_fmt_num(data['grand_total_ars'], 0)}", new_x="LMARGIN", new_y="NEXT")
    if data["grand_total_usd"]:
        pdf.cell(0, 6, f"TOTAL FINAL USD: USD {_fmt_num(data['grand_total_usd'], 0)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── 4. Clarification ──
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 4, "Este documento resume el total consolidado de la obra.", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "Ademas, se emiten presupuestos individuales por material:", new_x="LMARGIN", new_y="NEXT")
    for name in data.get("material_names", []):
        pdf.cell(0, 4, f"  - {name}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ── 5. Conditions ──
    pdf.set_font("Helvetica", "", 7)
    pdf.multi_cell(180, 3.5, "Forma de pago: Contado", new_x="LMARGIN", new_y="NEXT")
    if co.get("conditions_general"):
        pdf.multi_cell(180, 3.5, co["conditions_general"].strip(), new_x="LMARGIN", new_y="NEXT")
    if co.get("conditions_payment"):
        pdf.ln(1)
        pdf.multi_cell(180, 3.5, co["conditions_payment"].strip(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(180, 4, "No se suben mesadas que no entren en ascensor", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))


def _generate_resumen_obra_excel(excel_path: Path, data: dict) -> None:
    """Generate consolidated project summary Excel — one sheet, mirrors PDF."""
    import openpyxl
    from openpyxl.styles import Font, Alignment
    from app.modules.quote_engine.edificio_parser import _fmt_num

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumen Obra"

    bold = Font(name="Calibri", bold=True, size=10)
    bold_big = Font(name="Calibri", bold=True, size=12)
    normal = Font(name="Calibri", size=10)
    small = Font(name="Calibri", size=9)
    italic = Font(name="Calibri", italic=True, size=9)
    ars_fmt = '"$"#,##0'

    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 16
    ws.column_dimensions["G"].width = 16

    r = 1
    ws.cell(r, 1, "D'ANGELO MARMOLERIA").font = Font(name="Calibri", bold=True, size=14)
    r = 3
    ws.cell(r, 1, f"Cliente: {data['client_name']}").font = bold
    ws.cell(r, 4, "Forma de pago: CONTADO EFVO").font = normal
    r = 4
    ws.cell(r, 1, f"Proyecto: {data['project']}").font = bold
    ws.cell(r, 4, "Fecha de entrega: Segun cronograma de obra").font = normal
    r = 5
    ws.cell(r, 1, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}").font = normal
    r = 7
    ws.cell(r, 1, "RESUMEN GENERAL DE OBRA").font = bold_big

    # Materials table
    r = 9
    for ci, h in enumerate(["Material", "m2", "Moneda", "Precio unit", "Subtotal", "Descuento", "Total neto"], 1):
        ws.cell(r, ci, h).font = bold
    r = 10
    for m in data["materials"]:
        cur = m["currency"]
        ws.cell(r, 1, m["name"]).font = normal
        ws.cell(r, 2, m["m2"]).font = normal
        ws.cell(r, 2).number_format = '#,##0.00'
        ws.cell(r, 3, cur).font = normal
        if cur == "USD":
            ws.cell(r, 4, f"USD{m['price_unit']}").font = normal
            ws.cell(r, 5, f"USD{m['subtotal']}").font = normal
            ws.cell(r, 6, f"-USD{m['discount_amount']}" if m['discount_amount'] else "-").font = normal
            ws.cell(r, 7, f"USD{m['net']}").font = bold
        else:
            ws.cell(r, 4, m["price_unit"]).font = normal
            ws.cell(r, 4).number_format = ars_fmt
            ws.cell(r, 5, m["subtotal"]).font = normal
            ws.cell(r, 5).number_format = ars_fmt
            ws.cell(r, 6, -m["discount_amount"] if m["discount_amount"] else 0).font = normal
            ws.cell(r, 6).number_format = ars_fmt
            ws.cell(r, 7, m["net"]).font = bold
            ws.cell(r, 7).number_format = ars_fmt
        r += 1

    r += 1
    if data["total_mat_ars"]:
        ws.cell(r, 1, "Total materiales ARS").font = bold
        ws.cell(r, 7, data["total_mat_ars"]).font = bold
        ws.cell(r, 7).number_format = ars_fmt
        r += 1
    if data["total_mat_usd"]:
        ws.cell(r, 1, "Total materiales USD").font = bold
        ws.cell(r, 7, f"USD{data['total_mat_usd']}").font = bold
        r += 1

    # MO table
    r += 2
    ws.cell(r, 1, "MANO DE OBRA GLOBAL").font = bold_big
    r += 1
    for ci, h in enumerate(["Concepto", "Cantidad", "", "Precio c/IVA", "Total"], 1):
        if h:
            ws.cell(r, ci, h).font = bold
    r += 1
    for mo in data["mo_items"]:
        ws.cell(r, 1, mo.get("desc", "")).font = normal
        ws.cell(r, 2, mo.get("qty", 1)).font = normal
        ws.cell(r, 4, mo.get("price", 0)).font = normal
        ws.cell(r, 4).number_format = ars_fmt
        ws.cell(r, 5, mo.get("total", 0)).font = normal
        ws.cell(r, 5).number_format = ars_fmt
        r += 1

    r += 1
    ws.cell(r, 1, "Total mano de obra ARS").font = bold
    ws.cell(r, 5, data["mo_total"]).font = bold
    ws.cell(r, 5).number_format = ars_fmt

    # Grand totals
    r += 2
    ws.cell(r, 1, "TOTALES GENERALES DEL PROYECTO").font = bold_big
    r += 1
    if data["total_mat_ars"]:
        ws.cell(r, 1, "Total materiales ARS").font = normal
        ws.cell(r, 5, data["total_mat_ars"]).font = normal
        ws.cell(r, 5).number_format = ars_fmt
        r += 1
    if data["total_mat_usd"]:
        ws.cell(r, 1, "Total materiales USD").font = normal
        ws.cell(r, 5, f"USD{data['total_mat_usd']}").font = normal
        r += 1
    ws.cell(r, 1, "Total mano de obra ARS").font = normal
    ws.cell(r, 5, data["mo_total"]).font = normal
    ws.cell(r, 5).number_format = ars_fmt
    r += 1
    ws.cell(r, 1, "TOTAL FINAL ARS").font = bold
    ws.cell(r, 5, data["grand_total_ars"]).font = bold
    ws.cell(r, 5).number_format = ars_fmt
    r += 1
    if data["grand_total_usd"]:
        ws.cell(r, 1, "TOTAL FINAL USD").font = bold
        ws.cell(r, 5, f"USD{data['grand_total_usd']}").font = bold

    # Clarification
    r += 2
    ws.cell(r, 1, "Este documento resume el total consolidado de la obra.").font = italic
    r += 1
    ws.cell(r, 1, "Ademas, se emiten presupuestos individuales por material:").font = italic
    r += 1
    for name in data.get("material_names", []):
        ws.cell(r, 1, f"  - {name}").font = italic
        r += 1

    # Conditions
    r += 1
    ws.cell(r, 1, "Forma de pago: Contado").font = Font(name="Calibri", size=8)

    wb.save(str(excel_path))


def _generate_edificio_pdf(pdf_path: Path, data: dict) -> None:
    """Generate edificio PDF — same D'Angelo look, respects show_mo and grand_total_text."""
    from fpdf import FPDF
    import re as _re

    co = _load_company_config()
    client_name = data.get("client_name", "")
    project = data.get("project", "")
    date_str = datetime.now().strftime("%d/%m/%Y")
    delivery = data.get("delivery_days", "")
    mat_name = data.get("material_name", "")
    mat_m2 = data.get("material_m2", 0)
    mat_price = data.get("material_price_unit", 0)
    currency = data.get("material_currency", "USD")
    discount_pct = data.get("discount_pct", 0)
    sectors = data.get("sectors", [])
    mo_items = data.get("mo_items", [])
    show_mo = data.get("show_mo", len(mo_items) > 0)
    total_ars = data.get("total_ars", 0)
    total_usd = data.get("total_usd", 0)
    grand_text = data.get("grand_total_text", "")
    thickness = data.get("thickness_mm", 20)

    fmt_price = _fmt_usd if currency == "USD" else _fmt_ars

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
        pdf.set_y(12)
        pdf.set_font("Helvetica", "B", 28)
        pdf.cell(0, 12, co["name"], new_x="LMARGIN", new_y="NEXT")

    # Header — same layout as normal template
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"{co['address']} | Tel: {co['phone']} | {co['email']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    col_w = 95
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 5, f"Cliente: {client_name}")
    pdf.cell(col_w, 5, "Forma de pago", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(col_w, 5, "")
    pdf.cell(col_w, 5, "CONTADO EFVO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 5, "Proyecto")
    pdf.cell(col_w, 5, "", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(col_w, 5, project or "")
    pdf.cell(col_w, 5, "", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 5, "")
    pdf.cell(col_w, 5, "Fecha de entrega", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(col_w, 5, "")
    pdf.cell(col_w, 5, str(delivery) or "A CONVENIR", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_draw_color(26, 26, 26)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    # Table header
    w = [92, 22, 38, 38]
    rh = 5
    total_w = sum(w)
    row_n = [0]

    def row_fill():
        fill = row_n[0] % 2 == 1
        if fill:
            pdf.set_fill_color(243, 243, 243)
        return fill

    def row_done():
        row_n[0] += 1

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(w[0], 6, "Descripcion")
    pdf.cell(w[1], 6, "Cantidad", align="R")
    pdf.cell(w[2], 6, "Precio unitario", align="R")
    pdf.cell(w[3], 6, "Precio total", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    # Material row
    mat_total_bruto = data.get("material_total") or round(mat_m2 * mat_price)
    _mat_display = f"{mat_name} - {thickness}mm ESPESOR" if not _re.search(r'\d+[Mm][Mm]', mat_name) else mat_name

    f = row_fill()
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(w[0], rh, _mat_display, fill=f)
    pdf.cell(w[1], rh, _fmt_qty(mat_m2), align="R", fill=f)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(w[2], rh, fmt_price(mat_price), align="R", fill=f)
    pdf.cell(w[3], rh, fmt_price(mat_total_bruto), align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
    row_done()

    # Sectors/despiece — first piece row shows DESC and Total
    is_first_piece = True
    for sector in sectors:
        f = row_fill()
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(total_w, rh, sector.get("label", ""), fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()
        raw_pieces = sector.get("pieces", [])
        grouped = []
        seen = {}
        for p in raw_pieces:
            if p in seen:
                seen[p] += 1
            else:
                seen[p] = 1
                grouped.append(p)
        for piece in grouped:
            count = seen[piece]
            display = f"{piece} (x{count})" if count > 1 else piece
            f = row_fill()
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(w[0], rh, display, fill=f)
            if is_first_piece:
                # Show discount + total net on the first piece row
                pdf.set_font("Helvetica", "I", 8)
                if discount_pct:
                    pdf.cell(w[1], rh, "", fill=f)
                    pdf.cell(w[2], rh, f"DESC {discount_pct}%", align="R", fill=f)
                    disc_amount = round(mat_total_bruto * discount_pct / 100)
                    pdf.cell(w[3], rh, fmt_price(disc_amount), align="R", fill=f)
                    pdf.ln()
                    row_done()
                    # Net total row
                    f = row_fill()
                    pdf.cell(w[0], rh, "", fill=f)
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.cell(w[1], rh, "", fill=f)
                    pdf.cell(w[2], rh, f"Total {currency}", align="R", fill=f)
                    mat_net = mat_total_bruto - disc_amount
                    pdf.cell(w[3], rh, fmt_price(mat_net), align="R", fill=f)
                else:
                    pdf.cell(w[1], rh, "", fill=f)
                    pdf.cell(w[2], rh, f"Total {currency}", align="R", fill=f)
                    pdf.cell(w[3], rh, fmt_price(mat_total_bruto), align="R", fill=f)
                is_first_piece = False
            else:
                pdf.cell(w[1] + w[2] + w[3], rh, "", fill=f)
            pdf.ln()
            row_done()

    pdf.ln(3)

    # MO block — only if show_mo
    if show_mo and mo_items:
        f = row_fill()
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(total_w, rh, "MANO DE OBRA", fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()

        mo_subtotal = 0
        for mo in mo_items:
            f = row_fill()
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(w[0], rh, mo["description"], fill=f)
            pdf.cell(w[1], rh, _fmt_qty(mo["quantity"]), align="R", fill=f)
            pdf.cell(w[2], rh, _fmt_ars(mo["unit_price"]), align="R", fill=f)
            mo_total_line = mo.get("total", round(mo["unit_price"] * mo["quantity"]))
            pdf.cell(w[3], rh, _fmt_ars(mo_total_line), align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
            mo_subtotal += mo_total_line
            row_done()

        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(w[0] + w[1], 5, "")
        pdf.cell(w[2], 5, "TOTAL PESOS", align="R")
        pdf.cell(w[3], 5, _fmt_ars(mo_subtotal), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # Grand total box — use pre-built text from view model
    if grand_text:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_draw_color(26, 26, 26)
        y_box = pdf.get_y()
        pdf.rect(10, y_box, 190, 8)
        pdf.set_xy(10, y_box + 1.5)
        pdf.cell(190, 5, grand_text, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)

    # Conditions — use multi_cell for wrapping long lines
    pdf.set_font("Helvetica", "", 7)
    pdf.multi_cell(180, 3.5, "Forma de pago: Contado", new_x="LMARGIN", new_y="NEXT")
    if co.get("conditions_general"):
        pdf.multi_cell(180, 3.5, co["conditions_general"].strip(), new_x="LMARGIN", new_y="NEXT")
    if co.get("conditions_payment"):
        pdf.ln(1)
        pdf.multi_cell(180, 3.5, co["conditions_payment"].strip(), new_x="LMARGIN", new_y="NEXT")

    # Footer
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(180, 4, "No se suben mesadas que no entren en ascensor", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))


def _generate_edificio_excel(excel_path: Path, data: dict) -> None:
    """Generate edificio Excel — same D'Angelo template, respects show_mo."""
    import openpyxl

    TEMPLATE = TEMPLATES_DIR / "excel" / "quote-template-excel.xlsx"
    if not TEMPLATE.exists():
        TEMPLATE = TEMPLATES_DIR / "excel" / "quote-template.xlsx"
    wb = openpyxl.load_workbook(str(TEMPLATE))
    ws = wb.active

    # Unmerge all cells
    for mc in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(mc))

    from openpyxl.styles import Font
    bold = Font(name="Calibri", bold=True, size=10)
    normal = Font(name="Calibri", bold=False, size=10)
    ars_fmt = '"$"#,##0'
    qty_fmt = '#,##0.00'

    client_name = data.get("client_name", "")
    project = data.get("project", "")
    date_str = datetime.now().strftime("%d/%m/%Y")
    delivery = data.get("delivery_days", "A CONVENIR")
    mat_name = data.get("material_name", "")
    mat_m2 = data.get("material_m2", 0)
    mat_price = data.get("material_price_unit", 0)
    currency = data.get("material_currency", "USD")
    discount_pct = data.get("discount_pct", 0)
    sectors = data.get("sectors", [])
    mo_items = data.get("mo_items", [])
    show_mo = data.get("show_mo", len(mo_items) > 0)
    total_ars = data.get("total_ars", 0)
    total_usd = data.get("total_usd", 0)
    grand_text = data.get("grand_total_text", "")
    thickness = data.get("thickness_mm", 20)
    import re as _re

    # Header
    ws["A13"].value = f"Fecha: {date_str}"
    ws["A15"].value = f"Cliente: {client_name}"
    ws["D15"].value = "Forma de pago"
    ws["D16"].value = "CONTADO EFVO"
    ws["A17"].value = "Proyecto"
    ws["A18"].value = project
    ws["D18"].value = "Fecha de entrega"
    ws["D19"].value = delivery

    # Clear dynamic rows
    max_clear = 40 + max(0, len(mo_items))
    for row in range(22, max_clear + 1):
        for col in range(1, 7):
            ws.cell(row, col).value = None

    # Row 22: column headers
    ws["A22"].value = "Descripcion"
    ws["A22"].font = bold
    ws["D22"].value = "Cantidad"
    ws["D22"].font = bold
    ws["E22"].value = "Precio unitario"
    ws["E22"].font = bold
    ws["F22"].value = "Precio total"
    ws["F22"].font = bold

    # Row 23: Material
    _mat_display = f"{mat_name} - {thickness}MM ESPESOR" if not _re.search(r'\d+[Mm][Mm]', mat_name) else mat_name
    mat_total_bruto = data.get("material_total") or round(mat_m2 * mat_price)

    ws["A23"].value = _mat_display
    ws["A23"].font = bold
    ws["D23"].value = mat_m2
    ws["D23"].number_format = qty_fmt
    if currency == "USD":
        ws["E23"].value = f"USD{mat_price}"
        ws["F23"].value = f"USD{mat_total_bruto}"
    else:
        ws["E23"].value = mat_price
        ws["E23"].number_format = ars_fmt
        ws["F23"].value = mat_total_bruto
        ws["F23"].number_format = ars_fmt

    # Row 24+: Sectors/despiece + discount/total
    r = 24
    first_piece = True
    for sector in sectors:
        ws.cell(r, 1).value = sector.get("label", "")
        ws.cell(r, 1).font = bold
        r += 1
        for piece in sector.get("pieces", []):
            ws.cell(r, 1).value = piece
            ws.cell(r, 1).font = normal
            if first_piece:
                if discount_pct:
                    ws.cell(r, 5).value = f"DESC {discount_pct}%"
                    ws.cell(r, 5).font = Font(name="Calibri", italic=True, size=10)
                    disc = round(mat_total_bruto * discount_pct / 100)
                    if currency == "USD":
                        ws.cell(r, 6).value = f"USD{disc}"
                    else:
                        ws.cell(r, 6).value = disc
                        ws.cell(r, 6).number_format = ars_fmt
                    r += 1
                    ws.cell(r, 5).value = f"Total {currency}"
                    ws.cell(r, 5).font = bold
                    mat_net = mat_total_bruto - disc
                    if currency == "USD":
                        ws.cell(r, 6).value = f"USD{mat_net}"
                    else:
                        ws.cell(r, 6).value = mat_net
                        ws.cell(r, 6).number_format = ars_fmt
                    ws.cell(r, 6).font = bold
                else:
                    ws.cell(r, 5).value = f"Total {currency}"
                    ws.cell(r, 5).font = bold
                    if currency == "USD":
                        ws.cell(r, 6).value = f"USD{mat_total_bruto}"
                    else:
                        ws.cell(r, 6).value = mat_total_bruto
                        ws.cell(r, 6).number_format = ars_fmt
                    ws.cell(r, 6).font = bold
                first_piece = False
            r += 1

    r += 1  # spacer

    # MO block — only if show_mo
    if show_mo and mo_items:
        ws.cell(r, 1).value = "MANO DE OBRA"
        ws.cell(r, 1).font = bold
        r += 1

        mo_start = r
        for mo in mo_items:
            ws.cell(r, 1).value = mo["description"]
            ws.cell(r, 1).font = normal
            ws.cell(r, 4).value = mo["quantity"]
            ws.cell(r, 4).number_format = qty_fmt
            ws.cell(r, 5).value = mo["unit_price"]
            ws.cell(r, 5).number_format = ars_fmt
            mo_t = mo.get("total", round(mo["unit_price"] * mo["quantity"]))
            ws.cell(r, 6).value = mo_t
            ws.cell(r, 6).number_format = ars_fmt
            r += 1

        r += 1
        ws.cell(r, 5).value = "TOTAL PESOS"
        ws.cell(r, 5).font = bold
        ws.cell(r, 6).value = f"=SUM(F{mo_start}:F{mo_start + len(mo_items) - 1})"
        ws.cell(r, 6).number_format = ars_fmt
        ws.cell(r, 6).font = bold

    r += 2  # spacer

    # Grand total
    if grand_text:
        ws.cell(r, 1).value = grand_text
        ws.cell(r, 1).font = bold
        ws.merge_cells(f"A{r}:F{r}")

    wb.save(str(excel_path))
    _inject_locale(str(excel_path))


def _generate_pdf(pdf_path: Path, data: dict) -> None:
    """Generate clean PDF using fpdf2 — matches Excel content."""
    from fpdf import FPDF

    client_name = data.get("client_name", "")
    project = data.get("project", "")
    date_str = datetime.now().strftime("%d/%m/%Y")
    delivery = _normalize_delivery(data.get("delivery_days", ""))
    mat_name = data.get("material_name", "")
    mat_m2 = data.get("material_m2", 0)
    mat_price = data.get("material_price_unit", 0)
    currency = data.get("material_currency", "USD")
    discount_pct = data.get("discount_pct", 0)
    sectors = data.get("sectors", [])
    sinks = data.get("sinks", [])
    mo_items = data.get("mo_items", [])
    total_ars = data.get("total_ars", 0)
    total_usd = data.get("total_usd", 0)

    co = _load_company_config()

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Top bar
    pdf.set_fill_color(26, 47, 94)
    pdf.rect(0, 0, 210, 4, "F")

    # Logo image
    logo_path = TEMPLATES_DIR / "logo-dangelo.png"
    if logo_path.exists():
        pdf.image(str(logo_path), x=10, y=10, w=55)
        pdf.set_y(35)
    else:
        pdf.set_y(12)
        pdf.set_font("Helvetica", "B", 28)
        pdf.cell(0, 12, co["name"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 4, co["subtitle"], new_x="LMARGIN", new_y="NEXT")

    # Contact
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 4, co["address"], new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, co["phone"], new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, co["email"], new_x="LMARGIN", new_y="NEXT")

    # Title
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "Presupuesto", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, f"Fecha: {date_str}", new_x="LMARGIN", new_y="NEXT")

    # Client grid
    pdf.ln(3)
    col_w = 95
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 5, "Cliente:")
    pdf.cell(col_w, 5, "Forma de pago", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 5, client_name)
    pdf.cell(col_w, 5, "Contado", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 5, "Proyecto")
    pdf.cell(col_w, 5, "Fecha de entrega", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 5, project)
    pdf.cell(col_w, 5, str(delivery), new_x="LMARGIN", new_y="NEXT")

    # Separator
    pdf.ln(2)
    pdf.set_draw_color(26, 26, 26)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    # Table header
    w = [92, 22, 38, 38]
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(w[0], 6, "Descripcion")
    pdf.cell(w[1], 6, "Cantidad", align="R")
    pdf.cell(w[2], 6, "Precio unitario", align="R")
    pdf.cell(w[3], 6, "Precio total", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    # Material row — Argentine format
    fmt_price = _fmt_usd if currency == "USD" else _fmt_ars
    price_fmt = fmt_price(mat_price)
    total_mat_bruto = round(mat_m2 * mat_price)
    total_mat_fmt = fmt_price(total_mat_bruto)  # Show BRUTO in header row
    if discount_pct:
        total_mat = round(total_mat_bruto * (1 - discount_pct / 100))
    else:
        total_mat = total_mat_bruto

    # Alternating row helper — continuous counter across ALL content rows
    row_n = [0]
    rh = 5  # row height
    total_w = w[0] + w[1] + w[2] + w[3]

    def row_fill():
        """Returns True and sets gray fill for odd rows."""
        fill = row_n[0] % 2 == 1
        if fill:
            pdf.set_fill_color(243, 243, 243)
        return fill

    def row_done():
        row_n[0] += 1

    # Material header row
    f = row_fill()
    pdf.set_font("Helvetica", "B", 9)
    # Thickness: use from breakdown, skip if name already contains Nmm/NMM
    import re as _re
    _thickness = data.get("thickness_mm", 20)
    _mat_display = f"{mat_name} - {_thickness}mm" if not _re.search(r'\d+[Mm][Mm]', mat_name) else mat_name
    pdf.cell(w[0], rh, _mat_display, fill=f)
    pdf.cell(w[1], rh, _fmt_qty(mat_m2), align="R", fill=f)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(w[2], rh, price_fmt, align="R", fill=f)
    pdf.cell(w[3], rh, total_mat_fmt, align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
    row_done()

    # Sectors + pieces (group duplicates)
    is_first_piece = True
    for sector in sectors:
        f = row_fill()
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(total_w, rh, sector.get("label", ""), fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()
        # Group identical pieces: "1.20 × 3.38 Solía" × 8 → "1.20 × 3.38 Solía (×8)"
        raw_pieces = sector.get("pieces", [])
        grouped = []
        seen = {}
        for p in raw_pieces:
            if p in seen:
                seen[p] += 1
            else:
                seen[p] = 1
                grouped.append(p)
        for piece in grouped:
            count = seen[piece]
            display = f"{piece} (×{count})" if count > 1 else piece
            f = row_fill()
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(w[0], rh, display, fill=f)
            if is_first_piece:
                pdf.set_font("Helvetica", "B", 8)
                if currency == "USD":
                    # Only show material subtotal for imported (USD) materials
                    pdf.cell(w[1], rh, "", fill=f)
                    pdf.cell(w[2], rh, f"TOTAL {currency}", align="R", fill=f)
                    pdf.cell(w[3], rh, total_mat_fmt, align="R", fill=f)
                else:
                    pdf.cell(w[1] + w[2] + w[3], rh, "", fill=f)
                is_first_piece = False
            else:
                pdf.cell(w[1] + w[2] + w[3], rh, "", fill=f)
            pdf.ln()
            row_done()

    # Discount
    if discount_pct:
        f = row_fill()
        desc_amount = round(round(mat_m2 * mat_price) * discount_pct / 100)
        desc_fmt = fmt_price(desc_amount)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(w[0] + w[1], rh, "", fill=f)
        pdf.cell(w[2], rh, f"Descuento {discount_pct}%", align="R", fill=f)
        pdf.cell(w[3], rh, f"- {desc_fmt}", align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()

    # Spacer row
    pdf.ln(3)

    # Sinks
    for sink in sinks:
        f = row_fill()
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(w[0], rh, sink["name"], fill=f)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(w[1], rh, str(sink["quantity"]), align="R", fill=f)
        pdf.cell(w[2], rh, _fmt_ars(sink['unit_price']), align="R", fill=f)
        pdf.cell(w[3], rh, _fmt_ars(sink['unit_price'] * sink['quantity']), align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()

    # Spacer
    pdf.ln(2)

    # MO header
    f = row_fill()
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(total_w, rh, "MANO DE OBRA", fill=f, new_x="LMARGIN", new_y="NEXT")
    row_done()

    # MO items
    for mo in mo_items:
        f = row_fill()
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(w[0], rh, mo["description"], fill=f)
        pdf.cell(w[1], rh, _fmt_qty(mo["quantity"]), align="R", fill=f)
        pdf.cell(w[2], rh, _fmt_ars(mo['unit_price']), align="R", fill=f)
        pdf.cell(w[3], rh, _fmt_ars(round(mo['unit_price'] * mo['quantity'])), align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()

    # Total PESOS
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(w[0] + w[1], 5, "")
    pdf.cell(w[2], 5, "Total PESOS", align="R")
    pdf.cell(w[3], 5, _fmt_ars(total_ars), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # Grand total box
    grand = _format_grand_total(total_ars, total_usd, currency)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_draw_color(26, 26, 26)
    y_box = pdf.get_y()
    pdf.rect(10, y_box, 190, 8)
    pdf.set_xy(10, y_box + 1.5)
    pdf.cell(190, 5, grand, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)

    # Footer note
    pdf.set_font("Helvetica", "BI", 8)
    pdf.cell(0, 4, "No se suben mesadas que no entren en ascensor", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)

    # Conditions (from config.json) — use multi_cell for word wrap
    usable_w = 190  # A4 width (210) minus margins (10+10)
    if co["conditions_general"]:
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(0, 3, "CONDICIONES", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 7)
        for line in co["conditions_general"].split("\n"):
            if line.strip():
                pdf.multi_cell(usable_w, 3, line.strip(), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if co["conditions_payment"]:
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(0, 3, "FORMAS DE PAGO", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 7)
        for line in co["conditions_payment"].split("\n"):
            if line.strip():
                pdf.multi_cell(usable_w, 3, line.strip(), new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))


def _generate_excel(output_path: Path, data: dict) -> None:
    """Generate Excel from template — only replace values, keep all formatting."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side

    TEMPLATE = TEMPLATES_DIR / "excel" / "quote-template.xlsx"
    wb = openpyxl.load_workbook(str(TEMPLATE))
    ws = wb.active

    # Unmerge all cells first to avoid MergedCell write errors
    for mc in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(mc))

    client_name = data.get("client_name", "")
    project = data.get("project", "")
    date_str = datetime.now().strftime("%d/%m/%Y")
    delivery = _normalize_delivery(data.get("delivery_days", ""))
    mat_name = data.get("material_name", "")
    mat_m2 = data.get("material_m2", 0)
    mat_price = data.get("material_price_unit", 0)
    currency = data.get("material_currency", "USD")
    discount_pct = data.get("discount_pct", 0)
    sectors = data.get("sectors", [])
    mo_items = data.get("mo_items", [])
    total_ars = data.get("total_ars", 0)
    total_usd = data.get("total_usd", 0)

    bold = Font(name="Calibri", bold=True, size=10)
    normal = Font(name="Calibri", bold=False, size=10)
    small = Font(name="Calibri", bold=False, size=9)
    right_align = Alignment(horizontal="right")
    center_align = Alignment(horizontal="center")
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    ars_fmt = '"$"#,##0.00'
    qty_fmt = '#,##0.00'

    # Header — replace values, keep template formatting
    ws["A13"].value = f"Fecha: {date_str}"
    ws["A16"].value = client_name
    ws["A18"].value = project
    ws["C19"].value = delivery

    # Material row 22
    total_mat = round(mat_m2 * mat_price)
    total_mat_net = total_mat
    if discount_pct:
        total_mat_net = total_mat - round(total_mat * discount_pct / 100)

    import re as _re_xl
    _thickness_xl = data.get("thickness_mm", 20)
    ws["A22"].value = f"{mat_name} - {_thickness_xl}mm" if not _re_xl.search(r'\d+[Mm][Mm]', mat_name) else mat_name
    ws["D22"].value = mat_m2
    ws["D22"].number_format = qty_fmt
    if currency == "USD":
        ws["E22"].value = f"USD{mat_price}"
        ws["F22"].value = f"USD{total_mat}"  # Bruto (before discount)
    else:
        ws["E22"].value = mat_price
        ws["E22"].number_format = ars_fmt
        ws["F22"].value = total_mat  # Bruto (before discount)
        ws["F22"].number_format = ars_fmt

    # ── ONLY replace .value — NEVER touch .font, .fill, .alignment, .border ──
    # The template has all formatting correct. We just swap the data.

    # Clear values in dynamic rows (23 through max possible output row)
    max_clear = 35 + max(0, len(mo_items) - 4) + 3
    for row in range(23, max_clear + 1):
        for col in range(1, 7):
            ws.cell(row, col).value = None

    # Pieces (group duplicates)
    raw_all = []
    for sector in sectors:
        for piece in sector.get("pieces", []):
            raw_all.append(piece)
    all_pieces = []
    seen_xl = {}
    for p in raw_all:
        if p in seen_xl:
            seen_xl[p] += 1
        else:
            seen_xl[p] = 1
            all_pieces.append(p)
    all_pieces = [f"{p} (×{seen_xl[p]})" if seen_xl[p] > 1 else p for p in all_pieces]

    # Row 23: first piece + TOTAL
    if len(all_pieces) > 0:
        ws.cell(23, 1).value = all_pieces[0]
    # Row 24: second piece + TOTAL USD (template has TOTAL in E24)
    if len(all_pieces) > 1:
        ws.cell(24, 1).value = all_pieces[1]
    if currency == "USD":
        ws.cell(24, 5).value = f"TOTAL {currency}"
        ws.cell(24, 6).value = f"USD{total_mat_net}"
    else:
        # ARS-only: clear template's hardcoded "TOTAL USD" from E24/F24
        ws.cell(24, 5).value = None
        ws.cell(24, 6).value = None
    # Row 25+: remaining pieces
    for i, piece in enumerate(all_pieces[2:], start=25):
        ws.cell(i, 1).value = piece

    # MO items — template has 4 slots (rows 28-31). Insert extra rows if needed.
    MO_HEADER_ROW = 27
    MO_START_ROW = 28
    TEMPLATE_MO_SLOTS = 4
    extra_mo = max(0, len(mo_items) - TEMPLATE_MO_SLOTS)
    if extra_mo > 0:
        ws.insert_rows(MO_START_ROW + TEMPLATE_MO_SLOTS, extra_mo)

    ws.cell(MO_HEADER_ROW, 1).value = "MANO DE OBRA"
    for i, mo in enumerate(mo_items):
        row = MO_START_ROW + i
        ws.cell(row, 1).value = mo["description"]
        ws.cell(row, 4).value = mo["quantity"]
        ws.cell(row, 4).number_format = qty_fmt
        ws.cell(row, 5).value = mo["unit_price"]
        ws.cell(row, 5).number_format = ars_fmt
        ws.cell(row, 6).value = f"=D{row}*E{row}"
        ws.cell(row, 6).number_format = ars_fmt

    # Total PESOS — after all MO items
    mo_end_row = MO_START_ROW + len(mo_items) - 1
    total_pesos_row = mo_end_row + 1
    ws.cell(total_pesos_row, 5).value = "Total PESOS"
    ws.cell(total_pesos_row, 5).font = bold
    ws.cell(total_pesos_row, 6).value = f"=SUM(F{MO_START_ROW}:F{mo_end_row})"
    ws.cell(total_pesos_row, 6).number_format = ars_fmt
    ws.cell(total_pesos_row, 6).font = bold

    # Grand total — 3 rows after total pesos (matching template spacing)
    grand_row = total_pesos_row + 3
    grand = _format_grand_total(total_ars, total_usd, currency)
    ws.cell(grand_row, 1).value = grand
    ws.merge_cells(f"A{grand_row}:F{grand_row}")

    wb.save(str(output_path))
    _inject_locale(str(output_path))


def _inject_locale(xlsx_path: str):
    """Inject es_AR locale into xlsx for Google Sheets.

    Modifies xl/workbook.xml to add spreadsheetLocale="es_AR" to <calcPr>,
    and adds SpreadsheetLocale custom property to docProps/custom.xml.
    Both methods together ensure Google Sheets picks up the locale.
    """
    import zipfile, os, re

    custom_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="SpreadsheetLocale">
    <vt:lpwstr>es_AR</vt:lpwstr>
  </property>
</Properties>'''

    try:
        tmp = xlsx_path + ".tmp"
        with zipfile.ZipFile(xlsx_path, 'r') as zin, zipfile.ZipFile(tmp, 'w') as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)

                if item.filename == 'xl/workbook.xml':
                    text = data.decode('utf-8')
                    if '<calcPr' in text and 'spreadsheetLocale' not in text:
                        text = re.sub(
                            r'<calcPr\b',
                            '<calcPr spreadsheetLocale="es_AR"',
                            text,
                        )
                    elif '<calcPr' not in text:
                        text = text.replace(
                            '</workbook>',
                            '<calcPr spreadsheetLocale="es_AR" calcId="191029"/></workbook>',
                        )
                    data = text.encode('utf-8')

                elif item.filename == '[Content_Types].xml':
                    text = data.decode('utf-8')
                    if 'custom-properties' not in text:
                        text = text.replace(
                            '</Types>',
                            '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/></Types>',
                        )
                    data = text.encode('utf-8')

                elif item.filename == '_rels/.rels':
                    text = data.decode('utf-8')
                    if 'custom-properties' not in text:
                        text = text.replace(
                            '</Relationships>',
                            '<Relationship Id="rIdCustom" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/></Relationships>',
                        )
                    data = text.encode('utf-8')

                zout.writestr(item, data)
            zout.writestr('docProps/custom.xml', custom_xml)
        os.replace(tmp, xlsx_path)
    except Exception as e:
        import logging
        logging.warning(f"Could not inject locale into xlsx: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass


def _format_grand_total(total_ars: float, total_usd: float, currency: str) -> str:
    if currency == "USD" and total_usd:
        return f"PRESUPUESTO TOTAL: {_fmt_ars(total_ars)} mano de obra + {_fmt_usd(total_usd)} material"
    return f"PRESUPUESTO TOTAL: {_fmt_ars(total_ars)}"


def generate_comparison_pdf(pdf_path: Path, client_name: str, project: str, quotes_data: list[dict]) -> None:
    """Generate a landscape comparison PDF for multiple material variants."""
    from fpdf import FPDF

    co = _load_company_config()
    date_str = datetime.now().strftime("%d/%m/%Y")
    n = len(quotes_data)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Top bar
    pdf.set_fill_color(26, 47, 94)
    pdf.rect(0, 0, 297, 4, "F")

    # Logo
    logo_path = TEMPLATES_DIR / "logo-dangelo.png"
    if logo_path.exists():
        pdf.image(str(logo_path), x=10, y=10, w=55)
        pdf.set_y(35)
    else:
        pdf.set_y(12)
        pdf.set_font("Helvetica", "B", 28)
        pdf.cell(0, 12, co["name"], new_x="LMARGIN", new_y="NEXT")

    # Contact
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 4, f'{co["address"]}  |  {co["phone"]}  |  {co["email"]}', new_x="LMARGIN", new_y="NEXT")

    # Title
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Comparativo de Presupuestos", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Fecha: {date_str}  |  Cliente: {client_name}  |  Proyecto: {project}", new_x="LMARGIN", new_y="NEXT")

    # Separator
    pdf.ln(3)
    pdf.set_draw_color(26, 26, 26)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(4)

    # Table layout
    label_w = 55
    usable = 277 - label_w  # 297 - 2*10 margins - label
    col_w = usable / n

    # Extract data per variant
    def _mo_total(bd: dict) -> float:
        return sum(m.get("quantity", 0) * m.get("unit_price", 0) for m in bd.get("mo_items", []))

    variants = []
    for bd in quotes_data:
        merma = bd.get("merma", {})
        currency = bd.get("material_currency", "USD")
        fmt_price = _fmt_usd if currency == "USD" else _fmt_ars
        variants.append({
            "material": bd.get("_material") or bd.get("material_name", "—"),
            "currency": currency,
            "price_m2": fmt_price(bd.get("material_price_unit", 0)),
            "m2": _fmt_qty(bd.get("material_m2", 0)) + " m\u00b2",
            "total_mat": fmt_price(bd.get("material_total", 0)),
            "discount": f"{bd.get('discount_pct', 0)}%" if bd.get("discount_pct") else "No aplica",
            "mo_total": _fmt_ars(_mo_total(bd)),
            "merma": merma.get("motivo", "No aplica") if merma else "No aplica",
            "delivery": _normalize_delivery(bd.get("delivery_days", "")),
            "total_ars": bd.get("_total_ars") or bd.get("total_ars", 0),
            "total_usd": bd.get("_total_usd") or bd.get("total_usd", 0),
        })

    # Find cheapest by total_usd (or total_ars if no USD)
    best_idx = 0
    best_val = float("inf")
    for i, v in enumerate(variants):
        val = v["total_usd"] if v["total_usd"] else v["total_ars"]
        if val and val < best_val:
            best_val = val
            best_idx = i

    # Header row — material names
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(26, 47, 94)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(label_w, 8, "", fill=True)
    for i, v in enumerate(variants):
        pdf.cell(col_w, 8, v["material"][:30], align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    # Rows definition
    rows = [
        ("Precio / m\u00b2", "price_m2"),
        ("Superficie", "m2"),
        ("Total Material", "total_mat"),
        ("Descuento", "discount"),
        ("Mano de Obra", "mo_total"),
        ("Merma", "merma"),
        ("Plazo de entrega", "delivery"),
    ]

    row_counter = 0
    for label, key in rows:
        is_odd = row_counter % 2 == 0
        if is_odd:
            pdf.set_fill_color(242, 242, 242)
        else:
            pdf.set_fill_color(255, 255, 255)

        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(label_w, 7, label, fill=True)
        pdf.set_font("Helvetica", "", 9)
        for v in variants:
            pdf.cell(col_w, 7, str(v[key])[:35], align="C", fill=True)
        pdf.ln()
        row_counter += 1

    # Total rows — highlighted
    pdf.ln(2)
    pdf.set_draw_color(26, 47, 94)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(2)

    for total_label, total_key, fmt_fn in [
        ("TOTAL ARS", "total_ars", _fmt_ars),
        ("TOTAL USD", "total_usd", _fmt_usd),
    ]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(label_w, 9, total_label)
        for i, v in enumerate(variants):
            val = v[total_key]
            text = fmt_fn(val) if val else "—"
            if i == best_idx:
                pdf.set_text_color(0, 128, 0)
            pdf.cell(col_w, 9, text, align="C")
            pdf.set_text_color(0, 0, 0)
        pdf.ln()

    # Best option indicator
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(0, 128, 0)
    best_name = variants[best_idx]["material"]
    pdf.cell(0, 5, f"* Opcion mas economica: {best_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # Footer conditions (from config.json)
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 7)
    if co["conditions_general"]:
        for line in co["conditions_general"].split("\n"):
            if line.strip():
                pdf.cell(0, 3, line.strip(), new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))
