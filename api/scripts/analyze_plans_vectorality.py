#!/usr/bin/env python3
"""Analiza los planos subidos en quotes recientes y clasifica cada uno
como "vectorial limpio" vs "raster/scan" vs "desconocido".

Este script existe para decidir si vale la pena invertir en un fast-path
vectorial (PR 2d). Si la mayoría de los planos reales son PDFs con
vectores limpios, 2d resuelve estructuralmente el problema de
estocasticidad del topology LLM. Si la mayoría son scans/fotos, 2d
ayuda poco.

**Criterios de clasificación** — idénticos a los que usa el pipeline
en `agent.py` (vision detection, líneas 2480-2508):

- `raster_only`: PDF con imagen raster > 200x200 (scan embebido) SIN
  vectors limpios, o archivo imagen pura (jpg/png/webp).
- `vectorial_clean`: PDF con `lines > 20` o `rects > 10` o
  `curves > 20` en al menos 1 página (CAD/arquitectónico).
- `vectorial_and_raster`: ambos — PDF con scan + vectors.
- `unknown`: no pudimos abrir el PDF, o quedó sin señales claras.

**Uso:**

    python scripts/analyze_plans_vectorality.py              # últimas 50
    python scripts/analyze_plans_vectorality.py --limit 200  # últimas 200
    python scripts/analyze_plans_vectorality.py --json       # output JSON

Requiere DATABASE_URL + acceso HTTP a los `url` del source_files. Si
los archivos están en `/files/...` locales de Railway, correr el
script desde el mismo contenedor (o bajar los archivos primero).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import pdfplumber
import requests

SCRIPT_DIR = Path(__file__).parent
API_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(API_DIR))


# Umbrales idénticos a los de `agent.py` — si cambian allí, cambiar acá.
VECTOR_LINES_THRESHOLD = 20
VECTOR_RECTS_THRESHOLD = 10
VECTOR_CURVES_THRESHOLD = 20
RASTER_MIN_DIMENSION = 200  # px — imágenes < esto no cuentan como scan


def _classify_pdf(pdf_bytes: bytes) -> dict:
    """Analiza un PDF con pdfplumber y devuelve métricas agregadas.

    Devuelve dict con:
    - has_raster: True si hay imagen raster > 200x200 en alguna página.
    - has_vectors: True si alguna página supera umbrales de lines/rects/curves.
    - pages: int
    - raster_details: list of (w, h) por página.
    - vector_details: list of (lines, rects, curves) por página.
    - error: str si falló el parse.
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = pdf.pages
            has_raster = False
            has_vectors = False
            raster_details = []
            vector_details = []
            for page in pages:
                # Raster
                page_raster = False
                for img in (page.images or []):
                    w = img.get("width", 0) or (img.get("x1", 0) - img.get("x0", 0))
                    h = img.get("height", 0) or (img.get("top", 0) - img.get("bottom", 0))
                    if abs(w) > RASTER_MIN_DIMENSION and abs(h) > RASTER_MIN_DIMENSION:
                        page_raster = True
                        raster_details.append((abs(w), abs(h)))
                if page_raster:
                    has_raster = True

                # Vectors
                n_lines = len(page.lines or [])
                n_rects = len(page.rects or [])
                n_curves = len(page.curves or [])
                vector_details.append((n_lines, n_rects, n_curves))
                if (
                    n_lines > VECTOR_LINES_THRESHOLD
                    or n_rects > VECTOR_RECTS_THRESHOLD
                    or n_curves > VECTOR_CURVES_THRESHOLD
                ):
                    has_vectors = True

            return {
                "has_raster": has_raster,
                "has_vectors": has_vectors,
                "pages": len(pages),
                "raster_details": raster_details,
                "vector_details": vector_details,
            }
    except Exception as e:
        return {"error": f"pdf_parse_failed: {e}"}


def _classify_category(source_file: dict, pdf_bytes: Optional[bytes]) -> str:
    """Devuelve la categoría final:
    - "raster_only" — imagen pura (jpg/png/webp) o PDF scan sin vectors.
    - "vectorial_clean" — PDF con vectors + sin raster grande.
    - "vectorial_and_raster" — PDF con ambos.
    - "unknown" — no pudimos leer.
    """
    mime = (source_file.get("type") or "").lower()
    filename = (source_file.get("filename") or "").lower()

    # Archivos imagen: raster por definición
    if mime.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "raster_only"

    if not pdf_bytes:
        return "unknown"

    info = _classify_pdf(pdf_bytes)
    if info.get("error"):
        return "unknown"

    has_raster = info["has_raster"]
    has_vectors = info["has_vectors"]
    if has_vectors and has_raster:
        return "vectorial_and_raster"
    if has_vectors:
        return "vectorial_clean"
    return "raster_only"  # PDF sin vectors + con o sin raster — lo tratamos como scan


