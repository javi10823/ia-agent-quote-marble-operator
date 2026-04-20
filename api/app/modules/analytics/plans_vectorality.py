"""Helper compartido: clasifica source_files por vectorialidad vs raster.

Usado desde:
- `scripts/analyze_plans_vectorality.py` (CLI, baja archivos vía HTTP)
- `POST /api/admin/analyze-plans-vectorality` (backend, lee archivos del disco)

Criterios idénticos al pipeline real en `agent.py` (vision detection).
NO persiste nada. NO tiene UI. Solo devuelve un JSON resumen.
"""
from __future__ import annotations

import io
from collections import Counter
from typing import Callable, Optional

import pdfplumber

# Umbrales idénticos a los de `agent.py` (líneas 2480-2508).
VECTOR_LINES_THRESHOLD = 20
VECTOR_RECTS_THRESHOLD = 10
VECTOR_CURVES_THRESHOLD = 20
RASTER_MIN_DIMENSION = 200  # px — imágenes más chicas no cuentan como scan

# Umbral de decisión para recommend_2d: ratio usable ≥ 60%.
_USABLE_FOR_2D_THRESHOLD = 0.60


def classify_pdf(pdf_bytes: bytes) -> dict:
    """Analiza un PDF con pdfplumber y devuelve qué tiene.

    - has_raster: True si alguna página tiene imagen > 200x200 (scan).
    - has_vectors: True si alguna página supera umbrales de primitives.
    - error: str si falló el parse.
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            has_raster = False
            has_vectors = False
            for page in pdf.pages:
                for img in (page.images or []):
                    w = img.get("width", 0) or (img.get("x1", 0) - img.get("x0", 0))
                    h = img.get("height", 0) or (img.get("top", 0) - img.get("bottom", 0))
                    if abs(w) > RASTER_MIN_DIMENSION and abs(h) > RASTER_MIN_DIMENSION:
                        has_raster = True
                        break
                n_lines = len(page.lines or [])
                n_rects = len(page.rects or [])
                n_curves = len(page.curves or [])
                if (
                    n_lines > VECTOR_LINES_THRESHOLD
                    or n_rects > VECTOR_RECTS_THRESHOLD
                    or n_curves > VECTOR_CURVES_THRESHOLD
                ):
                    has_vectors = True
            return {"has_raster": has_raster, "has_vectors": has_vectors}
    except Exception as e:
        return {"error": f"pdf_parse_failed: {e}"}


def classify_source_file(source_file: dict, pdf_bytes: Optional[bytes]) -> str:
    """Categoría final según mime + resultado del parse PDF.

    Categorías:
    - `raster_only`: imagen pura (jpg/png/webp) o PDF scan sin vectors.
    - `vectorial_clean`: PDF con vectors + sin raster grande.
    - `vectorial_and_raster`: PDF con ambos.
    - `unknown`: no pudimos bajar o parsear.
    """
    mime = (source_file.get("type") or "").lower()
    filename = (source_file.get("filename") or "").lower()

    if mime.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "raster_only"

    if not pdf_bytes:
        return "unknown"

    info = classify_pdf(pdf_bytes)
    if info.get("error"):
        return "unknown"

    if info["has_vectors"] and info["has_raster"]:
        return "vectorial_and_raster"
    if info["has_vectors"]:
        return "vectorial_clean"
    return "raster_only"


def format_summary(categories: list[str]) -> dict:
    """Shape exacto de respuesta:

    {
      "total_analyzed": 150,
      "counts": {"vectorial_clean": 95, "raster_only": 35, ...},
      "percentages": {"vectorial_clean": 63.3, ...},
      "recommend_2d": true
    }
    """
    counts = Counter(categories)
    total = len(categories)
    percentages = {
        k: round(100 * v / total, 1) if total else 0.0
        for k, v in counts.items()
    }
    # recommend_2d: ≥60% usable (vectorial_clean + vectorial_and_raster).
    usable = counts.get("vectorial_clean", 0) + counts.get("vectorial_and_raster", 0)
    ratio_usable = (usable / total) if total else 0.0
    return {
        "total_analyzed": total,
        "counts": dict(counts),
        "percentages": percentages,
        "recommend_2d": ratio_usable >= _USABLE_FOR_2D_THRESHOLD,
    }


def analyze_source_files(
    items: list[tuple[str, dict]],
    fetch_pdf_bytes: Callable[[str, dict], Optional[bytes]],
) -> dict:
    """Itera los source_files y devuelve el resumen.

    `items` = lista de `(quote_id, source_file_dict)`.
    `fetch_pdf_bytes(quote_id, source_file)` → bytes del PDF o None si falla.

    No descarga nada por sí misma — el caller decide cómo obtener bytes
    (HTTP para CLI, lectura de disco para endpoint admin).
    """
    categories: list[str] = []
    for quote_id, sf in items:
        mime = (sf.get("type") or "").lower()
        filename = (sf.get("filename") or "").lower()
        # Short-circuit: imagen pura no necesita descarga.
        if mime.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            categories.append("raster_only")
            continue
        pdf_bytes = fetch_pdf_bytes(quote_id, sf)
        categories.append(classify_source_file(sf, pdf_bytes))
    return format_summary(categories)
