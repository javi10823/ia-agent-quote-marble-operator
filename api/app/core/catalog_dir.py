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
            await _sync_config_keys(async_session)
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

    # Always sync new top-level keys from config.json → DB
    await _sync_config_keys(async_session)


async def _sync_config_keys(async_session):
    """Merge new top-level keys from config.json file into DB config.

    Only adds keys that exist in the file but are missing in DB.
    Existing DB values are never overwritten (user edits win).
    """
    from sqlalchemy import text

    config_path = SOURCE_CATALOG_DIR / "config.json"
    if not config_path.exists():
        return

    with open(config_path, encoding="utf-8") as f:
        file_config = json.load(f)

    if not isinstance(file_config, dict):
        return

    async with async_session() as session:
        result = await session.execute(
            text("SELECT content FROM catalogs WHERE name = 'config'")
        )
        row = result.first()
        if not row:
            return

        db_config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        if not isinstance(db_config, dict):
            return

        new_keys = [k for k in file_config if k not in db_config]
        if not new_keys:
            return

        for k in new_keys:
            db_config[k] = file_config[k]

        await session.execute(
            text("UPDATE catalogs SET content = :content, updated_at = NOW() WHERE name = 'config'"),
            {"content": json.dumps(db_config, ensure_ascii=False)},
        )
        await session.commit()
        logger.info(f"Config sync: added {len(new_keys)} new keys from file → DB: {new_keys}")
