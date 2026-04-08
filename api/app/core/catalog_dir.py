"""Catalog persistence via PostgreSQL.

Catalogs are stored in the `catalogs` table. On first boot, they're
seeded from the source JSON files. Edits via the config UI persist
in the DB across deploys.

For tools that need sync access (catalog_tool.py), we provide
load_catalog() and save_catalog() that use synchronous DB access.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent  # api/
SOURCE_CATALOG_DIR = BASE_DIR / "catalog"

# Keep CATALOG_DIR for backward compat (templates, etc.)
CATALOG_DIR = SOURCE_CATALOG_DIR


def load_catalog_from_file(name: str) -> list:
    """Load catalog from source JSON file (fallback)."""
    path = SOURCE_CATALOG_DIR / f"{name}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("items", [data])


async def seed_catalogs_to_db(engine):
    """Seed catalogs from source JSONs into DB on first boot."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Check if table has data
        result = await session.execute(text("SELECT COUNT(*) FROM catalogs"))
        count = result.scalar()
        if count > 0:
            logger.info(f"Catalogs table already has {count} entries, skipping seed")
            return

        # Seed from source files
        source_files = list(SOURCE_CATALOG_DIR.glob("*.json"))
        for src in source_files:
            name = src.stem  # e.g. "labor" from "labor.json"
            try:
                with open(src, encoding="utf-8") as f:
                    content = json.load(f)
                await session.execute(
                    text("INSERT INTO catalogs (name, content) VALUES (:name, :content)"),
                    {"name": name, "content": json.dumps(content, ensure_ascii=False)},
                )
            except Exception as e:
                logger.warning(f"Could not seed catalog {name}: {e}")

        await session.commit()
        logger.info(f"Seeded {len(source_files)} catalogs to DB")
