import json
import math
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
CATALOG_DIR = BASE_DIR / "catalog"


def _load_catalog(name: str) -> list:
    path = CATALOG_DIR / f"{name}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("items", [])


def catalog_lookup(catalog: str, sku: str) -> dict:
    """Look up a SKU in the specified catalog and return price with IVA."""
    items = _load_catalog(catalog)
    sku_upper = sku.upper()

    for item in items:
        item_sku = item.get("sku", "").upper()
        if item_sku == sku_upper:
            result = {"found": True, "sku": item.get("sku"), "name": item.get("name", "")}

            # Price with IVA
            if "price_usd" in item:
                price_base = item["price_usd"]
                price_with_iva = math.floor(price_base * 1.21)
                result["price_usd"] = price_with_iva
                result["price_usd_base"] = price_base
                result["currency"] = "USD"
            elif "price_ars" in item:
                price_base = item["price_ars"]
                price_with_iva = round(price_base * 1.21)
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

    # Not found — try partial match
    matches = []
    for item in items:
        if sku_upper in item.get("sku", "").upper() or sku_upper in item.get("name", "").upper():
            matches.append({"sku": item.get("sku"), "name": item.get("name", "")})

    return {
        "found": False,
        "sku": sku,
        "catalog": catalog,
        "partial_matches": matches[:5],
        "message": f"SKU '{sku}' no encontrado en {catalog}",
    }


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
