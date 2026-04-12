"""Deterministic pipeline for visual/CAD building quotes.

Separates LLM extraction (soft) from computation (hard):
- Claude extracts JSON per tipología from plan pages
- This module resolves materials, validates, computes geometry, infers services

Only applies to visual/CAD multipágina path. Does NOT affect:
- ESH tabular pipeline (edificio_parser.py)
- Normal text quotes
- Simple image quotes
"""

from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

CATALOG_DIR = Path(__file__).parent.parent.parent.parent / "catalog"

# Material max slab length (m) — for physical piece count / flete calculation
MATERIAL_MAX_LENGTHS = {
    "silestone": 3.20,
    "purastone": 3.20,
    "puraprima": 3.20,
    "dekton": 3.20,
    "neolith": 3.20,
    "laminatto": 3.20,
    "granito nacional": 2.80,
    "granito importado": 3.00,
    "marmol": 2.80,
    "default": 3.00,
}

# Confidence thresholds
CONF_HIGH = 0.80
CONF_REVIEW = 0.55

# Validation limits
VALIDATION_ALWAYS_THRESHOLD = 10  # Always show validation if total units > this


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class MaterialResolution:
    raw_text: str
    resolved: list[str]
    mode: str  # "single" | "variants" | "needs_clarification"
    unresolved: list[str]
    thickness_mm: int = 20

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FieldConfidence:
    shape: float = 0.0
    depth: float = 0.0
    segments: float = 0.0
    backsplash: float = 0.0
    sink: float = 0.0
    hob: float = 0.0

    def min_score(self) -> float:
        return min(self.shape, self.depth, self.segments)

    def has_review_needed(self) -> bool:
        return any(v < CONF_HIGH for v in [self.shape, self.depth, self.segments,
                                            self.backsplash, self.sink, self.hob])

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TipologiaGeometry:
    id: str
    qty: int
    shape: str  # "L" | "linear"
    segments_m: list[float]
    depth_m: float
    m2_unit: float
    m2_total: float
    backsplash_ml_unit: float
    backsplash_m2_unit: float
    backsplash_m2_total: float
    physical_pieces_per_unit: int
    physical_pieces_total: int
    notes: list[str] = field(default_factory=list)
    confidence: FieldConfidence = field(default_factory=FieldConfidence)


@dataclass
class GeometrySummary:
    tipologias: list[TipologiaGeometry]
    total_mesada_m2: float
    total_backsplash_m2: float
    total_m2: float
    total_physical_pieces: int
    flete_qty: int

    def to_dict(self) -> dict:
        return {
            "tipologias": [asdict(t) for t in self.tipologias],
            "total_mesada_m2": self.total_mesada_m2,
            "total_backsplash_m2": self.total_backsplash_m2,
            "total_m2": self.total_m2,
            "total_physical_pieces": self.total_physical_pieces,
            "flete_qty": self.flete_qty,
        }


