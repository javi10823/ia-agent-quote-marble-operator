"""Shared config.json reader — single source of truth for business parameters."""

import json
import logging
from pathlib import Path
from typing import Any

_cache: dict | None = None
_CONFIG_PATH = Path(__file__).parent.parent.parent / "catalog" / "config.json"


def get_config() -> dict:
    """Load and cache config.json. Returns full config dict."""
    global _cache
    if _cache is not None:
        return _cache
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
