#!/usr/bin/env python3
"""CLI wrapper del helper `app.modules.analytics.plans_vectorality`.

Útil para correr el análisis sin levantar el backend — pero requiere
DATABASE_URL + env vars de settings. Si peleas con eso, usá el endpoint
admin POST /api/admin/analyze-plans-vectorality que hace lo mismo sin
secrets locales.

**Uso:**

    python scripts/analyze_plans_vectorality.py              # últimas 50
    python scripts/analyze_plans_vectorality.py --limit 200
    python scripts/analyze_plans_vectorality.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

SCRIPT_DIR = Path(__file__).parent
API_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(API_DIR))


async def _collect_source_files(limit: int) -> list[tuple[str, dict]]:
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


def _make_http_fetcher(base_url: str):
    def _fetch(quote_id: str, source_file: dict) -> Optional[bytes]:
        candidates = []
        for key in ("drive_download_url", "drive_url", "url"):
            u = source_file.get(key)
            if not u:
                continue
            if u.startswith("/") and base_url:
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
    return _fetch


async def main():
    from app.modules.analytics.plans_vectorality import analyze_source_files

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--base-url", default=os.environ.get("FILES_BASE_URL", ""),
    )
    args = parser.parse_args()

    print(f"→ Trayendo últimas {args.limit} quotes...", file=sys.stderr)
    items = await _collect_source_files(args.limit)
    print(f"  {len(items)} source_files encontrados.", file=sys.stderr)

    fetcher = _make_http_fetcher(args.base_url) if args.base_url else (
        lambda q, sf: None
    )
    summary = analyze_source_files(items, fetcher)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print()
    print("=" * 60)
    print("RESUMEN — ratio vectorial vs scan")
    print("=" * 60)
    print(f"Total analizados: {summary['total_analyzed']}")
    print()
    for cat, count in summary["counts"].items():
        pct = summary["percentages"][cat]
        print(f"  {cat:22s}: {count:4d}  ({pct}%)")
    print()
    rec = summary["recommend_2d"]
    print(f"recommend_2d: {rec}")


if __name__ == "__main__":
    asyncio.run(main())