@dataclass
class ServiceInference:
    is_building: bool = True
    colocacion: bool = False  # edificio → no
    pegadopileta_qty: int = 0
    pegadopileta_confidence: float = 0.0
    anafe_qty: int = 0
    anafe_confidence: float = 0.0
    backsplash_height_m: float = 0.075
    flete_qty: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ── 1. Material Resolution ─────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Lowercase, strip, remove accents, collapse whitespace."""
    text = text.lower().strip()
    # Remove accents
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def _load_material_aliases() -> dict[str, str]:
    """Load material_aliases from config.json."""
    try:
        with open(CATALOG_DIR / "config.json") as f:
            cfg = json.load(f)
        return cfg.get("material_aliases", {})
    except Exception:
        return {}


def _fuzzy_alias_match(text: str, aliases: dict[str, str]) -> Optional[str]:
    """Try exact match first, then normalized match."""
    norm = _normalize_text(text)

    # Exact match (case-insensitive)
    for alias_key, canonical in aliases.items():
        if _normalize_text(alias_key) == norm:
            return canonical

    # Substring match: if normalized text contains an alias
    for alias_key, canonical in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if _normalize_text(alias_key) in norm:
            return canonical

    return None


def _catalog_exists(material_name: str) -> bool:
    """Check if a material name exists in any catalog (fuzzy)."""
    norm = _normalize_text(material_name)
    for catalog_file in CATALOG_DIR.glob("materials-*.json"):
        try:
            with open(catalog_file) as f:
                items = json.load(f)
            for item in items:
                if _normalize_text(item.get("name", "")) == norm:
                    return True
                # Also check partial match
                if norm in _normalize_text(item.get("name", "")):
                    return True
        except Exception:
            continue
    return False


def resolve_visual_materials(raw_text: str) -> MaterialResolution:
    """Resolve material text from plan into canonical catalog names.

    Rules:
    - Try alias match first
    - If 2-3 resolved materials → mode="variants" (auto)
    - If 1 resolved → mode="single"
    - If any unresolved → mode="needs_clarification"
    """
    aliases = _load_material_aliases()

    # Parse "Material A o Material B" patterns
    # Also handle "Material A / Material B"
    # Strip thickness info first
    clean = re.sub(r"\d+\s*(cm|mm)\s*(de\s+)?espesor", "", raw_text, flags=re.IGNORECASE).strip()
    thickness_match = re.search(r"(\d+)\s*(cm|mm)", raw_text, re.IGNORECASE)
    thickness_mm = 20
    if thickness_match:
        val = int(thickness_match.group(1))
        unit = thickness_match.group(2).lower()
        thickness_mm = val * 10 if unit == "cm" else val

    # Split by "o" / "or" / "/"
    parts = re.split(r"\s+o\s+|\s*/\s*", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]

    resolved = []
    unresolved = []

    for part in parts:
        # Try alias first
        canonical = _fuzzy_alias_match(part, aliases)
        if canonical:
            if canonical not in resolved:
                resolved.append(canonical)
            continue

        # Try direct catalog match
        if _catalog_exists(part):
            if part not in resolved:
                resolved.append(part)
            continue

        unresolved.append(part)

    if unresolved:
        mode = "needs_clarification"
    elif len(resolved) >= 2:
        mode = "variants"
    elif len(resolved) == 1:
        mode = "single"
    else:
        mode = "needs_clarification"

    return MaterialResolution(
        raw_text=raw_text,
        resolved=resolved,
        mode=mode,
        unresolved=unresolved,
        thickness_mm=thickness_mm,
    )


# ── 2. Field Confidence (deterministic, not from LLM) ─────────────────────────

def compute_field_confidence(tipologia: dict) -> FieldConfidence:
    """Compute confidence per field using deterministic range checks."""
    segs = tipologia.get("segments_m", [])
    depth = tipologia.get("depth_m", 0)
    shape = tipologia.get("shape", "unknown")
    sink = tipologia.get("embedded_sink_count", 0)
    hob = tipologia.get("hob_count", 0)
    backsplash = tipologia.get("backsplash_ml")

    conf = FieldConfidence()

    # Shape: must be explicit
    if shape in ("L", "linear"):
        conf.shape = 0.9
    elif shape == "unknown":
        conf.shape = 0.3  # Needs review
    else:
        conf.shape = 0.4

    # Shape-segment consistency
    if shape == "L" and len(segs) != 2:
        conf.segments = 0.3
    elif shape == "linear" and len(segs) != 1:
        conf.segments = 0.3
    elif all(0.3 <= s <= 5.0 for s in segs) and len(segs) > 0:
        conf.segments = 0.9
    else:
        conf.segments = 0.5

    # Depth: typical mesada range
    if 0.40 <= depth <= 0.80:
        conf.depth = 0.9
    elif 0.20 <= depth <= 1.0:
        conf.depth = 0.6
    else:
        conf.depth = 0.3

    # Sink: expected 0 or 1 per unit
    if 0 <= sink <= 2:
        conf.sink = 0.9
    else:
        conf.sink = 0.5

    # Hob: expected 0 or 1
    if 0 <= hob <= 1:
        conf.hob = 0.9
    else:
        conf.hob = 0.5

    # Backsplash: always needs review (visually weak)
    if backsplash is not None:
        total_seg = sum(segs) if segs else 1
        if backsplash > total_seg * 2.5:
            conf.backsplash = 0.3  # incoherent
        elif backsplash < depth * 0.5:
            conf.backsplash = 0.4  # suspiciously low
        else:
            conf.backsplash = 0.6  # plausible but always review
    else:
        conf.backsplash = 0.5  # no data → will use fallback

    return conf


# ── 3. Validate Visual Extraction ──────────────────────────────────────────────

@dataclass
class ValidationResult:
    all_tipologias: list[dict]  # original + confidence added
    high_confidence: list[dict]
    needs_review: list[dict]
    unusable: list[dict]
    soft_field_warnings: list[str]
    requires_operator_validation: bool


def validate_visual_extraction(tipologias: list[dict]) -> ValidationResult:
    """Validate extracted tipologías and classify by confidence."""
    high = []
    review = []
    unusable = []
    warnings = []

    total_units = sum(t.get("qty", 1) for t in tipologias)

    for t in tipologias:
        conf = compute_field_confidence(t)
        t["_confidence"] = conf.to_dict()

        min_core = min(conf.shape, conf.depth, conf.segments)
        if min_core >= CONF_HIGH:
            high.append(t)
        elif min_core >= CONF_REVIEW:
            review.append(t)
        else:
            unusable.append(t)

        # Soft field warnings — only warn about backsplash if incoherent
        bl = t.get("backsplash_ml")
        segs = t.get("segments_m", [])
        if backsplash_needs_confirmation(bl, segs, t.get("shape", "linear")):
            warnings.append(f"{t.get('id', '?')}: zócalo/backsplash valor incoherente — requiere confirmación")
        if conf.sink < CONF_HIGH:
            warnings.append(f"{t.get('id', '?')}: cantidad de piletas requiere confirmación")
        if conf.hob < CONF_HIGH:
            warnings.append(f"{t.get('id', '?')}: anafe requiere confirmación")

    # Always validate if large project or if there are review/unusable items
    forced_by_unit_count = total_units > VALIDATION_ALWAYS_THRESHOLD
    requires_validation = (
        len(review) > 0
        or len(unusable) > 0
        or forced_by_unit_count
    )

    # For large projects, ALL tipologías need review (even high confidence)
    if forced_by_unit_count and high:
        review.extend(high)
        high = []

    return ValidationResult(
        all_tipologias=tipologias,
        high_confidence=high,
        needs_review=review,
        unusable=unusable,
        soft_field_warnings=warnings,
        requires_operator_validation=requires_validation,
    )


# ── 4. Compute Geometry (deterministic) ────────────────────────────────────────

def _get_material_max_length(material_name: str) -> float:
    """Get max slab length for a material."""
    norm = _normalize_text(material_name)
    for key, length in MATERIAL_MAX_LENGTHS.items():
        if key in norm:
            return length
    return MATERIAL_MAX_LENGTHS["default"]


def compute_physical_pieces(segments_m: list[float], material_max_length: float) -> int:
    """Each segment divided into physical pieces by material max slab length."""
    total = 0
    for seg in segments_m:
        total += math.ceil(seg / material_max_length)
    return total


def compute_visual_geometry(
    tipologias: list[dict],
    material_resolution: MaterialResolution,
    backsplash_height_m: float = 0.075,
) -> GeometrySummary:
    """Compute exact m², backsplash, physical pieces from validated tipologías."""
    # Use first resolved material for max length (both variants share geometry)
    mat_name = material_resolution.resolved[0] if material_resolution.resolved else ""
    max_length = _get_material_max_length(mat_name)

    results = []
    total_mesada = 0
    total_backsplash = 0
    total_pieces = 0

    for t in tipologias:
        tid = t.get("id", "?")
        qty = t.get("qty", 1)
        shape = t.get("shape", "linear")
        segs = t.get("segments_m", [])
        depth = t.get("depth_m", 0.60)
        notes = t.get("notes", [])

        # m² per unit — L-shape subtracts corner overlap
        if shape == "L" and len(segs) == 2:
            m2_unit = (segs[0] * depth) + (segs[1] * depth) - (depth * depth)
        else:
            m2_unit = sum(s * depth for s in segs)
        m2_unit = round(m2_unit, 2)
        m2_total = round(m2_unit * qty, 2)

        # Backsplash ml per unit
        backsplash_ml = t.get("backsplash_ml")
        if backsplash_ml is None:
            # Fallback: conservative (all segments + depth for L)
            # TODO: this overestimates if not all sides have backsplash
            backsplash_ml = sum(segs)
            if shape == "L":
                backsplash_ml += depth  # return side
        backsplash_m2_unit = round(backsplash_ml * backsplash_height_m, 2)
        backsplash_m2_total = round(backsplash_m2_unit * qty, 2)

        # Physical pieces per unit
        pieces_unit = compute_physical_pieces(segs, max_length)
        pieces_total = pieces_unit * qty

        geo = TipologiaGeometry(
            id=tid,
            qty=qty,
            shape=shape,
            segments_m=segs,
            depth_m=depth,
            m2_unit=m2_unit,
            m2_total=m2_total,
            backsplash_ml_unit=round(backsplash_ml, 2),
            backsplash_m2_unit=backsplash_m2_unit,
            backsplash_m2_total=backsplash_m2_total,
            physical_pieces_per_unit=pieces_unit,
            physical_pieces_total=pieces_total,
            notes=notes,
        )
        results.append(geo)
        total_mesada += m2_total
        total_backsplash += backsplash_m2_total
        total_pieces += pieces_total

    if total_pieces > 0:
        flete_qty = math.ceil(total_pieces / 6)
    else:
        logging.warning("[geometry] total_physical_pieces=0 — using fallback flete=1")
        flete_qty = 1

    return GeometrySummary(
        tipologias=results,
        total_mesada_m2=round(total_mesada, 2),
        total_backsplash_m2=round(total_backsplash, 2),
        total_m2=round(total_mesada + total_backsplash, 2),
        total_physical_pieces=total_pieces,
        flete_qty=flete_qty,
    )


# ── 5. Infer Services ─────────────────────────────────────────────────────────

def infer_visual_services(
    tipologias: list[dict],
    geometry: GeometrySummary,
) -> ServiceInference:
    """Infer building services from tipologías."""
    total_sinks = 0
    total_hobs = 0
    min_sink_conf = 1.0
    min_hob_conf = 1.0

    for t in tipologias:
        qty = t.get("qty", 1)
        total_sinks += t.get("embedded_sink_count", 0) * qty
        total_hobs += t.get("hob_count", 0) * qty

        conf = t.get("_confidence", {})
        min_sink_conf = min(min_sink_conf, conf.get("sink", 0.5))
        min_hob_conf = min(min_hob_conf, conf.get("hob", 0.5))

    return ServiceInference(
        is_building=True,
        colocacion=False,
        pegadopileta_qty=total_sinks,
        pegadopileta_confidence=min_sink_conf,
        anafe_qty=total_hobs,
        anafe_confidence=min_hob_conf,
        backsplash_height_m=0.075,
        flete_qty=geometry.flete_qty,
    )


# ── 6. Pending Questions (deterministic) ───────────────────────────────────────

def build_visual_pending_questions(
    material_res: MaterialResolution,
    services: ServiceInference,
    tipologias: list[dict],
    quote: Optional[dict] = None,
) -> list[str]:
    """Build list of genuinely pending commercial questions."""
    questions = []

    # Planilla always first
    questions.append("planilla_marmoleria")

    # Client name
    q = quote or {}
    if not q.get("client_name"):
        questions.append("client_name")

    # Locality — only if not already set (NOT defaulting to Rosario)
    if not q.get("locality"):
        questions.append("locality")

    # Material — only if needs clarification
    if material_res.mode == "needs_clarification":
        questions.append("material_definition")

    # Pileta provision — only if sinks detected
    if services.pegadopileta_qty > 0:
        questions.append("pileta_provision")

    # Only ask about backsplash if value is incoherent (not just low confidence)
    for t in tipologias:
        bl = t.get("backsplash_ml")
        segs = t.get("segments_m", [])
        shape = t.get("shape", "linear")
        if backsplash_needs_confirmation(bl, segs, shape):
            questions.append(f"confirm_backsplash_{t.get('id', '?')}")

    # Tipologías with non-direct extraction need review
    for t in tipologias:
        method = t.get("extraction_method", "fallback")
        if method != "direct_read":
            tid = t.get("id", "?")
            questions.append(f"{tid}_extraction_needs_review")

    # Tipologías with unknown shape need review
    for t in tipologias:
        if t.get("shape") == "unknown":
            tid = t.get("id", "?")
            if f"{tid}_extraction_needs_review" not in questions:
                questions.append(f"{tid}_extraction_needs_review")

    return questions


# ── 6b. Second Pass — identify tipologías needing focused re-read ─────────────

def get_tipologias_needing_second_pass(
    tipologias: list[dict],
    field_confidences: Optional[dict] = None,
) -> list[str]:
    """Return IDs that need a second focused vision pass.

    Criteria:
    - extraction_method != "direct_read"
    - shape == "unknown"
    - segments confidence < CONF_HIGH
    - shape confidence < CONF_HIGH
    """
    if field_confidences is None:
        field_confidences = {}

    needs_review = []
    for t in tipologias:
        tid = t.get("id", "")
        if not tid:
            continue
        method = t.get("extraction_method", "fallback")
        shape = t.get("shape", "unknown")

        # Check field-level confidence (from _confidence or external dict)
        conf = field_confidences.get(tid, t.get("_confidence", {}))

        if (method != "direct_read"
                or shape == "unknown"
                or conf.get("segments", 0) < CONF_HIGH
                or conf.get("shape", 0) < CONF_HIGH):
            needs_review.append(tid)

    return needs_review


def merge_second_pass(
    tipologias: list[dict],
    second_pass: dict,
    tipologia_id: str,
) -> list[dict]:
    """Merge second pass result into original tipología.

    Second pass has priority over fields it changed.
    Untouched fields remain intact.
    """
    result = []
    mergeable_fields = ["shape", "segments_m", "depth_m", "extraction_method"]

    for t in tipologias:
        if t.get("id") == tipologia_id:
            updated = {**t}
            for field in mergeable_fields:
                if field in second_pass:
                    updated[field] = second_pass[field]

            # Guard: reject segments where tramo1 < tramo2 (inverted L)
            new_segs = updated.get("segments_m", [])
            if len(new_segs) == 2 and new_segs[0] < new_segs[1]:
                logging.warning(
                    f"[merge] {tipologia_id}: tramo1 ({new_segs[0]}) < tramo2 ({new_segs[1]}) "
                    f"— rejecting second pass segments, keeping original"
                )
                updated["segments_m"] = t.get("segments_m", new_segs)
                updated["extraction_method"] = "inferred"

            updated["second_pass_notes"] = second_pass.get("second_pass_notes", "")
            result.append(updated)
        else:
            result.append(t)
    return result


def get_tipologia_page(tipologia_id: str, tipologias: list[dict]) -> int:
    """Return 1-indexed page number for a tipología.

    Uses explicit 'page' field if present, otherwise position order.
    """
    for i, t in enumerate(tipologias):
        if t.get("id") == tipologia_id:
            return t.get("page", i + 1)
    return 1


def parse_focused_response(text: str) -> Optional[dict]:
    """Parse second pass JSON response from Claude.

    Validates field types to prevent shape=0.9 or segments=[wrong values].
    """
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not json_match:
        return None
    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None

    # Validate required fields
    if "shape" not in data and "segments_m" not in data:
        return None

    # Validate shape is a string, not a number (Claude sometimes returns confidence as shape)
    if "shape" in data:
        if not isinstance(data["shape"], str):
            logging.warning(f"[parse_focused] shape is {type(data['shape']).__name__} ({data['shape']}), not str — discarding")
            del data["shape"]
        elif data["shape"] not in ("L", "linear", "unknown"):
            logging.warning(f"[parse_focused] invalid shape value: {data['shape']} — discarding")
            del data["shape"]

    # Validate segments_m is a list of numbers in valid range
    if "segments_m" in data:
        segs = data["segments_m"]
        if not isinstance(segs, list) or not segs:
            del data["segments_m"]
        else:
            valid = []
            for s in segs:
                try:
                    s = float(s)
                    if 0.1 <= s <= 10.0:
                        valid.append(round(s, 2))
                except (TypeError, ValueError):
                    pass
            if valid:
                data["segments_m"] = valid
            else:
                del data["segments_m"]

    # Validate depth_m is a number in valid range
    if "depth_m" in data:
        try:
            d = float(data["depth_m"])
            if 0.1 <= d <= 2.0:
                data["depth_m"] = round(d, 2)
            else:
                del data["depth_m"]
        except (TypeError, ValueError):
            del data["depth_m"]

    # Validate extraction_method is a valid string
    if "extraction_method" in data:
        if data["extraction_method"] not in ("direct_read", "inferred", "fallback"):
            del data["extraction_method"]

    # Must still have at least one valid field after validation
    if not any(k in data for k in ("shape", "segments_m", "depth_m")):
        return None

    return data


# ── 7. Parse Operator Corrections (deterministic regex) ────────────────────────

# Flexible ID pattern: DC-02, BAÑ-01, COC-03, TIPO-A, etc.
CORRECTION_PATTERN = re.compile(
    r"(\S+[-]\S+|\S+\d+)\s+"                    # tipología ID (flexible)
    r"(profundidad|depth|tramo\d?|tramo_?\d?|"
    r"zocalo_ml|zocalo|backsplash|"
    r"qty|cantidad|largo|ancho|"
    r"segments?|segmento?\d?)\s*"
    r"[=:]\s*"
    r"([\d]+[.,]?\d*)",
    re.IGNORECASE,
)


def normalize_field_name(raw: str) -> str:
    """Normalize correction field name to canonical."""
    raw = raw.lower().strip()
    mapping = {
        "profundidad": "depth_m",
        "depth": "depth_m",
        "ancho": "depth_m",
        "tramo": "segments_m_0",
        "tramo1": "segments_m_0",
        "tramo_1": "segments_m_0",
        "tramo2": "segments_m_1",
        "tramo_2": "segments_m_1",
        "segmento1": "segments_m_0",
        "segmento2": "segments_m_1",
        "segment1": "segments_m_0",
        "segment2": "segments_m_1",
        "largo": "segments_m_0",
        "zocalo_ml": "backsplash_ml",
        "zocalo": "backsplash_ml",
        "backsplash": "backsplash_ml",
        "qty": "qty",
        "cantidad": "qty",
    }
    return mapping.get(raw, raw)


def parse_number(raw: str) -> float:
    """Parse number with comma or dot decimal."""
    raw = raw.strip().replace(",", ".")
    return float(raw)


def looks_like_correction(text: str) -> bool:
    """Detect if text looks like it INTENDS to be a correction but failed regex."""
    indicators = ["=", ":", "tramo", "profundidad", "zocalo", "zócalo", "largo", "ancho"]
    text_lower = text.lower()
    return any(ind in text_lower for ind in indicators)


def parse_operator_corrections(text: str, known_ids: list[str] = None) -> Optional[list[dict]]:
    """Parse operator corrections using deterministic regex.

    Returns list of corrections, or None if text looks like a correction
    but couldn't be parsed (→ ask for format).
    Returns empty list if text is not a correction (e.g., "confirmo").
    """
    corrections = []
    for match in CORRECTION_PATTERN.finditer(text):
        raw_id = match.group(1).upper()
        raw_field = match.group(2)
        raw_value = match.group(3)

        # Validate against known IDs if provided
        if known_ids and raw_id not in [k.upper() for k in known_ids]:
            logging.warning(f"[correction] Unknown tipología ID: {raw_id}")
            continue

        corrections.append({
            "tipologia_id": raw_id,
            "field": normalize_field_name(raw_field),
            "value": parse_number(raw_value),
        })

    if not corrections and looks_like_correction(text):
        return None  # Tried to correct but format didn't match

    return corrections


def apply_corrections(tipologias: list[dict], corrections: list[dict]) -> list[dict]:
    """Apply parsed corrections to tipologías."""
    tip_map = {t.get("id", "").upper(): t for t in tipologias}

    for corr in corrections:
        tid = corr["tipologia_id"]
        field = corr["field"]
        value = corr["value"]

        if tid not in tip_map:
            logging.warning(f"[correction] Tipología {tid} not found")
            continue

        t = tip_map[tid]

        if field == "depth_m":
            t["depth_m"] = value
        elif field == "qty":
            t["qty"] = int(value)
        elif field == "backsplash_ml":
            t["backsplash_ml"] = value
        elif field.startswith("segments_m_"):
            idx = int(field.split("_")[-1])
            segs = t.get("segments_m", [])
            if idx < len(segs):
                segs[idx] = value
            else:
                segs.append(value)
            t["segments_m"] = segs

        logging.info(f"[correction] Applied: {tid} {field} = {value}")

    return tipologias


# ── 8. Render Functions ────────────────────────────────────────────────────────

def backsplash_needs_confirmation(
    backsplash_ml: Optional[float],
    segments_m: list[float],
    shape: str,
) -> bool:
    """Only ask confirmation if backsplash value is incoherent.

    Reasonable range: between 50% of longest segment and 150% of sum.
    If within range → use silently. If outside → confirm.
    """
    if backsplash_ml is None:
        return False  # Will use fallback, which is conservative — OK
    if not segments_m:
        return True

    max_possible = sum(segments_m) * 1.5
    min_possible = max(segments_m) * 0.5

    if backsplash_ml > max_possible:
        return True
    if backsplash_ml < min_possible:
        return True

    return False


def render_field(value: str, conf: float, method: str) -> str:
    """Render a field value with confidence marker.

    Rules:
    - ❌: fallback method OR very low confidence (< CONF_REVIEW)
    - ⚠️: low confidence (< CONF_HIGH) regardless of method
    - ✅: high confidence (>= CONF_HIGH) — even if method is "inferred"
           (high conf inferred = Claude read it clearly from the plan)
    """
    if method == "fallback" or conf < CONF_REVIEW:
        return f"{value} ❌"
    elif conf < CONF_HIGH:
        return f"{value} ⚠️"
    return f"{value} ✅"


def render_visual_extraction_summary(
    validation: ValidationResult,
    material_res: MaterialResolution,
) -> str:
    """Render validation summary for operator review."""
    lines = []

    # Material
    if material_res.mode == "variants":
        lines.append(f"**Material:** {' / '.join(material_res.resolved)} (se generan ambas variantes)")
    elif material_res.mode == "single":
        lines.append(f"**Material:** {material_res.resolved[0]}")
    else:
        lines.append(f"**Material:** ⚠️ {material_res.raw_text} — requiere definición")

    lines.append(f"**Espesor:** {material_res.thickness_mm}mm")
    lines.append("")
    lines.append("**Tipologías extraídas del plano:**")
    lines.append("")

    for t in validation.all_tipologias:
        conf = t.get("_confidence", {})
        tid = t.get("id", "?")
        qty = t.get("qty", 1)
        shape = t.get("shape", "?")
        segs = t.get("segments_m", [])
        depth = t.get("depth_m", 0)
        method = t.get("extraction_method", "fallback")
        bl = t.get("backsplash_ml")

        # Per-field markers
        seg_parts = []
        for s in segs:
            seg_parts.append(render_field(f"{s}m", conf.get("segments", 0), method))
        seg_str = " + ".join(seg_parts) if seg_parts else "?"

        depth_str = render_field(f"prof {depth}m", conf.get("depth", 0), method)

        # Shape marker
        if shape == "unknown":
            shape_str = f"{shape} ❌"
        elif conf.get("shape", 0) >= CONF_HIGH:
            shape_str = f"{shape} ✅"
        else:
            shape_str = f"{shape} ⚠️"

        lines.append(f"- **{tid}** ×{qty} — {shape_str} — {seg_str} — {depth_str}")

        # Backsplash: only flag if incoherent, otherwise show as OK
        if backsplash_needs_confirmation(bl, segs, shape):
            bl_str = f"zócalo {bl}ml ⚠️ requiere confirmación" if bl else "zócalo sin dato ⚠️"
        else:
            bl_str = f"zócalo {bl}ml ✅" if bl else "zócalo (fallback conservador) ✅"
        lines.append(f"  ↳ {bl_str}")

    if validation.soft_field_warnings:
        lines.append("")
        lines.append("**Campos que requieren confirmación:**")
        for w in validation.soft_field_warnings:  # Show ALL warnings
            lines.append(f"- {w}")

    lines.append("")
    if validation.requires_operator_validation:
        lines.append("¿Confirmás estos datos? Si hay que corregir, usá el formato:")
        lines.append("`DC-02 profundidad = 0.65` o `DC-07 tramo2 = 1.54`")
    else:
        lines.append("Datos validados automáticamente. Calculando despiece...")

    return "\n".join(lines)


def render_visual_building_step1(
    geometry: GeometrySummary,
    services: ServiceInference,
    material_res: MaterialResolution,
    pending: list[str],
) -> str:
    """Render PASO 1 with deterministic geometry."""
    lines = []

    # Material header
    if material_res.mode == "variants":
        lines.append(f"**Despiece geométrico** (aplica para ambos materiales: {' y '.join(material_res.resolved)})")
    else:
        mat_name = material_res.resolved[0] if material_res.resolved else "?"
        lines.append(f"**Despiece — {mat_name}**")

    lines.append("")
    lines.append("| Tipología | Cant | Forma | Medida unit | m² unit | m² total |")
    lines.append("|-----------|------|-------|-------------|---------|----------|")

    for t in geometry.tipologias:
        if t.shape == "L":
            medida = f"{t.segments_m[0]}×{t.depth_m} + {t.segments_m[1]}×{t.depth_m}"
        else:
            medida = f"{t.segments_m[0]}×{t.depth_m}" if t.segments_m else "?"
        lines.append(f"| {t.id} | {t.qty} | {t.shape} | {medida} | {t.m2_unit} | {t.m2_total} |")

    lines.append(f"| **TOTAL MESADA** | | | | | **{geometry.total_mesada_m2}** |")
    lines.append(f"| **TOTAL ZÓCALO** | | | | | **{geometry.total_backsplash_m2}** |")
    lines.append(f"| **TOTAL GENERAL** | | | | | **{geometry.total_m2}** |")

    lines.append("")
    lines.append("**Servicios:**")
    lines.append(f"- Colocación: NO (edificio)")
    lines.append(f"- PEGADOPILETA: ×{services.pegadopileta_qty}")
    lines.append(f"- ANAFE: ×{services.anafe_qty}")
    lines.append(f"- Flete + toma medidas: {services.flete_qty} viaje(s) (ceil({geometry.total_physical_pieces} piezas / 6))")

    # Pending questions
    if pending:
        lines.append("")
        lines.append("**Para avanzar con la cotización, confirmame:**")

        q_labels = {
            "planilla_marmoleria": "¿Tenés la planilla de marmolería? Si la tenés, subila para acelerar. Si no, avanzo con los planos.",
            "client_name": "Nombre del cliente",
            "locality": "Localidad de la obra",
            "material_definition": f"Material: {material_res.raw_text} — ¿cuál corresponde?",
            "pileta_provision": "Piletas: ¿las provee el cliente o D'Angelo?",
        }

        for i, q in enumerate(pending, 1):
            if q.startswith("confirm_backsplash_"):
                lines.append(f"{i}. Zócalo: confirmar ml por tipología")
            elif q in q_labels:
                lines.append(f"{i}. {q_labels[q]}")

    return "\n".join(lines)


# ── 9b. Fix D — Zone Detection + Page-by-Page ─────────────────────────────────

def parse_zone_detection(claude_response: str) -> list[dict]:
    """Parse zone detection JSON from Claude's pasada 0 response.

    Expected format: {"zones": [{"name": "PLANTA", "bbox": [x1,y1,x2,y2]}, ...]}
    """
    json_match = re.search(r"```json\s*(.*?)```", claude_response, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()
    else:
        json_match = re.search(r"\{[\s\S]*\"zones\"[\s\S]*\}", claude_response)
        if json_match:
            raw = json_match.group(0)
        else:
            return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    zones = data.get("zones", [])
    cleaned = []
    for idx, z in enumerate(zones):
        name = z.get("name", "")
        if not name:
            name = f"ZONA-{idx + 1}"
        bbox = z.get("bbox", [])
        if isinstance(bbox, list) and len(bbox) == 4:
            try:
                bbox = [int(b) for b in bbox]
            except (TypeError, ValueError):
                bbox = [0, 0, 700, 700]
        else:
            bbox = [0, 0, 700, 700]
        view_type = z.get("view_type", "unknown")
        if view_type not in ("top_view", "section", "detail", "unknown"):
            view_type = "unknown"
        try:
            zone_conf = float(z.get("confidence", 0.5))
            zone_conf = max(0.0, min(1.0, zone_conf))
        except (TypeError, ValueError):
            zone_conf = 0.5
        cleaned.append({"name": name, "bbox": bbox, "view_type": view_type, "confidence": zone_conf})

    return cleaned


def auto_select_zone(
    zones: list[dict],
    zone_default: Optional[str] = None,
) -> Optional[dict]:
    """Auto-select the most likely marmolería zone.

    Priority:
    1. zone_default (learned from previous page) — exact match case-insensitive
    2. view_type == "top_view" — vista cenital = marmolería
    3. Zone containing "PLANTA" in name — fallback if no view_type
    4. Largest zone by bbox area (excluding CORTE/DETALLE names)
    5. Largest zone overall
    6. None if empty list
    """
    if not zones:
        return None

    def bbox_area(z):
        b = z.get("bbox", [0, 0, 0, 0])
        return abs(b[2] - b[0]) * abs(b[3] - b[1])

    # 1. zone_default (learned from previous page)
    if zone_default:
        for z in zones:
            if z["name"].lower() == zone_default.lower():
                return z

    # 2. view_type == "top_view" — most reliable signal
    top_views = [z for z in zones if z.get("view_type") == "top_view"]
    if top_views:
        # Prefer highest confidence, then largest area as tiebreaker
        return max(top_views, key=lambda z: (z.get("confidence", 0.5), bbox_area(z)))

    # 3. Contains "PLANTA" in name
    for z in zones:
        if "planta" in z["name"].lower():
            return z

    # 4. Largest non-corte zone
    corte_keywords = ["corte", "detalle", "vista", "sección", "seccion"]
    non_corte = [z for z in zones if not any(kw in z["name"].lower() for kw in corte_keywords)]
    if non_corte:
        return max(non_corte, key=bbox_area)

    # 5. Largest overall
    return max(zones, key=bbox_area)


_CONFIRM_WORDS = {"sí", "si", "ok", "dale", "correcto", "confirmo", "confirmar", "bien", "perfecto", "listo"}
_SKIP_WORDS = {"skip", "ninguna", "saltar", "no hay", "no tiene", "sin marmolería"}


def parse_page_confirmation(
    text: str,
    current_tipologias: list[dict],
    available_zones: list[dict],
) -> dict:
    """Parse operator's response to page confirmation.

    Returns dict with 'action' key:
    - confirm: operator approved
    - zone_correction: operator wants a different zone → includes 'zone' key
    - value_correction: operator corrected measurements → includes 'corrections' key
    - skip: page has no marmolería
    - unclear: couldn't parse
    """
    text_lower = text.strip().lower()

    # Skip
    if any(w in text_lower for w in _SKIP_WORDS):
        return {"action": "skip"}

    # Confirm
    if text_lower in _CONFIRM_WORDS or text_lower.rstrip(".!") in _CONFIRM_WORDS:
        return {"action": "confirm"}

    # Zone correction: "zona = CORTE 1-1" or "zona: planta"
    zone_match = re.search(r"zona\s*[=:]\s*(.+)", text, re.IGNORECASE)
    if zone_match:
        zone_name = zone_match.group(1).strip()
        for z in available_zones:
            if z["name"].lower() == zone_name.lower() or zone_name.lower() in z["name"].lower():
                return {"action": "zone_correction", "zone": z}
        return {"action": "unclear"}

    # Value corrections (reuse existing parser)
    known_ids = [t.get("id", "") for t in current_tipologias]
    corrections = parse_operator_corrections(text, known_ids)
    if corrections:
        return {"action": "value_correction", "corrections": corrections}
    if corrections is None:
        return {"action": "unclear"}  # Looked like correction but didn't parse

    # Confirm if very short affirmative
    if len(text_lower) <= 5 and any(c in text_lower for c in ["si", "sí", "ok"]):
        return {"action": "confirm"}

    return {"action": "unclear"}


def render_page_confirmation(
    page: int,
    total_pages: int,
    selected_zone: dict,
    tipologias: list[dict],
    geometries: list,
    zone_was_auto: bool,
) -> str:
    """Render page confirmation message for operator."""
    lines = []

    lines.append(f"**Página {page}/{total_pages}**")
    zone_label = f"(auto: {selected_zone['name']})" if zone_was_auto else f"({selected_zone['name']})"
    lines.append(f"Zona analizada: {zone_label}")
    lines.append("")

    if not tipologias:
        lines.append("No se detectaron tipologías de marmolería en esta zona.")
        lines.append("")
        lines.append("Si hay marmolería en otra zona, indicá: `zona = CORTE 1-1`")
        lines.append("Si no hay marmolería en esta página: `skip`")
        return "\n".join(lines)

    for tip, geo in zip(tipologias, geometries):
        tid = tip.get("id", "?")
        qty = tip.get("qty", 1)
        shape = tip.get("shape", "?")
        method = tip.get("extraction_method", "fallback")
        conf = tip.get("_confidence", {})

        # Segments with markers
        segs = tip.get("segments_m", [])
        seg_parts = [render_field(f"{s}m", conf.get("segments", 0), method) for s in segs]
        seg_str = " + ".join(seg_parts) if seg_parts else "?"

        depth = tip.get("depth_m", 0)
        depth_str = render_field(f"prof {depth}m", conf.get("depth", 0), method)

        # Shape
        if shape == "unknown":
            shape_str = f"{shape} ❌"
        elif conf.get("shape", 0) >= CONF_HIGH:
            shape_str = f"{shape} ✅"
        else:
            shape_str = f"{shape} ⚠️"

        lines.append(f"**{tid}** ×{qty} — {shape_str} — {seg_str} — {depth_str}")

        # Geometry summary
        if hasattr(geo, "m2_unit"):
            lines.append(f"  m² unit: {geo.m2_unit} — m² total: {geo.m2_total}")

        # Backsplash
        bl = tip.get("backsplash_ml")
        if backsplash_needs_confirmation(bl, segs, shape):
            lines.append(f"  ↳ zócalo {bl}ml ⚠️" if bl else "  ↳ zócalo sin dato ⚠️")
        else:
            lines.append(f"  ↳ zócalo {bl}ml ✅" if bl else "  ↳ zócalo (fallback) ✅")

        lines.append("")

    lines.append("¿Confirmás? Si hay que corregir:")
    lines.append("- Medidas: `DC-02 profundidad = 0.65`")
    lines.append("- Zona: `zona = CORTE 1-1`")
    lines.append("- Sin marmolería: `skip`")

    return "\n".join(lines)


def render_final_paso1(
    all_geometries: list[TipologiaGeometry],
    services: ServiceInference,
    material_res: MaterialResolution,
    pending_questions: list[str],
) -> str:
    """Render final PASO 1 from all confirmed page geometries."""
    lines = []

    # Material header
    if material_res.mode == "variants":
        lines.append(f"**Despiece geométrico** (aplica para ambos materiales: {' y '.join(material_res.resolved)})")
    else:
        mat_name = material_res.resolved[0] if material_res.resolved else "?"
        lines.append(f"**Despiece — {mat_name}**")

    lines.append("")
    lines.append("| Tipología | Cant | Forma | Medida unit | m² unit | m² total |")
    lines.append("|-----------|------|-------|-------------|---------|----------|")

    total_mesada = 0
    total_backsplash = 0
    total_pieces = 0

    for t in all_geometries:
        if t.shape == "L" and len(t.segments_m) == 2:
            medida = f"{t.segments_m[0]}×{t.depth_m} + {t.segments_m[1]}×{t.depth_m}"
        else:
            medida = f"{t.segments_m[0]}×{t.depth_m}" if t.segments_m else "?"
        lines.append(f"| {t.id} | {t.qty} | {t.shape} | {medida} | {t.m2_unit} | {t.m2_total} |")
        total_mesada += t.m2_total
        total_backsplash += t.backsplash_m2_total
        total_pieces += t.physical_pieces_total

    total_mesada = round(total_mesada, 2)
    total_backsplash = round(total_backsplash, 2)
    total_m2 = round(total_mesada + total_backsplash, 2)

    lines.append(f"| **TOTAL MESADA** | | | | | **{total_mesada}** |")
    lines.append(f"| **TOTAL ZÓCALO** | | | | | **{total_backsplash}** |")
    lines.append(f"| **TOTAL GENERAL** | | | | | **{total_m2}** |")

    lines.append("")
    lines.append("**Servicios:**")
    lines.append(f"- Colocación: NO (edificio)")
    lines.append(f"- PEGADOPILETA: ×{services.pegadopileta_qty}")
    lines.append(f"- ANAFE: ×{services.anafe_qty}")
    flete_qty = math.ceil(total_pieces / 6) if total_pieces > 0 else 1
    lines.append(f"- Flete + toma medidas: {flete_qty} viaje(s)")

    if pending_questions:
        lines.append("")
        lines.append("**Para avanzar con la cotización, confirmame:**")
        q_labels = {
            "planilla_marmoleria": "¿Tenés la planilla de marmolería? Si la tenés, subila para acelerar. Si no, avanzo con los planos.",
            "client_name": "Nombre del cliente",
            "locality": "Localidad de la obra",
            "material_definition": f"Material: {material_res.raw_text} — ¿cuál corresponde?",
            "pileta_provision": "Piletas: ¿las provee el cliente o D'Angelo?",
        }
        for i, q in enumerate(pending_questions, 1):
            if q in q_labels:
                lines.append(f"{i}. {q_labels[q]}")
            elif q.startswith("confirm_backsplash_"):
                lines.append(f"{i}. Zócalo: confirmar ml por tipología")
            elif q.endswith("_extraction_needs_review"):
                tid = q.replace("_extraction_needs_review", "")
                lines.append(f"{i}. {tid}: medidas requieren confirmación")

    return "\n".join(lines)


# ── 9. JSON Parser (robust) ───────────────────────────────────────────────────

def parse_visual_extraction(claude_response: str) -> Optional[dict]:
    """Extract and validate JSON from Claude's response.

    Returns dict with 'material_text' and 'tipologias', or None on failure.
    """
    # Try to find JSON block in markdown
    json_match = re.search(r"```json\s*(.*?)```", claude_response, re.DOTALL)
    if json_match:
        raw_json = json_match.group(1).strip()
    else:
        # Try to find raw JSON object
        json_match = re.search(r"\{[\s\S]*\"tipologias\"[\s\S]*\}", claude_response)
        if json_match:
            raw_json = json_match.group(0)
        else:
            logging.warning("[visual_parse] No JSON found in Claude response")
            return None

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logging.error(f"[visual_parse] JSON decode error: {e}")
        return None

    # Validate required fields
    tipologias = data.get("tipologias", [])
    if not tipologias:
        logging.warning("[visual_parse] No tipologías in JSON")
        return None

    # Validate and clean each tipología
    cleaned = []
    seen_ids = set()
    for idx, t in enumerate(tipologias):
        tid = t.get("id", "")
        if not tid:
            continue

        # Dedup
        if tid in seen_ids:
            logging.warning(f"[visual_parse] Duplicate tipología: {tid}")
            continue
        seen_ids.add(tid)

        # Required fields with defaults
        qty = t.get("qty", 1)
        if not isinstance(qty, int) or qty < 1 or qty > 100:
            qty = 1

        shape = t.get("shape", "linear")
        if shape not in ("L", "linear", "unknown"):
            shape = "unknown"

        segs = t.get("segments_m", [])
        if not isinstance(segs, list) or not segs:
            continue
        # Validate segment ranges
        valid_segs = []
        for s in segs:
            try:
                s = float(s)
                if 0.1 <= s <= 10.0:
                    valid_segs.append(round(s, 2))
            except (TypeError, ValueError):
                pass
        if not valid_segs:
            continue

        depth = t.get("depth_m", 0.60)
        try:
            depth = float(depth)
            if not (0.1 <= depth <= 2.0):
                depth = 0.60
        except (TypeError, ValueError):
            depth = 0.60

        cleaned.append({
            "id": tid,
            "qty": qty,
            "shape": shape,
            "depth_m": round(depth, 2),
            "segments_m": valid_segs,
            "backsplash_ml": t.get("backsplash_ml"),
            "embedded_sink_count": t.get("embedded_sink_count", 0),
            "hob_count": t.get("hob_count", 0),
            "notes": t.get("notes", []),
            "extraction_method": t.get("extraction_method", "fallback"),
            "page": t.get("page", idx + 1),
        })

    if not cleaned:
        return None

    return {
        "material_text": data.get("material_text", ""),
        "tipologias": cleaned,
    }
