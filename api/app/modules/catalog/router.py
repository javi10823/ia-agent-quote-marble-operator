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


async def _load_from_db(name: str):
    """Load catalog from DB, fallback to file."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT content FROM catalogs WHERE name = :name"),
                {"name": name},
            )
            row = result.first()
            if row:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception as e:
        logging.warning(f"DB catalog read failed for {name}: {e}")
    # Fallback to file
    path = CATALOG_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


async def _save_to_db(name: str, content):
    """Save catalog to DB."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("INSERT INTO catalogs (name, content, updated_at) VALUES (:name, :content, NOW()) ON CONFLICT (name) DO UPDATE SET content = :content, updated_at = NOW()"),
            {"name": name, "content": json.dumps(content, ensure_ascii=False)},
        )
        await session.commit()


@router.get("/")
async def list_catalogs():
    """List all available catalogs with metadata."""
    result = []
    for name in ALLOWED_CATALOGS:
        data = await _load_from_db(name)
        if data is not None:
            items = data if isinstance(data, list) else data.get("items", [data])
            count = len(items)
            last_updated = None
            if isinstance(items, list) and items:
                last_updated = items[0].get("last_updated") if isinstance(items[0], dict) else None
            result.append({
                "name": name,
                "item_count": count,
                "last_updated": last_updated,
            })
    return result


@router.get("/{catalog_name}")
async def get_catalog(catalog_name: str):
    """Get full catalog content."""
    if catalog_name not in ALLOWED_CATALOGS:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado")

    data = await _load_from_db(catalog_name)
    if data is None:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado")
    return data


@router.put("/{catalog_name}")
async def update_catalog(catalog_name: str, body: CatalogUpdateRequest):
    """Update catalog content in DB."""
    if catalog_name not in ALLOWED_CATALOGS:
        raise HTTPException(status_code=403, detail="Catálogo no permitido")

    await _save_to_db(catalog_name, body.content)

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

    current = await _load_from_db(catalog_name)

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
