"""Deterministic edificio PDF parser.

Pipeline: raw tables → parse → normalize → aggregate → validate.
Claude never calculates — only formats pre-computed data.
"""
import math
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Types ────────────────────────────────────────────────────────────────────

class DetectionResult(dict):
    """Result of detect_edificio()."""
    pass  # {is_edificio, confidence, reasons}


class RawRow(dict):
    """Raw row from PDF table — strings only, no parsing."""
    pass


class RawSection(dict):
    """Raw section: type + header + rows."""
    pass


class RawEdificioData(dict):
    """Faithful PDF extraction — no business logic."""
    pass


class NormalizedPiece(dict):
    """Piece with parsed types and derived fields."""
    pass


class NormalizedEdificioData(dict):
    """All pieces normalized with derived calculations."""
    pass


class MaterialSummary(dict):
    """Aggregated data for one material."""
    pass


class EdificioSummary(dict):
    """All materials + grand totals."""
    pass


class ValidationResult(dict):
    """Validation outcome with errors/warnings."""
    pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_number(raw: Optional[str]) -> Optional[float]:
    """Parse '2,3' or '2.3' or '1.380' to float. None if unparseable."""
    if not raw or raw.strip() in ("-", "", "None"):
        return None
    try:
        return float(raw.strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_int(raw: Optional[str]) -> Optional[int]:
    """Parse '19' or '2' to int. None if unparseable."""
    if not raw or raw.strip() in ("-", "", "None"):
        return None
    try:
        return int(float(raw.strip().replace(",", ".")))
    except (ValueError, TypeError):
        return None


def _cell_is_empty(cell: Optional[str]) -> bool:
    """Return True if cell is None, '-', empty, or 'None'."""
    if cell is None:
        return True
    s = str(cell).strip()
    return s in ("", "-", "None", "none", "—")


_PERF_REGEX = re.compile(
    r"(\d+)\s*(?:bachas?|piletas?|lavatorios?)",
    re.IGNORECASE,
)
_APOYO_REGEX = re.compile(r"apoy[oa]r?", re.IGNORECASE)

_FALDON_REGEX = re.compile(
    r"[Ff]ald[oó]n\s*(?:de\s*)?(\d+)\s*cm",
    re.IGNORECASE,
)

_SECTION_KEYWORDS = {
    "marmoleria": ["marmolería", "marmoleria", "marmolerías"],
    "umbrales": ["umbrales", "umbral"],
    "alfeizares": ["alfeizares", "alféizares", "alfeizar"],
    "escalones": ["escalones", "escalón", "escalon"],
}


def _detect_section_type(header_row: list[str]) -> Optional[str]:
    """Detect section type from a header/title row."""
    row_text = " ".join(str(c).lower() for c in header_row if c)
    for stype, keywords in _SECTION_KEYWORDS.items():
        if any(kw in row_text for kw in keywords):
            return stype
    return None


def _find_column_index(header: list[str], keywords: list[str]) -> Optional[int]:
    """Find column index by matching keywords in header cells."""
    for i, cell in enumerate(header):
        if cell and any(kw in str(cell).lower() for kw in keywords):
            return i
    return None


# ── 1. detect_edificio ───────────────────────────────────────────────────────

def detect_edificio(user_message: str, tables: list[list[list]]) -> DetectionResult:
    """Detect if PDF is an edificio. Returns structured result with reasons and confidence."""
    reasons = []
    confidence = 0.0

    # Signal 1: operator says "edificio" or similar (strong)
    msg_lower = (user_message or "").lower()
    if any(kw in msg_lower for kw in [
        "edificio", "edificios", "building", "concesionario",
        "departamento", "departamentos", "unidades",
        "torre", "torres", "constructora", "consorcio",
        "obra nueva",
    ]):
        reasons.append("operador indicó edificio en el enunciado")
        confidence += 0.5

    # Signal 2: table has UMBRALES/ESCALONES/ALFEIZARES sections (strong)
    section_types_found = set()
    total_rows = 0
    unique_materials = set()
    for table in tables:
        for row in table:
            row_text = " ".join(str(c).lower() for c in row if c)
            total_rows += 1
            for stype, keywords in _SECTION_KEYWORDS.items():
                if stype != "marmoleria" and any(kw in row_text for kw in keywords):
                    section_types_found.add(stype)
            # Count unique materials
            for cell in row:
                cell_str = str(cell).lower() if cell else ""
                if any(m in cell_str for m in ["negro", "boreal", "brasil", "sahara", "silestone", "dekton", "marmol", "mármol", "granito"]):
                    unique_materials.add(cell_str[:20])

    for stype in section_types_found:
        reasons.append(f"tabla tiene sección {stype.upper()}")
        confidence += 0.3

    # Signal 3: multiple materials in same spreadsheet (medium)
    if len(unique_materials) >= 3:
        reasons.append(f"múltiples materiales detectados ({len(unique_materials)})")
        confidence += 0.3

    # Signal 4: many rows (weak)
    if total_rows > 15:
        reasons.append(f"planilla con {total_rows} filas")
        confidence += 0.2

    return DetectionResult(
        is_edificio=confidence >= 0.5,
        confidence=min(confidence, 1.0),
        reasons=reasons,
    )


# ── 2. parse_edificio_tables ─────────────────────────────────────────────────

def parse_edificio_tables(tables: list[list[list]]) -> RawEdificioData:
    """Parse pdfplumber tables into faithful raw structure. No business logic."""
    sections = []
    free_text_parts = []
    parse_warnings = []
    current_section_type = None

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Check first row for section type
        first_row_type = _detect_section_type(table[0])
        if first_row_type:
            current_section_type = first_row_type

        # Find header row (row with "ID" or "Largo" or similar keywords)
        header_idx = None
        for i, row in enumerate(table):
            row_text = " ".join(str(c).lower() for c in row if c)
            if any(kw in row_text for kw in ["id", "largo", "pieza", "ubicación", "ubicacion"]):
                header_idx = i
                break

        if header_idx is None:
            # Try to extract as free text
            for row in table:
                text = " ".join(str(c).strip() for c in row if c and str(c).strip())
                if text:
                    free_text_parts.append(text)
            continue

        header = [str(c).strip() if c else "" for c in table[header_idx]]

        # Map columns by keywords
        col_id = _find_column_index(header, ["id", "pieza"])
        col_ubicacion = _find_column_index(header, ["ubicación", "ubicacion"])
        col_largo = _find_column_index(header, ["largo"])
        col_ancho = _find_column_index(header, ["ancho"])
        col_superficie = _find_column_index(header, ["superficie", "m2"])
        col_espesor = _find_column_index(header, ["espesor"])
        col_material = _find_column_index(header, ["material", "tipo de material"])
        col_terminacion = _find_column_index(header, ["terminación", "terminacion"])
        col_perforaciones = _find_column_index(header, ["perforac", "calado"])
        col_aclaraciones = _find_column_index(header, ["aclarac", "observ", "nota"])
        col_cantidad = _find_column_index(header, ["cantidad", "cant"])

        rows = []
        for row_idx in range(header_idx + 1, len(table)):
            row = table[row_idx]
            if not row or all(_cell_is_empty(c) for c in row):
                continue

            def _get(col_idx):
                if col_idx is None or col_idx >= len(row):
                    return None
                val = row[col_idx]
                if _cell_is_empty(val):
                    return None
                return str(val).strip()

            raw_id = _get(col_id)
            if not raw_id:
                continue  # Skip rows without ID

            rows.append(RawRow(
                id=raw_id,
                ubicacion=_get(col_ubicacion),
                largo_raw=_get(col_largo),
                ancho_raw=_get(col_ancho),
                superficie_raw=_get(col_superficie),
                espesor_raw=_get(col_espesor),
                material_raw=_get(col_material),
                terminacion_raw=_get(col_terminacion),
                perforaciones_raw=_get(col_perforaciones),
                aclaraciones_raw=_get(col_aclaraciones),
                cantidad_raw=_get(col_cantidad),
            ))

        if rows:
            section_type = current_section_type or first_row_type or "marmoleria"
            sections.append(RawSection(
                type=section_type,
                header=header,
                rows=rows,
            ))

    return RawEdificioData(
        sections=sections,
        free_text="\n".join(free_text_parts),
        parse_warnings=parse_warnings,
    )


# ── 3. normalize_edificio_data ───────────────────────────────────────────────

def _load_material_aliases() -> dict:
    """Load material aliases from config.json (DB or file). Administrable from dashboard."""
    try:
        from app.modules.agent.tools.catalog_tool import _load_catalog
        config = _load_catalog("config")
        if isinstance(config, list) and len(config) == 1:
            config = config[0]
        if isinstance(config, dict):
            return config.get("material_aliases", {})
    except Exception:
        pass
    # Fallback: read from file
    try:
        import json as _json
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent.parent.parent / "catalog" / "config.json"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = _json.load(f)
            return cfg.get("material_aliases", {})
    except Exception:
        pass
    return {}


def normalize_edificio_data(raw: RawEdificioData, material_aliases: dict | None = None) -> NormalizedEdificioData:
    """Parse types + derive calculated fields. Quantity > 1 handled correctly.

    material_aliases: optional dict mapping PDF material names (lowercase) to catalog names.
    If not provided, loads from config.json (administrable from dashboard).
    """
    loaded = material_aliases if material_aliases is not None else _load_material_aliases()
    aliases = {k.lower().strip(): v for k, v in loaded.items()}
    sections = []

    for raw_section in raw.get("sections", []):
        pieces = []
        for raw_row in raw_section.get("rows", []):
            largo = _parse_number(raw_row.get("largo_raw"))
            ancho = _parse_number(raw_row.get("ancho_raw"))
            cantidad = _parse_int(raw_row.get("cantidad_raw")) or 1

            # m² calculation
            m2_calc_unit = round(largo * ancho, 4) if largo and ancho else 0
            m2_calc_total = round(m2_calc_unit * cantidad, 4)
            m2_pdf = _parse_number(raw_row.get("superficie_raw"))

            # Perforaciones parsing
            perf_text = raw_row.get("perforaciones_raw")
            pileta_count = 0
            pileta_type = None
            if perf_text:
                match = _PERF_REGEX.search(perf_text)
                if match:
                    pileta_count = int(match.group(1))
                    pileta_type = "apoyo" if _APOYO_REGEX.search(perf_text) else "empotrada"

            # Aclaraciones parsing
            acl_text = raw_row.get("aclaraciones_raw")
            faldon_cm = None
            faldon_ml_unit = None
            faldon_ml_total = None
            if acl_text:
                match = _FALDON_REGEX.search(acl_text)
                if match:
                    faldon_cm = int(match.group(1))
                    faldon_ml_unit = largo
                    faldon_ml_total = round(largo * cantidad, 2) if largo else None

            # Apply material alias (PDF name → catalog name)
            raw_material = raw_row.get("material_raw")
            resolved_material = aliases.get((raw_material or "").lower().strip(), raw_material)

            pieces.append(NormalizedPiece(
                id=raw_row.get("id"),
                ubicacion=raw_row.get("ubicacion"),
                material=resolved_material,
                material_raw=raw_material,  # preserve original
                terminacion=raw_row.get("terminacion_raw"),
                perforaciones_text=perf_text,
                aclaraciones_text=acl_text,
                largo=largo or 0,
                ancho=ancho or 0,
                espesor_cm=_parse_int(raw_row.get("espesor_raw")),
                cantidad=cantidad,
                m2_calc_unit=m2_calc_unit,
                m2_calc_total=m2_calc_total,
                m2_pdf=m2_pdf,
                pileta_count=pileta_count,
                pileta_type=pileta_type,
                faldon_cm=faldon_cm,
                faldon_ml_unit=faldon_ml_unit,
                faldon_ml_total=faldon_ml_total,
            ))

        sections.append({"type": raw_section.get("type"), "pieces": pieces})

    return NormalizedEdificioData(
        sections=sections,
        free_text=raw.get("free_text", ""),
    )


# ── 4. compute_edificio_aggregates ───────────────────────────────────────────

def compute_edificio_aggregates(data: NormalizedEdificioData) -> EdificioSummary:
    """Deterministic calculation of ALL totals. No approximations."""
    materials: dict[str, MaterialSummary] = {}

    for section in data.get("sections", []):
        for piece in section.get("pieces", []):
            mat = piece.get("material") or "Desconocido"
            if mat not in materials:
                materials[mat] = MaterialSummary(
                    pieces=[],
                    faldon_pieces=[],
                    m2_mesadas=0,
                    m2_faldones=0,
                    m2_total=0,
                    pileta_pegado=0,
                    pileta_apoyo=0,
                    faldon_ml_total=0,
                    piece_count_physical=0,
                )

            ms = materials[mat]
            ms["pieces"].append(piece)

            # m² for mesadas (the actual piece)
            ms["m2_mesadas"] += piece["m2_calc_total"]

            # Physical piece count (multiply by cantidad, exclude faldones)
            ms["piece_count_physical"] += piece["cantidad"]

            # Piletas
            if piece["pileta_type"] == "empotrada":
                ms["pileta_pegado"] += piece["pileta_count"]
            elif piece["pileta_type"] == "apoyo":
                ms["pileta_apoyo"] += piece["pileta_count"]

            # Faldón — generate separate piece for material m²
            if piece["faldon_cm"] is not None and piece["faldon_ml_total"]:
                alto_m = piece["faldon_cm"] / 100
                faldon_m2 = round(piece["faldon_ml_total"] * alto_m, 4)
                ms["faldon_pieces"].append({
                    "id": f"Faldón {piece['id']}",
                    "largo": piece["faldon_ml_total"],
                    "alto": alto_m,
                    "m2": faldon_m2,
                })
                ms["m2_faldones"] += faldon_m2
                ms["faldon_ml_total"] += piece["faldon_ml_total"]

    # Round and compute totals per material
    grand_m2 = 0
    grand_physical = 0
    grand_pegado = 0
    grand_apoyo = 0
    grand_faldon_ml = 0

    for mat, ms in materials.items():
        ms["m2_mesadas"] = round(ms["m2_mesadas"], 2)
        ms["m2_faldones"] = round(ms["m2_faldones"], 3)
        ms["m2_total"] = round(ms["m2_mesadas"] + ms["m2_faldones"], 2)
        ms["faldon_ml_total"] = round(ms["faldon_ml_total"], 2)

        grand_m2 += ms["m2_total"]
        grand_physical += ms["piece_count_physical"]
        grand_pegado += ms["pileta_pegado"]
        grand_apoyo += ms["pileta_apoyo"]
        grand_faldon_ml += ms["faldon_ml_total"]

    grand_m2 = round(grand_m2, 2)
    _per_trip = 8
    try:
        from app.core.company_config import get as _cfg
        _per_trip = _cfg("building.flete_mesadas_per_trip", 8)
    except Exception:
        pass
    flete_qty = math.ceil(grand_physical / _per_trip) if grand_physical > 0 else 1

    return EdificioSummary(
        materials=materials,
        totals={
            "m2_total": grand_m2,
            "pieces_physical_total": grand_physical,
            "flete_qty": flete_qty,
            "pileta_pegado_total": grand_pegado,
            "pileta_apoyo_total": grand_apoyo,
            "faldon_ml_total": round(grand_faldon_ml, 2),
            "descuento_18_aplica": grand_m2 > 15,
        },
    )


# ── 5. validate_edificio ─────────────────────────────────────────────────────

def validate_edificio(data: NormalizedEdificioData, summary: EdificioSummary) -> ValidationResult:
    """Hard validation. Errors block automatic quoting."""
    _per_trip = 8
    try:
        from app.core.company_config import get as _cfg
        _per_trip = _cfg("building.flete_mesadas_per_trip", 8)
    except Exception:
        pass
    errors = []
    warnings = []

    all_ids = []

    for section in data.get("sections", []):
        for piece in section.get("pieces", []):
            pid = piece.get("id", "?")
            all_ids.append(pid)

            # ERROR: invented piletas
            if piece["perforaciones_text"] is None and piece["pileta_count"] > 0:
                errors.append(f"{pid}: pileta_count={piece['pileta_count']} pero perforaciones=null")

            # ERROR: invented faldones
            if piece["aclaraciones_text"] is None and piece["faldon_cm"] is not None:
                errors.append(f"{pid}: faldon_cm={piece['faldon_cm']} pero aclaraciones=null")

            # WARNING: m2_pdf vs m2_calc mismatch
            if piece["m2_pdf"] is not None and abs(piece["m2_pdf"] - piece["m2_calc_unit"]) > 0.02:
                warnings.append(f"{pid}: m2 PDF={piece['m2_pdf']} vs calc={piece['m2_calc_unit']}")

            # WARNING: no ubicacion
            if piece["ubicacion"] is None:
                warnings.append(f"{pid}: sin ubicación en planilla")

            # WARNING: cantidad > 1
            if piece["cantidad"] > 1:
                warnings.append(f"{pid}: cantidad={piece['cantidad']}")

    # ERROR: duplicate IDs per section
    for section in data.get("sections", []):
        ids_in_section = [p["id"] for p in section.get("pieces", [])]
        seen = set()
        for pid in ids_in_section:
            if pid in seen:
                errors.append(f"ID duplicado en sección {section.get('type')}: {pid}")
            seen.add(pid)

    # ERROR: flete mismatch
    totals = summary.get("totals", {})
    expected_flete = math.ceil(totals.get("pieces_physical_total", 0) / _per_trip) if totals.get("pieces_physical_total", 0) > 0 else 1
    if totals.get("flete_qty") != expected_flete:
        errors.append(f"flete: {totals.get('flete_qty')} != ceil({totals.get('pieces_physical_total')}/8)={expected_flete}")

    # ERROR: pileta sum mismatch
    actual_pegado = sum(
        p["pileta_count"] for s in data.get("sections", []) for p in s.get("pieces", [])
        if p.get("pileta_type") == "empotrada"
    )
    actual_apoyo = sum(
        p["pileta_count"] for s in data.get("sections", []) for p in s.get("pieces", [])
        if p.get("pileta_type") == "apoyo"
    )
    if totals.get("pileta_pegado_total") != actual_pegado:
        errors.append(f"PEGADO: summary={totals.get('pileta_pegado_total')} vs sum={actual_pegado}")
    if totals.get("pileta_apoyo_total") != actual_apoyo:
        errors.append(f"APOYO: summary={totals.get('pileta_apoyo_total')} vs sum={actual_apoyo}")

    # ERROR: m² validation by components per material
    for mat, ms in summary.get("materials", {}).items():
        pieces_m2 = sum(p["m2_calc_total"] for p in ms.get("pieces", []))
        faldones_m2 = sum(f["m2"] for f in ms.get("faldon_pieces", []))
        expected_total = round(round(pieces_m2, 2) + round(faldones_m2, 3), 2)
        if abs(ms["m2_total"] - expected_total) > 0.05:
            errors.append(f"{mat}: m2_total={ms['m2_total']} != mesadas({round(pieces_m2,2)}) + faldones({round(faldones_m2,3)}) = {expected_total}")

    is_valid = len(errors) == 0
    needs_review = len(warnings) > 0

    return ValidationResult(
        is_valid=is_valid,
        needs_review=needs_review,
        errors=errors,
        warnings=warnings,
    )


# ── 6. render_edificio_paso1 — deterministic Paso 1 output ──────────────────

def _fmt_num(n, decimals=2) -> str:
    """Format number with Argentine locale (comma decimal, dot thousands)."""
    if n is None:
        return "—"
    rounded = round(n, decimals)
    if decimals == 0 or rounded == int(rounded):
        return f"{int(rounded):,}".replace(",", ".")
    s = f"{rounded:,.{decimals}f}"
    # Swap , and . for Argentine format
    s = s.replace(",", "_TEMP_").replace(".", ",").replace("_TEMP_", ".")
    return s


def render_edificio_paso1(norm: NormalizedEdificioData, summary: dict) -> str:
    """Render Paso 1 output for edificio — 100% deterministic, no LLM involved.

    Produces a commercial-grade markdown block separated by material,
    with correct totals, aliases applied, and MO summary.
    """
    # Known OCR garbage from vertically rotated merged cells in PDFs
    _OCR_GARBAGE = {"AJAB\nATNALP", "ATNALP\nATLA", "AJAB ATNALP", "ATNALP ATLA"}
    _OCR_REPLACEMENTS = {
        "AJAB\nATNALP": "Planta Baja",
        "ATNALP\nATLA": "Planta Alta",
    }

    lines = []
    totals = summary.get("totals", {})
    materials = summary.get("materials", {})

    lines.append("## VERIFICACIÓN EDIFICIO")
    lines.append("")

    for mat_name, mat_data in materials.items():
        m2_total = mat_data.get("m2_total", 0)
        pieces = mat_data.get("pieces", [])
        faldon_pieces = mat_data.get("faldon_pieces", [])

        lines.append(f"### {mat_name.upper()} — {_fmt_num(m2_total)} m²")
        lines.append("")

        # Determine if any piece has cantidad > 1
        has_qty = any(p.get("cantidad", 1) > 1 for p in pieces)
        has_pileta = any(p.get("pileta_count", 0) > 0 for p in pieces)
        has_faldon = any(p.get("faldon_cm") for p in pieces)

        # Header
        cols = ["ID", "Ubicación", "Medida", "m²"]
        if has_qty:
            cols.append("Cant")
        if has_pileta:
            cols.append("Pileta")
        if has_faldon:
            cols.append("Faldón")
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")

        # Rows
        for p in pieces:
            pid = p.get("id", "")
            raw_ubic = p.get("ubicacion") or ""
            ubic = _OCR_REPLACEMENTS.get(raw_ubic, raw_ubic.replace("\n", " ")) or "—"
            largo = p.get("largo", 0)
            ancho = p.get("ancho", 0)
            medida = f"{_fmt_num(largo)} × {_fmt_num(ancho)}"
            cantidad = p.get("cantidad", 1)
            m2 = p.get("m2_calc_total", 0)
            pileta_count = p.get("pileta_count", 0)
            pileta_type = p.get("pileta_type")
            faldon_cm = p.get("faldon_cm")

            row = [pid, ubic, medida, _fmt_num(m2)]
            if has_qty:
                row.append(f"×{cantidad}" if cantidad > 1 else "")
            if has_pileta:
                if pileta_count > 0 and pileta_type:
                    ptype = "emp" if "empotrada" in pileta_type else "apoyo"
                    row.append(f"{pileta_count} {ptype}")
                else:
                    row.append("—")
            if has_faldon:
                row.append(f"{faldon_cm}cm" if faldon_cm else "—")
            lines.append("| " + " | ".join(str(c) for c in row) + " |")

        # Faldones summary (if any)
        if faldon_pieces:
            m2_fald = mat_data.get("m2_faldones", 0)
            lines.append(f"+ {len(faldon_pieces)} {'faldón' if len(faldon_pieces) == 1 else 'faldones'} ({_fmt_num(m2_fald)} m²)")

        lines.append("")

    # MO summary
    lines.append("### SERVICIOS (MO)")
    lines.append("- Sin colocación (edificio)")

    peg = totals.get("pileta_pegado_total", 0)
    apo = totals.get("pileta_apoyo_total", 0)
    if peg > 0:
        lines.append(f"- PEGADOPILETA ×{peg}")
    if apo > 0:
        lines.append(f"- AGUJEROAPOYO ×{apo}")

    fald_ml = totals.get("faldon_ml_total", 0)
    if fald_ml > 0:
        lines.append(f"- Armado faldón ×{_fmt_num(fald_ml)} ml")

    flete = totals.get("flete_qty", 0)
    phys = totals.get("pieces_physical_total", 0)
    if flete > 0:
        lines.append(f"- Flete ×{flete} viajes ({phys} piezas físicas)")

    lines.append("")

    # Descuento
    if totals.get("descuento_18_aplica"):
        m2_tot = totals.get("m2_total", 0)
        lines.append("### DESCUENTOS")
        lines.append(f"18% por volumen — {_fmt_num(m2_tot)} m² > 15 → aplica a TODOS los materiales")
        lines.append("")

    # Grand total
    m2_grand = totals.get("m2_total", 0)
    lines.append(f"**TOTAL: {_fmt_num(m2_grand)} m²**")

    return "\n".join(lines)
