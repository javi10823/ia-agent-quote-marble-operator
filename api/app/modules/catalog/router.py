import json
import os
import tempfile
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Union

from app.modules.agent.tools.catalog_tool import invalidate_catalog_cache
from app.modules.agent.tools.document_tool import invalidate_company_config_cache

from app.core.catalog_dir import CATALOG_DIR

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
    content: Union[list, dict]

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, v):
        if v is None:
            raise ValueError("content cannot be null")
        return v


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

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.error(f"Malformed catalog JSON: {catalog_name} — {e}")
        raise HTTPException(status_code=500, detail="Error leyendo catálogo (JSON corrupto)")


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

    # Atomic write: temp file + os.replace (POSIX atomic)
    content_str = json.dumps(body.content, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=str(CATALOG_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content_str)
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    invalidate_catalog_cache(catalog_name)
    if catalog_name == "config":
        invalidate_company_config_cache()
        from app.core.company_config import invalidate_config_cache
        invalidate_config_cache()

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
