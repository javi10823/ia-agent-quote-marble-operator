import json
import logging
import math
from pathlib import Path

from app.core.catalog_dir import CATALOG_DIR

_catalog_cache: dict[str, tuple[float, list]] = {}  # name -> (mtime, items)
_config_cache: dict | None = None
_ai_config_cache: dict | None = None


def get_ai_config() -> dict:
    """Read AI engine toggles from config.json (DB first, file fallback)."""
    global _ai_config_cache
    if _ai_config_cache is not None:
        return _ai_config_cache
    defaults = {"use_opus_for_plans": True, "rotate_plan_images": False, "max_examples": 1, "monthly_budget_usd": 300, "enable_hard_limit": True}
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
        eng = create_engine(sync_url)
        with eng.connect() as conn:
            result = conn.execute(text("SELECT content FROM catalogs WHERE name = 'config'"))
            row = result.first()
            if row:
                cfg = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                ai = cfg.get("ai_engine", {})
                _ai_config_cache = {**defaults, **ai}
                eng.dispose()
                return _ai_config_cache
        eng.dispose()
    except Exception:
        pass
    try:
        cfg = json.loads((CATALOG_DIR / "config.json").read_text(encoding="utf-8"))
        ai = cfg.get("ai_engine", {})
        _ai_config_cache = {**defaults, **ai}
    except Exception:
        _ai_config_cache = defaults
    return _ai_config_cache


def invalidate_ai_config_cache():
    global _ai_config_cache
    _ai_config_cache = None


def _get_iva_multiplier() -> float:
    """Read IVA multiplier from config (DB first, file fallback)."""
    global _config_cache
    if _config_cache is None:
        try:
            from sqlalchemy import create_engine, text
            from app.core.config import settings
            sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
            eng = create_engine(sync_url)
            with eng.connect() as conn:
                result = conn.execute(text("SELECT content FROM catalogs WHERE name = 'config'"))
                row = result.first()
                if row:
                    _config_cache = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            eng.dispose()
        except Exception:
            pass
        if _config_cache is None:
            try:
                _config_cache = json.loads((CATALOG_DIR / "config.json").read_text(encoding="utf-8"))
            except Exception:
                _config_cache = {}
    return _config_cache.get("iva", {}).get("multiplier", 1.21)


def _load_catalog(name: str) -> list:
    # Check file mtime to auto-invalidate stale cache
    path = CATALOG_DIR / f"{name}.json"
    current_mtime = path.stat().st_mtime if path.exists() else 0.0
    if name in _catalog_cache:
        cached_mtime, cached_items = _catalog_cache[name]
        if cached_mtime >= current_mtime and current_mtime > 0:
            return cached_items
    # Try DB first (persistent), fallback to file
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
        eng = create_engine(sync_url)
        with eng.connect() as conn:
            result = conn.execute(text("SELECT content FROM catalogs WHERE name = :name"), {"name": name})
            row = result.first()
            if row:
                raw = row[0]
                data = json.loads(raw) if isinstance(raw, str) else raw
                items = data if isinstance(data, list) else data.get("items", [data]) if isinstance(data, dict) else []
                _catalog_cache[name] = (current_mtime, items)
                logging.debug(f"Loaded catalog '{name}' from DB: {len(items)} items")
                return items
        eng.dispose()
    except Exception as e:
        logging.warning(f"DB catalog read failed for {name}: {e}")
    # Fallback to file
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.error(f"Malformed catalog JSON: {name}.json — {e}")
        return []
    items = data if isinstance(data, list) else data.get("items", [])
    _catalog_cache[name] = (current_mtime, items)
    return items


def invalidate_catalog_cache(name: str | None = None):
    """Invalidate cached catalog data. If name is None, clears all."""
    if name is None:
        _catalog_cache.clear()
    else:
        _catalog_cache.pop(name, None)


