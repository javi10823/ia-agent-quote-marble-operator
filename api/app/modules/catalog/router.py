import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from app.modules.agent.tools.catalog_tool import invalidate_catalog_cache
from app.modules.agent.tools.document_tool import invalidate_company_config_cache

BASE_DIR = Path(__file__).parent.parent.parent.parent
CATALOG_DIR = BASE_DIR / "catalog"

router = APIRouter(prefix="/catalog", tags=["catalog"])

ALLOWED_CATALOGS = [
    "labor",
    "delivery-zones",
    "sinks",
    "materials-silestone",
    "materials-purastone",
    "materials-dekton",
    "materials-neolith",
    "materials-puraprima",
    "materials-laminatto",
    "materials-granito-nacional",
    "materials-granito-importado",
    "materials-marmol",
    "stock",
    "architects",
    "config",
]


class CatalogUpdateRequest(BaseModel):
    content: Any  # JSON content to save


@router.get("/")
async def list_catalogs():
    """List all available catalogs with metadata."""
    result = []
    for name in ALLOWED_CATALOGS:
        path = CATALOG_DIR / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("items", [data])
            count = len(items)
            # Get last_updated from first item if available
            last_updated = None
            if isinstance(items, list) and items:
                last_updated = items[0].get("last_updated") if isinstance(items[0], dict) else None

            result.append({
                "name": name,
                "item_count": count,
                "last_updated": last_updated,
                "size_kb": round(path.stat().st_size / 1024, 1),
            })
    return result


@router.get("/{catalog_name}")
async def get_catalog(catalog_name: str):
    """Get full catalog content."""
    if catalog_name not in ALLOWED_CATALOGS:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado")

    path = CATALOG_DIR / f"{catalog_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return json.loads(path.read_text(encoding="utf-8"))


@router.put("/{catalog_name}")
async def update_catalog(catalog_name: str, body: CatalogUpdateRequest):
    """Update catalog content after AI validation."""
    if catalog_name not in ALLOWED_CATALOGS:
        raise HTTPException(status_code=403, detail="Catálogo no permitido")

    path = CATALOG_DIR / f"{catalog_name}.json"

    # Backup before saving
    backup_path = CATALOG_DIR / f"{catalog_name}.json.bak"
    if path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    path.write_text(
        json.dumps(body.content, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    invalidate_catalog_cache(catalog_name)
    if catalog_name == "config":
        invalidate_company_config_cache()

    return {"ok": True, "catalog": catalog_name}


@router.post("/{catalog_name}/validate")
async def validate_catalog(catalog_name: str, body: CatalogUpdateRequest):
    """
    Use AI to validate catalog changes before saving.
    Returns warnings about suspicious price changes, missing SKUs, etc.
    """
    if catalog_name not in ALLOWED_CATALOGS:
        raise HTTPException(status_code=403, detail="Catálogo no permitido")

    path = CATALOG_DIR / f"{catalog_name}.json"
    current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    warnings = []
    new_content = body.content

    # Basic structural validation
    if isinstance(new_content, list):
        for item in new_content:
            if not isinstance(item, dict):
                warnings.append({"type": "error", "message": "Cada ítem debe ser un objeto JSON"})
                break

    # Price change detection
    if current and isinstance(current, list) and isinstance(new_content, list):
        current_by_sku = {i.get("sku"): i for i in current if isinstance(i, dict)}
        for item in new_content:
            if not isinstance(item, dict):
                continue
            sku = item.get("sku")
            if sku in current_by_sku:
                old = current_by_sku[sku]
                for price_field in ["price_ars", "price_usd"]:
                    old_price = old.get(price_field)
                    new_price = item.get(price_field)
                    if old_price and new_price:
                        change_pct = abs(new_price - old_price) / old_price * 100
                        if change_pct > 30:
                            warnings.append({
                                "type": "warning",
                                "sku": sku,
                                "message": f"{price_field}: cambio de {old_price:,.2f} → {new_price:,.2f} ({change_pct:.1f}%)",
                            })

    return {
        "valid": not any(w["type"] == "error" for w in warnings),
        "warnings": warnings,
        "item_count": len(new_content) if isinstance(new_content, list) else 1,
    }
