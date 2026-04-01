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
    """Format ARS price: $65.147 (dot for thousands, no decimals)."""
    n = round(value)
    formatted = f"{abs(n):,}".replace(",", ".")
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

        # Generate both in parallel
        await asyncio.gather(
            _generate_excel(excel_path, quote_data),
            _generate_pdf(pdf_path, quote_data),
        )

        return {
            "ok": True,
            "pdf_url": f"/files/{quote_id}/{filename_base}.pdf",
            "excel_url": f"/files/{quote_id}/{filename_base}.xlsx",
            "filename_base": filename_base,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _generate_pdf(pdf_path: Path, data: dict) -> None:
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


async def _generate_excel(output_path: Path, data: dict) -> None:
    """Generate Excel based on validated reference template."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill

    if EXCEL_REFERENCE.exists():
        wb = openpyxl.load_workbook(str(EXCEL_REFERENCE))
    else:
        wb = openpyxl.load_workbook(str(TEMPLATES_DIR / "excel" / "quote-template-excel.xlsx"))
        # Unmerge all from row 22 for clean rebuild
        ws = wb.active
        for merged in list(ws.merged_cells.ranges):
            ws.unmerge_cells(str(merged))
        for row in ws.iter_rows(min_row=22, max_row=100):
            for cell in row:
                cell.value = None

    ws = wb.active

    # Clear ALL borders from template to get clean PDF export
    from openpyxl.styles import Border
    no_border = Border()
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=10):
        for cell in row:
            cell.border = no_border

    # Helper fonts
    bold = Font(name="Calibri", bold=True, size=10)
    normal = Font(name="Calibri", bold=False, size=10)
    small = Font(name="Calibri", bold=False, size=9)
    bold_small = Font(name="Calibri", bold=True, size=9)
    bold_italic = Font(name="Calibri", bold=True, italic=True, size=9)
    right = Alignment(horizontal="right")
    left = Alignment(horizontal="left")
    center = Alignment(horizontal="center")

    gray_fill = PatternFill(start_color="F3F3F3", end_color="F3F3F3", fill_type="solid")

    from openpyxl.styles import Border, Side
    thin = Side(style="thin")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

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

    # Header
    ws["A13"].value = f"Fecha: {date_str}"; ws["A13"].font = bold
    ws["A16"].value = client_name; ws["A16"].font = normal
    ws["C16"].value = "Contado"; ws["C16"].font = normal; ws["C16"].alignment = left
    ws["A18"].value = project; ws["A18"].font = normal; ws["A18"].alignment = left
    ws["C18"].value = "Fecha de entrega"; ws["C18"].font = bold
    ws["C19"].value = delivery; ws["C19"].font = normal; ws["C19"].alignment = left

    # Column titles row 22
    for col, title in [(1, "Descripción"), (4, "Cantidad"), (5, "Precio unitario"), (6, "Precio total")]:
        ws.cell(22, col).value = title
        ws.cell(22, col).font = bold
        ws.cell(22, col).alignment = right if col >= 4 else left

    # USD/ARS format helpers
    usd_fmt = '"USD"#.##0'
    ars_fmt = '"$"#.##0,00'
    price_fmt = usd_fmt if currency == "USD" else ars_fmt

    # Material row 23
    total_mat_gross = round(mat_m2 * mat_price)
    ws["A23"].value = mat_name; ws["A23"].font = bold
    ws["D23"].value = mat_m2; ws["D23"].font = normal
    ws["D23"].number_format = "#.##0,00"; ws["D23"].alignment = right
    ws["E23"].value = mat_price; ws["E23"].font = normal; ws["E23"].alignment = right
    ws["E23"].number_format = price_fmt
    ws["F23"].value = total_mat_gross; ws["F23"].font = normal; ws["F23"].alignment = right
    ws["F23"].number_format = price_fmt

    # Pieces starting row 24 (no sector headers — just piece measurements)
    r = 24
    piece_idx = 0
    for s_idx, sector in enumerate(sectors):
        for p_idx, piece in enumerate(sector.get("pieces", [])):
            # Alternating fill
            fill = gray_fill if piece_idx % 2 == 0 else None
            ws.cell(r, 1).value = piece
            ws.cell(r, 1).font = small
            if fill:
                for c in range(1, 7):
                    ws.cell(r, c).fill = fill

            # First piece row: DESCUENTO (if any) and TOTAL USD
            if piece_idx == 0 and discount_pct:
                ws.cell(r, 5).value = f"DESCUENTO {int(discount_pct)} %"
                ws.cell(r, 5).font = Font(name="Calibri", italic=True, size=9)
                ws.cell(r, 5).alignment = right
                discount_amount = round(total_mat_gross * discount_pct / 100)
                ws.cell(r, 6).value = discount_amount
                ws.cell(r, 6).font = normal; ws.cell(r, 6).alignment = right
                ws.cell(r, 6).number_format = price_fmt
                r += 1
                piece_idx += 1
                # Next row: Total USD
                ws.cell(r, 1).value = piece if p_idx == 0 else ""
                ws.cell(r, 1).font = small

            if piece_idx <= 1:
                # Show Total on first or second piece row
                total_mat_net = total_mat_gross - round(total_mat_gross * discount_pct / 100) if discount_pct else total_mat_gross
                ws.cell(r, 5).value = f"Total {currency}"
                ws.cell(r, 5).font = bold; ws.cell(r, 5).alignment = right
                ws.cell(r, 6).value = total_mat_net
                ws.cell(r, 6).font = bold; ws.cell(r, 6).alignment = right
                ws.cell(r, 6).number_format = price_fmt

            r += 1
            piece_idx += 1

    r += 1  # spacer

    # Argentine locale format for ARS
    ars_cell_fmt = '"$"#.##0'

    # Sinks
    for i, sink in enumerate(sinks):
        fill = gray_fill if i % 2 == 1 else None
        ws.cell(r, 1).value = sink["name"]; ws.cell(r, 1).font = bold
        ws.cell(r, 4).value = sink["quantity"]; ws.cell(r, 4).font = normal; ws.cell(r, 4).alignment = right
        ws.cell(r, 5).value = sink["unit_price"]; ws.cell(r, 5).font = normal
        ws.cell(r, 5).number_format = ars_cell_fmt; ws.cell(r, 5).alignment = right
        ws.cell(r, 6).value = f"=D{r}*E{r}"; ws.cell(r, 6).font = normal
        ws.cell(r, 6).number_format = ars_cell_fmt; ws.cell(r, 6).alignment = right
        if fill:
            for c in range(1, 7): ws.cell(r, c).fill = fill
        r += 1

    r += 1  # spacer

    # MO
    ws.cell(r, 1).value = "MANO DE OBRA"; ws.cell(r, 1).font = bold; ws.cell(r, 1).alignment = left
    r += 1
    mo_start = r
    for i, mo in enumerate(mo_items):
        fill = gray_fill if i % 2 == 0 else None
        ws.cell(r, 1).value = mo["description"]; ws.cell(r, 1).font = normal
        ws.cell(r, 4).value = mo["quantity"]; ws.cell(r, 4).font = normal; ws.cell(r, 4).alignment = right
        ws.cell(r, 4).number_format = "#.##0,00"
        ws.cell(r, 5).value = mo["unit_price"]; ws.cell(r, 5).font = normal
        ws.cell(r, 5).number_format = ars_cell_fmt; ws.cell(r, 5).alignment = right
        ws.cell(r, 6).value = f"=D{r}*E{r}"; ws.cell(r, 6).font = normal
        ws.cell(r, 6).number_format = ars_cell_fmt; ws.cell(r, 6).alignment = right
        if fill:
            for c in range(1, 7): ws.cell(r, c).fill = fill
        r += 1

    # Total PESOS (sinks + MO)
    ws.cell(r, 5).value = "Total PESOS"; ws.cell(r, 5).font = bold; ws.cell(r, 5).alignment = right
    sink_start = mo_start - len(sinks) - 2
    ws.cell(r, 6).value = f"=SUM(F{sink_start}:F{r-1})"
    ws.cell(r, 6).font = bold; ws.cell(r, 6).number_format = ars_cell_fmt; ws.cell(r, 6).alignment = right
    r += 2

    # Grand total with border
    grand = _format_grand_total(total_ars, total_usd, currency)
    for col in range(1, 7):
        ws.cell(r, col).border = box
    ws.cell(r, 1).value = grand
    ws.cell(r, 1).font = bold; ws.cell(r, 1).alignment = center
    ws.merge_cells(f"A{r}:F{r}")
    r += 1

    # Footer note
    ws.cell(r, 1).value = "No se suben mesadas que no entren en ascensor"
    ws.cell(r, 1).font = bold_italic
    r += 1

    # Clear any stale borders from template on spacer row
    no_border = Border()
    for col in range(1, 7):
        ws.cell(r, col).border = no_border
    ws.row_dimensions[r].height = 8
    r += 1

    # Conditions footer (same as PDF) — fixed row heights to prevent giant rows
    conditions_font = Font(name="Calibri", size=8)
    conditions_bold = Font(name="Calibri", size=8, bold=True)
    footer_row_height = 14

    ws.cell(r, 1).value = "*COTIZACION OFICIAL: dolar venta banco nacion. Los materiales expresados en dólares se pagan en pesos según la cotizacion del dia."
    ws.cell(r, 1).font = conditions_font
    ws.row_dimensions[r].height = footer_row_height
    r += 1
    ws.row_dimensions[r].height = 8  # small spacer
    r += 1

    ws.cell(r, 1).value = "CONDICIONES"
    ws.cell(r, 1).font = conditions_bold
    ws.row_dimensions[r].height = footer_row_height
    r += 1

    for line in [
        "*PRESUPUESTO SUJETO A VARIACIÓN DE PRECIO",
        "*MATERIALES IMPORTADOS SEGÚN COTIZACION DOLAR VENTA BANCO NACIÓN AL MOMENTO DE LA CONFIRMACION",
        "*LA TOMA DE MEDIDAS NO PODRÁ SUPERAR LOS 30 DÍAS DESDE LA CONFIRMACIÓN, CASO CONTRARIO EL 20% RESTANTE SE ACTUALIZARA SEGÚN INDICE LA CONSTRUCCIÓN",
        "*PRESUPUESTO DEFINITIVO SEGÚN MEDIDAS TOMADAS EN OBRA",
        "*LOS PRECIOS INCLUYEN IVA",
    ]:
        ws.cell(r, 1).value = line
        ws.cell(r, 1).font = conditions_font
        ws.row_dimensions[r].height = footer_row_height
        r += 1

    ws.row_dimensions[r].height = 8  # small spacer
    r += 1
    ws.cell(r, 1).value = "FORMAS DE PAGO"
    ws.cell(r, 1).font = conditions_bold
    ws.row_dimensions[r].height = footer_row_height
    r += 1

    for line in [
        "*Materiales Importados: 80% seña, 20% restante contra entrega (cotización dolar venta BCO NACIÓN).",
        "*Materiales Nacionales: 80% seña, 20% restante contra entrega.",
        "Pago contado / transferencia / débito / crédito / cheques 15 días para importados y 30 días para nacionales",
    ]:
        ws.cell(r, 1).value = line
        ws.cell(r, 1).font = conditions_font
        ws.row_dimensions[r].height = footer_row_height
        r += 1

    ws.row_dimensions[r].height = 8  # small spacer
    r += 1
    ws.cell(r, 1).value = "TARJETAS DE CREDITO CONSULTAR PLANES"
    ws.cell(r, 1).font = conditions_font
    ws.row_dimensions[r].height = footer_row_height

    # Column widths
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 5
    ws.column_dimensions["C"].width = 5
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 22
    ws.column_dimensions["F"].width = 18

    # Print settings — so PDF export looks clean (no gridlines, proper margins)
    from openpyxl.worksheet.views import SheetView
    from openpyxl.worksheet.page import PageMargins

    ws.views.sheetView[0].showGridLines = False
    ws.print_area = f"A1:F{r}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(
        left=0.5, right=0.5, top=0.4, bottom=0.4,
        header=0.2, footer=0.2,
    )

    # Force Argentine locale in Excel/Google Sheets
    # Custom XML property: SpreadsheetLocale = es_AR
    from openpyxl.packaging.core import DocumentProperties
    wb.properties = DocumentProperties()
    wb.properties.language = "es-AR"

    # Add custom doc property for Google Sheets locale detection
    from openpyxl.xml.functions import Element, SubElement
    import copy
    try:
        # Set calcPr to force locale interpretation
        from openpyxl.workbook.properties import CalcProperties
        wb.calculation = CalcProperties(calcId=191029)
    except Exception:
        pass

    wb.save(str(output_path))

    # Post-process: inject SpreadsheetLocale into docProps/custom.xml
    # This forces Google Sheets to use Argentine locale
    import zipfile, io, shutil as shutil_mod
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
