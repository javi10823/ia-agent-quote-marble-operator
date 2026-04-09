import json
import os
import tempfile
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, field_validator
from typing import Union

from app.modules.agent.tools.catalog_tool import invalidate_catalog_cache
from app.modules.agent.tools.document_tool import invalidate_company_config_cache
from app.modules.catalog.import_parser import parse_import_file

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


# ── IMPORT: preview + apply ─────────────────────────────────────────────────

@router.post("/import-preview")
async def import_preview(file: UploadFile = File(...)):
    """Parse a Dux export file and generate preview of changes per catalog.

    Supports .xls, .xlsx, .csv. Detects format automatically.
    Classifies items by catalog via SKU matching.
    Returns diff (updated/new/missing/zero_price) per catalog + warnings.

    Does NOT modify any data — preview only.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Archivo sin nombre")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xls", ".xlsx", ".csv"):
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}. Usar .xls, .xlsx o .csv")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    # Load all current catalogs for classification
    current_catalogs = {}
    for name in ALLOWED_CATALOGS:
        if name in ("config", "stock", "architects"):
            continue  # Not importable via price lists
        data = await _load_from_db(name)
        if data is not None:
            items = data if isinstance(data, list) else data.get("items", [])
            current_catalogs[name] = items

    try:
        result = parse_import_file(file_bytes, file.filename, current_catalogs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"[import-preview] Parse error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error al parsear archivo: {str(e)[:200]}")

    return result


class ImportApplyRequest(BaseModel):
    """Request to apply a previewed import to specific catalogs."""
    catalogs: list[str]  # catalog names to update (from preview)
    source_file: str = ""  # original filename for audit
    include_new: bool = True  # include new items (not in current catalog)


@router.post("/import-apply")
async def import_apply(
    body: ImportApplyRequest,
    file: UploadFile = File(...),
):
    """Apply a previewed import: backup current → update catalogs.

    1. Re-parse the file (same as preview)
    2. For each catalog in body.catalogs:
       a. Backup current catalog to catalog_backups table
       b. Apply upsert (update existing by SKU, optionally add new)
       c. Invalidate caches
    3. Return stats per catalog

    Items with price $0 are ALWAYS skipped.
    Items in current catalog but NOT in file are NEVER deleted.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Archivo sin nombre")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    # Load current catalogs
    current_catalogs = {}
    for name in ALLOWED_CATALOGS:
        if name in ("config", "stock", "architects"):
            continue
        data = await _load_from_db(name)
        if data is not None:
            items = data if isinstance(data, list) else data.get("items", [])
            current_catalogs[name] = items

    # Re-parse
    try:
        preview = parse_import_file(file_bytes, file.filename, current_catalogs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al parsear: {str(e)[:200]}")

    if preview.get("iva_warning"):
        raise HTTPException(
            status_code=400,
            detail="El archivo solo tiene columna de precio CON IVA. No se puede importar sin confirmar conversión."
        )

    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    results = {}

    for cat_name in body.catalogs:
        if cat_name not in preview.get("catalogs", {}):
            results[cat_name] = {"ok": False, "error": "No hay datos para este catálogo en el archivo"}
            continue

        diff = preview["catalogs"][cat_name]
        current_items = current_catalogs.get(cat_name, [])
        price_field = diff["price_field"]

        # ── 1. Backup current catalog ──
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("""INSERT INTO catalog_backups (catalog_name, content, source_file, stats)
                            VALUES (:name, :content, :source, :stats)"""),
                    {
                        "name": cat_name,
                        "content": json.dumps(current_items, ensure_ascii=False),
                        "source": body.source_file or file.filename,
                        "stats": json.dumps({
                            "items_before": len(current_items),
                            "updated": len(diff["updated"]),
                            "new": len(diff["new"]),
                        }),
                    },
                )
                await session.commit()
        except Exception as e:
            logging.error(f"[import-apply] Backup failed for {cat_name}: {e}")
            results[cat_name] = {"ok": False, "error": f"Backup falló: {str(e)[:100]}"}
            continue

        # ── 2. Apply upsert ──
        updated_catalog = list(current_items)  # Copy
        by_sku = {item["sku"].upper(): i for i, item in enumerate(updated_catalog) if isinstance(item, dict) and "sku" in item}

        stats = {"updated": 0, "added": 0, "skipped_zero": 0}
        today = __import__("datetime").datetime.now().strftime("%d/%m/%Y")

        # Update existing
        for change in diff["updated"]:
            sku_upper = change["sku"].upper()
            if sku_upper in by_sku:
                idx = by_sku[sku_upper]
                updated_catalog[idx][price_field] = change["new_price"]
                updated_catalog[idx]["last_updated"] = today
                if change.get("name"):
                    updated_catalog[idx]["name"] = change["name"]
                stats["updated"] += 1

        # Add new items (if enabled)
        if body.include_new:
            for new_item in diff["new"]:
                entry = {
                    "sku": new_item["sku"],
                    "name": new_item["name"],
                    price_field: new_item["price"],
                    "currency": diff["currency"],
                    "price_includes_vat": False,
                    "last_updated": today,
                }
                updated_catalog.append(entry)
                stats["added"] += 1

        stats["skipped_zero"] = len(diff["zero_price"])

        # ── 3. Save to DB ──
        try:
            await _save_to_db(cat_name, updated_catalog)
            invalidate_catalog_cache(cat_name)
            results[cat_name] = {"ok": True, **stats}
            logging.info(f"[import-apply] {cat_name}: updated={stats['updated']}, added={stats['added']}, skipped_zero={stats['skipped_zero']}")
        except Exception as e:
            logging.error(f"[import-apply] Save failed for {cat_name}: {e}")
            results[cat_name] = {"ok": False, "error": f"Error guardando: {str(e)[:100]}"}

    return {
        "ok": all(r.get("ok") for r in results.values()),
        "results": results,
        "source_file": body.source_file or file.filename,
    }


