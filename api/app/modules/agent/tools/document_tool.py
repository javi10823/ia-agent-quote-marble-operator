import math
import shutil
from pathlib import Path
from datetime import datetime
import asyncio

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

from app.core.static import OUTPUT_DIR


DELIVERY_SUFFIX = "días desde la toma de medidas"
CATALOG_DIR = BASE_DIR / "catalog"

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
        filename_base = f"{prefix}{quote_id[:8]}_{client_name} - {material} - {date_str}"
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
    total_mat = round(mat_m2 * mat_price)
    if discount_pct:
        total_mat = round(total_mat * (1 - discount_pct / 100))
    total_mat_fmt = fmt_price(total_mat)

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
    pdf.cell(w[0], rh, f"{mat_name} - 20mm", fill=f)
    pdf.cell(w[1], rh, _fmt_qty(mat_m2), align="R", fill=f)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(w[2], rh, price_fmt, align="R", fill=f)
    pdf.cell(w[3], rh, total_mat_fmt, align="R", fill=f, new_x="LMARGIN", new_y="NEXT")
    row_done()

    # Sectors + pieces
    is_first_piece = True
    for sector in sectors:
        f = row_fill()
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(total_w, rh, sector.get("label", ""), fill=f, new_x="LMARGIN", new_y="NEXT")
        row_done()
        for piece in sector.get("pieces", []):
            f = row_fill()
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(w[0], rh, piece, fill=f)
            if is_first_piece:
                pdf.set_font("Helvetica", "B", 8)
                pdf.cell(w[1], rh, "", fill=f)
                pdf.cell(w[2], rh, f"TOTAL {currency}", align="R", fill=f)
                pdf.cell(w[3], rh, total_mat_fmt, align="R", fill=f)
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

    ws["A22"].value = f"{mat_name} - 20mm"
    ws["D22"].value = mat_m2
    ws["D22"].number_format = qty_fmt
    if currency == "USD":
        ws["E22"].value = f"USD{mat_price}"
        ws["F22"].value = f"USD{total_mat_net}"
    else:
        ws["E22"].value = mat_price
        ws["E22"].number_format = ars_fmt
        ws["F22"].value = total_mat_net
        ws["F22"].number_format = ars_fmt

    # ── ONLY replace .value — NEVER touch .font, .fill, .alignment, .border ──
    # The template has all formatting correct. We just swap the data.

    # Clear only the values in dynamic rows (23-34)
    for row in range(23, 35):
        for col in range(1, 7):
            ws.cell(row, col).value = None

    # Pieces
    all_pieces = []
    for sector in sectors:
        for piece in sector.get("pieces", []):
            all_pieces.append(piece)

    # Row 23: first piece + TOTAL
    if len(all_pieces) > 0:
        ws.cell(23, 1).value = all_pieces[0]
    # Row 24: second piece + TOTAL USD (template has TOTAL in E24)
    if len(all_pieces) > 1:
        ws.cell(24, 1).value = all_pieces[1]
    ws.cell(24, 5).value = f"TOTAL {currency}"
    if currency == "USD":
        ws.cell(24, 6).value = f"USD{total_mat_net}"
    else:
        ws.cell(24, 6).value = total_mat_net
    # Row 25+: remaining pieces
    for i, piece in enumerate(all_pieces[2:], start=25):
        ws.cell(i, 1).value = piece

    # MO items — template rows 27 (header), 28-31 (items), 32 (total)
    ws.cell(27, 1).value = "MANO DE OBRA"
    for i, mo in enumerate(mo_items):
        row = 28 + i
        if row > 31:
            break  # Template only has 4 MO rows
        ws.cell(row, 1).value = mo["description"]
        ws.cell(row, 4).value = mo["quantity"]
        ws.cell(row, 5).value = mo["unit_price"]
        ws.cell(row, 6).value = f"=D{row}*E{row}"

    # Total PESOS — row 32
    mo_end = min(28 + len(mo_items) - 1, 31)
    ws.cell(32, 5).value = "Total PESOS"
    ws.cell(32, 6).value = f"=SUM(F28:F{mo_end})"

    # Grand total — row 35
    grand = _format_grand_total(total_ars, total_usd, currency)
    ws.cell(35, 1).value = grand
    ws.merge_cells("A35:F35")

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
    return f"PRESUPUESTO TOTAL: {_fmt_ars(total_ars)} mano de obra + material"


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