def catalog_lookup(catalog: str, sku: str) -> dict:
    """Look up a SKU in the specified catalog and return price with IVA."""
    # Strip .json extension if Valentina adds it
    catalog = catalog.replace(".json", "")
    items = _load_catalog(catalog)
    if not items:
        logging.warning(f"catalog_lookup: catalog '{catalog}' returned 0 items!")
    sku_upper = sku.upper()

    for item in items:
        item_sku = item.get("sku", "").upper()
        if item_sku == sku_upper:
            result = {"found": True, "sku": item.get("sku"), "name": item.get("name", "")}

            # Price with IVA (from config.json)
            # Business rule: USD uses floor(), ARS uses round() — intentional
            iva = _get_iva_multiplier()
            if "price_usd" in item:
                price_base = item["price_usd"]
                price_with_iva = math.floor(price_base * iva)  # USD: floor per business rule
                result["price_usd"] = price_with_iva
                result["price_usd_base"] = price_base
                result["currency"] = "USD"
            elif "price_ars" in item:
                price_base = item["price_ars"]
                price_with_iva = round(price_base * iva)  # ARS: round per business rule
                result["price_ars"] = price_with_iva
                result["price_ars_base"] = price_base
                result["currency"] = "ARS"

            # Extra fields
            if "unit" in item:
                result["unit"] = item["unit"]
            if "material_type" in item:
                result["material_type"] = item["material_type"]
            if "origin" in item:
                result["origin"] = item["origin"]
            if "sink_type" in item:
                result["sink_type"] = item["sink_type"]
            if "thickness_mm" in item:
                result["thickness_mm"] = item["thickness_mm"]

            return result

    # Not found by exact SKU — try matching by name
    name_matches = []
    for item in items:
        item_name = item.get("name", "").upper()
        item_sku = item.get("sku", "").upper()
        # Match if search term appears in name or SKU
        if sku_upper in item_name or sku_upper in item_sku:
            name_matches.append(item)

    # If exactly one match by name, return it as found
    if len(name_matches) == 1:
        item = name_matches[0]
        result = {"found": True, "sku": item.get("sku"), "name": item.get("name", ""), "matched_by": "name"}

        iva = _get_iva_multiplier()
        if "price_usd" in item:
            price_base = item["price_usd"]
            price_with_iva = math.floor(price_base * iva)
            result["price_usd"] = price_with_iva
            result["price_usd_base"] = price_base
            result["currency"] = "USD"
        elif "price_ars" in item:
            price_base = item["price_ars"]
            price_with_iva = round(price_base * iva)
            result["price_ars"] = price_with_iva
            result["price_ars_base"] = price_base
            result["currency"] = "ARS"

        if "unit" in item:
            result["unit"] = item["unit"]
        if "material_type" in item:
            result["material_type"] = item["material_type"]
        if "origin" in item:
            result["origin"] = item["origin"]

        return result

    # Multiple or no matches — return suggestions
    suggestions = [{"sku": m.get("sku"), "name": m.get("name", "")} for m in name_matches[:5]]

    return {
        "found": False,
        "sku": sku,
        "catalog": catalog,
        "partial_matches": suggestions,
        "message": f"SKU '{sku}' no encontrado en {catalog}" + (f". Opciones similares: {', '.join(s['name'] for s in suggestions)}" if suggestions else ""),
    }


def catalog_batch_lookup(queries: list[dict]) -> dict:
    """Look up multiple SKUs across catalogs in a single call. Returns results keyed by index."""
    results = {}
    for i, q in enumerate(queries):
        catalog = q.get("catalog", "")
        sku = q.get("sku", "")
        results[str(i)] = catalog_lookup(catalog, sku)
    return {"results": results, "count": len(results)}


def check_architect(client_name: str) -> dict:
    """Check if a client is a registered architect with discount."""
    items = _load_catalog("architects")
    name_lower = client_name.lower().strip()

    # Exact match
    for item in items:
        item_name = (item.get("name") or "").lower()
        item_firm = (item.get("firm") or "").lower()
        if name_lower == item_name or name_lower == item_firm:
            return {"found": True, "exact": True, "name": item["name"], "firm": item.get("firm"), "discount": item.get("discount", True)}

    # Fuzzy match — substring and word overlap
    partial = []
    name_words = set(name_lower.split())
    for item in items:
        item_name = (item.get("name") or "").lower()
        item_firm = (item.get("firm") or "").lower()
        item_words = set(item_name.replace("arq.", "").replace("arq ", "").strip().split())

        # Substring match: "munge" in "estudio munge" or vice versa
        # Guard against empty strings (empty in anything is always True)
        if (name_lower and name_lower in item_name) or (name_lower and item_firm and name_lower in item_firm) or (item_name and item_name in name_lower) or (item_firm and item_firm in name_lower):
            partial.append({"name": item["name"], "firm": item.get("firm"), "discount": item.get("discount", True)})
            continue

        # Word overlap: at least 1 significant word (>3 chars) matches
        common_words = name_words & item_words
        significant = [w for w in common_words if len(w) > 3]
        if significant:
            partial.append({"name": item["name"], "firm": item.get("firm"), "discount": item.get("discount", True)})

    if partial:
        return {"found": True, "exact": len(partial) == 1, "name": partial[0]["name"], "firm": partial[0].get("firm"), "discount": partial[0].get("discount", True), "matches": partial, "message": f"Arquitecta encontrada: {', '.join(p['name'] for p in partial)}. Aplicar descuento."}

    return {"found": False, "message": f"'{client_name}' no está en architects.json"}


