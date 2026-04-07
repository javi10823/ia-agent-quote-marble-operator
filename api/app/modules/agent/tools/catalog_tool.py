import json
import logging
import math
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
CATALOG_DIR = BASE_DIR / "catalog"

_catalog_cache: dict[str, list] = {}
_config_cache: dict | None = None


def _get_iva_multiplier() -> float:
    """Read IVA multiplier from config.json."""
    global _config_cache
    if _config_cache is None:
        try:
            _config_cache = json.loads((CATALOG_DIR / "config.json").read_text(encoding="utf-8"))
        except Exception:
            _config_cache = {}
    return _config_cache.get("iva", {}).get("multiplier", 1.21)


def _load_catalog(name: str) -> list:
    if name in _catalog_cache:
        return _catalog_cache[name]
    path = CATALOG_DIR / f"{name}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.error(f"Malformed catalog JSON: {name}.json — {e}")
        return []
    items = data if isinstance(data, list) else data.get("items", [])
    _catalog_cache[name] = items
    return items


def invalidate_catalog_cache(name: str | None = None):
    """Invalidate cached catalog data. If name is None, clears all."""
    if name is None:
        _catalog_cache.clear()
    else:
        _catalog_cache.pop(name, None)


def catalog_lookup(catalog: str, sku: str) -> dict:
    """Look up a SKU in the specified catalog and return price with IVA."""
    items = _load_catalog(catalog)
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

    # Fuzzy match — require at least 2 words to match (name + surname, not just first name)
    partial = []
    name_words = set(name_lower.split())
    for item in items:
        item_name = (item.get("name") or "").lower()
        item_firm = (item.get("firm") or "").lower()
        item_words = set(item_name.replace("arq.", "").replace("arq ", "").strip().split())
        # Match if at least 2 words overlap (e.g. "luciana pacor" matches "ARQ. LUCIANA PACOR")
        # Single word like "luciana" alone does NOT match
        common_words = name_words & item_words
        if len(common_words) >= 2:
            partial.append({"name": item["name"], "firm": item.get("firm")})
        elif item_firm and (name_lower == item_firm or item_firm == name_lower):
            partial.append({"name": item["name"], "firm": item.get("firm")})

    if partial:
        return {"found": True, "exact": False, "matches": partial, "message": f"Posible arquitecta: {', '.join(p['name'] for p in partial)}. Confirmar con operador."}

    return {"found": False, "message": f"'{client_name}' no está en architects.json"}


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
