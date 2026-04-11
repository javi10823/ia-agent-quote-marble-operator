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
    """Detect if PDF is an edificio. Returns structured result with reasons, confidence,
    and detection_mode for auditability.

    detection_mode values:
    - "manual_override": operator explicitly declared edificio (confidence=1.0)
    - "keyword": detected via keyword signals + table analysis
    - "tabular": would be set by caller when tabular path is used
    - "visual_auto": would be set by caller when visual path is used
    """
    reasons = []
    confidence = 0.0
    msg_lower = (user_message or "").lower()

    # Signal 0: EXPLICIT operator override — confidence=1.0 immediately
    # These phrases are unambiguous declarations, not just keywords
    _explicit_override = [
        "es edificio", "es obra", "obra padre", "es una obra",
        "tratalo como edificio", "tratalo como obra",
        "modo edificio", "modo obra",
    ]
    if any(phrase in msg_lower for phrase in _explicit_override):
        reasons.append("operador forzó modo edificio explícitamente")
        return DetectionResult(
            is_edificio=True, confidence=1.0, reasons=reasons,
            detection_mode="manual_override",
        )

    # Signal 1: operator says "edificio" or similar (strong)
    if any(kw in msg_lower for kw in [
        "edificio", "edificios", "building", "concesionario",
        "departamento", "departamentos", "unidades",
        "torre", "torres", "constructora", "consorcio",
        "obra nueva", "fideicomiso",
        "planos", "láminas", "laminas", "tipología", "tipologia",
        "cocinas",  # "309 cocinas" = building, not single kitchen
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
        detection_mode="keyword",
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


# ── 7. render_edificio_paso2 — deterministic pricing output ──────────────────

def render_edificio_paso2(summary: dict, localidad: str = "Rosario") -> dict:
    """Calculate prices and render Paso 2 for edificio — 100% deterministic.

    Uses catalog_lookup for material prices and MO prices directly.
    No calculate_quote — avoids residential logic (sinks, colocacion, split flete).

    Returns: {
        "rendered": str (markdown),
        "calc_results": {material_name: {...prices...}},
        "grand_total_ars": int,
        "grand_total_usd": int,
    }
    """
    from app.modules.agent.tools.catalog_tool import catalog_lookup
    from app.modules.quote_engine.calculator import _find_flete, _get_mo_price

    materials = summary.get("materials", {})
    totals = summary.get("totals", {})
    discount_pct = 18 if totals.get("descuento_18_aplica") else 0

    # ── 1. Price each material ──
    mat_results = {}
    grand_ars = 0
    grand_usd = 0

    for mat_name, mat_data in materials.items():
        m2 = mat_data.get("m2_total", 0)  # includes faldones m²

        # Lookup material price
        mat_result = catalog_lookup("materials-granito-nacional", mat_name)
        if not mat_result.get("found"):
            mat_result = catalog_lookup("materials-granito-importado", mat_name)
        if not mat_result.get("found"):
            # Try all catalogs
            from app.modules.quote_engine.calculator import _find_material
            mat_result = _find_material(mat_name)

        if not mat_result.get("found"):
            mat_results[mat_name] = {"ok": False, "error": f"Material '{mat_name}' no encontrado"}
            continue

        currency = mat_result.get("currency", "ARS")
        if currency == "USD":
            price_unit = mat_result.get("price_usd", 0)  # already with IVA (floor)
            price_base = mat_result.get("price_usd_base", 0)
        else:
            price_unit = mat_result.get("price_ars", 0)  # already with IVA (round)
            price_base = mat_result.get("price_ars_base", 0)

        material_total = round(m2 * price_unit)
        discount_amount = round(material_total * discount_pct / 100) if discount_pct else 0
        material_net = material_total - discount_amount

        mat_results[mat_name] = {
            "ok": True,
            "currency": currency,
            "m2": m2,
            "price_unit": price_unit,
            "price_base": price_base,
            "material_total": material_total,
            "discount_pct": discount_pct,
            "discount_amount": discount_amount,
            "material_net": material_net,
            "catalog_name": mat_result.get("name", mat_name),
        }

        if currency == "USD":
            grand_usd += material_net
        else:
            grand_ars += material_net

    # ── 2. Calculate global MO ──
    mo_items = []
    mo_total = 0

    # Detect sinterizado for any material (affects MO SKUs)
    from app.modules.quote_engine.calculator import SINTERIZADOS
    any_sint = any(
        any(s in mat_name.lower() for s in SINTERIZADOS)
        for mat_name in materials.keys()
    )

    # PEGADOPILETA
    peg_count = totals.get("pileta_pegado_total", 0)
    if peg_count > 0:
        sku = "PILETADEKTON/NEOLITH" if any_sint else "PEGADOPILETA"
        price, base = _get_mo_price(sku)
        # Edificio: ÷1.05
        price_edif = round(price / 1.05)
        total = price_edif * peg_count
        mo_items.append({"desc": "Agujero y pegado pileta", "qty": peg_count, "price": price_edif, "total": total})
        mo_total += total

    # AGUJEROAPOYO
    apo_count = totals.get("pileta_apoyo_total", 0)
    if apo_count > 0:
        sku = "PILETAAPOYODEKTON/NEO" if any_sint else "AGUJEROAPOYO"
        price, base = _get_mo_price(sku)
        price_edif = round(price / 1.05)
        total = price_edif * apo_count
        mo_items.append({"desc": "Agujero pileta apoyo", "qty": apo_count, "price": price_edif, "total": total})
        mo_total += total

    # Armado faldón
    fald_ml = totals.get("faldon_ml_total", 0)
    if fald_ml > 0:
        sku = "FALDONDEKTON/NEOLITH" if any_sint else "FALDON"
        price, base = _get_mo_price(sku)
        price_edif = round(price / 1.05)
        total = round(price_edif * fald_ml)
        mo_items.append({"desc": "Armado faldón", "qty": fald_ml, "price": price_edif, "total": total})
        mo_total += total

    # Flete (global, NOT ÷1.05)
    flete_qty = totals.get("flete_qty", 0)
    if flete_qty > 0:
        flete_result = _find_flete(localidad)
        if flete_result.get("found"):
            flete_price = flete_result.get("price_ars", 0)
            flete_total = flete_price * flete_qty
            flete_label = f"Flete obra ({localidad})" if localidad.lower().strip() != "rosario" else "Flete + toma medidas"
            mo_items.append({"desc": flete_label, "qty": flete_qty, "price": flete_price, "total": round(flete_total)})
            mo_total += round(flete_total)

    grand_ars += mo_total

    # ── 3. Render markdown ──
    lines = []
    lines.append("## Presupuesto Edificio")
    lines.append("")

    # Materials — show base + IVA clearly
    for mat_name, mr in mat_results.items():
        if not mr.get("ok"):
            lines.append(f"### {mat_name.upper()} — ERROR: {mr.get('error')}")
            lines.append("")
            continue

        cur = mr["currency"]
        cur_sym = "USD " if cur == "USD" else "$"
        m2 = mr["m2"]

        lines.append(f"### {mat_name.upper()} — {_fmt_num(m2)} m²")
        lines.append("")
        lines.append("| Concepto | Valor |")
        lines.append("| --- | --- |")
        lines.append(f"| Precio base (sin IVA) | {cur_sym}{_fmt_num(mr['price_base'], 0)}/m² |")
        lines.append(f"| Precio con IVA (×1,21) | {cur_sym}{_fmt_num(mr['price_unit'], 0)}/m² |")
        lines.append(f"| Superficie | {_fmt_num(m2)} m² |")
        lines.append(f"| Subtotal | {cur_sym}{_fmt_num(mr['material_total'], 0)} |")
        if mr["discount_pct"]:
            lines.append(f"| Descuento {mr['discount_pct']}% | -{cur_sym}{_fmt_num(mr['discount_amount'], 0)} |")
            lines.append(f"| **Total material** | **{cur_sym}{_fmt_num(mr['material_net'], 0)}** |")
        else:
            lines.append(f"| **Total material** | **{cur_sym}{_fmt_num(mr['material_total'], 0)}** |")
        lines.append("")

    # Global MO
    lines.append("### MANO DE OBRA")
    lines.append("")
    lines.append("| Concepto | Cant | Precio c/IVA | Total |")
    lines.append("| --- | --- | --- | --- |")
    for mo in mo_items:
        qty_str = _fmt_num(mo["qty"], 2) if isinstance(mo["qty"], float) else str(mo["qty"])
        lines.append(f"| {mo['desc']} | {qty_str} | ${_fmt_num(mo['price'], 0)} | ${_fmt_num(mo['total'], 0)} |")
    lines.append(f"| **Total MO** | | | **${_fmt_num(mo_total, 0)}** |")
    lines.append("")
    lines.append("*Sin colocación (edificio). MO ÷1.05 excepto flete.*")
    lines.append("")

    # Descuento note
    if discount_pct:
        lines.append("### DESCUENTOS")
        lines.append(f"18% por volumen ({_fmt_num(totals.get('m2_total', 0))} m² > 15) — aplicado a material de cada presupuesto")
        lines.append("")

    # Grand total — structured, no ambiguity
    ars_mat = sum(mr["material_net"] for mr in mat_results.values() if mr.get("ok") and mr["currency"] == "ARS")
    lines.append("### GRAND TOTAL")
    lines.append("")
    lines.append("| Concepto | Moneda | Monto |")
    lines.append("| --- | --- | --- |")
    if grand_usd > 0:
        lines.append(f"| Material (USD) | USD | **{_fmt_num(grand_usd, 0)}** |")
    if ars_mat > 0:
        lines.append(f"| Material (ARS) | ARS | **${_fmt_num(ars_mat, 0)}** |")
    lines.append(f"| Mano de obra | ARS | **${_fmt_num(mo_total, 0)}** |")
    if ars_mat > 0 or mo_total > 0:
        lines.append(f"| **Total ARS** | **ARS** | **${_fmt_num(grand_ars, 0)}** |")
    if grand_usd > 0:
        lines.append(f"| **Total USD** | **USD** | **{_fmt_num(grand_usd, 0)}** |")
    lines.append("")

    rendered = "\n".join(lines)

    return {
        "rendered": rendered,
        "calc_results": mat_results,
        "mo_items": mo_items,
        "mo_total": mo_total,
        "grand_total_ars": grand_ars,
        "grand_total_usd": grand_usd,
    }


# ── 8. distribute_flete — deterministic flete distribution ───────────────────

def distribute_flete(total_qty: int, piece_counts: dict[str, int]) -> dict[str, int]:
    """Distribute flete trips across materials using largest remainder method.

    Pure function. Sum of result always equals total_qty.
    Tie-break: alphabetical order by material name (stable).
    """
    total_pieces = sum(piece_counts.values())
    if total_pieces == 0 or total_qty == 0:
        return {k: 0 for k in piece_counts}

    # Calculate raw shares and base allocations
    raw = {}
    base = {}
    for mat, count in piece_counts.items():
        share = total_qty * count / total_pieces
        base[mat] = math.floor(share)
        raw[mat] = share - base[mat]  # remainder

    # Distribute leftover trips by largest remainder, tie-break alphabetical
    leftover = total_qty - sum(base.values())
    sorted_mats = sorted(raw.keys(), key=lambda m: (-raw[m], m))
    for i in range(leftover):
        base[sorted_mats[i]] += 1

    return base


# ── 9. build_edificio_doc_context — presentation model for PDF/Excel ────────

_OCR_CLEAN = {
    "AJAB\nATNALP": "Planta Baja",
    "ATNALP\nATLA": "Planta Alta",
}


def build_edificio_doc_context(
    summary: dict,
    paso2_calc: dict,
    client_name: str,
    project: str,
) -> list[dict]:
    """Build ready-to-render document contexts for edificio. One per material.

    MO is distributed per material (not concentrated in one):
    - PEGADOPILETA: by material's pileta_pegado count
    - AGUJEROAPOYO: by material's pileta_apoyo count
    - Armado faldón: by material's faldon_ml_total
    - Flete: distribute_flete() by piece_count_physical

    Lines with qty=0 are excluded. If no MO lines → show_mo=False.
    No recalculation. All prices from paso2_calc.
    """
    calc_results = paso2_calc.get("calc_results", {})
    mo_items_raw = paso2_calc.get("mo_items", [])
    materials_summary = summary.get("materials", {})
    totals = summary.get("totals", {})

    # ── Get MO unit prices from paso2_calc (already with IVA, already ÷1.05) ──
    mo_prices = {}
    for mo in mo_items_raw:
        desc = mo.get("desc", "").lower()
        mo_prices[desc] = {"price": mo.get("price", 0), "price_base": mo.get("price_base", mo.get("price", 0))}

    # ── Distribute flete ──
    piece_counts = {}
    for mat_name, mat_data in materials_summary.items():
        piece_counts[mat_name] = mat_data.get("piece_count_physical", 0)
    flete_total = totals.get("flete_qty", 0)
    flete_dist = distribute_flete(flete_total, piece_counts)

    # Get flete unit price
    flete_price_info = mo_prices.get("flete + toma medidas", mo_prices.get("flete", {"price": 0, "price_base": 0}))
    # Try to find flete price from any key containing "flete"
    if flete_price_info["price"] == 0:
        for k, v in mo_prices.items():
            if "flete" in k:
                flete_price_info = v
                break

    contexts = []

    for mat_name, mr in calc_results.items():
        if not mr.get("ok"):
            continue

        cur = mr["currency"]
        mat_data = materials_summary.get(mat_name, {})

        # ── Build piece_groups from pieces grouped by ubicacion ──
        pieces = mat_data.get("pieces", [])
        groups_by_ubic: dict[str, list[str]] = {}

        for p in pieces:
            ubic = p.get("ubicacion") or "General"
            if "\n" in ubic:
                ubic = _OCR_CLEAN.get(ubic, ubic.replace("\n", " "))
            qty = p.get("cantidad", 1)
            largo = p.get("largo", 0)
            ancho = p.get("ancho", 0)

            if qty > 1:
                label = f"{_fmt_num(largo)} X {_fmt_num(ancho)} X {qty} UNID"
            else:
                label = f"{_fmt_num(largo)} X {_fmt_num(ancho)}"
            groups_by_ubic.setdefault(ubic, []).append(label)

        # Faldones in their own group
        faldon_pieces = mat_data.get("faldon_pieces", [])
        if faldon_pieces:
            faldon_labels = []
            for fp in faldon_pieces:
                faldon_labels.append(f"{_fmt_num(fp.get('largo', 0))}ML X {_fmt_num(fp.get('alto', 0))} FALDON")
            groups_by_ubic["Faldones"] = faldon_labels

        piece_groups = [{"label": ubic, "lines": labels} for ubic, labels in groups_by_ubic.items()]

        # ── Build MO lines for this material (only non-zero) ──
        mo_lines = []
        mo_subtotal = 0

        peg = mat_data.get("pileta_pegado", 0)
        if peg > 0:
            p_info = mo_prices.get("agujero y pegado pileta", {"price": 0, "price_base": 0})
            total = p_info["price"] * peg
            mo_lines.append({"desc": "Agujero y pegado pileta", "qty": peg, "price": p_info["price"], "price_base": p_info["price_base"], "total": total})
            mo_subtotal += total

        apo = mat_data.get("pileta_apoyo", 0)
        if apo > 0:
            a_info = mo_prices.get("agujero pileta apoyo", {"price": 0, "price_base": 0})
            total = a_info["price"] * apo
            mo_lines.append({"desc": "Agujero pileta apoyo", "qty": apo, "price": a_info["price"], "price_base": a_info["price_base"], "total": total})
            mo_subtotal += total

        fald_ml = mat_data.get("faldon_ml_total", 0)
        if fald_ml and fald_ml > 0:
            f_info = mo_prices.get("armado faldón", mo_prices.get("armado faldon", {"price": 0, "price_base": 0}))
            # Try any key with "fald"
            if f_info["price"] == 0:
                for k, v in mo_prices.items():
                    if "fald" in k:
                        f_info = v
                        break
            total = round(f_info["price"] * fald_ml)
            mo_lines.append({"desc": "Armado faldón", "qty": round(fald_ml, 2), "price": f_info["price"], "price_base": f_info["price_base"], "total": total})
            mo_subtotal += total

        mat_flete = flete_dist.get(mat_name, 0)
        if mat_flete > 0:
            total = flete_price_info["price"] * mat_flete
            mo_lines.append({"desc": "Flete + toma medidas", "qty": mat_flete, "price": flete_price_info["price"], "price_base": flete_price_info["price_base"], "total": total})
            mo_subtotal += total

        show_mo = len(mo_lines) > 0

        # ── Convert mo_lines to template format ──
        mo_for_template = []
        for ml in mo_lines:
            mo_for_template.append({
                "description": ml["desc"],
                "quantity": ml["qty"],
                "unit_price": ml["price"],
                "base_price": ml["price_base"],
                "total": ml["total"],
            })

        # ── Totals ──
        material_net = mr["material_net"]
        if cur == "ARS":
            total_ars = material_net + mo_subtotal
            total_usd = 0
        else:
            total_ars = mo_subtotal if show_mo else 0
            total_usd = material_net

        # ── Grand total text ──
        if cur == "ARS" and show_mo:
            gt_text = f"PRESUPUESTO TOTAL: ${_fmt_num(total_ars, 0)} de mano de obra y material"
        elif cur == "USD" and show_mo:
            gt_text = f"PRESUPUESTO TOTAL: ${_fmt_num(mo_subtotal, 0)} mano de obra + USD {_fmt_num(total_usd, 0)} material"
        elif cur == "USD" and not show_mo:
            gt_text = f"PRESUPUESTO TOTAL: USD {_fmt_num(total_usd, 0)} material"
        else:
            gt_text = f"PRESUPUESTO TOTAL: ${_fmt_num(material_net, 0)} material"

        contexts.append({
            # Header
            "client_name": client_name,
            "project": project,
            "delivery_days": "Segun cronograma de obra",
            # Material
            "material_name": mr.get("catalog_name", mat_name),
            "material_m2": mr["m2"],
            "material_price_unit": mr["price_unit"],
            "material_currency": cur,
            "material_total": mr["material_total"],
            "discount_pct": mr.get("discount_pct", 0),
            "thickness_mm": mr.get("thickness_mm", 20),
            # Despiece
            "sectors": [{"label": g["label"], "pieces": g["lines"]} for g in piece_groups],
            # MO
            "sinks": [],
            "mo_items": mo_for_template,
            "show_mo": show_mo,
            # Totals
            "total_ars": total_ars,
            "total_usd": total_usd,
            "grand_total_text": gt_text,
            # Metadata
            "_mat_name_raw": mat_name,
            "_currency": cur,
        })

    return contexts
