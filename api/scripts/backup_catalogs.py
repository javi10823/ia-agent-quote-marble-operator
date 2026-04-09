#!/usr/bin/env python3
"""Export ALL catalogs to a single JSON backup file.

Usage:
    python scripts/backup_catalogs.py

Reads from DB if available (DATABASE_URL), otherwise from catalog/*.json files.
Output: backups/catalog_backup_YYYY-MM-DD_HHmm.json
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
API_DIR = SCRIPT_DIR.parent
CATALOG_DIR = API_DIR / "catalog"
BACKUP_DIR = API_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

CATALOGS = [
    "labor", "delivery-zones", "sinks",
    "materials-silestone", "materials-purastone",
    "materials-dekton", "materials-neolith",
    "materials-puraprima", "materials-laminatto",
    "materials-granito-nacional", "materials-granito-importado",
    "materials-marmol",
    "stock", "architects", "config",
]


def load_from_db():
    """Try loading catalogs from PostgreSQL."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url or "sqlite" in db_url:
        return None

    try:
        from sqlalchemy import create_engine, text
        sync_url = db_url.replace("+asyncpg", "").replace("+aiosqlite", "")
        engine = create_engine(sync_url)
        catalogs = {}
        with engine.connect() as conn:
            for name in CATALOGS:
                result = conn.execute(text("SELECT content FROM catalogs WHERE name = :n"), {"n": name})
                row = result.first()
                if row:
                    content = row[0]
                    catalogs[name] = json.loads(content) if isinstance(content, str) else content
        engine.dispose()
        return catalogs if catalogs else None
    except Exception as e:
        print(f"  DB not available ({e.__class__.__name__}), falling back to files")
        return None


def load_from_files():
    """Load catalogs from JSON files."""
    catalogs = {}
    for name in CATALOGS:
        path = CATALOG_DIR / f"{name}.json"
        if path.exists():
            catalogs[name] = json.loads(path.read_text(encoding="utf-8"))
    return catalogs


def main():
    # Try .env
    env_path = API_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    print("Backing up all catalogs...")

    # Try DB first, fallback to files
    source = "database"
    catalogs = load_from_db()
    if not catalogs:
        source = "files"
        catalogs = load_from_files()

    if not catalogs:
        print("ERROR: No catalogs found in DB or files")
        sys.exit(1)

    # Count items
    total_items = 0
    for name, data in catalogs.items():
        if isinstance(data, list):
            total_items += len(data)
        elif isinstance(data, dict):
            items = data.get("items", data.get("stock", []))
            total_items += len(items) if isinstance(items, list) else 1

    ts = datetime.now()
    backup = {
        "timestamp": ts.isoformat(),
        "source": source,
        "catalog_count": len(catalogs),
        "total_items": total_items,
        "catalogs": catalogs,
    }

    filename = f"catalog_backup_{ts.strftime('%Y-%m-%d_%H%M')}.json"
    output_path = BACKUP_DIR / filename
    output_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"\n  Source: {source}")
    print(f"  Catalogs: {len(catalogs)}")
    print(f"  Total items: {total_items}")
    print(f"  File: {output_path}")
    print(f"  Size: {size_kb:.1f} KB")
    print(f"\nBackup complete.")


if __name__ == "__main__":
    main()