# ── BACKUPS ──────────────────────────────────────────────────────────────────

@router.get("/backups/{catalog_name}")
async def list_backups(catalog_name: str):
    """List backups for a catalog, most recent first."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT id, created_at, source_file, stats FROM catalog_backups WHERE catalog_name = :name ORDER BY created_at DESC LIMIT 20"),
            {"name": catalog_name},
        )
        rows = result.fetchall()

    return [
        {"id": r[0], "created_at": r[1].isoformat() if r[1] else None, "source_file": r[2], "stats": r[3]}
        for r in rows
    ]


@router.post("/backups/{backup_id}/restore")
async def restore_backup(backup_id: int):
    """Restore a catalog from a backup."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT catalog_name, content FROM catalog_backups WHERE id = :id"),
            {"id": backup_id},
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="Backup no encontrado")

        cat_name = row[0]
        content = json.loads(row[1]) if isinstance(row[1], str) else row[1]

    # Save backup of CURRENT state before restoring (safety net)
    current = await _load_from_db(cat_name)
    if current:
        from app.core.database import AsyncSessionLocal as _ASL
        async with _ASL() as session:
            await session.execute(
                text("""INSERT INTO catalog_backups (catalog_name, content, source_file, stats)
                        VALUES (:name, :content, :source, :stats)"""),
                {
                    "name": cat_name,
                    "content": json.dumps(current, ensure_ascii=False),
                    "source": f"pre-restore-backup-{backup_id}",
                    "stats": json.dumps({"reason": f"Auto-backup before restoring backup #{backup_id}"}),
                },
            )
            await session.commit()

    await _save_to_db(cat_name, content)
    invalidate_catalog_cache(cat_name)
    if cat_name == "config":
        invalidate_company_config_cache()
        from app.core.company_config import invalidate_config_cache
        invalidate_config_cache()

    return {"ok": True, "catalog": cat_name, "restored_from_backup": backup_id}
