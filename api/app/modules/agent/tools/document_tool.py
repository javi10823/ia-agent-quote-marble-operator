import math
import shutil
from pathlib import Path
from datetime import datetime
import asyncio

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

EXCEL_REFERENCE = TEMPLATES_DIR / "excel" / "quote-template-reference.xlsx"

DELIVERY_SUFFIX = "días desde la toma de medidas"


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

        # Generate both in thread pool (sync I/O — fpdf2, openpyxl)
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
        pdf.cell(0, 12, "D'ANGELO", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 4, "MARMOLERIA", new_x="LMARGIN", new_y="NEXT")

    # Contact
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 4, "SAN NICOLAS 1160", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "341-3082996", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "marmoleriadangelo@gmail.com", new_x="LMARGIN", new_y="NEXT")

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

    # Conditions
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(0, 3, "*COTIZACION OFICIAL: dolar venta banco nacion. Los materiales expresados en dolares se pagan en pesos segun la cotizacion del dia.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(0, 3, "CONDICIONES", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    for line in [
        "*PRESUPUESTO SUJETO A VARIACION DE PRECIO",
        "*MATERIALES IMPORTADOS SEGUN COTIZACION DOLAR VENTA BANCO NACION AL MOMENTO DE LA CONFIRMACION",
        "*LA TOMA DE MEDIDAS NO PODRA SUPERAR LOS 30 DIAS DESDE LA CONFIRMACION, CASO CONTRARIO EL 20% RESTANTE SE ACTUALIZARA SEGUN INDICE LA CONSTRUCCION",
        "*PRESUPUESTO DEFINITIVO SEGUN MEDIDAS TOMADAS EN OBRA",
        "*LOS PRECIOS INCLUYEN IVA",
    ]:
        pdf.cell(0, 3, line, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(0, 3, "FORMAS DE PAGO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    for line in [
        "*Materiales Importados: 80% sena, 20% restante contra entrega (cotizacion dolar venta BCO NACION).",
        "*Materiales Nacionales: 80% sena, 20% restante contra entrega.",
        "Pago contado / transferencia / debito / credito / cheques 15 dias para importados y 30 dias para nacionales",
    ]:
        pdf.cell(0, 3, line, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(1)
    pdf.cell(0, 3, "TARJETAS DE CREDITO CONSULTAR PLANES", new_x="LMARGIN", new_y="NEXT")

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
                    # Add spreadsheetLocale to calcPr if it exists
                    if '<calcPr' in text and 'spreadsheetLocale' not in text:
                        text = re.sub(
                            r'<calcPr\b',
                            '<calcPr spreadsheetLocale="es_AR"',
                            text,
                        )
                    elif '<calcPr' not in text:
                        # Add calcPr before </workbook>
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


def _build_html(data: dict) -> str:
    """Build HTML for WeasyPrint PDF generation."""
    client_name = data["client_name"]
    project = data.get("project", "")
    date_str = datetime.now().strftime("%d.%m.%Y")
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

    price_fmt = f"USD {mat_price:,}" if currency == "USD" else f"${mat_price:,}"
    total_mat = round(mat_m2 * mat_price)
    if discount_pct:
        total_mat = round(total_mat * (1 - discount_pct / 100))
    total_mat_fmt = f"USD {total_mat:,}" if currency == "USD" else f"${total_mat:,}"

    # Build rows
    rows = ""
    rows += f'<tr class="row-mat"><td>{mat_name} - 20mm</td><td class="right">{mat_m2:.2f}</td><td class="right">{price_fmt}</td><td class="right">{price_fmt}</td></tr>\n'

    for s_idx, sector in enumerate(sectors):
        rows += f'<tr class="row-piece"><td><strong>{sector["label"]}</strong></td><td></td><td></td><td></td></tr>\n'
        for p_idx, piece in enumerate(sector.get("pieces", [])):
            if s_idx == 0 and p_idx == 0:
                rows += f'<tr class="row-piece"><td>{piece}</td><td></td><td class="right"><strong>TOTAL {currency}</strong></td><td class="right"><strong>{total_mat_fmt}</strong></td></tr>\n'
            else:
                rows += f'<tr class="row-piece"><td>{piece}</td><td></td><td></td><td></td></tr>\n'

    if discount_pct:
        desc_amount = round(round(mat_m2 * mat_price) * discount_pct / 100)
        desc_fmt = fmt_price(desc_amount)
        rows += f'<tr class="row-desc"><td></td><td></td><td class="right"><em>Descuento {discount_pct}%</em></td><td class="right">- {desc_fmt}</td></tr>\n'

    rows += '<tr class="row-spacer"><td colspan="4"></td></tr>\n'

    for sink in sinks:
        sp = f"${sink['unit_price']:,}"
        st = f"${sink['unit_price'] * sink['quantity']:,}"
        rows += f'<tr class="row-mat"><td>{sink["name"]}</td><td class="right">{sink["quantity"]}</td><td class="right">{sp}</td><td class="right">{st}</td></tr>\n'

    rows += '<tr class="row-spacer"><td colspan="4"></td></tr>\n'
    rows += '<tr class="row-mo-header"><td colspan="4">MANO DE OBRA</td></tr>\n'

    total_pesos = total_ars
    for mo in mo_items:
        mop = f"${mo['unit_price']:,}"
        mot = f"${round(mo['unit_price'] * mo['quantity']):,}"
        rows += f'<tr class="row-labor"><td>{mo["description"]}</td><td class="right">{mo["quantity"]}</td><td class="right">{mop}</td><td class="right">{mot}</td></tr>\n'

    ars_fmt = f"${total_ars:,.0f}".replace(",", ".")
    rows += f'<tr class="row-total-pesos"><td colspan="2"></td><td>Total PESOS</td><td>{ars_fmt}</td></tr>\n'

    grand = _format_grand_total(total_ars, total_usd, currency)

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: sans-serif; font-size: 9pt; color: #1a1a1a; }}
.top-bar {{ background-color: #1a2f5e; height: 8px; width: 100%; }}
.content {{ padding: 12mm 18mm 15mm 18mm; }}
.logo-text {{ font-size: 22pt; font-weight: 700; line-height: 1; }}
.logo-text .sub {{ font-size: 7pt; font-weight: 500; letter-spacing: 0.3em; color: #555; display: block; }}
.contact {{ margin-top: 3mm; font-size: 8pt; line-height: 1.7; }}
h1 {{ font-size: 18pt; font-weight: 700; margin: 3mm 0 1mm; }}
.fecha {{ font-size: 8.5pt; margin-bottom: 3mm; }}
.client-grid {{ display: grid; grid-template-columns: 1fr 1fr; margin: 3mm 0; }}
.client-cell {{ padding: 1mm 0; font-size: 8.5pt; }}
.client-label {{ font-weight: 700; }}
hr {{ border: none; border-top: 1px solid #1a1a1a; margin: 3mm 0; }}
table {{ width: 100%; border-collapse: collapse; }}
thead th {{ font-size: 8.5pt; font-weight: 700; text-align: left; padding: 2mm 0; border-bottom: 1px solid #1a1a1a; }}
thead th.right {{ text-align: right; }}
tbody tr:nth-child(odd) td {{ background-color: #f3f3f3; }}
td {{ padding: 0.3mm 2mm 0.3mm 0; font-size: 8.5pt; }}
.right {{ text-align: right; }}
.row-mat td {{ font-weight: 700; padding-top: 1.5mm; }}
.row-mat td.right {{ font-weight: 400; }}
.row-piece td {{ font-size: 8pt; font-weight: 400; padding: 0.2mm 2mm 0.2mm 0; }}
.row-mo-header td {{ font-weight: 700; padding-top: 1.5mm; }}
.row-labor td {{ font-size: 8.5pt; }}
.row-total-pesos td {{ text-align: right; padding: 1.5mm 2mm; }}
.row-total-pesos td:last-child {{ font-weight: 700; }}
.row-spacer td {{ padding: 2mm 0; }}
.footer-note {{ font-size: 8pt; font-weight: 700; font-style: italic; margin: 3mm 0 2mm; }}
.grand-total {{ border: 1.5px solid #1a1a1a; text-align: center; padding: 3.5mm; font-size: 9pt; font-weight: 700; margin: 4mm 0; }}
.footer {{ font-size: 7.5pt; line-height: 1.6; }}
.footer .bold {{ font-weight: 700; }}
.footer .section {{ margin-top: 2.5mm; }}
@page {{ size: A4; margin: 0; }}
</style></head><body>
<div class="top-bar"></div>
<div class="content">
  <div class="logo-text">D'ANGELO<span class="sub">MARMOLERÍA</span></div>
  <div class="contact">SAN NICOLAS 1160<br>341-3082996<br>marmoleriadangelo@gmail.com</div>
  <h1>Presupuesto</h1>
  <div class="fecha">Fecha: {date_str}</div>
  <div class="client-grid">
    <div class="client-cell"><span class="client-label">Cliente: </span>{client_name}</div>
    <div class="client-cell"><span class="client-label">Forma de pago</span><br>Contado</div>
    <div class="client-cell" style="margin-top:2mm"><span class="client-label">Proyecto: </span>{project}</div>
    <div class="client-cell" style="margin-top:2mm"><span class="client-label">Fecha de entrega</span><br>{delivery}</div>
  </div>
  <hr>
  <table>
    <thead><tr>
      <th style="width:54%">Descripción</th>
      <th class="right" style="width:12%">Cantidad</th>
      <th class="right" style="width:20%">Precio unitario</th>
      <th class="right" style="width:14%">Precio total</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="footer-note">No se suben mesadas que no entren en ascensor</div>
  <div class="grand-total">{grand}</div>
  <div class="footer">
    <p><span class="bold">*COTIZACION OFICIAL:</span> dolar venta banco nacion. Los materiales expresados en dólares se pagan en pesos según la cotizacion del dia.</p>
    <p class="section bold">CONDICIONES</p>
    <p>*PRESUPUESTO SUJETO A VARIACIÓN DE PRECIO</p>
    <p>*MATERIALES IMPORTADOS SEGÚN COTIZACION DOLAR VENTA BANCO NACIÓN AL MOMENTO DE LA CONFIRMACION</p>
    <p>*LA TOMA DE MEDIDAS NO PODRÁ SUPERAR LOS 30 DÍAS DESDE LA CONFIRMACIÓN, CASO CONTRARIO EL 20% RESTANTE SE ACTUALIZARA SEGÚN INDICE LA CONSTRUCCIÓN</p>
    <p>*PRESUPUESTO DEFINITIVO SEGÚN MEDIDAS TOMADAS EN OBRA</p>
    <p>*LOS PRECIOS INCLUYEN IVA</p>
    <p class="section bold">FORMAS DE PAGO</p>
    <p>*Materiales Importados: 80% seña, 20% restante contra entrega (cotización dolar venta BCO NACIÓN).</p>
    <p>*Materiales Nacionales: 80% seña, 20% restante contra entrega.</p>
    <p>Pago contado / transferencia / débito / crédito / cheques 15 días para importados y 30 días para nacionales</p>
    <p class="section">TARJETAS DE CREDITO CONSULTAR PLANES</p>
  </div>
</div>
</body></html>"""
