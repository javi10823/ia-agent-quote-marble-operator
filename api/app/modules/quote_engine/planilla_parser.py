"""Deterministic parser for planilla de marmolería PDFs.

Extracts structured data from the characteristics table on the right side
of planilla PDFs (UBICACIÓN, MATERIAL, ESPESOR, CANTOS, PILETA, etc.)
and separates it from the drawing on the left side.

This module does NOT use any LLM — all parsing is deterministic.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PlanillaData:
    """Structured data extracted from a planilla table."""
    ubicacion: str = ""
    cantidad: int = 1
    material: str = ""
    espesor: str = ""
    cantos: str = ""
    pileta: str = ""
    griferia: str = ""
    zocalos: str = ""
    m2: Optional[float] = None
    m2_raw: str = ""
    notas: list[str] = field(default_factory=list)
    # Table bounding box for cropping
    table_x0: float = 0
    table_y0: float = 0
    table_x1: float = 0
    table_y1: float = 0
    page_width: float = 0
    page_height: float = 0
    # Raw key-value pairs for debugging
    raw_pairs: dict = field(default_factory=dict)


# Common field labels in planilla tables (case-insensitive)
FIELD_ALIASES = {
    "ubicación": "ubicacion",
    "ubicacion": "ubicacion",
    "cantidad": "cantidad",
    "material": "material",
    "espesor": "espesor",
    "cantos": "cantos",
    "pileta": "pileta",
    "griferia": "griferia",
    "grifería": "griferia",
    "zocalos": "zocalos",
    "zócalos": "zocalos",
    "m2": "m2_raw",
    "superficie": "m2_raw",
}


def parse_planilla_table(tables: list, page_width: float = 0, page_height: float = 0,
                          table_bboxes: list = None) -> Optional[PlanillaData]:
    """Parse planilla table into structured data.

    Args:
        tables: List of tables from pdfplumber extract_tables()
        page_width: Page width in points
        page_height: Page height in points
        table_bboxes: List of table bboxes from find_tables()

    Returns:
        PlanillaData if a planilla table is detected, None otherwise.
    """
    if not tables:
        return None

    # Look for a table that has characteristic planilla fields
    for t_idx, table in enumerate(tables):
        if not table or len(table) < 3:
            continue

        # Try to parse as key-value pairs
        # Tables can be 2-col (key, val) or 3-col (empty/drawing, key, val)
        pairs = {}
        for row in table:
            if not row or len(row) < 2:
                continue
            # Try last two non-empty columns as key-value
            non_empty = [(i, str(c or "").strip()) for i, c in enumerate(row) if c and str(c).strip()]
            if len(non_empty) >= 2:
                key = non_empty[-2][1].lower()
                val = non_empty[-1][1]
                if key and val and len(key) < 50:
                    pairs[key] = val
            elif len(non_empty) == 1 and len(row) >= 2:
                # Single value — might be a header row, skip
                pass

        # Check if this looks like a planilla (has at least 3 characteristic fields)
        matched_fields = sum(1 for k in pairs if any(alias in k for alias in FIELD_ALIASES))
        if matched_fields < 3:
            continue

        # Parse into structured data
        data = PlanillaData()
        data.raw_pairs = pairs

        for raw_key, raw_val in pairs.items():
            for alias, field_name in FIELD_ALIASES.items():
                if alias in raw_key:
                    if field_name == "cantidad":
                        try:
                            data.cantidad = int(re.search(r'\d+', raw_val).group())
                        except (ValueError, AttributeError):
                            data.cantidad = 1
                    elif field_name == "m2_raw":
                        data.m2_raw = raw_val
                        # Extract numeric m2 value
                        m2_match = re.search(r'(\d+[.,]\d+)', raw_val)
                        if m2_match:
                            data.m2 = float(m2_match.group(1).replace(",", "."))
                    else:
                        setattr(data, field_name, raw_val)
                    break

        # Store bbox if available
        if table_bboxes and t_idx < len(table_bboxes):
            bbox = table_bboxes[t_idx]
            if hasattr(bbox, 'bbox'):
                bbox = bbox.bbox
            data.table_x0 = bbox[0]
            data.table_y0 = bbox[1]
            data.table_x1 = bbox[2]
            data.table_y1 = bbox[3]

        data.page_width = page_width
        data.page_height = page_height

        # Extract notes from remaining text
        for key, val in pairs.items():
            if key not in FIELD_ALIASES and val and len(val) > 3:
                data.notas.append(f"{key}: {val}")

        logger.info(f"Planilla parsed: material={data.material}, m2={data.m2}, "
                     f"pileta={data.pileta}, zocalos={data.zocalos}")
        return data

    return None


def build_planilla_context(data: PlanillaData) -> str:
    """Build extracted context string from planilla data for Claude.

    This replaces the raw table text with structured, labeled data
    that Claude can use directly without re-interpreting.
    """
    lines = [
        "[DATOS EXTRAÍDOS DE LA PLANILLA — DETERMINÍSTICO, 100% EXACTO]",
        "⛔ Estos datos son la fuente de verdad. NO re-interpretar del dibujo.",
        "",
    ]

    if data.ubicacion:
        lines.append(f"UBICACIÓN: {data.ubicacion}")
    if data.cantidad > 1:
        lines.append(f"CANTIDAD: {data.cantidad}")
    if data.material:
        lines.append(f"MATERIAL: {data.material}")
    if data.espesor:
        lines.append(f"ESPESOR: {data.espesor}")
    if data.cantos:
        lines.append(f"CANTOS: {data.cantos}")
    if data.pileta:
        lines.append(f"PILETA: {data.pileta}")
    if data.griferia:
        lines.append(f"GRIFERÍA: {data.griferia}")
    if data.zocalos:
        lines.append(f"ZÓCALOS: {data.zocalos}")
    if data.m2 is not None:
        lines.append(f"SUPERFICIE TOTAL: {data.m2} m² ({data.m2_raw})")
        lines.append(f"⛔ Tus piezas DEBEN sumar {data.m2} m². Si no coincide, revisá las cotas.")
    if data.notas:
        lines.append("")
        lines.append("NOTAS:")
        for n in data.notas:
            lines.append(f"  - {n}")

    lines.append("")
    lines.append("El DIBUJO adjunto muestra las cotas/medidas de las piezas.")
    lines.append("Usá las cotas del dibujo para largo × ancho de cada pieza.")

    return "\n".join(lines)


def crop_drawing_from_page(page_img, planilla_data: PlanillaData, dpi: int = 200) -> "Image":
    """Crop the drawing area (left side) from a rasterized page.

    Args:
        page_img: PIL Image of the full rasterized page
        planilla_data: PlanillaData with table bbox
        dpi: DPI used for rasterization

    Returns:
        PIL Image of the drawing area only (left of the table)
    """
    if not planilla_data.page_width or not planilla_data.table_x0:
        return page_img  # No bbox info — return full page

    # Scale from page points to pixel coordinates
    scale_x = page_img.width / planilla_data.page_width

    # Table starts at table_x0 — crop everything to the left
    # Add small margin (10px) to avoid cutting into the drawing
    crop_x = int(planilla_data.table_x0 * scale_x) - 10
    crop_x = max(0, min(crop_x, page_img.width - 100))

    drawing = page_img.crop((0, 0, crop_x, page_img.height))
    logger.info(f"Cropped drawing: {page_img.width}x{page_img.height} → {drawing.width}x{drawing.height} "
                f"(table starts at x={planilla_data.table_x0:.0f}, pixel={crop_x})")

    return drawing
