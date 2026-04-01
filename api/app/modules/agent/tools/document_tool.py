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


async def generate_documents(quote_id: str, quote_data: dict) -> dict:
    """Generate PDF and Excel for a quote."""
    try:
        client_name = quote_data["client_name"]
        material = quote_data.get("material_name", "")
        date_str = quote_data.get("date", datetime.now().strftime("%d.%m.%Y"))
        # Sanitize date: replace / with . to avoid path issues
        date_str = date_str.replace("/", ".")
        # Sanitize filename: remove any remaining invalid characters
        filename_base = f"{client_name} - {material} - {date_str}"
        filename_base = filename_base.replace("/", "-").replace("\\", "-")

        quote_dir = OUTPUT_DIR / quote_id
        quote_dir.mkdir(exist_ok=True)

        pdf_path = quote_dir / f"{filename_base}.pdf"
        excel_path = quote_dir / f"{filename_base}.xlsx"

        # Generate Excel first, then convert to PDF via LibreOffice
        await _generate_excel(excel_path, quote_data)
        await _generate_pdf_from_excel(excel_path, pdf_path)

        return {
            "ok": True,
            "pdf_url": f"/files/{quote_id}/{filename_base}.pdf",
            "excel_url": f"/files/{quote_id}/{filename_base}.xlsx",
            "filename_base": filename_base,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _generate_pdf_from_excel(excel_path: Path, pdf_path: Path) -> None:
    """Convert Excel to PDF using LibreOffice headless. PDF is identical to Excel."""
    import subprocess
    import logging

    try:
        result = subprocess.run(
            [
                "libreoffice", "--headless", "--calc",
                "--convert-to", "pdf",
                "--outdir", str(pdf_path.parent),
                str(excel_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logging.warning(f"LibreOffice PDF conversion failed: {result.stderr}")
        else:
            logging.info(f"PDF generated from Excel: {pdf_path}")
    except FileNotFoundError:
        logging.warning("LibreOffice not installed — PDF not generated (Excel only)")
    except subprocess.TimeoutExpired:
        logging.warning("LibreOffice PDF conversion timed out")


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
    date_str = data.get("date", datetime.now().strftime("%d.%m.%Y"))
    delivery = data.get("delivery_days", "40 días desde la toma de medidas")
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

    # Material row 23
    ws["A23"].value = f"{mat_name} - 20mm"; ws["A23"].font = bold
    ws["D23"].value = mat_m2; ws["D23"].font = normal
    ws["D23"].number_format = "0.00"; ws["D23"].alignment = right
    ws["E23"].value = mat_price; ws["E23"].font = normal; ws["E23"].alignment = right
    ws["F23"].value = "=D23*E23"; ws["F23"].font = normal; ws["F23"].alignment = right

    if currency == "USD":
        ws["E23"].number_format = '"USD "#,##0'
        ws["F23"].number_format = '"USD "#,##0'
    else:
        ws["E23"].number_format = "$#,##0"
        ws["F23"].number_format = "$#,##0"

    # Sectors + pieces starting row 24
    r = 24
    first_piece_row = None
    for s_idx, sector in enumerate(sectors):
        ws.cell(r, 1).value = sector["label"]
        ws.cell(r, 1).font = bold_small
        r += 1
        for p_idx, piece in enumerate(sector.get("pieces", [])):
            # First piece gets TOTAL in E/F
            is_first = (s_idx == 0 and p_idx == 0)
            ws.cell(r, 1).value = piece
            ws.cell(r, 1).font = small
            if is_first:
                first_piece_row = r
                ws.cell(r, 5).value = f"TOTAL {currency}"
                ws.cell(r, 5).font = bold; ws.cell(r, 5).alignment = right
                total_mat = round(mat_m2 * mat_price)
                if discount_pct:
                    total_mat = round(total_mat * (1 - discount_pct / 100))
                ws.cell(r, 6).value = total_mat
                ws.cell(r, 6).font = bold; ws.cell(r, 6).alignment = right
                if currency == "USD":
                    ws.cell(r, 6).number_format = '"USD "#,##0'
                else:
                    ws.cell(r, 6).number_format = "$#,##0"
            r += 1

    # Discount row if applicable
    if discount_pct:
        ws.cell(r, 1).value = f"Descuento {discount_pct}%"
        ws.cell(r, 1).font = Font(name="Calibri", italic=True, size=9)
        r += 1

    r += 1  # spacer

    # Sinks
    for i, sink in enumerate(sinks):
        fill = gray_fill if i % 2 == 1 else None
        ws.cell(r, 1).value = sink["name"]; ws.cell(r, 1).font = bold
        ws.cell(r, 4).value = sink["quantity"]; ws.cell(r, 4).font = normal; ws.cell(r, 4).alignment = right
        ws.cell(r, 5).value = sink["unit_price"]; ws.cell(r, 5).font = normal
        ws.cell(r, 5).number_format = "$#,##0"; ws.cell(r, 5).alignment = right
        ws.cell(r, 6).value = f"=D{r}*E{r}"; ws.cell(r, 6).font = normal
        ws.cell(r, 6).number_format = "$#,##0"; ws.cell(r, 6).alignment = right
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
        ws.cell(r, 5).value = mo["unit_price"]; ws.cell(r, 5).font = normal
        ws.cell(r, 5).number_format = "$#,##0"; ws.cell(r, 5).alignment = right
        ws.cell(r, 6).value = f"=D{r}*E{r}"; ws.cell(r, 6).font = normal
        ws.cell(r, 6).number_format = "$#,##0"; ws.cell(r, 6).alignment = right
        if fill:
            for c in range(1, 7): ws.cell(r, c).fill = fill
        r += 1

    # Total PESOS (sinks + MO)
    ws.cell(r, 5).value = "Total PESOS"; ws.cell(r, 5).font = bold; ws.cell(r, 5).alignment = right
    sink_start = mo_start - len(sinks) - 2
    ws.cell(r, 6).value = f"=SUM(F{sink_start}:F{r-1})"
    ws.cell(r, 6).font = bold; ws.cell(r, 6).number_format = "$#,##0"; ws.cell(r, 6).alignment = right
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

    wb.save(str(output_path))


def _format_grand_total(total_ars: float, total_usd: float, currency: str) -> str:
    ars_fmt = f"${total_ars:,.0f}".replace(",", ".")
    if currency == "USD" and total_usd:
        usd_fmt = f"USD {total_usd:,.0f}".replace(",", ".")
        return f"PRESUPUESTO TOTAL: {ars_fmt} mano de obra + {usd_fmt} material"
    return f"PRESUPUESTO TOTAL: {ars_fmt} mano de obra + material"


def _build_html(data: dict) -> str:
    """Build HTML for WeasyPrint PDF generation."""
    client_name = data["client_name"]
    project = data.get("project", "")
    date_str = data.get("date", datetime.now().strftime("%d.%m.%Y"))
    delivery = data.get("delivery_days", "40 días desde la toma de medidas")
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
        desc_fmt = f"USD {desc_amount:,}" if currency == "USD" else f"${desc_amount:,}"
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
