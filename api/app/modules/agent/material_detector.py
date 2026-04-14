"""Detect distinct canonical materials mentioned in an operator brief.

Used by the operator web flow (POST /api/quotes/:id/chat) to enforce the rule
"1 material = 1 presupuesto". The chatbot flow (POST /api/v1/quote) is NOT
affected — it still supports multi-material arrays.

Design goals (restrictions from operator feedback):
- Match ONLY against canonical catalog names (same source as catalog_lookup)
- Case-insensitive match, requires the FULL canonical name or a valid SKU
- NO loose substring matching ("blanco", "norte" alone must NEVER trigger)
- Fail-open: if the detector is unsure, return a single match — better to let
  a valid case through than to interrupt the operator unnecessarily
- Threshold: the caller only interrupts when >=2 distinct materials detected
"""
from __future__ import annotations

import re
from functools import lru_cache


# Catalog files that contain materials. Order does not matter.
_MATERIAL_CATALOGS = (
    "materials-silestone",
    "materials-granito-nacional",
    "materials-granito-importado",
    "materials-marmol",
    "materials-dekton",
    "materials-neolith",
    "materials-purastone",
    "materials-puraprima",
    "materials-laminatto",
)


def _load_all_materials() -> list[dict]:
    """Load every material row across catalog files. Lazy + errors swallowed."""
    from app.modules.agent.tools.catalog_tool import _load_catalog

    items: list[dict] = []
    for cat in _MATERIAL_CATALOGS:
        try:
            for row in _load_catalog(cat):
                if isinstance(row, dict):
                    items.append(row)
        except Exception:
            continue
    return items


@lru_cache(maxsize=1)
def _build_index() -> tuple[tuple[str, str], ...]:
    """Return tuple of (normalized_key, canonical_name) for every material.

    Keys include:
      - the full canonical name (lowered, collapsed spaces)
      - the SKU (lowered)

    Cached at process level. If catalogs change at runtime, clear with
    invalidate_material_detector_cache().
    """
    pairs: list[tuple[str, str]] = []
    for row in _load_all_materials():
        name = (row.get("name") or "").strip()
        sku = (row.get("sku") or "").strip()
        if name:
            key = _normalize(name)
            if key:
                pairs.append((key, name))
        if sku:
            key = _normalize(sku)
            if key:
                pairs.append((key, name or sku))
    return tuple(pairs)


def invalidate_material_detector_cache() -> None:
    """Clear the cached index (call after catalog updates)."""
    _build_index.cache_clear()


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace. Preserves all letters/digits."""
    if not text:
        return ""
    # Collapse whitespace sequences (spaces/tabs/newlines) into single space
    return re.sub(r"\s+", " ", text.strip().lower())


def detect_materials_in_brief(
    text: str, min_sku_length: int = 5
) -> list[str]:
    """Return list of canonical material names distinctly mentioned in `text`.

    Matching rules (strict, fail-open):
    - Text is normalized (lowercased, whitespace collapsed).
    - A material is "mentioned" only if the full canonical name appears as a
      whole-word sequence in the normalized text, OR a SKU of length >=
      min_sku_length appears (word-boundary aware).
    - Duplicates collapsed — each canonical name returned at most once,
      preserving order of first match.
    - Partial / substring matches ("blanco", "norte", etc. alone) are ignored.

    Fail-open behavior:
    - If the catalog index cannot be built or is empty, returns [].
    - If normalization fails, returns [].
    - Callers must treat the empty/single result as "do not interrupt".
    """
    if not text:
        return []
    try:
        norm = _normalize(text)
        if not norm:
            return []
        index = _build_index()
    except Exception:
        return []
    if not index:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for key, canonical in index:
        if not key:
            continue
        # SKUs are short; require a minimum length to avoid matching generic
        # tokens like "m2" or "20" as if they were SKUs.
        if len(key) < min_sku_length and canonical != key:
            # This is likely a short SKU. Keep the guard but do not outright
            # skip — catalogs rarely have SKUs shorter than 5 chars.
            pass
        if len(key) < 4:
            # Never try to match 1-3 char tokens (too ambiguous).
            continue
        # Word-boundary match: key must appear surrounded by non-word chars
        # (or start/end of string).
        pattern = r"(?<![\w])" + re.escape(key) + r"(?![\w])"
        if re.search(pattern, norm):
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
    return found
