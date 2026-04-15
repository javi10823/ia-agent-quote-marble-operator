"""Deterministic cota (dimension) extraction from PDF plans.

Extracts dimensional text (e.g. "1.72", "0.60") from the drawing area of a
pdfplumber-loaded page, with precise pixel coordinates in the space of the
rasterized crop image. Handles:
  - Horizontal cotas via extract_words() with use_text_flow=True
  - Rotated (vertical) cotas by manually grouping chars with upright=False
  - Re-join of tokens split by CAD kerning (e.g. ["1", ".74"] → "1.74")
  - Decimal comma normalization ("2,50" → 2.5)
  - Unit heuristic: if ≥80% of values are >100, divide all by 1000 (mm → m)
  - Vertical filter: excludes caratula (top 10%) and footer (bottom 5%)

Coordinates are transformed from PDF points to crop pixels using:
    scale = dpi / 72.0
    x_crop = (x_pdf - crop_offset_x) * scale
    y_crop = (y_pdf - crop_offset_y) * scale

Returns empty list if page has no extractable text (scanned PDFs).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# A cota is a decimal number with a point or comma (integers are excluded
# to avoid capturing codes, scales, etc.)
COTA_REGEX = re.compile(r'^\d+[.,]\d+$')

# Known prefixes that mark zócalo / alto cotas
PREFIX_PATTERNS = [
    (re.compile(r'^Z=?', re.IGNORECASE), 'Z'),
    (re.compile(r'^ZOC=?', re.IGNORECASE), 'ZOC'),
    (re.compile(r'^H=?', re.IGNORECASE), 'H'),
    (re.compile(r'^h=?', re.IGNORECASE), 'H'),
]


@dataclass
class Cota:
    """A detected dimension in the drawing, in CROP pixel coordinates."""
    text: str                 # original string as extracted ("1.72")
    value: float              # normalized float (1.72)
    x: float                  # crop-space x (pixels, top-left origin)
    y: float                  # crop-space y (pixels, top-left origin)
    width: float              # bbox width in crop pixels
    height: float             # bbox height in crop pixels
    prefix: Optional[str] = None   # "Z", "ZOC", "H" if detected; None for plain cotas
    rotated: bool = False     # True if the cota was vertical in the PDF


def _normalize_value(text: str) -> Optional[float]:
    """Convert '2,50' → 2.5. Returns None if not a valid decimal cota."""
    if not COTA_REGEX.match(text):
        return None
    try:
        return float(text.replace(',', '.'))
    except ValueError:
        return None


def _detect_prefix(text: str) -> tuple[Optional[str], str]:
    """If text starts with a known prefix, strip it and return (prefix, rest)."""
    for pat, name in PREFIX_PATTERNS:
        m = pat.match(text)
        if m:
            return name, text[m.end():].strip()
    return None, text


def _rejoin_adjacent_numeric_tokens(words: list[dict]) -> list[dict]:
    """Fuse adjacent tokens that together form a valid decimal cota.

    CAD fonts sometimes split "1.74" into ["1", ".74"] or ["1.", "74"].
    This pass joins them before regex filtering.

    Criterion:
      - same line (diff in `top` < 2pt)
      - horizontal gap (word2.x0 - word1.x1) < 3pt
      - concatenated text matches COTA_REGEX
    """
    if not words:
        return []

    # Sort by top then x0 so adjacent tokens are near each other in the list
    sorted_words = sorted(words, key=lambda w: (w.get("top", 0), w.get("x0", 0)))
    out: list[dict] = []
    skip = set()

    for i, w in enumerate(sorted_words):
        if i in skip:
            continue
        merged = dict(w)
        j = i + 1
        while j < len(sorted_words):
            nxt = sorted_words[j]
            same_line = abs(nxt.get("top", 0) - merged.get("top", 0)) < 2
            gap = nxt.get("x0", 0) - merged.get("x1", 0)
            if not same_line or gap > 3 or gap < -1:
                break
            combined = merged["text"] + nxt["text"]
            if COTA_REGEX.match(combined):
                merged["text"] = combined
                merged["x1"] = nxt.get("x1", merged["x1"])
                merged["bottom"] = max(merged.get("bottom", 0), nxt.get("bottom", 0))
                skip.add(j)
                j += 1
            else:
                break
        out.append(merged)

    return out


def _extract_rotated_cotas(page, table_x0: float) -> list[dict]:
    """Detect vertical (rotated) cotas by grouping chars with upright=False.

    pdfplumber's extract_words() concatenates rotated chars in the wrong
    order (top→bottom instead of bottom→top), so "0.75" comes out as "57.0".
    We group chars by x-column and sort by `top` descending to get the
    correct string.

    Returns a list of pseudo-word dicts compatible with the horizontal flow:
      {text, x0, x1, top, bottom, rotated=True}
    """
    try:
        rotated_chars = [
            c for c in page.chars
            if not c.get('upright', True) and c.get('x0', 0) < table_x0
        ]
    except Exception:
        return []

    if not rotated_chars:
        return []

    # Cluster by x0 (same column = ~3pt tolerance)
    cols: dict[int, list] = defaultdict(list)
    for c in rotated_chars:
        key = round(c.get('x0', 0) / 3)
        cols[key].append(c)

    pseudo_words: list[dict] = []
    for _, chars in cols.items():
        if len(chars) < 2:
            continue
        # Rotated 90° CW: top→bottom in PDF = right→left when read.
        # Sorting by top DESC reconstructs the left-to-right reading order.
        chars_sorted = sorted(chars, key=lambda c: -c.get('top', 0))
        text = ''.join(c.get('text', '') for c in chars_sorted)
        if not text.strip():
            continue
        xs = [c.get('x0', 0) for c in chars]
        x1s = [c.get('x1', 0) for c in chars]
        tops = [c.get('top', 0) for c in chars]
        bottoms = [c.get('bottom', 0) for c in chars]
        pseudo_words.append({
            'text': text,
            'x0': min(xs),
            'x1': max(x1s),
            'top': min(tops),
            'bottom': max(bottoms),
            '_rotated': True,
        })

    return pseudo_words


def _apply_mm_heuristic(values: list[float]) -> tuple[list[float], bool]:
    """If ≥80% of values are >100, assume mm and divide by 1000.

    Returns (possibly_converted_values, was_converted).
    """
    if not values:
        return values, False
    big_count = sum(1 for v in values if v > 100)
    if big_count / len(values) >= 0.8:
        converted = [v / 1000.0 for v in values]
        logger.warning(
            f"[cotas] MM heuristic triggered: {big_count}/{len(values)} values >100. "
            f"Original: {values} → converted to meters: {converted}"
        )
        return converted, True
    return values, False


def extract_cotas_from_drawing(
    page,
    table_x0: float,
    dpi: int = 300,
    crop_offset_x: float = 0.0,
    crop_offset_y: float = 0.0,
) -> list[Cota]:
    """Extract dimensional cotas from the drawing area of a page.

    Args:
        page: pdfplumber Page object
        table_x0: x-coordinate (in PDF points) where the right-side table starts.
                  Only words with x0 < table_x0 are considered (drawing area).
        dpi: DPI of the rasterized crop image that will be shown to the LLM.
             Used to transform coordinates from PDF points to crop pixels.
        crop_offset_x: x-offset (in PDF points) of the crop origin. Default 0
                       (crop starts at left edge). Used by V2 sector crops.
        crop_offset_y: y-offset (in PDF points) of the crop origin. Default 0.

    Returns:
        List of Cota objects with coordinates already in crop-pixel space.
        Empty list if no cotas found (scanned PDFs, or no decimal numbers
        in the drawing area).
    """
    if not page:
        return []

    try:
        # Horizontal text flow
        raw_words = page.extract_words(use_text_flow=True) or []
    except Exception as e:
        logger.warning(f"[cotas] extract_words failed: {e}")
        raw_words = []

    # Add rotated cotas as pseudo-words
    rotated_words = _extract_rotated_cotas(page, table_x0)
    all_words = list(raw_words) + rotated_words

    # Filter by drawing region (x < table_x0)
    drawing_words = [w for w in all_words if w.get('x0', 0) < table_x0]

    # Vertical filter: exclude caratula (top 10%) and footer (bottom 5%)
    page_h = float(getattr(page, 'height', 0) or 0)
    if page_h > 0:
        caratula_y = page_h * 0.10
        footer_y = page_h * 0.95
        drawing_words = [
            w for w in drawing_words
            if caratula_y < w.get('top', 0) < footer_y
        ]

    # Re-join adjacent tokens split by kerning
    drawing_words = _rejoin_adjacent_numeric_tokens(drawing_words)

    # Parse each word into a Cota (if valid)
    raw_cotas: list[tuple[dict, float, Optional[str]]] = []
    for w in drawing_words:
        text = str(w.get('text', '')).strip()
        if not text:
            continue
        prefix, rest = _detect_prefix(text)
        value = _normalize_value(rest)
        if value is None:
            continue
        # Out-of-range filter (pre-heuristic): allow 0.04-10 (m) and 40-10000 (mm)
        if not (0.04 <= value <= 10000):
            continue
        raw_cotas.append((w, value, prefix))

    if not raw_cotas:
        logger.info("[cotas] No decimal cotas found in drawing area")
        return []

    # Apply mm → m heuristic on all values at once (consistent conversion)
    values = [v for _, v, _ in raw_cotas]
    converted, was_mm = _apply_mm_heuristic(values)

    # Build final Cotas with coordinates in crop-pixel space
    scale = dpi / 72.0
    cotas: list[Cota] = []
    for (w, _orig_value, prefix), final_value in zip(raw_cotas, converted):
        # Final range check (in meters) — exclude anything still out of range
        if not (0.04 <= final_value <= 10):
            continue
        x0_pt = float(w.get('x0', 0)) - crop_offset_x
        y0_pt = float(w.get('top', 0)) - crop_offset_y
        x1_pt = float(w.get('x1', 0)) - crop_offset_x
        y1_pt = float(w.get('bottom', 0)) - crop_offset_y
        x_crop = x0_pt * scale
        y_crop = y0_pt * scale
        width_crop = (x1_pt - x0_pt) * scale
        height_crop = (y1_pt - y0_pt) * scale

        cotas.append(Cota(
            text=str(w.get('text', '')),
            value=round(final_value, 4),
            x=round(x_crop, 1),
            y=round(y_crop, 1),
            width=round(width_crop, 1),
            height=round(height_crop, 1),
            prefix=prefix,
            rotated=bool(w.get('_rotated', False)),
        ))

    # Sort top-left → bottom-right for predictable output
    cotas.sort(key=lambda c: (c.y, c.x))

    logger.info(
        f"[cotas] Extracted {len(cotas)} cotas from drawing "
        f"(mm_heuristic={was_mm}, dpi={dpi}): "
        f"{[(c.text, c.value) for c in cotas]}"
    )
    return cotas


def format_cotas_for_prompt(cotas: list[Cota]) -> str:
    """Format cotas as a structured context block to inject into the LLM prompt.

    The coordinates are in pixels of the cropped drawing image, so the LLM
    can associate each number with a position on the image it sees.
    """
    if not cotas:
        return ""

    lines = [
        "COTAS DETECTADAS EN EL DIBUJO (fuente de verdad — NO inventes otros números):",
        "Coordenadas en píxeles de la imagen adjunta (origen top-left). Tu trabajo es",
        "geométrico: decidir qué cota es largo, ancho, zócalo, etc. usando la posición.",
        "",
    ]
    for c in cotas:
        prefix_str = f" [prefix={c.prefix}]" if c.prefix else ""
        rot_str = " (rotada)" if c.rotated else ""
        lines.append(
            f"- {c.value:.2f} m  @ (x={c.x:.0f}, y={c.y:.0f})"
            f"{prefix_str}{rot_str}"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Specs extraction — leyendas / tablas de características
# ═══════════════════════════════════════════════════════
#
# El plano normalmente tiene, al costado del dibujo o debajo, una tabla de
# características con texto tipo "ZOCALOS: 7 cm de altura", "PILETA: Johnson
# LUXOR COMPACT SI71", "MATERIAL: Purastone Blanco Paloma", etc.
#
# `extract_cotas_from_drawing` ignora todo esto porque filtra por decimales
# y excluye el área de la tabla (x0 >= table_x0). Resultado: los modelos de
# visión NO reciben los datos explícitos del plano y terminan reportando
# como "ambigüedad" cosas que están escritas literalmente al lado del dibujo.
#
# Esta extractor capta TODO el texto legible (sin filtro numérico) de áreas
# candidatas a leyenda y lo formatea para inyectar en el prompt.

# Keys conocidas — líneas con alguna de estas se consideran "spec útil"
_SPEC_KEYS = (
    "zocalo", "zócalo", "zocalos", "zócalos",
    "pileta", "bacha",
    "material", "mármol", "marmol", "granito", "silestone", "dekton",
    "neolith", "purastone", "puraprima", "laminatto", "quartz",
    "espesor", "20mm", "30mm", "2cm", "3cm",
    "frentin", "faldón", "faldon",
    "regrueso",
    "pulido", "pulida", "canto",
    "color", "terminación", "terminacion",
    "altura", "cm de altura",
)


def _is_spec_line(text: str) -> bool:
    """True si la línea parece contener una especificación útil (no un número suelto)."""
    t = text.lower().strip()
    if not t or len(t) < 3:
        return False
    # Solo un número → es una cota, no spec
    if COTA_REGEX.match(t):
        return False
    return any(k in t for k in _SPEC_KEYS)


def _group_words_into_lines(words: list[dict], y_tolerance: float = 3.0) -> list[str]:
    """Agrupa words por línea (misma `top` ± tolerancia) y ordena x0."""
    if not words:
        return []
    sorted_ws = sorted(words, key=lambda w: (w.get("top", 0), w.get("x0", 0)))
    lines: list[list[dict]] = []
    for w in sorted_ws:
        if lines and abs(w.get("top", 0) - lines[-1][-1].get("top", 0)) < y_tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [
        " ".join(str(w.get("text", "")).strip() for w in ln if w.get("text"))
        for ln in lines
    ]


def extract_specs_from_table(page, table_x0: float) -> list[str]:
    """Extraé líneas de la tabla de características / leyenda del plano.

    Captura texto a la DERECHA de table_x0 (típicamente la tabla de
    especificaciones) y también el margen inferior del área del dibujo
    (notas "ZOCALOS 7 cm", etc.). Filtra por keywords conocidas para
    descartar ruido (nombre del estudio, logo, escalas, etc.).
    """
    if not page:
        return []
    try:
        raw_words = page.extract_words(use_text_flow=True) or []
    except Exception as e:
        logger.warning(f"[specs] extract_words failed: {e}")
        return []

    # Tabla lateral: x0 >= table_x0. Además, capturamos cualquier texto del
    # dibujo que matchee keywords (notas al pie tipo "ZOCALOS 7 cm altura").
    page_h = float(getattr(page, "height", 0) or 0)
    footer_cutoff = page_h * 0.95 if page_h else float("inf")
    caratula_cutoff = page_h * 0.05 if page_h else 0

    table_words = [
        w for w in raw_words
        if w.get("x0", 0) >= table_x0 and caratula_cutoff < w.get("top", 0) < footer_cutoff
    ]
    drawing_words_with_spec_kw = [
        w for w in raw_words
        if w.get("x0", 0) < table_x0
        and any(k in str(w.get("text", "")).lower() for k in _SPEC_KEYS)
    ]

    lines = _group_words_into_lines(table_words + drawing_words_with_spec_kw)
    specs = [ln for ln in lines if _is_spec_line(ln)]
    # Dedup preservando orden
    seen: set[str] = set()
    out: list[str] = []
    for s in specs:
        key = s.lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(s.strip())
    logger.info(f"[specs] Extracted {len(out)} spec lines from table/legend: {out}")
    return out


def format_specs_for_prompt(specs: list[str]) -> str:
    """Formatea las especificaciones como bloque para inyectar en el prompt."""
    if not specs:
        return ""
    lines = [
        "ESPECIFICACIONES EXPLÍCITAS DEL PLANO (texto literal — NO las marques como ambigüedad):",
        "Si alguna de estas líneas cubre un dato (altura de zócalo, modelo de pileta, material,",
        "espesor, etc.), usá ese valor directo y NO reportes 'no especificado' en ambiguedades.",
        "",
    ]
    for s in specs:
        lines.append(f"- {s}")
    return "\n".join(lines)


def format_cotas_and_specs(cotas: list[Cota], specs: list[str]) -> str:
    """Combine cotas + specs en un único bloque de contexto."""
    parts = []
    cotas_block = format_cotas_for_prompt(cotas)
    if cotas_block:
        parts.append(cotas_block)
    specs_block = format_specs_for_prompt(specs)
    if specs_block:
        parts.append(specs_block)
    return "\n\n".join(parts)