def _fetch_pdf_bytes(source_file: dict, base_url: str) -> Optional[bytes]:
    """Intenta bajar el PDF. Orden:
    1. drive_download_url (si existe).
    2. drive_url (si existe).
    3. url relativo (prepend base_url).

    Devuelve bytes o None si falla.
    """
    candidates = []
    for key in ("drive_download_url", "drive_url", "url"):
        u = source_file.get(key)
        if not u:
            continue
        if u.startswith("/"):
            u = base_url.rstrip("/") + u
        candidates.append(u)

    for url in candidates:
        try:
            r = requests.get(url, timeout=30, allow_redirects=True)
            if r.status_code == 200 and r.content:
                return r.content
        except Exception:
            continue
    return None


async def _collect_source_files(limit: int) -> list[tuple[str, dict]]:
    """Trae los últimos N source_files de la DB, ordenados por created_at desc.
    Devuelve lista de (quote_id, source_file_dict)."""
    from app.core.database import AsyncSessionLocal
    from app.models.quote import Quote
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Quote).order_by(Quote.created_at.desc()).limit(limit)
        )
        quotes = result.scalars().all()
        out: list[tuple[str, dict]] = []
        for q in quotes:
            for sf in (q.source_files or []):
                out.append((q.id, sf))
        return out


def _format_summary(results: list[dict]) -> dict:
    by_category = Counter(r["category"] for r in results)
    total = len(results)
    ratios = {k: round(v / total, 3) if total else 0 for k, v in by_category.items()}
    return {
        "total_files": total,
        "by_category": dict(by_category),
        "ratios": ratios,
        "categories_explained": {
            "raster_only": (
                "imagen pura o PDF scan sin vectors — 2d NO ayuda acá, "
                "seguimos dependiendo del VLM"
            ),
            "vectorial_clean": (
                "PDF con primitives limpias (lines/rects/curves) — "
                "2d puede extraer bboxes determinísticos"
            ),
            "vectorial_and_raster": (
                "ambos — 2d puede aprovechar los vectors, combinar con "
                "el raster si es necesario"
            ),
            "unknown": "no pudimos leer el archivo (link muerto, parse failed, etc)",
        },
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="cantidad de quotes a analizar (default 50)")
    parser.add_argument("--json", action="store_true", help="output JSON (default: tabla legible)")
    parser.add_argument(
        "--base-url", default=os.environ.get("FILES_BASE_URL", ""),
        help="URL base para source_file.url relativos (ej: https://xxx.railway.app)",
    )
    args = parser.parse_args()

    print(f"→ Trayendo últimas {args.limit} quotes con source_files...", file=sys.stderr)
    items = await _collect_source_files(args.limit)
    print(f"  {len(items)} source_files encontrados.", file=sys.stderr)

    results: list[dict] = []
    for i, (quote_id, sf) in enumerate(items, 1):
        mime = sf.get("type") or ""
        filename = sf.get("filename") or "<sin nombre>"
        if mime.startswith("image/") or filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            # No intentamos descargar — sabemos que es raster por tipo
            cat = _classify_category(sf, None)
            results.append({"quote_id": quote_id, "filename": filename, "mime": mime, "category": cat})
            continue
        print(f"  [{i}/{len(items)}] {filename[:50]}... ", file=sys.stderr, end="")
        pdf_bytes = _fetch_pdf_bytes(sf, args.base_url) if args.base_url or sf.get("drive_download_url") else None
        cat = _classify_category(sf, pdf_bytes)
        print(cat, file=sys.stderr)
        results.append({"quote_id": quote_id, "filename": filename, "mime": mime, "category": cat})

    summary = _format_summary(results)

    if args.json:
        print(json.dumps({"summary": summary, "files": results}, ensure_ascii=False, indent=2))
        return

    # Output legible
    print()
    print("=" * 60)
    print("RESUMEN — ratio vectorial vs scan")
    print("=" * 60)
    print(f"Total analizados: {summary['total_files']}")
    print()
    for cat, count in summary["by_category"].items():
        pct = int(summary["ratios"][cat] * 100)
        print(f"  {cat:22s}: {count:4d}  ({pct}%)")
    print()
    print("Decisión sobre PR 2d (fast-path vectorial):")
    v_clean = summary["by_category"].get("vectorial_clean", 0)
    v_both = summary["by_category"].get("vectorial_and_raster", 0)
    total = max(summary["total_files"], 1)
    usable_for_2d = (v_clean + v_both) / total
    if usable_for_2d >= 0.6:
        print(f"  ✅ {int(usable_for_2d*100)}% usable para 2d → vale la inversión")
    elif usable_for_2d >= 0.3:
        print(f"  ⚠️  {int(usable_for_2d*100)}% usable — decisión mixta")
    else:
        print(f"  ❌ solo {int(usable_for_2d*100)}% usable — 2d ayuda poco, buscar otra estrategia")


if __name__ == "__main__":
    asyncio.run(main())