def fuzzy_sink_lookup(query: str) -> dict:
    """Fuzzy match a sink by brand keywords + model number patterns.

    Only searches actual sinks (sink_type set or 'PILETA' in name),
    never accessories like escurreplatos/canastos.

    E.g. "LUXOR COMPACT SI71" → matches LUXOR171 (PILETA JOHNSON LUXOR S171)
    E.g. "SI71" → extracts "71", tries "171" variant, matches LUXOR S171
    """
    import re
    all_items = _load_catalog("sinks")
    query_upper = query.upper().strip()

    # Filter to actual sinks only — exclude accessories (escurreplatos, canastos, tablas, etc.)
    items = [
        i for i in all_items
        if i.get("sink_type") or "PILETA" in (i.get("name") or "").upper()
    ]

    # Extract brand keywords (>2 chars, not generic words)
    skip_words = {"PILETA", "JOHNSON", "COMPACT", "MINI", "DOBLE", "SIMPLE", "BACHA", "EMPOTRADA", "APOYO"}
    words = [w for w in query_upper.split() if len(w) > 2 and w not in skip_words]

    # Extract numeric patterns (2-3 digits)
    nums = re.findall(r'\d{2,3}', query_upper)
    # Also try with "1" prefix: SI71 → 71 → also try 171 (common pattern: S171)
    extended_nums = list(nums)
    for n in nums:
        if len(n) == 2:
            extended_nums.append("1" + n)  # 71 → 171

    if not words and not extended_nums:
        return {"found": False, "message": f"No se pudo extraer datos de búsqueda de '{query}'"}

    candidates = []
    for item in items:
        name = (item.get("name") or "").upper()
        sku = (item.get("sku") or "").upper()
        score = 0
        # Brand match (e.g. "LUXOR", "QUADRA")
        for w in words:
            if w in name or w in sku:
                score += 2
        # Numeric match — original nums score higher than extended variants
        matched_nums = set()
        for n in nums:
            if n in name or n in sku:
                score += 4  # Direct number match (high confidence)
                matched_nums.add(n)
        for n in extended_nums:
            if n not in nums and n not in matched_nums and (n in name or n in sku):
                score += 2  # Extended variant match (lower confidence)
        if score > 0:
            candidates.append((score, item))

    if not candidates:
        return {"found": False, "message": f"Ninguna pileta matchea con '{query}' en sinks.json"}

    candidates.sort(key=lambda x: -x[0])
    best = candidates[0][1]
    logging.info(f"Fuzzy sink match: '{query}' → {best.get('sku')} ({best.get('name')}) [score={candidates[0][0]}]")
    # Do a proper catalog_lookup to get price with IVA
    result = catalog_lookup("sinks", best.get("sku", ""))
    if result.get("found"):
        result["matched_by"] = "fuzzy"
        result["original_query"] = query
    return result


def check_stock(material_sku: str) -> dict:
    """Check available stock pieces for a material."""
    items = _load_catalog("stock")
    sku_upper = material_sku.upper()

    matching = [
        item for item in items
        if item.get("material_sku", "").upper() == sku_upper
    ]

    if not matching:
        return {
            "found": False,
            "material_sku": material_sku,
            "message": "Sin stock disponible para este material",
        }

    return {
        "found": True,
        "material_sku": material_sku,
        "pieces": [
            {
                "id": p.get("id"),
                "largo": p.get("largo_cm"),
                "ancho": p.get("ancho_cm"),
                "m2": round((p.get("largo_cm", 0) / 100) * (p.get("ancho_cm", 0) / 100), 4),
                "notes": p.get("notes", ""),
            }
            for p in matching
        ],
    }
