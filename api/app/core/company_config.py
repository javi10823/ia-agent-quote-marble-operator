"""Shared config.json reader — single source of truth for business parameters."""

import json
import logging
from pathlib import Path
from typing import Any

_cache: dict | None = None
_CONFIG_PATH = Path(__file__).parent.parent.parent / "catalog" / "config.json"


def get_config() -> dict:
    """Load config from DB first, file fallback. Returns full config dict."""
    global _cache
    if _cache is not None:
        return _cache
    # Try DB first (matches catalog_tool pattern)
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
        eng = create_engine(sync_url)
        with eng.connect() as conn:
            result = conn.execute(text("SELECT content FROM catalogs WHERE name = 'config'"))
            row = result.first()
            if row:
                data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                _cache = data
                eng.dispose()
                return _cache
        eng.dispose()
    except Exception as e:
        logging.debug(f"DB config read failed, falling back to file: {e}")
    # Fallback to file
    try:
        _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        _cache = {}
    return _cache


def invalidate_config_cache():
    """Clear cached config — call after config.json is updated."""
    global _cache
    _cache = None


def get(path: str, default: Any = None) -> Any:
    """Get a nested config value by dot-separated path.

    Example: get("iva.multiplier") → 1.21
    """
    config = get_config()
    keys = path.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
        if val is None:
            return default
    return val
