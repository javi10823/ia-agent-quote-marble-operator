from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json
import logging
import re
import uuid

logger = logging.getLogger(__name__)

# File upload constants
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 10

from app.core.database import get_db
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.agent import AgentService
from app.modules.observability import log_event
from app.modules.agent.schemas import (
    CreateQuoteRequest,
    QuoteListResponse,
    QuoteDetailResponse,
    QuoteCompareItem,
    QuoteCompareResponse,
    QuoteStatusUpdate,
    QuotePatchRequest,
    DeriveMaterialRequest,
    PieceListResponse,
    PieceSchema,
    PieceOptionsSchema,
    CalculationResponse,
    MaterialRowSchema,
    LaborRowDataSchema,
    MermaSectionSchema,
    PiletaSectionSchema,
    FleteRowSchema,
    GrandTotalsSchema,
    GrandTotalsCurrencySchema,
    DatosPdfDefaultsSchema,
)

router = APIRouter(tags=["agent"])
agent_service = AgentService()

# Valid status transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"validated", "pending"},
    "pending": {"validated", "draft"},
    "validated": {"sent", "draft"},
    "sent": {"validated"},
}


# ── AUTHENTICATED FILE SERVING ───────────────────────────────────────────────
# Separate router mounted at /files (not /api/files) to match existing URLs in DB

files_router = APIRouter(tags=["files"])

@files_router.get("/files/{file_path:path}")
async def serve_file(file_path: str, db: AsyncSession = Depends(get_db)):
    """Serve files with Drive-first fallback for ephemeral filesystems.

    Resolution order:
    1. If local file exists → serve it
    2. If not local, search files_v2 metadata for Drive URL → redirect 302
    3. If parent has files_v2 for this file → redirect 302
    4. Nothing found → 404
    """
    from app.core.static import OUTPUT_DIR
    from starlette.responses import RedirectResponse
    import mimetypes, urllib.parse

    # 1. Try local filesystem first
    full_path = (OUTPUT_DIR / file_path).resolve()
    if full_path.is_relative_to(OUTPUT_DIR.resolve()) and full_path.exists() and full_path.is_file():
        media_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
        return FileResponse(full_path, media_type=media_type)

    # 2. File not local — try Drive fallback via files_v2
    # Extract quote_id from path: "{quote_id}/filename"
    parts = file_path.split("/", 1)
    if len(parts) == 2:
        req_quote_id, req_filename = parts[0], urllib.parse.unquote(parts[1])

        # Search in the quote itself
        drive_url = await _find_drive_url_in_files_v2(db, req_quote_id, req_filename)
        if drive_url:
            return RedirectResponse(url=drive_url, status_code=302)

        # If this is a child, search in parent
        try:
            quote_result = await db.execute(select(Quote).where(Quote.id == req_quote_id))
            quote = quote_result.scalar_one_or_none()
            if quote and quote.parent_quote_id:
                drive_url = await _find_drive_url_in_files_v2(db, quote.parent_quote_id, req_filename)
                if drive_url:
                    return RedirectResponse(url=drive_url, status_code=302)
            # If this is a parent, search children (files might be stored under parent ID)
            if quote and quote.quote_kind == "building_parent":
                drive_url = await _find_drive_url_in_files_v2(db, req_quote_id, req_filename)
                if drive_url:
                    return RedirectResponse(url=drive_url, status_code=302)
        except Exception as e:
            logging.warning(f"files_v2 lookup failed: {e}")

    raise HTTPException(status_code=404, detail="Archivo no encontrado")


async def _find_drive_url_in_files_v2(db: AsyncSession, quote_id: str, filename: str) -> str | None:
    """Search files_v2 in a quote's breakdown for a matching file. Returns drive_download_url or None."""
    try:
        result = await db.execute(select(Quote).where(Quote.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote or not quote.quote_breakdown:
            return None
        # Check files_v2 in breakdown
        files_v2 = quote.quote_breakdown.get("files_v2", {}) if quote.quote_breakdown else {}
        for item in files_v2.get("items", []):
            item_filename = urllib.parse.unquote(item.get("filename", ""))
            if item_filename == filename or item.get("local_url", "").endswith(filename):
                return item.get("drive_download_url") or item.get("drive_url")

        # Also check source_files (for source/plan files with drive info)
        for sf in (quote.source_files or []):
            if sf.get("filename") == filename or (sf.get("url") or "").endswith(filename):
                drive_dl = sf.get("drive_download_url") or sf.get("drive_url")
                if drive_dl:
                    return drive_dl
    except Exception:
        pass
    return None


# ── LIST QUOTES ──────────────────────────────────────────────────────────────

def _pick_plan_and_extras(
    validated_files: list[tuple[bytes, str]],
) -> tuple[bytes | None, str | None, list[tuple[bytes, str]]]:
    """Pick the technical plan from uploaded files.

    Si hay al menos un PDF → ese es el plano principal (los PDFs son
    técnicos por convención en este dominio). El resto pasa como contexto
    visual. Si no hay PDFs, caemos al primer archivo (orden de upload).

    Antes se usaba ``validated_files[0]`` — frágil cuando el operador
    sube renders fotorrealistas antes del PDF técnico (caso Bernardi:
    JPG, JPG, PDF) porque dual_read terminaba corriendo sobre el render.
    """
    if not validated_files:
        return None, None, []
    pdf_idx = next(
        (i for i, (_b, name) in enumerate(validated_files)
         if name.lower().endswith(".pdf")),
        None,
    )
    if pdf_idx is None:
        return validated_files[0][0], validated_files[0][1], validated_files[1:]
    plan_bytes, plan_filename = validated_files[pdf_idx]
    extras = [f for i, f in enumerate(validated_files) if i != pdf_idx]
    return plan_bytes, plan_filename, extras


def _extract_drive_urls(quote) -> dict:
    """Extract drive_pdf_url and drive_excel_url from files_v2 in breakdown."""
    bd = quote.quote_breakdown if quote.quote_breakdown else {}
    files_v2 = bd.get("files_v2", {})
    result = {"drive_pdf_url": None, "drive_excel_url": None}
    for item in files_v2.get("items", []):
        kind = item.get("kind", "")
        url = item.get("drive_url") or item.get("drive_download_url")
        if kind == "pdf" and url and not result["drive_pdf_url"]:
            result["drive_pdf_url"] = url
        elif kind == "excel" and url and not result["drive_excel_url"]:
            result["drive_excel_url"] = url
        elif kind == "summary_pdf" and url and not result["drive_pdf_url"]:
            result["drive_pdf_url"] = url
        elif kind == "summary_excel" and url and not result["drive_excel_url"]:
            result["drive_excel_url"] = url
    return result


@router.get("/quotes")
async def list_quotes(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import defer
    from sqlalchemy import or_, and_
    result = await db.execute(
        select(Quote)
        .options(defer(Quote.messages), defer(Quote.quote_breakdown), defer(Quote.source_files))
        .where(
            # Exclude empty drafts (no client_name) — only show drafts with real data
            or_(
                Quote.status != "draft",
                and_(Quote.status == "draft", Quote.client_name != "", Quote.client_name.isnot(None)),
            ),
            # Exclude building children — they live inside their parent
            or_(Quote.quote_kind != "building_child_material", Quote.quote_kind.is_(None)),
        )
        .order_by(Quote.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


# ── CHECK FOR CHANGES (lightweight polling) ─────────────────────────────────

@router.get("/quotes/check")
async def check_quotes(db: AsyncSession = Depends(get_db)):
    """Lightweight check: returns count + last update timestamp for smart polling."""
    from sqlalchemy import func, or_, and_
    result = await db.execute(
        select(
            func.count(Quote.id),
            func.max(Quote.updated_at),
        ).where(
            or_(
                Quote.status != "draft",
                and_(Quote.status == "draft", Quote.client_name != "", Quote.client_name.isnot(None)),
            )
        )
    )
    row = result.one()
    return {
        "count": row[0],
        "last_updated_at": row[1].isoformat() if row[1] else None,
    }


# ── GET QUOTE DETAIL ─────────────────────────────────────────────────────────

def _compute_pdf_outdated(quote: Quote) -> tuple[bool, Optional[datetime]]:
    """Devuelve (pdf_outdated, pdf_generated_at) según change_history.

    PR #442 — banner "PDF desactualizado":

    El operador edita campos del quote (PATCH /quotes) sin regenerar
    el PDF. El detalle del frontend muestra el cambio (lee de
    breakdown/columnas), pero el PDF guardado en disco/Drive sigue
    siendo el viejo. Para no engañar al operador, computamos un flag
    visible.

    Lógica:
    - Si NO hay `pdf_url` → False (no hay PDF para comparar).
    - Buscar en `change_history` el último entry con
      `action in {"regenerate_docs", "generate_docs"}`. Su
      `timestamp` es `pdf_generated_at`.
    - `pdf_outdated = updated_at > pdf_generated_at + tolerance`.
      Tolerancia = 5s para evitar race del propio regenerate (su
      `update(Quote).values(...)` triggerea `updated_at`).
    - Si NO hay entries de regenerate/generate pero hay pdf_url:
      asumir conservadoramente NOT outdated. Quotes viejos sin
      tracking no se marcan — el operador puede regenerar manual
      si quiere. Esto evita ruido en presupuestos legacy.

    Returns:
        (False, None) si no hay PDF.
        (False, ts) si está al día.
        (True, ts) si hay edits posteriores.
    """
    from datetime import timedelta as _td
    if not quote.pdf_url:
        return False, None

    history = quote.change_history or []
    REGEN_ACTIONS = {"regenerate_docs", "generate_docs"}
    last_pdf_ts: Optional[datetime] = None
    for entry in history:
        if not isinstance(entry, dict):
            continue
        if entry.get("action") not in REGEN_ACTIONS:
            continue
        ts_raw = entry.get("timestamp")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if isinstance(ts_raw, str) else ts_raw
        except (TypeError, ValueError):
            continue
        if last_pdf_ts is None or ts > last_pdf_ts:
            last_pdf_ts = ts

    if last_pdf_ts is None:
        # PDF existe pero no hay tracking en history (quote legacy
        # pre-#442 o flujos que no logueaban). Conservador: no
        # marcar como outdated para no spamear al operador con
        # falsos positivos.
        return False, None

    # Comparar con `updated_at`. Normalizar tz: si updated_at es
    # naive, asumimos UTC. Si tiene tz, convertimos last_pdf_ts a
    # la misma referencia (ambos en UTC).
    updated_at = quote.updated_at
    if updated_at is None:
        return False, last_pdf_ts
    # Defensivo: si las dos son naive o ambas tz-aware, comparar
    # directo; si una es naive, normalizar.
    try:
        if updated_at.tzinfo is None and last_pdf_ts.tzinfo is not None:
            from datetime import timezone as _tz
            updated_at = updated_at.replace(tzinfo=_tz.utc)
        elif updated_at.tzinfo is not None and last_pdf_ts.tzinfo is None:
            from datetime import timezone as _tz
            last_pdf_ts = last_pdf_ts.replace(tzinfo=_tz.utc)
    except Exception:
        pass

    TOLERANCE = _td(seconds=5)
    pdf_outdated = updated_at > (last_pdf_ts + TOLERANCE)
    return pdf_outdated, last_pdf_ts


def _client_name_from_breakdown(bd: dict | None) -> str | None:
    """Extrae el nombre del cliente desde el `quote_breakdown`.

    El wizard (brief → contexto → despiece) guarda el cliente extraído SOLO
    dentro del JSON `quote_breakdown` (en `verified_context_analysis` /
    `context_analysis_pending`), nunca en la columna denormalizada
    `Quote.client_name`. Por eso el header (`GET /quotes/{id}`) y el dashboard
    (que filtra drafts con `client_name` vacío) no veían el nombre y caían al
    fallback `Presupuesto {uuid}`.

    Replica la MISMA precedencia que el adapter del frontend
    (`web/src/lib/api/adapters/context-from-breakdown.ts`):

      1. entry "Cliente" en `data_known`/`assumptions` de `verified_*`
      2. ídem en `context_analysis_pending`
      3. `_brief_analysis_raw.client_name` (verified → pending → top-level)

    Devuelve `None` si no hay nombre utilizable.
    """
    if not isinstance(bd, dict):
        return None

    verified = bd.get("verified_context_analysis")
    pending = bd.get("context_analysis_pending")

    def _find_entry(analysis: object, field_name: str) -> str | None:
        if not isinstance(analysis, dict):
            return None
        for bucket in ("data_known", "assumptions"):
            for entry in analysis.get(bucket) or []:
                if isinstance(entry, dict) and entry.get("field") == field_name:
                    val = (entry.get("value") or "").strip()
                    if val:
                        return val
        return None

    name = _find_entry(verified, "Cliente") or _find_entry(pending, "Cliente")
    if name:
        return name

    for source in (verified, pending, bd):
        raw = source.get("_brief_analysis_raw") if isinstance(source, dict) else None
        if isinstance(raw, dict):
            raw_name = (raw.get("client_name") or "").strip() if raw.get("client_name") else ""
            if raw_name:
                return raw_name

    return None


def _field_valor(field: object) -> float | None:
    """Extrae `.valor` de un FieldValue (shape `{valor, opus, sonnet, status}`
    usado por `dual_read_result`), o asume un número plano. None si no se
    puede extraer."""
    if field is None:
        return None
    if isinstance(field, dict):
        v = field.get("valor")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    if isinstance(field, (int, float)):
        return float(field)
    return None


def _serialize_dual_read_to_pieces(dual_read: dict | None) -> list[dict]:
    """Convierte `dual_read_result.sectores[].tramos[]` a lista de `Piece`
    dicts en el shape que espera el frontend `useDespiece` hook.

    Sub-PR despiece-real-wire · cierra deuda de mocks → real backend.
    `verified_derived_pieces` ya no se persiste (PR #386), todo vive en
    `dual_read_result` post-confirm via `apply_answers` + merges.

    Cada tramo (mesada) emite 1 `Piece` de tipo "encimera". Cada zócalo del
    tramo emite 1 `Piece` adicional de tipo "zocalo". `_manual:true` del
    tramo se traduce a `origin="EDITADO"` (operador puede haber tocado);
    sin flag, `origin="IA"`. `_manual:true` NO se expone al frontend.
    """
    pieces: list[dict] = []
    sectores = (dual_read or {}).get("sectores") or []
    for sector in sectores:
        tramos = sector.get("tramos") or []
        for tramo in tramos:
            largo_m = _field_valor(tramo.get("largo_m"))
            ancho_m = _field_valor(tramo.get("ancho_m"))
            if largo_m is None or ancho_m is None:
                continue
            quantity_raw = tramo.get("quantity") or 1
            try:
                quantity = max(1, int(quantity_raw))
            except (TypeError, ValueError):
                quantity = 1
            tramo_id = str(tramo.get("id") or f"t{len(pieces) + 1}")
            pieces.append({
                "id": tramo_id,
                "type": "encimera",
                "label": str(tramo.get("descripcion") or "Mesada"),
                "width_mm": round(largo_m * 1000, 2),
                "depth_mm": round(ancho_m * 1000, 2),
                "quantity": quantity,
                "options": {},
                "origin": "EDITADO" if tramo.get("_manual") else "IA",
                "edited": False,
            })
            for idx, z in enumerate(tramo.get("zocalos") or []):
                ml = z.get("ml")
                alto_m = z.get("alto_m")
                if ml is None or alto_m is None:
                    continue
                try:
                    ml_f = float(ml)
                    alto_f = float(alto_m)
                except (TypeError, ValueError):
                    continue
                z_quantity_raw = z.get("quantity") or 1
                try:
                    z_quantity = max(1, int(z_quantity_raw))
                except (TypeError, ValueError):
                    z_quantity = 1
                lado = str(z.get("lado") or "").strip() or "trasero"
                pieces.append({
                    "id": f"{tramo_id}-z{idx + 1}",
                    "type": "zocalo",
                    "label": f"Zócalo {lado}",
                    "width_mm": round(ml_f * 1000, 2),
                    "depth_mm": round(alto_f * 1000, 2),
                    "quantity": z_quantity,
                    "options": {},
                    "origin": "IA",
                    "edited": False,
                })
    return pieces


def _extract_calc_pieces_from_dual_read(dual_read: dict | None) -> list[dict]:
    """Itera `dual_read_result.sectores[].tramos[]` y emite shape
    `{description, largo, prof|alto, quantity?}` apto para `calculate_quote.pieces[]`.

    Sub-PR derive-material-ui-wire backend fix · destapado por validación visual
    #515: quotes del flujo Operador (post-#512 text_parse) tienen piezas SOLO en
    `dual_read_result`, no en `quote.pieces` raw ni en `breakdown.piece_details`.
    El endpoint `/derive-material` necesita este fallback adicional para no
    rechazar esos quotes con HTTP 400.

    Hermano de `_serialize_dual_read_to_pieces` (mismo source · distinto target
    shape: el helper de #512 emite `Piece` del frontend, este emite el shape
    que el calculator consume).
    """
    if not isinstance(dual_read, dict):
        return []
    pieces: list[dict] = []
    for sector in dual_read.get("sectores") or []:
        for tramo in sector.get("tramos") or []:
            largo_m = _field_valor(tramo.get("largo_m"))
            ancho_m = _field_valor(tramo.get("ancho_m"))
            if largo_m is None:
                continue
            t_piece: dict = {
                "description": tramo.get("descripcion") or "Mesada",
                "largo": largo_m,
            }
            if ancho_m is not None:
                t_piece["prof"] = ancho_m
            t_qty = tramo.get("quantity")
            if isinstance(t_qty, int) and t_qty > 1:
                t_piece["quantity"] = t_qty
            pieces.append(t_piece)
            for z in tramo.get("zocalos") or []:
                ml = z.get("ml")
                alto = z.get("alto_m")
                if ml is None or alto is None:
                    continue
                try:
                    ml_f = float(ml)
                    alto_f = float(alto)
                except (TypeError, ValueError):
                    continue
                lado = str(z.get("lado") or "trasero").strip() or "trasero"
                z_piece: dict = {
                    "description": f"Zócalo {lado}",
                    "largo": ml_f,
                    "alto": alto_f,
                }
                z_qty = z.get("quantity")
                if isinstance(z_qty, int) and z_qty > 1:
                    z_piece["quantity"] = z_qty
                pieces.append(z_piece)
    return pieces


# ── Calculation serializer helpers · sub-PR calculation-real-wire ────────
# Convierten el shape backend (`calculate_quote()` return inlined al top-level
# del `quote_breakdown`) al shape `CalculationResult` del frontend
# (types.ts:344). PASO 0 EXP-2 confirmó shapes vía Railway query:
#   - mo_items: [{description, quantity, unit_price, base_price, total}]
#   - sinks: [{name, quantity, unit_price}]
#   - merma: {aplica, desperdicio, sobrante_m2, motivo}
#   - piece_details: [{description, largo, dim2, m2, quantity, override, _is_frentin}]


def _format_ars(value: float | int | None) -> str:
    """Locale es-AR · "$1.234,56" (separador miles "." · decimal ",")."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    formatted = f"{v:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${formatted}"


def _format_usd(value: float | int | None) -> str:
    """Locale es-AR · "USD 1.234"."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    formatted = f"{v:,.0f}".replace(",", ".")
    return f"USD {formatted}"


def _format_qty_m2(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    formatted = f"{v:.2f}".replace(".", ",")
    return f"{formatted} m²"


def _is_flete_item(item: dict) -> bool:
    """Heurística confirmada PASO 0 EXP-2: el item flete tiene `description`
    que arranca con "flete" (case-insensitive). Sample real:
    "Flete + toma medidas ibarlucea"."""
    desc = (item.get("description") or "").lower().strip()
    return desc.startswith("flete")


def _serialize_residential_calc(breakdown: dict, quote) -> CalculationResponse:
    """Adapter no trivial · mapea ~7 secciones del shape backend al shape
    `CalculationResult` del frontend. Solo residential (edificio out-of-scope).

    Shape source confirmado PASO 0 EXP + EXP-2 vs Railway DB.
    """
    quote_id = str(quote.id)
    mo_items = breakdown.get("mo_items") or []
    sinks = breakdown.get("sinks") or []
    merma = breakdown.get("merma") or {}
    material_currency = breakdown.get("material_currency") or "USD"
    pileta = (breakdown.get("pileta") or "").strip().lower()

    # ── Material section · 1 row + descuento opcional + subtotal ──
    material_name = breakdown.get("material_name") or "Material"
    material_m2 = breakdown.get("material_m2") or 0
    material_total = breakdown.get("material_total") or 0
    material_total_bruto = breakdown.get("material_total_bruto") or material_total
    material_price_unit = breakdown.get("material_price_unit") or 0
    discount_pct = breakdown.get("discount_pct") or 0
    discount_amount = breakdown.get("discount_amount") or 0

    is_usd = material_currency == "USD"
    _fmt_money = _format_usd if is_usd else _format_ars

    material_rows: list[MaterialRowSchema] = [
        MaterialRowSchema(
            label=material_name,
            qty=_format_qty_m2(material_m2),
            unit=f"{material_currency} {int(material_price_unit)}",
            total=_fmt_money(material_total_bruto),
        )
    ]
    if discount_amount and discount_pct:
        material_rows.append(
            MaterialRowSchema(
                label=f"Descuento {discount_pct}%",
                qty="",
                unit="",
                total="−" + _fmt_money(discount_amount),
                variant="discount",
            )
        )
    material_subtotal = _fmt_money(material_total)

    # ── Merma section ──
    if bool(merma.get("aplica")):
        sobrante_m2 = breakdown.get("sobrante_m2") or 0
        sobrante_total = breakdown.get("sobrante_total") or 0
        merma_rows: list[MaterialRowSchema] = []
        if sobrante_m2 > 0:
            merma_rows.append(
                MaterialRowSchema(
                    label="Sobrante recuperable",
                    qty=_format_qty_m2(sobrante_m2),
                    unit="",
                    total=_fmt_money(sobrante_total),
                )
            )
        merma_section = MermaSectionSchema(
            status="aplica",
            chipLabel="APLICA",
            sub=str(merma.get("motivo") or ""),
            rows=merma_rows or None,
        )
    else:
        merma_section = MermaSectionSchema(
            status="na",
            chipLabel=f"N/A — {merma.get('motivo') or 'sin merma'}",
        )

    # ── Labor section · mo_items filtrados (skip flete) ──
    labor_rows: list[LaborRowDataSchema] = []
    labor_subtotal_total = 0.0
    for item in mo_items:
        if not isinstance(item, dict) or _is_flete_item(item):
            continue
        item_total = item.get("total") or 0
        labor_subtotal_total += float(item_total)
        labor_rows.append(
            LaborRowDataSchema(
                sku="MO",
                label=str(item.get("description") or ""),
                qty=str(item.get("quantity") or 1),
                basePrice=_format_ars(item.get("base_price")),
                iva="×1,21",
                total=_format_ars(item_total),
            )
        )
    labor_subtotal_str = _format_ars(labor_subtotal_total)

    # ── Flete section · single trip residential ──
    flete_item = next((it for it in mo_items if isinstance(it, dict) and _is_flete_item(it)), None)
    localidad = breakdown.get("localidad") or "—"
    if flete_item:
        flete_section = FleteRowSchema(
            zona=str(localidad).title(),
            qty="1 viaje",
            basePrice=_format_ars(flete_item.get("base_price")),
            total=_format_ars(flete_item.get("total")),
        )
    else:
        flete_section = FleteRowSchema(
            zona=str(localidad).title(),
            qty="—",
            basePrice="—",
            total="—",
        )

    # ── Piletas section · 3 escenarios por `pileta` value ──
    if pileta == "empotrada_cliente":
        piletas_section = PiletaSectionSchema(
            chipLabel="N/A — pileta empotrada (la trae el cliente)",
            variant="na",
        )
    elif pileta == "empotrada_johnson":
        if sinks:
            sink0 = sinks[0]
            piletas_section = PiletaSectionSchema(
                chipLabel="APLICA",
                variant="info",
                sub=f"{sink0.get('name', '—')} × {sink0.get('quantity', 1)} · {_format_ars(sink0.get('unit_price'))}",
            )
        else:
            piletas_section = PiletaSectionSchema(
                chipLabel="APLICA",
                variant="info",
                sub="Johnson (catálogo)",
            )
    elif pileta == "apoyo":
        piletas_section = PiletaSectionSchema(
            chipLabel="N/A — pileta de apoyo",
            variant="na",
        )
    else:
        piletas_section = PiletaSectionSchema(chipLabel="—", variant="na")

    # ── Totals ──
    total_ars = breakdown.get("total_ars") or 0
    total_usd = breakdown.get("total_usd") or 0
    totals = GrandTotalsSchema(
        ars=GrandTotalsCurrencySchema(value=_format_ars(total_ars), meta="MO + flete (ARS)"),
        usd=GrandTotalsCurrencySchema(value=_format_usd(total_usd), meta="Material importado (USD)"),
    )

    # ── DatosPdf defaults · desde columnas Quote + breakdown ──
    delivery_days = breakdown.get("delivery_days") or "30 días"
    datos_pdf = DatosPdfDefaultsSchema(
        plazo=str(delivery_days),
        anticipoPct="50%",
        saldo="Contra entrega",
        envio="Incluye flete" if flete_item else "Retira en taller",
        notas=str(quote.notes or ""),
        vigenciaDias="30",
    )

    # ── Banner summary · pre-rendered string ──
    n_pieces = len(breakdown.get("piece_details") or [])
    banner_parts = [
        f"✓ Calculado",
        material_name,
        _format_qty_m2(material_m2),
        f"{_format_ars(total_ars)} + {_format_usd(total_usd)}",
    ]
    if n_pieces:
        banner_parts.insert(0, f"{n_pieces} piezas")
    banner_summary = " · ".join(banner_parts)

    return CalculationResponse(
        quoteId=quote_id,
        status="ok",
        bannerSummary=banner_summary,
        bannerAdjustments=[],
        material={"rows": [r.model_dump() for r in material_rows], "subtotal": material_subtotal},
        merma=merma_section,
        labor={"rows": [r.model_dump() for r in labor_rows], "subtotal": labor_subtotal_str},
        piletas=piletas_section,
        flete=flete_section,
        totals=totals,
        datosPdf=datos_pdf,
    )


def _pending_calculation_response(quote_id: str, summary: str) -> CalculationResponse:
    """Empty CalculationResponse para pending / edificio_not_supported."""
    return CalculationResponse(
        quoteId=quote_id,
        status="pending",
        bannerSummary=summary,
        bannerAdjustments=[],
        material={"rows": [], "subtotal": "—"},
        merma=MermaSectionSchema(status="na", chipLabel="—"),
        labor={"rows": [], "subtotal": "—"},
        piletas=PiletaSectionSchema(chipLabel="—", variant="na"),
        flete=FleteRowSchema(zona="—", qty="—", basePrice="—", total="—"),
        totals=GrandTotalsSchema(
            ars=GrandTotalsCurrencySchema(value="—", meta=""),
            usd=GrandTotalsCurrencySchema(value="—", meta=""),
        ),
        datosPdf=DatosPdfDefaultsSchema(
            plazo="30 días", anticipoPct="50%", saldo="Contra entrega",
            envio="—", notas="", vigenciaDias="30",
        ),
    )


def _phone_email_from_breakdown(bd: dict | None) -> tuple[str | None, str | None]:
    """Extrae phone + email desde el `_brief_analysis_raw` del breakdown JSON.

    Pareja de `_client_name_from_breakdown` · cierra la deuda documentada en
    `brief_analyzer.EMPTY_SCHEMA` (phone/email se persistían al JSON pero
    nunca al column `Quote.client_phone` / `Quote.client_email`). Sigue la
    misma precedencia: verified → pending → top-level. Devuelve tupla con
    cualquier campo None si no hay valor utilizable.
    """
    if not isinstance(bd, dict):
        return None, None

    verified = bd.get("verified_context_analysis")
    pending = bd.get("context_analysis_pending")

    for source in (verified, pending, bd):
        raw = source.get("_brief_analysis_raw") if isinstance(source, dict) else None
        if isinstance(raw, dict):
            phone = (raw.get("phone") or "").strip() or None
            email = (raw.get("email") or "").strip() or None
            if phone or email:
                return phone, email
    return None, None


@router.get("/quotes/{quote_id}")
async def get_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Lazy denormalization — si la fila no tiene `client_name` / `client_phone`
    # / `client_email` pero el `quote_breakdown` ya los extrajo (caso típico
    # del wizard), los copiamos a las columnas y persistimos una sola vez. Así
    # el header deja de mostrar "Presupuesto {uuid}" y el quote aparece/agrupa
    # en el dashboard. Mismo patrón de cache lazy que `email_draft`.
    # Idempotente: cada campo se llena solo mientras esté vacío.
    bd_changed = False
    if not (quote.client_name or "").strip():
        derived = _client_name_from_breakdown(quote.quote_breakdown)
        if derived:
            quote.client_name = derived[:500]
            bd_changed = True
    if not (quote.client_phone or "").strip() or not (quote.client_email or "").strip():
        bd_phone, bd_email = _phone_email_from_breakdown(quote.quote_breakdown)
        if bd_phone and not (quote.client_phone or "").strip():
            quote.client_phone = bd_phone[:100]
            bd_changed = True
        if bd_email and not (quote.client_email or "").strip():
            quote.client_email = bd_email[:200]
            bd_changed = True
    if bd_changed:
        await db.commit()
        await db.refresh(quote)

    # PR #442 — computar pdf_outdated antes de armar el response.
    pdf_outdated, pdf_generated_at = _compute_pdf_outdated(quote)

    # For building_parent, include children in the response
    response = QuoteDetailResponse.model_validate(quote)
    response.pdf_outdated = pdf_outdated
    response.pdf_generated_at = pdf_generated_at
    if quote.quote_kind == "building_parent":
        children_result = await db.execute(
            select(Quote)
            .where(Quote.parent_quote_id == quote_id, Quote.quote_kind == "building_child_material")
            .order_by(Quote.created_at)
        )
        children = children_result.scalars().all()
        response_dict = response.model_dump()
        response_dict["children"] = [QuoteListResponse.model_validate(c).model_dump() for c in children]
        return response_dict

    return response


# ── DESPIECE PIECES (read-only · sub-PR despiece-real-wire) ─────────────────

@router.get("/quotes/{quote_id}/pieces", response_model=PieceListResponse)
async def list_pieces_for_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Lista piezas del despiece desde el `quote_breakdown.dual_read_result`.

    Cierra el gap del frontend `useDespiece` hook que consumía 100% mocks.
    Source único: `dual_read_result.sectores[].tramos[]` (pre o post-confirm
    del operador · `verified_derived_pieces` ya no se persiste · PR #386).

    Las 4 mutaciones (update/add/delete/regenerate) siguen mock-only · sub-PR
    siguiente las migra al modelo agentic via /chat (no CRUD plano).
    """
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="quote_not_found")

    breakdown = quote.quote_breakdown or {}
    dual_read = breakdown.get("dual_read_result")

    if not dual_read:
        return PieceListResponse(
            pieces=[],
            status="pending",
            timeline=[],
            warnings=[],
        )

    pieces = _serialize_dual_read_to_pieces(dual_read)
    if not pieces:
        return PieceListResponse(
            pieces=[],
            status="failed",
            timeline=[],
            warnings=["Valentina no detectó piezas en este despiece"],
        )

    return PieceListResponse(
        pieces=[PieceSchema(**p) for p in pieces],
        status="done",
        timeline=[],
        warnings=[],
    )


# ── CALCULATION (read-only display · sub-PR calculation-real-wire) ─────────

@router.get("/quotes/{quote_id}/calculation", response_model=CalculationResponse)
async def get_calculation_for_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Serializa `quote_breakdown` al shape `CalculationResult` del frontend.

    Cierra el gap del paso 4 que consumía 100% mocks. Sub-PR scope:
    - Residential (top-level breakdown.material_*, mo_items, merma, etc.)
    - Edificio out-of-scope · devuelve status=pending con summary específico
      (multi-material UI no soportado por `CalculationResult` actual)
    - Sin cálculo → status=pending

    Helpers de mapeo en `_serialize_residential_calc()` y
    `_pending_calculation_response()`. `triggerCalculation` y `applyAutoFix`
    siguen mock-only · sub-PR aparte si Marina los necesita.
    """
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="quote_not_found")

    breakdown = quote.quote_breakdown or {}

    # Edificio out-of-scope (multi-material via paso2_calc.calc_results)
    if breakdown.get("is_edificio") or "paso2_calc" in breakdown:
        return _pending_calculation_response(
            str(quote.id),
            "Cálculo de edificios no disponible en esta vista todavía",
        )

    # Residential sin cálculo aún
    if not breakdown.get("material_name") or not breakdown.get("total_ars"):
        return _pending_calculation_response(
            str(quote.id),
            "Cálculo pendiente · esperá a que Valentina termine el paso 3",
        )

    # Residential con cálculo completo
    return _serialize_residential_calc(breakdown, quote)


# ── COMPARE QUOTES ───────────────────────────────────────────────────────────

@router.get("/quotes/{quote_id}/compare", response_model=QuoteCompareResponse)
async def compare_quotes(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Return all related quotes (parent + children) for side-by-side comparison."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    root_id = quote.parent_quote_id or quote.id

    # Load root quote
    if root_id != quote.id:
        root_result = await db.execute(select(Quote).where(Quote.id == root_id))
        root = root_result.scalar_one_or_none()
        if not root:
            raise HTTPException(status_code=404, detail="Presupuesto padre no encontrado")
    else:
        root = quote

    # Load all children
    children_result = await db.execute(
        select(Quote)
        .where(Quote.parent_quote_id == root_id)
        .order_by(Quote.created_at)
    )
    children = children_result.scalars().all()

    all_quotes = [root] + list(children)
    if len(all_quotes) < 2:
        raise HTTPException(status_code=404, detail="No hay variantes para comparar")

    return QuoteCompareResponse(
        parent_id=root_id,
        client_name=root.client_name,
        project=root.project,
        quotes=[QuoteCompareItem.model_validate(q) for q in all_quotes],
    )


@router.get("/quotes/{quote_id}/compare/pdf")
async def compare_pdf(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Generate and return a comparison PDF for all related quotes."""
    from fastapi.responses import FileResponse
    from app.modules.agent.tools.document_tool import generate_comparison_pdf, OUTPUT_DIR

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    root_id = quote.parent_quote_id or quote.id

    if root_id != quote.id:
        root_result = await db.execute(select(Quote).where(Quote.id == root_id))
        root = root_result.scalar_one_or_none()
        if not root:
            raise HTTPException(status_code=404, detail="Presupuesto padre no encontrado")
    else:
        root = quote

    children_result = await db.execute(
        select(Quote)
        .where(Quote.parent_quote_id == root_id)
        .order_by(Quote.created_at)
    )
    children = children_result.scalars().all()
    all_quotes = [root] + list(children)

    if len(all_quotes) < 2:
        raise HTTPException(status_code=404, detail="No hay variantes para comparar")

    quotes_data = []
    for q in all_quotes:
        bd = q.quote_breakdown or {}
        bd["_total_ars"] = q.total_ars or bd.get("total_ars", 0)
        bd["_total_usd"] = q.total_usd or bd.get("total_usd", 0)
        bd["_material"] = q.material or bd.get("material_name", "")
        quotes_data.append(bd)

    pdf_dir = OUTPUT_DIR / root_id
    pdf_dir.mkdir(exist_ok=True)
    pdf_path = pdf_dir / "comparativo.pdf"

    import asyncio
    await asyncio.to_thread(
        generate_comparison_pdf, pdf_path, root.client_name, root.project, quotes_data
    )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"Comparativo - {root.client_name}.pdf",
    )


# ── UPDATE QUOTE STATUS ───────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}/status")
async def update_status(
    quote_id: str,
    body: QuoteStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    current = quote.status.value if hasattr(quote.status, "value") else quote.status
    target = body.status.value if hasattr(body.status, "value") else body.status
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(status_code=400, detail=f"Transición inválida: {current} → {target}")

    await db.execute(
        update(Quote)
        .where(Quote.id == quote_id)
        .values(status=body.status)
    )
    await log_event(
        db, event_type="quote.status_changed", source="router",
        summary=f"Status changed {current} → {target}",
        request=request, quote_id=quote_id,
        payload={"from": current, "to": target},
    )
    await db.commit()
    return {"ok": True}


# ── REOPEN MEASUREMENTS (unlock post-confirmation editing) ─────────────────
#
# PR #378 — El operador aprieta "Editar despiece" en la UI cuando quiere
# corregir medidas/piezas después de haber confirmado. Este endpoint
# invalida el Paso 2 (borra material + MO + totales + commercial_attrs
# + derived_pieces) y deja el quote en estado "Paso 1 editable" — el
# operador corrige, reconfirma, Valentina regenera Paso 2 limpio.
#
# Alternativa que usábamos antes: el operador escribía "agregá zócalo..."
# en el chat y card_editor detectaba keywords para hacer lo mismo. Sigue
# funcionando (mismo helper `reset_quote_to_paso1`), pero este endpoint
# es explícito: un click, no-chat-prompt.
#
# Prohibido en quotes con status {validated, sent} — ya se generó PDF
# al cliente. Si el operador necesita rearmar, hay que duplicar el quote
# (separate flow) o cambiar status manualmente.

@router.post("/quotes/{quote_id}/reopen-measurements")
async def reopen_measurements(
    quote_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Resetea el quote a Paso 1 para permitir edición post-confirmación.

    Side-effects (PR #383):
    - Promueve `verified_measurements` → `dual_read_result` si existe
      (para que la card re-emitida muestre las medidas editadas, no el
      snapshot pre-edit).
    - Corta `Quote.messages` desde el último turn assistant con
      `__DUAL_READ__` (inclusive) y regenera esa card con el despiece
      actualizado. El historial posterior (Paso 2 stale, preguntas de
      Valentina con datos viejos, etc.) se descarta — "nunca dejar
      historial viejo mezclado con estado nuevo".
    - El brief inicial del operador y todo lo previo a la card se
      preservan tal cual.

    Returns the updated quote.

    Codes:
        200 — reopen aplicado, breakdown con Paso 2 limpio + chat cortado.
        404 — quote no existe.
        409 — status no permite reopen (validated/sent).
        400 — no había confirmación previa (nada que reabrir).
    """
    from app.modules.agent.card_editor import (
        reset_quote_to_paso1,
        is_paso2_confirmed,
        truncate_history_at_card,
    )
    from app.modules.agent._trace import log_http_enter, log_reopen
    log_http_enter(quote_id, "POST /quotes/:id/reopen-measurements")

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Status gate: validated/sent no se reabre (PDF ya entregado).
    status_value = quote.status.value if hasattr(quote.status, "value") else str(quote.status)
    if status_value in ("validated", "sent"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"El presupuesto está en estado '{status_value}'. No se puede "
                "reabrir edición — el PDF ya fue generado/enviado. Duplicá el "
                "quote si necesitás rearmar."
            ),
        )

    bd = quote.quote_breakdown or {}
    if not is_paso2_confirmed(bd):
        # Idempotencia + claridad: si no hay nada que reabrir (el quote
        # sigue en Paso 1 o es nuevo), devolvemos 400 para que la UI
        # sepa que el botón está en un estado inconsistente. El caso
        # normal es que la UI solo muestre el botón si is_paso2_confirmed
        # es true (el breakdown trae verified_context).
        raise HTTPException(
            status_code=400,
            detail=(
                "No hay confirmación de medidas que reabrir. El quote ya "
                "está en Paso 1 editable."
            ),
        )

    # PR #383 — preservar las medidas editadas promoviéndolas a
    # dual_read_result. `reset_quote_to_paso1` borra verified_measurements,
    # entonces lo capturamos antes. Si el operador nunca editó
    # (verified_measurements no existe), dual_read_result queda como estaba.
    verified = bd.get("verified_measurements")
    new_bd = reset_quote_to_paso1(bd)
    if verified:
        new_bd["dual_read_result"] = verified

    # Cortar historial desde la card de despiece + regenerar.
    msgs_pre = list(quote.messages or [])
    new_messages, truncate_matched = truncate_history_at_card(
        msgs_pre,
        marker_prefix="__DUAL_READ__",
        new_payload=new_bd.get("dual_read_result"),
    )

    # También limpiamos total_ars / total_usd en la tabla (reflejan lo
    # calculado en Paso 2). brief_analysis y client_name se preservan.
    await db.execute(
        update(Quote)
        .where(Quote.id == quote_id)
        .values(
            quote_breakdown=new_bd,
            messages=new_messages,
            total_ars=None,
            total_usd=None,
        )
    )
    await db.commit()

    log_reopen(
        quote_id,
        kind="measurements",
        bd_pre=bd,
        bd_post=new_bd,
        msgs_count_pre=len(msgs_pre),
        msgs_count_post=len(new_messages),
        truncate_matched=truncate_matched,
    )
    # Audit: quote.reopened — payload distingue kind=measurements|context.
    await log_event(
        db, event_type="quote.reopened", source="router",
        summary=f"Quote reopened (kind=measurements, msgs {len(msgs_pre)}→{len(new_messages)})",
        request=request, quote_id=quote_id,
        payload={"kind": "measurements", "msgs_pre": len(msgs_pre), "msgs_post": len(new_messages),
                 "truncate_matched": truncate_matched},
    )
    await db.commit()

    # Refetch para devolver shape consistente con el listado.
    refreshed = await db.execute(select(Quote).where(Quote.id == quote_id))
    q = refreshed.scalar_one()
    return q


# ── REOPEN CONTEXT (editar card de análisis de contexto) ──────────────────
#
# PR #383 — Gemelo del endpoint /reopen-measurements pero para la card de
# contexto (`__CONTEXT_ANALYSIS__`). El operador aprieta "Editar contexto"
# cuando necesita cambiar un dato comercial que ya respondió (ej:
# corregir la cantidad de anafes, cambiar material, rectificar dirección).
#
# Diferencias vs /reopen-measurements:
# - Gate de reopen: `verified_context_analysis` existe (contexto confirmado),
#   no `verified_context` (medidas confirmadas).
# - El reset limpia también `verified_context_analysis` + todo lo de
#   Paso 2. `context_analysis_pending` se PRESERVA (preservado también
#   post-confirm gracias al cambio en `agent.py` del mismo PR) para que
#   la card se pueda regenerar con los mismos `data_known + assumptions
#   + pending_questions` que vio el operador al confirmar.
# - El corte del chat es en `__CONTEXT_ANALYSIS__`. Todo lo posterior
#   (dual_read card, [DUAL_READ_CONFIRMED], Paso 2 markdown, etc.) se
#   descarta. Brief y turns pre-card de contexto se preservan.

@router.post("/quotes/{quote_id}/reopen-context")
async def reopen_context(
    quote_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Resetea el quote al estado pre-confirmación del contexto.

    Side-effects:
    - Limpia Paso 2 + `verified_context_analysis` + `verified_context`
      + `verified_measurements` del breakdown.
    - Preserva `dual_read_result`, `context_analysis_pending`,
      `brief_analysis` y metadata (plan hash, etc.).
    - Corta `Quote.messages` desde el último turn assistant con
      `__CONTEXT_ANALYSIS__` (inclusive) y regenera esa card con
      `context_analysis_pending` actual.

    Codes:
        200 — reopen aplicado, contexto editable.
        404 — quote no existe.
        409 — status no permite reopen (validated/sent).
        400 — no había confirmación de contexto para reabrir.
    """
    from app.modules.agent.card_editor import (
        reset_quote_to_pre_context,
        truncate_history_at_card,
    )
    from app.modules.agent._trace import log_http_enter, log_reopen
    log_http_enter(quote_id, "POST /quotes/:id/reopen-context")

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    status_value = quote.status.value if hasattr(quote.status, "value") else str(quote.status)
    if status_value in ("validated", "sent"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"El presupuesto está en estado '{status_value}'. No se puede "
                "reabrir edición — el PDF ya fue generado/enviado. Duplicá el "
                "quote si necesitás rearmar."
            ),
        )

    bd = quote.quote_breakdown or {}
    if not bd.get("verified_context_analysis"):
        raise HTTPException(
            status_code=400,
            detail=(
                "No hay confirmación de contexto que reabrir. El quote aún "
                "no pasó por la card de análisis."
            ),
        )

    new_bd = reset_quote_to_pre_context(bd)

    # PR #386/#388 — quitar TODOS los tramos `_derived:true` del dual_read,
    # de cualquier kind (patas de isla `isla_pata`, alzadas `alzada`, y los
    # que se agreguen a futuro). Se materializan en `[CONTEXT_CONFIRMED]` a
    # partir de las respuestas del operador. Si reabre contexto, esas
    # respuestas podrían cambiar → los derivados viejos quedan stale. La
    # re-confirmación del contexto los regenera con los valores nuevos.
    if new_bd.get("dual_read_result"):
        from app.modules.quote_engine.dual_reader import (
            clear_all_derived_tramos,
        )
        new_bd["dual_read_result"] = clear_all_derived_tramos(
            new_bd["dual_read_result"],
        )

    # Cortar historial desde la card de contexto + regenerar con
    # context_analysis_pending (preservado post-#383).
    context_payload = new_bd.get("context_analysis_pending")
    msgs_pre = list(quote.messages or [])
    new_messages, truncate_matched = truncate_history_at_card(
        msgs_pre,
        marker_prefix="__CONTEXT_ANALYSIS__",
        new_payload=context_payload,
    )

    await db.execute(
        update(Quote)
        .where(Quote.id == quote_id)
        .values(
            quote_breakdown=new_bd,
            messages=new_messages,
            total_ars=None,
            total_usd=None,
        )
    )
    await db.commit()

    log_reopen(
        quote_id,
        kind="context",
        bd_pre=bd,
        bd_post=new_bd,
        msgs_count_pre=len(msgs_pre),
        msgs_count_post=len(new_messages),
        truncate_matched=truncate_matched,
    )
    await log_event(
        db, event_type="quote.reopened", source="router",
        summary=f"Quote reopened (kind=context, msgs {len(msgs_pre)}→{len(new_messages)})",
        request=request, quote_id=quote_id,
        payload={"kind": "context", "msgs_pre": len(msgs_pre), "msgs_post": len(new_messages),
                 "truncate_matched": truncate_matched},
    )
    await db.commit()

    refreshed = await db.execute(select(Quote).where(Quote.id == quote_id))
    q = refreshed.scalar_one()
    return q


# ── REHYDRATE LEGACY CHAT HISTORY (non-destructive) ─────────────────────────
#
# PR #380 — Repara quotes viejos cuyo `Quote.messages` quedó con placeholders
# `_SHOWN_` vacíos, bloques internos del system prompt pegados al user
# turn, o fake turns "(contexto confirmado)". El helper puro
# `rehydrate_messages` reconstruye el historial usando `quote_breakdown`
# como fuente de verdad (dual_read_result, context_analysis_pending)
# sin inventar data ausente.
#
# Idempotente: si el historial ya está limpio, `changed=False` y no hay
# UPDATE a DB. No toca cálculo, totales ni pricing — solo `messages`.
#
# Uso típico: operador abre un quote viejo, ve markers crudos, llama
# este endpoint (manualmente o vía UI futura). También usable desde
# un script de migration one-shot.

@router.post("/quotes/{quote_id}/rehydrate-history")
async def rehydrate_history(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Reconstruye el historial de chat desde `quote_breakdown` si hay
    markers legacy. No modifica nada del cálculo.

    Codes:
        200 con {changed: bool, quote_id} — idempotente si changed=False.
        404 — quote no existe.
    """
    from app.modules.agent.card_editor import rehydrate_messages

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    new_messages, changed = rehydrate_messages(
        list(quote.messages or []), quote.quote_breakdown or {},
    )

    if not changed:
        return {"changed": False, "quote_id": quote_id}

    await db.execute(
        update(Quote)
        .where(Quote.id == quote_id)
        .values(messages=new_messages)
    )
    await db.commit()
    logger.info(
        f"[rehydrate] quote {quote_id} messages updated: "
        f"{len(quote.messages or [])} → {len(new_messages)} turns"
    )
    return {"changed": True, "quote_id": quote_id, "turn_count": len(new_messages)}


# ── VALIDATE QUOTE (generate docs + change status) ──────────────────────────

@router.post("/quotes/{quote_id}/validate")
async def validate_quote(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate PDF/Excel/Drive from existing breakdown and set status to validated."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    bd = quote.quote_breakdown
    if not bd:
        raise HTTPException(status_code=400, detail="El presupuesto no tiene desglose calculado")

    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_to_drive

    # Use complete breakdown as source of truth — it contains all fields
    # that generate_documents needs (sectors, mo_items, material_total,
    # merma, piece_details, sinks, discount_amount, etc.)
    # Only fill fallbacks for fields that might be missing in legacy breakdowns.
    doc_data = dict(bd)
    doc_data.setdefault("client_name", quote.client_name)
    doc_data.setdefault("project", quote.project)
    doc_data.setdefault("material_name", quote.material)
    doc_data.setdefault("total_ars", quote.total_ars)
    doc_data.setdefault("total_usd", quote.total_usd)
    doc_data.setdefault("discount_pct", 0)
    doc_data.setdefault("sectors", [])
    doc_data.setdefault("mo_items", [])

    doc_result = await generate_documents(quote_id, doc_data)
    pdf_url = doc_result.get("pdf_url") if doc_result.get("ok") else None
    excel_url = doc_result.get("excel_url") if doc_result.get("ok") else None

    # Preserve existing drive_url if new upload fails
    existing_drive_url = quote.drive_url
    existing_drive_file_id = quote.drive_file_id

    drive_url = None
    drive_file_id = None
    if doc_result.get("ok"):
        # Delete old Drive file before uploading new one
        if existing_drive_file_id:
            from app.modules.agent.tools.drive_tool import delete_drive_file
            await delete_drive_file(existing_drive_file_id)

        drive_result = await upload_to_drive(
            quote_id,
            doc_data["client_name"],
            doc_data["material_name"],
            doc_data.get("date"),
        )
        if drive_result.get("ok"):
            drive_url = drive_result.get("drive_url")
            drive_file_id = drive_result.get("drive_file_id")

    # If upload failed, preserve existing drive_url
    final_drive_url = drive_url or existing_drive_url
    final_drive_file_id = drive_file_id or existing_drive_file_id

    update_values = {
        "status": QuoteStatus.VALIDATED,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
    }
    # Only update drive fields if we have new values (don't overwrite with None)
    if drive_url:
        update_values["drive_url"] = drive_url
        update_values["drive_file_id"] = drive_file_id

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(**update_values)
    )
    await db.commit()

    return {
        "ok": True,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "drive_url": final_drive_url,
    }


# ── REGENERATE — re-emit PDF/Excel from existing breakdown, no recalc ────────
#
# Caso de uso: corregiste un bug en el template (grand total duplicado, SKU
# mal, formato Excel) y querés refrescar los archivos de un presupuesto
# YA validado, SIN re-correr Valentina y SIN tocar ningún dato del negocio.
#
# Diferencias con /validate (que sí podría usarse pero cambia estado):
#   - NO toca status (un quote validated/sent sigue como estaba).
#   - NO toca client_name, project, totales, quote_breakdown.
#   - Solo actualiza las URLs de archivos (pdf_url, excel_url, drive_url,
#     drive_file_id) y appendea un entry a change_history para auditoría.

_ALZADA_LABEL_RE = re.compile(
    r"^(?P<dim>\d+[.,]\d+\s*[×xX]\s*\d+[.,]\d+)\s+Alzada\b.*$",
    re.IGNORECASE,
)


def _normalize_piece_labels(sectors: list) -> list:
    """Rewrite cached piece labels so that Alzadas render as '{L} × {D} Alzada'.

    /regenerate no recalcula — usa el `quote_breakdown.sectors` guardado. Los
    quotes viejos tienen labels tipo "3.01 × 0.60 Alzada corrida (fondo
    completo sin heladera) (SE REALIZA EN 2 TRAMOS)" que quedaron pegados.
    Acá los colapsamos in-memory sin tocar la DB. Preserva sufijos ' *' del
    override de m² (ver calculator.py).
    """
    if not isinstance(sectors, list):
        return sectors
    out = []
    for sec in sectors:
        if not isinstance(sec, dict):
            out.append(sec)
            continue
        pieces = sec.get("pieces")
        if not isinstance(pieces, list):
            out.append(sec)
            continue
        new_pieces = []
        for p in pieces:
            if isinstance(p, str):
                base, star = (p[:-2], " *") if p.rstrip().endswith(" *") else (p, "")
                m = _ALZADA_LABEL_RE.match(base.strip())
                if m:
                    new_pieces.append(f"{m.group('dim')} Alzada{star}")
                else:
                    new_pieces.append(p)
            else:
                new_pieces.append(p)
        new_sec = dict(sec)
        new_sec["pieces"] = new_pieces
        out.append(new_sec)
    return out


def _build_regenerate_doc_data(quote: Quote, bd: dict) -> dict:
    """Prep doc_data for /regenerate: start from the cached breakdown and
    override the fields that the operator can edit manually (no recalc).

    `setdefault` for the rest — legacy breakdowns that might be missing keys
    get filled from the Quote columns; newer breakdowns keep their values.
    """
    doc_data = dict(bd)
    # Editable-from-detail-view fields: the operator may have edited these via
    # PATCH /quotes/:id after the breakdown was cached. Force-override so the
    # regenerated PDF/Excel reflects the latest values.
    doc_data["client_name"] = quote.client_name
    doc_data["project"] = quote.project
    doc_data["notes"] = quote.notes
    doc_data.setdefault("material_name", quote.material)
    doc_data.setdefault("total_ars", quote.total_ars)
    doc_data.setdefault("total_usd", quote.total_usd)
    doc_data.setdefault("discount_pct", 0)
    doc_data.setdefault("sectors", [])
    doc_data.setdefault("mo_items", [])
    doc_data["sectors"] = _normalize_piece_labels(doc_data["sectors"])
    return doc_data


@router.post("/quotes/{quote_id}/regenerate")
async def regenerate_quote_docs(
    quote_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Re-generate PDF/Excel from existing breakdown. No recalc, no status change."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    bd = quote.quote_breakdown
    if not bd:
        raise HTTPException(
            status_code=400,
            detail="El presupuesto no tiene desglose calculado — no hay datos para regenerar",
        )

    from datetime import datetime
    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_to_drive, delete_drive_file

    doc_data = _build_regenerate_doc_data(quote, bd)

    doc_result = await generate_documents(quote_id, doc_data)
    if not doc_result.get("ok"):
        raise HTTPException(
            status_code=500,
            detail=f"Falló la generación de documentos: {doc_result.get('error')}",
        )

    pdf_url = doc_result.get("pdf_url")
    excel_url = doc_result.get("excel_url")

    # PR #38 — el regenerate debe reemplazar los LINKS DE DRIVE separados
    # (drive_pdf_url y drive_excel_url). Antes solo se actualizaba
    # drive_url/file_id (uno solo), dejando los botones PDF/Excel Drive
    # del UI apuntando a los archivos VIEJOS → operador veía el layout
    # pre-fix aunque regenerara.
    from app.modules.agent.tools.drive_tool import (
        upload_single_file_to_drive, delete_drive_file,
    )
    from app.core.static import OUTPUT_DIR as _OUT_DIR
    from pathlib import Path as _P2

    # Delete the previous Drive files if we had file ids.
    for _old_id in (quote.drive_file_id, getattr(quote, "drive_pdf_file_id", None)):
        if _old_id:
            try:
                await delete_drive_file(_old_id)
            except Exception as e:
                logging.warning(f"[regenerate] delete_drive_file({_old_id}) failed: {e}")

    # Re-upload PDF and Excel as SEPARATE files. upload_to_drive returns only
    # the last url, which is why the previous implementation ended up with
    # stale Drive links. upload_single_file_to_drive returns per-file info.
    new_drive_pdf_url = None
    new_drive_excel_url = None
    new_drive_file_id = None
    filename_base = doc_result.get("filename_base")
    subfolder = doc_data.get("client_name") or "Sin cliente"
    if filename_base:
        _quote_dir = _OUT_DIR / quote_id
        _pdf_path = _quote_dir / f"{filename_base}.pdf"
        _xlsx_path = _quote_dir / f"{filename_base}.xlsx"
        try:
            if _pdf_path.exists():
                _r_pdf = await upload_single_file_to_drive(str(_pdf_path), subfolder)
                if _r_pdf.get("ok"):
                    new_drive_pdf_url = _r_pdf.get("drive_url")
                    new_drive_file_id = _r_pdf.get("file_id")
        except Exception as e:
            logging.warning(f"[regenerate] PDF Drive upload failed: {e}")
        try:
            if _xlsx_path.exists():
                _r_xls = await upload_single_file_to_drive(str(_xlsx_path), subfolder)
                if _r_xls.get("ok"):
                    new_drive_excel_url = _r_xls.get("drive_url")
        except Exception as e:
            logging.warning(f"[regenerate] Excel Drive upload failed: {e}")

    # Backcompat fields used elsewhere.
    existing_drive_url = quote.drive_url
    new_drive_url = new_drive_pdf_url or new_drive_excel_url
    existing_drive_file_id = quote.drive_file_id
    final_drive_url = new_drive_url or existing_drive_url
    final_drive_file_id = new_drive_file_id or existing_drive_file_id

    # Audit log: append to change_history (column ya existe, formato igual
    # que el que usa calculate_quote save al final del loop).
    regenerated_at = datetime.now().isoformat()
    change_entry = {
        "timestamp": regenerated_at,
        "action": "regenerate_docs",
        "pdf_url_before": quote.pdf_url,
        "excel_url_before": quote.excel_url,
        "pdf_url_after": pdf_url,
        "excel_url_after": excel_url,
    }
    history = list(quote.change_history or [])
    history.append(change_entry)

    update_values = {
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "change_history": history,
    }
    if new_drive_url:
        update_values["drive_url"] = new_drive_url
        update_values["drive_file_id"] = new_drive_file_id
    # PR #38 — también actualizar los links separados que usa el UI
    # (botones 'PDF Drive' / 'Excel Drive').
    if new_drive_pdf_url:
        update_values["drive_pdf_url"] = new_drive_pdf_url
    if new_drive_excel_url:
        update_values["drive_excel_url"] = new_drive_excel_url

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(**update_values)
    )
    # Audit: docs.regenerated — punto canónico único. Reemplaza el
    # `logging.info` de abajo. Drive info incluida en payload (en lugar
    # de un evento `drive.uploaded` separado, ver desvío del plan).
    # Honestidad operativa (E2E test #4): si pidió Drive y falló (alguna
    # URL None), success=False con error_message explícito — no mentir.
    _drive_failed = not (new_drive_pdf_url and new_drive_excel_url)
    _missing_parts = []
    if not new_drive_pdf_url:
        _missing_parts.append("PDF")
    if not new_drive_excel_url:
        _missing_parts.append("Excel")
    _re_error = (
        f"Drive upload failed for: {', '.join(_missing_parts)} "
        f"(local regeneration OK)"
    ) if _drive_failed else None
    await log_event(
        db, event_type="docs.regenerated", source="router",
        summary=f"PDF + Excel regenerated{' (drive partial-fail)' if _drive_failed else ''}",
        request=request, quote_id=quote_id,
        payload={
            "pdf_url_before": quote.pdf_url, "pdf_url_after": pdf_url,
            "excel_url_before": quote.excel_url, "excel_url_after": excel_url,
            "drive_pdf_url": new_drive_pdf_url, "drive_excel_url": new_drive_excel_url,
            "drive_file_id": final_drive_file_id,
            "drive_ok": not _drive_failed,
        },
        success=not _drive_failed,
        error_message=_re_error,
    )
    await db.commit()
    return {
        "ok": True,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "drive_url": final_drive_url,
        "regenerated_at": regenerated_at,
    }


# ── DERIVE MATERIAL — create new quote with different material ───────────────

@router.post("/quotes/{quote_id}/derive-material")
async def derive_material(
    quote_id: str,
    body: DeriveMaterialRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a NEW quote derived from an existing one, replacing only the material.

    Copies client data, pieces, and options from the original.
    Recalculates everything from scratch via calculate_quote.
    The new quote is born in DRAFT status with no documents.

    Traceability: new quote's parent_quote_id points to the original.
    conversation_id is NOT copied — the derived quote starts its own chat.
    """
    import uuid as _uuid
    from app.modules.quote_engine.calculator import calculate_quote

    # Load original
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Presupuesto original no encontrado")

    # ── Source of truth for pieces ──
    # Priority order:
    #   1. quote.pieces (raw input · flujo web/chatbot legacy)
    #   2. breakdown.piece_details (calculator output reconstruido)
    #   3. breakdown.dual_read_result (flujo Operador post-#512 · sub-PR
    #      derive-material-ui-wire fix destapado por validación visual #515)
    # If none, reject — no reliable base to recalculate.
    pieces = None
    if original.pieces:
        # Raw pieces saved at creation — best source
        pieces = original.pieces
    elif original.quote_breakdown and original.quote_breakdown.get("piece_details"):
        # Fallback: reconstruct from breakdown's piece_details
        pieces = []
        for pd in original.quote_breakdown["piece_details"]:
            piece = {"description": pd["description"], "largo": pd["largo"]}
            if pd.get("dim2"):
                # dim2 is prof for mesadas, alto for zócalos
                desc_lower = pd["description"].lower()
                if "zócalo" in desc_lower or "zocalo" in desc_lower:
                    piece["alto"] = pd["dim2"]
                else:
                    piece["prof"] = pd["dim2"]
            pieces.append(piece)
        logging.info(f"[derive] Reconstructed {len(pieces)} pieces from breakdown for {quote_id}")
    elif original.quote_breakdown and original.quote_breakdown.get("dual_read_result"):
        # Fallback flujo Operador (sub-PR derive-material-ui-wire):
        # quotes del text_parse tienen piezas solo en dual_read_result.
        pieces = _extract_calc_pieces_from_dual_read(
            original.quote_breakdown["dual_read_result"]
        )
        if pieces:
            logging.info(
                f"[derive] Extracted {len(pieces)} pieces from dual_read_result for {quote_id}"
            )
    if not pieces:
        raise HTTPException(status_code=400, detail="El presupuesto original no tiene piezas. No se puede derivar.")

    # ── Plazo: from breakdown or config default ──
    plazo = None
    if original.quote_breakdown:
        plazo = original.quote_breakdown.get("delivery_days")
    if not plazo:
        try:
            from app.core.company_config import get as _cfg
            plazo = _cfg("delivery_days.display", _cfg("delivery_days.display", "30 dias desde la toma de medidas"))
        except Exception:
            plazo = _cfg("delivery_days.display", "30 dias desde la toma de medidas")

    # ── Build calculate_quote input ──
    calc_input = {
        "client_name": original.client_name or "",
        "project": original.project or "",
        "material": body.material,
        "pieces": pieces,
        "localidad": original.localidad or "rosario",
        "colocacion": original.colocacion if original.colocacion is not None else True,
        "pileta": original.pileta,
        "anafe": original.anafe or False,
        "plazo": plazo,
        "skip_flete": original.quote_breakdown.get("skip_flete", False) if original.quote_breakdown else False,
    }
    # Carry over frentin/inglete/pulido (y PR #401: regrueso) from original
    # breakdown if they existed. Sin este carry-over un derive_material
    # perdería el regrueso del original.
    if original.quote_breakdown:
        for key in ("frentin", "frentin_ml", "regrueso", "regrueso_ml", "inglete", "pulido", "discount_pct", "is_edificio"):
            val = original.quote_breakdown.get(key)
            if val:
                calc_input[key] = val

    # ── Calculate ──
    calc_result = calculate_quote(calc_input)
    if not calc_result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Error al calcular con material '{body.material}': {calc_result.get('error', 'desconocido')}"
        )

    # ── Create new quote ──
    new_id = str(_uuid.uuid4())
    new_quote = Quote(
        id=new_id,
        client_name=original.client_name,
        project=original.project,
        material=calc_result.get("material_name", body.material),
        total_ars=calc_result.get("total_ars"),
        total_usd=calc_result.get("total_usd"),
        quote_breakdown=calc_result,
        status=QuoteStatus.DRAFT,
        source=original.source,
        is_read=True,
        # Client contact
        client_phone=original.client_phone,
        client_email=original.client_email,
        # Quote options (copied from original)
        localidad=original.localidad,
        colocacion=original.colocacion,
        pileta=original.pileta,
        anafe=original.anafe,
        sink_type=original.sink_type,
        pieces=pieces,
        notes=original.notes,
        # Traceability
        parent_quote_id=original.parent_quote_id or original.id,
        # Fresh state — no docs, no chat, no history
        messages=[],
        change_history=[],
        # conversation_id intentionally NOT copied:
        # the derived quote starts its own chat context.
    )
    db.add(new_quote)
    await db.commit()

    logging.info(
        f"[derive-material] {quote_id} → {new_id} | "
        f"material: {original.material} → {body.material} | "
        f"total_ars: {original.total_ars} → {calc_result.get('total_ars')} | "
        f"total_usd: {original.total_usd} → {calc_result.get('total_usd')}"
    )

    return {
        "ok": True,
        "quote_id": new_id,
        "material": calc_result.get("material_name"),
        "total_ars": calc_result.get("total_ars"),
        "total_usd": calc_result.get("total_usd"),
        "derived_from": quote_id,
    }


# ── PATCH QUOTE (admin) ──────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}")
async def patch_quote(
    quote_id: str,
    body: QuotePatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Verify quote exists
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Quote not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # PR #438 — guardar los keys ORIGINALES del patch antes de
    # cualquier mutación interna (mirror al breakdown, rename
    # `origin → source`, etc.) para que el response liste lo que
    # el cliente pidió, no la mecánica interna como `quote_breakdown`.
    _original_patch_keys = set(updates.keys())

    # Map origin -> source
    if "origin" in updates:
        updates["source"] = updates.pop("origin")

    # Serialize material array to comma-separated string
    if "material" in updates and isinstance(updates["material"], list):
        updates["material"] = ", ".join(updates["material"])

    # Serialize pieces to list of dicts for JSON column
    if "pieces" in updates and updates["pieces"] is not None:
        updates["pieces"] = [p.model_dump() for p in body.pieces]

    # Serialize sink_type to dict for JSON column
    if "sink_type" in updates and body.sink_type is not None:
        updates["sink_type"] = body.sink_type.model_dump()

    # PR #437 (P1.2) — delivery_days NO es columna en Quote; lo
    # extraemos del dict de columnas y lo persistimos en el JSON
    # `quote_breakdown.delivery_days`. Sin este split, SQLAlchemy
    # tiraría "no such column delivery_days" al hacer
    # `update(Quote).values(delivery_days=...)`.
    breakdown_only_updates: dict = {}
    if "delivery_days" in updates:
        breakdown_only_updates["delivery_days"] = updates.pop("delivery_days")

    # PR #438 (P1.1) — sync REST → breakdown para campos que tienen
    # mirror en ambas capas. Antes de este PR, PATCH /quotes cambiaba
    # solo la columna y el breakdown JSON quedaba viejo → frontend
    # detail view (que lee del breakdown) mostraba el valor anterior,
    # PDF re-generado leía el viejo, Paso 2 markdown idem. Bug
    # latente que solo se evitaba porque el frontend no exponía
    # EditableField de esos campos. Con P2.1 (próximo PR) se exponen.
    #
    # Map: nombre del campo en columna → key en breakdown JSON.
    # `material` se mapea a `material_name` (rename histórico).
    # NO incluye `pieces` (requiere recálculo, no es simple mirror)
    # ni `sink_type` / `client_phone` / `client_email` / `status` /
    # `notes` / `parent_quote_id` / `conversation_id` / `source`
    # (no tienen mirror en breakdown).
    _BREAKDOWN_MIRROR_FIELDS = {
        "client_name": "client_name",
        "project": "project",
        "localidad": "localidad",
        "colocacion": "colocacion",
        "pileta": "pileta",
        "anafe": "anafe",
        "material": "material_name",  # rename: columna `material` → bd `material_name`
    }
    breakdown_mirror_updates: dict = {}
    for col_key, bd_key in _BREAKDOWN_MIRROR_FIELDS.items():
        if col_key in updates:
            breakdown_mirror_updates[bd_key] = updates[col_key]

    if breakdown_only_updates or breakdown_mirror_updates:
        # Leer breakdown actual y mergear ambos sets de updates al JSON.
        existing_q = await db.execute(select(Quote).where(Quote.id == quote_id))
        existing_quote = existing_q.scalar_one_or_none()
        bd = dict(existing_quote.quote_breakdown or {}) if existing_quote else {}
        for k, v in breakdown_only_updates.items():
            bd[k] = v
        for k, v in breakdown_mirror_updates.items():
            bd[k] = v
        # Si ya hay quote_breakdown en `updates` por algún motivo,
        # respetarlo y mergear arriba; si no, crear el patch.
        if "quote_breakdown" in updates and isinstance(updates["quote_breakdown"], dict):
            updates["quote_breakdown"] = {
                **updates["quote_breakdown"],
                **breakdown_only_updates,
                **breakdown_mirror_updates,
            }
        else:
            updates["quote_breakdown"] = bd

    if updates:
        await db.execute(update(Quote).where(Quote.id == quote_id).values(**updates))
        # Audit: quote.patched. Solo registramos las keys del patch
        # original (no las internas tipo quote_breakdown). Sanitizer
        # redacta valores sensibles (phone, email).
        await log_event(
            db, event_type="quote.patched", source="router",
            summary=f"Quote patched (fields: {sorted(_original_patch_keys)})",
            request=request, quote_id=quote_id,
            payload={"fields": sorted(_original_patch_keys)},
        )
        await db.commit()

    logger.info(
        "[patch] Quote %s updated: %s breakdown_only=%s mirrored=%s",
        quote_id,
        list(updates.keys()),
        list(breakdown_only_updates.keys()),
        list(breakdown_mirror_updates.keys()),
    )
    # Response — solo los keys que vinieron en el patch original
    # (sin `quote_breakdown` interno, sin renames como source/origin).
    # `delivery_days` está en `_original_patch_keys` aunque
    # internamente se haya movido a breakdown.
    return {
        "ok": True,
        "updated": sorted(_original_patch_keys),
    }


# ── MARK QUOTE AS READ ───────────────────────────────────────────────────────

@router.patch("/quotes/{quote_id}/read")
async def mark_as_read(quote_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


# ── GENERATE DOCUMENTS (for web quotes without docs) ─────────────────────────

@router.post("/quotes/{quote_id}/generate")
async def generate_quote_documents(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Generate PDF/Excel/Drive for a quote that has quote_breakdown but no documents yet."""
    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_to_drive

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    bd = quote.quote_breakdown
    if not bd:
        raise HTTPException(status_code=400, detail="Este presupuesto no tiene datos de cálculo (quote_breakdown)")

    # Sub-PR paso-5-pdf-real-wire: copia full breakdown como /validate y
    # /regenerate. Antes este endpoint copiaba 14 keys a mano · faltaban
    # sobrante_m2/total, mo_discount_pct/amount, has_m2_override, is_edificio,
    # thickness_mm, notes, material_total_bruto · el PDF no renderea bloques
    # cuando faltan. `dict(bd)` cierra el gap en una línea (FASE 1 mapeo).
    doc_data = dict(bd)
    # Fallbacks defensivos para breakdowns legacy sin estos top-level fields.
    doc_data.setdefault("client_name", quote.client_name)
    doc_data.setdefault("project", quote.project)
    doc_data.setdefault("date", "")
    doc_data.setdefault("material_name", quote.material or "")
    # Notes vienen del Quote DB (no del breakdown) · cierra deuda PR #439.
    # El operador puede editar notas después del cálculo · el breakdown
    # podría tener una versión vieja o no tenerlas.
    doc_data["notes"] = quote.notes

    # Generate PDF + Excel
    doc_result = await generate_documents(quote_id, doc_data)
    if not doc_result.get("ok"):
        raise HTTPException(status_code=500, detail=doc_result.get("error", "Error generando documentos"))

    pdf_url = doc_result.get("pdf_url")
    excel_url = doc_result.get("excel_url")

    # Upload to Drive
    drive_url = None
    drive_file_id = None
    drive_result = await upload_to_drive(
        quote_id,
        doc_data["client_name"],
        doc_data["material_name"],
        doc_data["date"],
    )
    if drive_result.get("ok"):
        drive_url = drive_result.get("drive_url")
        drive_file_id = drive_result.get("drive_file_id")

    # Update quote with file URLs + status
    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(
            pdf_url=pdf_url,
            excel_url=excel_url,
            drive_url=drive_url,
            drive_file_id=drive_file_id,
            status=QuoteStatus.VALIDATED.value,
        )
    )
    await db.commit()

    logging.info(f"Generated documents for quote {quote_id}: pdf={pdf_url}, drive={drive_url}")

    return {
        "ok": True,
        "pdf_url": pdf_url,
        "excel_url": excel_url,
        "drive_url": drive_url,
    }


# ── DELETE QUOTE ──────────────────────────────────────────────────────────────

@router.delete("/quotes/{quote_id}")
async def delete_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Resolve the family root and collect all related quotes
    root_id = quote.parent_quote_id or quote.id
    family_result = await db.execute(
        select(Quote).where(
            (Quote.id == root_id) | (Quote.parent_quote_id == root_id)
        )
    )
    family = list(family_result.scalars().all())

    logging.info(
        f"Cascade-deleting quote family root={root_id}: "
        f"{[q.id for q in family]} (triggered by {quote_id})"
    )

    import shutil
    from app.core.static import OUTPUT_DIR

    for q in family:
        # Delete Drive file if exists (best-effort)
        if q.drive_file_id:
            try:
                from app.modules.agent.tools.drive_tool import delete_drive_file
                await delete_drive_file(q.drive_file_id)
            except Exception as e:
                logging.warning(f"Failed to delete Drive file {q.drive_file_id}: {e}")

        # Delete local files
        output_dir = OUTPUT_DIR / q.id
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
            except Exception as e:
                logging.warning(f"Failed to delete local files for {q.id}: {e}")

        await db.delete(q)

    await db.commit()
    return {"ok": True, "deleted": [q.id for q in family]}


# ── CREATE QUOTE (new chat) ───────────────────────────────────────────────────

class ResumenObraRequest(BaseModel):
    quote_ids: List[str]
    notes: Optional[str] = None
    force_same_client: Optional[bool] = False


class MergeClientRequest(BaseModel):
    quote_ids: List[str]
    canonical_client_name: str


class ClientMatchCheckRequest(BaseModel):
    quote_ids: List[str]


@router.post("/quotes/client-match-check")
async def client_match_check(
    body: ClientMatchCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """Preview: do these quotes look like the same client?

    Returns { same: bool, reason: "exact"|"fuzzy"|"ambiguous",
              distinct_names: [...] }

    The frontend uses this to decide whether to show a confirmation dialog
    before POSTing to /resumen-obra.
    """
    from app.modules.agent.tools.client_match import are_fuzzy_same_client
    from app.modules.agent.tools.resumen_obra_tool import _normalize_client

    if not body.quote_ids:
        raise HTTPException(status_code=400, detail="quote_ids vacío")
    res = await db.execute(select(Quote).where(Quote.id.in_(body.quote_ids)))
    quotes = list(res.scalars().all())
    if len(quotes) < len(set(body.quote_ids)):
        found = {q.id for q in quotes}
        missing = [qid for qid in body.quote_ids if qid not in found]
        raise HTTPException(status_code=404, detail=f"Presupuestos no encontrados: {missing}")

    distinct = sorted({q.client_name or "" for q in quotes})
    if len(quotes) <= 1:
        return {"same": True, "reason": "exact", "distinct_names": distinct}

    anchor = quotes[0].client_name
    normalized_anchor = _normalize_client(anchor)
    all_exact = all(
        _normalize_client(q.client_name) == normalized_anchor for q in quotes
    )
    if all_exact:
        return {"same": True, "reason": "exact", "distinct_names": distinct}

    all_fuzzy = all(
        are_fuzzy_same_client(q.client_name, anchor) for q in quotes[1:]
    )
    if all_fuzzy:
        return {"same": True, "reason": "fuzzy", "distinct_names": distinct}

    return {"same": False, "reason": "ambiguous", "distinct_names": distinct}


@router.post("/quotes/merge-client")
async def merge_client_endpoint(
    body: MergeClientRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rename the client_name of N quotes to a single canonical value.

    Used when the operator confirms that several quotes with different raw
    names all belong to the same client. This unifies future grouping
    without touching any numeric data.
    """
    name = (body.canonical_client_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="canonical_client_name requerido")
    if len(name) > 500:
        raise HTTPException(status_code=400, detail="canonical_client_name demasiado largo")
    if not body.quote_ids:
        raise HTTPException(status_code=400, detail="quote_ids vacío")

    res = await db.execute(select(Quote).where(Quote.id.in_(body.quote_ids)))
    quotes = list(res.scalars().all())
    found = {q.id for q in quotes}
    missing = [qid for qid in body.quote_ids if qid not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Presupuestos no encontrados: {missing}")

    # Apply rename + invalidate email_draft (names affect the prompt).
    updated = []
    for q in quotes:
        if q.client_name != name:
            updated.append(q.id)
        q.client_name = name
        q.email_draft = None
    await db.commit()
    return {
        "ok": True,
        "updated_ids": updated,
        "client_name": name,
        "quote_ids": body.quote_ids,
    }


@router.get("/quotes/{quote_id}/email-draft")
async def get_email_draft(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return AI-generated commercial email draft for the client.

    Lazy cache on Quote.email_draft — regenerates when stale (anchor quote,
    any sibling of the same client, or resumen_obra timestamp changed).
    """
    from app.modules.agent.tools.email_draft_tool import (
        generate_email_draft,
        EmailDraftError,
    )
    try:
        return await generate_email_draft(db, quote_id, force=False)
    except EmailDraftError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    except Exception as e:
        logging.error(f"[email-draft] unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno generando el email")


@router.post("/quotes/{quote_id}/email-draft/regenerate")
async def regenerate_email_draft(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Force regeneration of the email draft, bypassing the cache."""
    from app.modules.agent.tools.email_draft_tool import (
        generate_email_draft,
        EmailDraftError,
    )
    try:
        return await generate_email_draft(db, quote_id, force=True)
    except EmailDraftError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    except Exception as e:
        logging.error(f"[email-draft] unexpected error on regenerate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno generando el email")


@router.post("/quotes/resumen-obra")
async def generate_resumen_obra_endpoint(
    body: ResumenObraRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a consolidated 'resumen de obra' PDF from N selected quotes.

    - Validates: same client, all validated, 1<=N<=20, notes<=1000 chars
    - Generates PDF (no Excel), uploads to Drive (non-fatal)
    - Persists record in each selected quote's `resumen_obra` field
    - Invalidates each quote's `email_draft` cache (regen on next GET)
    """
    from app.modules.agent.tools.resumen_obra_tool import (
        generate_resumen_obra,
        ResumenObraError,
    )

    try:
        record = await generate_resumen_obra(
            db=db,
            quote_ids=body.quote_ids,
            notes_raw=body.notes,
            force_same_client=bool(body.force_same_client),
        )
    except ResumenObraError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    except Exception as e:
        logging.error(f"[resumen-obra] unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno generando el resumen")

    return record


@router.post("/quotes")
async def create_quote(
    request: Request,
    db: AsyncSession = Depends(get_db),
    body: Optional[CreateQuoteRequest] = None,
):
    # Opportunistic cleanup of old empty drafts
    from app.core.database import cleanup_empty_drafts
    import asyncio
    asyncio.create_task(cleanup_empty_drafts())

    quote = Quote(
        id=str(uuid.uuid4()),
        client_name="",
        project="",
        messages=[],
        status=body.status if body and body.status else QuoteStatus.DRAFT,
    )
    db.add(quote)
    await log_event(
        db, event_type="quote.created", source="router",
        summary=f"Quote created (status={quote.status.value})",
        request=request, quote_id=quote.id,
        payload={"status": quote.status.value},
    )
    await db.commit()
    return {"id": quote.id}


# ── ADMIN: Analyze plans vectorality ──────────────────────────────────────────

@router.post("/admin/analyze-plans-vectorality")
async def analyze_plans_vectorality(
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Analiza las últimas N quotes y clasifica cada `source_file` como
    `vectorial_clean` / `vectorial_and_raster` / `raster_only` / `unknown`.

    Usado para decidir si vale la inversión del fast-path vectorial (2d).
    Criterios idénticos al pipeline real (agent.py vision detection).

    Autenticado por el middleware JWT global — no requiere rol extra.
    Lee los archivos desde disco local (OUTPUT_DIR), sin descarga HTTP.

    Respuesta:
    ```
    {
      "total_analyzed": 150,
      "counts": {"vectorial_clean": 95, "raster_only": 35, ...},
      "percentages": {"vectorial_clean": 63.3, ...},
      "recommend_2d": true
    }
    ```
    """
    from pathlib import Path
    from app.core.static import OUTPUT_DIR
    from app.modules.analytics.plans_vectorality import analyze_source_files

    # Últimas N quotes con source_files no vacío
    result = await db.execute(
        select(Quote)
        .where(Quote.source_files.isnot(None))
        .order_by(Quote.created_at.desc())
        .limit(limit)
    )
    quotes = result.scalars().all()

    items: list[tuple[str, dict]] = []
    for q in quotes:
        for sf in (q.source_files or []):
            items.append((q.id, sf))

    def _fetch_from_disk(quote_id: str, source_file: dict) -> bytes | None:
        """Intenta leer el PDF del disco local. Archivos viven en
        `OUTPUT_DIR/{quote_id}/sources/{filename}`."""
        filename = source_file.get("filename")
        if not filename:
            return None
        path = Path(OUTPUT_DIR) / quote_id / "sources" / filename
        try:
            if path.exists() and path.is_file():
                return path.read_bytes()
        except Exception:
            return None
        return None

    summary = analyze_source_files(items, _fetch_from_disk)
    return summary


# ── ADMIN: Backfill Drive URLs for existing quotes ───────────────────────────

@router.post("/admin/backfill-drive")
async def backfill_drive(db: AsyncSession = Depends(get_db)):
    """Regenerate PDF/Excel and upload to Drive for quotes missing drive_pdf_url.

    Safe: reads from existing quote_breakdown, regenerates docs, uploads to Drive.
    Does NOT recalculate anything. Idempotent — skips quotes that already have Drive URLs.
    """
    from app.modules.agent.tools.document_tool import generate_documents
    from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
    from app.core.static import OUTPUT_DIR

    # Find quotes that are validated but missing Drive URLs
    from sqlalchemy import or_ as _or
    result = await db.execute(
        select(Quote).where(
            Quote.status.in_(["validated", "sent"]),
            Quote.drive_pdf_url.is_(None),
            Quote.quote_breakdown.isnot(None),
            # Skip building children — they get handled via parent
            _or(Quote.quote_kind != "building_child_material", Quote.quote_kind.is_(None)),
        )
    )
    quotes = result.scalars().all()
    logging.info(f"[backfill-drive] Found {len(quotes)} quotes to backfill")

    results = []
    for q in quotes:
        bd = q.quote_breakdown
        if not bd or not bd.get("ok", True):
            results.append({"id": q.id, "status": "skipped", "reason": "no valid breakdown"})
            continue

        try:
            # Regenerate docs from breakdown
            doc_result = await generate_documents(q.id, bd)
            if not doc_result.get("ok"):
                results.append({"id": q.id, "status": "error", "reason": f"generate failed: {doc_result.get('error', '')[:100]}"})
                continue

            # Upload each file to Drive
            drive_pdf = None
            drive_excel = None
            subfolder = q.client_name or ""

            for url_key, kind in [("pdf_url", "pdf"), ("excel_url", "excel")]:
                local_url = doc_result.get(url_key)
                if not local_url:
                    continue
                local_path = str(OUTPUT_DIR / local_url.replace("/files/", "", 1))
                try:
                    dr = await upload_single_file_to_drive(local_path, subfolder)
                    if dr.get("ok"):
                        if kind == "pdf":
                            drive_pdf = dr["drive_url"]
                        else:
                            drive_excel = dr["drive_url"]
                except Exception as e:
                    logging.warning(f"[backfill] Drive upload failed for {q.id} {kind}: {e}")

            # Update quote
            update_vals = {
                "pdf_url": doc_result.get("pdf_url"),
                "excel_url": doc_result.get("excel_url"),
            }
            if drive_pdf:
                update_vals["drive_pdf_url"] = drive_pdf
                update_vals["drive_url"] = drive_pdf
            if drive_excel:
                update_vals["drive_excel_url"] = drive_excel

            # Build files_v2
            files_v2_items = []
            mat_label = (q.material or "").replace(" ", "_").lower()[:30]
            for kind, url in [("pdf", doc_result.get("pdf_url")), ("excel", doc_result.get("excel_url"))]:
                if url:
                    item = {
                        "kind": kind,
                        "scope": "self",
                        "owner_quote_id": q.id,
                        "file_key": f"{mat_label}:{kind}",
                        "filename": url.split("/")[-1],
                        "local_url": url,
                        "local_path": str(OUTPUT_DIR / url.replace("/files/", "", 1)),
                    }
                    if kind == "pdf" and drive_pdf:
                        item["drive_url"] = drive_pdf
                        item["drive_download_url"] = drive_pdf.replace("/view", "/export?format=pdf") if "/view" in drive_pdf else drive_pdf
                    elif kind == "excel" and drive_excel:
                        item["drive_url"] = drive_excel
                        item["drive_download_url"] = drive_excel
                    files_v2_items.append(item)

            if files_v2_items:
                bd_copy = dict(bd)
                bd_copy["files_v2"] = {"items": files_v2_items}
                update_vals["quote_breakdown"] = bd_copy

            await db.execute(update(Quote).where(Quote.id == q.id).values(**update_vals))
            await db.commit()

            results.append({
                "id": q.id,
                "client": q.client_name,
                "material": q.material,
                "status": "ok",
                "drive_pdf": bool(drive_pdf),
                "drive_excel": bool(drive_excel),
            })
            logging.info(f"[backfill] {q.id} ({q.client_name} / {q.material}): pdf={bool(drive_pdf)}, excel={bool(drive_excel)}")

        except Exception as e:
            logging.error(f"[backfill] Failed for {q.id}: {e}", exc_info=True)
            results.append({"id": q.id, "status": "error", "reason": str(e)[:200]})

    return {"total": len(quotes), "results": results}


# ── ZONE SELECT — operator draws rectangle on plan page ───────────────────────

from pydantic import BaseModel as _BaseModel


class ZoneSelectRequest(_BaseModel):
    bbox_normalized: dict  # {x1, y1, x2, y2} in 0-1 range
    page_num: int = 1


@router.post("/quotes/{quote_id}/zone-select")
async def zone_select(
    quote_id: str,
    body: ZoneSelectRequest,
    db: AsyncSession = Depends(get_db),
):
    """Receive operator's rectangle selection on a plan page.

    Converts normalized bbox to pixels, persists as selected_zone
    and zone_default for subsequent pages.
    """
    import logging
    from PIL import Image as _PILImage
    from app.modules.quote_engine.visual_quote_builder import normalize_bbox_to_pixels

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    bd = quote.quote_breakdown or {}

    # Read real image dimensions from disk
    from app.core.static import OUTPUT_DIR
    img_path = OUTPUT_DIR / quote_id / f"page_{body.page_num}.jpg"
    if img_path.exists():
        with _PILImage.open(img_path) as img:
            real_w, real_h = img.size
    else:
        logging.warning(f"[zone-select] Image not found at {img_path}, using fallback 1200x1200")
        real_w, real_h = 1200, 1200

    bbox_px = normalize_bbox_to_pixels(body.bbox_normalized, real_w, real_h)
    logging.info(f"[zone-select] Quote {quote_id}: bbox_normalized={body.bbox_normalized} → bbox_px={bbox_px} (image {real_w}×{real_h})")

    # Persist as selected zone + zone_default
    page_key = str(body.page_num)
    page_data = bd.get("page_data", {})
    pd = page_data.get(page_key, {})
    pd["selected_zone"] = {
        "name": "OPERADOR_SELECTION",
        "bbox": bbox_px,
        "view_type": "top_view",
        "confidence": 1.0,
        "source": "operator_rectangle",
    }
    page_data[page_key] = pd
    bd["page_data"] = page_data
    bd["zone_default"] = "OPERADOR_SELECTION"
    bd["zone_default_bbox"] = bbox_px
    bd["building_step"] = f"visual_page_{body.page_num}"

    await db.execute(
        update(Quote).where(Quote.id == quote_id).values(quote_breakdown=bd)
    )
    await db.commit()

    return {"ok": True, "bbox_px": bbox_px, "image_size": [real_w, real_h]}


@router.post("/quotes/{quote_id}/dual-read-retry")
async def dual_read_retry(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Operator-triggered second pass with Opus when measurements don't match.

    Called from DualReadResult component when operator clicks
    'Las medidas no coinciden' button. Uses the saved crop to call Opus
    and reconcile with the previously saved Sonnet result.
    """
    import logging
    from app.modules.quote_engine.dual_reader import _call_vision, reconcile, _check_m2
    from app.core.config import settings
    from app.modules.agent.tools.catalog_tool import get_ai_config

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    bd = quote.quote_breakdown or {}
    prev_result = bd.get("dual_read_result")
    if not prev_result:
        raise HTTPException(status_code=400, detail="No prior dual read result found")

    crop_path = prev_result.get("_crop_path")
    if not crop_path:
        raise HTTPException(status_code=400, detail="Crop not saved — cannot retry")

    import os
    if not os.path.exists(crop_path):
        raise HTTPException(status_code=400, detail="Crop file missing on disk")

    with open(crop_path, "rb") as f:
        crop_bytes = f.read()

    # Call Opus directly. Timeout alto porque Opus vision toma 60-90s para
    # planos con mucho vector/detalle. El operador disparó esto a propósito,
    # ok hacerlo esperar.
    opus_model = get_ai_config().get("opus_model", "claude-opus-4-6")
    _opus_timeout = int(get_ai_config().get("opus_retry_timeout_seconds", 120))
    logging.info(
        f"[dual-read-retry] Quote {quote_id}: calling Opus for second opinion "
        f"(timeout={_opus_timeout}s)"
    )
    opus_result = await _call_vision(crop_bytes, opus_model, timeout=_opus_timeout)

    if opus_result.get("error"):
        # Antes: 500 → frontend mostraba "Error" y perdía el contexto.
        # Ahora: 200 con flag de error + la card previa de Sonnet intacta.
        # El frontend ve opus_error y muestra mensaje amigable sin romper
        # la card que ya tenía.
        logging.warning(
            f"[dual-read-retry] Opus failed for {quote_id}: {opus_result['error']}"
        )
        graceful = dict(prev_result)
        graceful["opus_error"] = opus_result["error"]
        graceful["_retry"] = True
        return graceful

    # Retrieve original Sonnet result (saved as _sonnet_raw in prev result)
    sonnet_raw = prev_result.get("_sonnet_raw")
    planilla_m2 = bd.get("dual_read_planilla_m2")

    if sonnet_raw:
        # Reconcile Opus with original Sonnet
        new_result = reconcile(opus_result, sonnet_raw)
        new_result["source"] = "DUAL"
    else:
        # No original Sonnet raw — just return Opus alone
        from app.modules.quote_engine.dual_reader import _build_single_result
        new_result = _build_single_result(opus_result, "SOLO_OPUS")

    new_result["m2_warning"] = _check_m2(new_result, planilla_m2)
    new_result["_crop_path"] = crop_path
    new_result["_retry"] = True

    # Save updated result
    bd["dual_read_result"] = new_result
    await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=bd))
    await db.commit()

    logging.info(f"[dual-read-retry] Quote {quote_id}: Opus retry complete, source={new_result['source']}")
    return new_result


# ── CHAT — SSE STREAMING ──────────────────────────────────────────────────────

@router.post("/quotes/{quote_id}/chat")
async def chat(
    quote_id: str,
    request: Request,
    message: str = Form(...),
    plan_files: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_db),
):
    from app.main import touch_chat_activity
    from app.modules.agent._trace import log_http_enter
    touch_chat_activity()

    # PR #385 — traza del request HTTP entrante al chat. Lo primero que
    # vemos en el log cuando se dispara un turn del agente.
    log_http_enter(
        quote_id,
        "POST /quotes/:id/chat",
        message_preview=(message or "")[:200].replace("\n", " "),
        plan_files=len(plan_files or []),
    )
    # Audit: chat.message_sent — punto canónico único.
    # Phase 2: en modo debug global, capturamos el texto del brief
    # completo para reproducir bugs de interpretación. Sin debug,
    # solo metadata (largo + cantidad de archivos).
    await log_event(
        db, event_type="chat.message_sent", source="router",
        summary=f"Operator sent chat message ({len(message or '')} chars, {len(plan_files or [])} files)",
        request=request, quote_id=quote_id,
        payload={"message_chars": len(message or ""), "plan_files_count": len(plan_files or [])},
        debug_only_payload={"message_text": message or ""},
    )

    # Budget check — read DIRECTLY from DB (not cached config — multi-worker cache stale)
    try:
        from sqlalchemy import text as sql_text
        monthly_limit = 300
        hard_limit = True
        _budget_result = await db.execute(sql_text("SELECT content FROM catalogs WHERE name = 'config'"))
        _budget_row = _budget_result.first()
        if _budget_row and _budget_row[0]:
            import json as _budget_json
            _budget_val = _budget_row[0]
            _budget_cfg = _budget_json.loads(_budget_val) if isinstance(_budget_val, str) else _budget_val
            _budget_ai = _budget_cfg.get("ai_engine", {})
            monthly_limit = _budget_ai.get("monthly_budget_usd", 300)
            hard_limit = _budget_ai.get("enable_hard_limit", True)
        if hard_limit and monthly_limit > 0:
            month_start = __import__("datetime").datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            spent_result = await db.execute(
                sql_text("SELECT COALESCE(SUM(cost_usd), 0) FROM token_usage WHERE created_at >= :start"),
                {"start": month_start},
            )
            spent = spent_result.scalar() or 0
            if spent >= monthly_limit:
                raise HTTPException(status_code=429, detail=f"Límite mensual de API alcanzado (${spent:.2f} de ${monthly_limit:.2f}). Contactá al administrador.")
    except HTTPException:
        raise
    except Exception as e:
        logging.warning(f"Budget check failed: {e}")

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Validate and read uploaded files
    from pathlib import Path
    from datetime import datetime
    from app.modules.agent.tools.plan_tool import save_plan_to_temp

    validated_files: list[tuple[bytes, str]] = []  # (bytes, filename)
    errors: list[str] = []

    if len(plan_files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_FILES} archivos por mensaje")

    for pf in plan_files:
        if not pf.filename:
            continue
        # Sanitize filename — strip directory traversal (../ etc.)
        safe_filename = Path(pf.filename).name
        if not safe_filename:
            continue
        # Validate MIME type
        content_type = pf.content_type or ""
        if content_type not in ALLOWED_MIME_TYPES:
            errors.append(f"'{safe_filename}' — tipo no soportado ({content_type}). Solo PDF, JPG, PNG, WEBP.")
            continue
        # Read and validate size
        file_bytes = await pf.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            errors.append(f"'{safe_filename}' — excede 10MB ({len(file_bytes) / 1048576:.1f}MB)")
            continue
        validated_files.append((file_bytes, safe_filename))

        # Save to temp for read_plan tool
        save_plan_to_temp(safe_filename, file_bytes)

        # Persist source file for download
        from app.core.static import OUTPUT_DIR as _OUT
        sources_dir = _OUT / quote_id / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / safe_filename).write_bytes(file_bytes)

        # Upload source file to Drive for durable storage
        source_drive_info = {}
        try:
            from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
            local_source_path = str(sources_dir / safe_filename)
            dr = await upload_single_file_to_drive(local_source_path, "Archivos Origen")
            if dr.get("ok"):
                source_drive_info = {
                    "drive_file_id": dr["file_id"],
                    "drive_url": dr["drive_url"],
                    "drive_download_url": dr["drive_download_url"],
                }
        except Exception as e:
            logging.warning(f"Drive upload of source file failed: {e}")

        # Update DB with source file metadata
        existing_files = quote.source_files or []
        if not any(f["filename"] == safe_filename for f in existing_files):
            existing_files.append({
                "filename": safe_filename,
                "type": content_type,
                "size": len(file_bytes),
                "url": f"/files/{quote_id}/sources/{safe_filename}",
                "uploaded_at": datetime.now().isoformat(),
                **source_drive_info,
            })
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(source_files=existing_files)
            )

            # Also persist in files_v2 for Drive-first resolution
            bd = quote.quote_breakdown or {}
            fv2 = bd.get("files_v2", {"items": []})
            fv2["items"].append({
                "kind": "source",
                "scope": "parent",
                "file_key": "parent:source",
                "filename": safe_filename,
                "local_path": str(sources_dir / safe_filename),
                "local_url": f"/files/{quote_id}/sources/{safe_filename}",
                **({f"drive_{k}": v for k, v in source_drive_info.items()} if source_drive_info else {}),
            })
            bd["files_v2"] = fv2

            # Una subida de archivo nueva INVALIDA cualquier lectura previa:
            # el operador está presentando un plano (quizás el mismo, quizás
            # distinto) y espera ver la card de dual_read. Si dejamos
            # dual_read_result / verified_measurements del turno anterior,
            # el skip check los interpreta como "ya confirmado" y la card
            # nunca aparece.
            for _stale_key in ("dual_read_result", "verified_measurements",
                               "verified_context", "dual_read_planilla_m2",
                               "dual_read_crop_label", "measurements_confirmed"):
                bd.pop(_stale_key, None)

            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=bd)
            )
            await db.commit()

    if errors:
        raise HTTPException(status_code=400, detail=" | ".join(errors))

    # ── RESTAURAR archivo guardado si este mensaje no trae uno ──────────────
    # El PDF/imagen del plano NO debe perderse entre mensajes: una vez que
    # el operador subió el plano, queda disponible en todas las requests
    # siguientes. Recuperamos el más reciente desde source_files si este
    # mensaje no adjuntó nada nuevo.
    #
    # EXCEPCIÓN: [SYSTEM_TRIGGER:*] tienen handlers propios que no necesitan
    # el plano. [DUAL_READ_CONFIRMED] SÍ necesita restauración — Claude en
    # Paso 2 necesita el plano + planilla (material, pileta, ubicación) o
    # alucina el material. La skip-lógica del dual_read check previene la
    # re-emisión de la card.
    _is_system_trigger_only = message.startswith("[SYSTEM_TRIGGER:")
    if not validated_files and quote.source_files and not _is_system_trigger_only:
        from app.core.static import OUTPUT_DIR as _OUT_RE
        # Tomamos el archivo más reciente (último en la lista)
        for _sf in reversed(quote.source_files):
            _sf_name = _sf.get("filename", "")
            _sf_type = (_sf.get("type") or "").lower()
            _is_plan = (
                _sf_name.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".webp"))
                or _sf_type.startswith(("application/pdf", "image/"))
            )
            if not _is_plan:
                continue
            _sf_path = _OUT_RE / quote_id / "sources" / _sf_name
            try:
                if _sf_path.exists():
                    _bytes = _sf_path.read_bytes()
                    validated_files.append((_bytes, _sf_name))
                    logging.info(
                        f"[chat] Restoring saved plan {_sf_name} "
                        f"({len(_bytes)} bytes) for quote {quote_id}"
                    )
                    break
            except Exception as e:
                logging.warning(f"[chat] Failed to restore {_sf_name}: {e}")

    # ── GATE: planos multi-página bloqueantes (fase 2/3) ────────────────────
    # Por ahora solo se soportan planos de 1 página (PDF) o imágenes sueltas.
    # Si llega un PDF de 2+ páginas, no procesamos y avisamos al operador.
    _gate_multipage_msg = None
    for _fbytes, _fname in validated_files:
        if _fname.lower().endswith(".pdf"):
            try:
                import pdfplumber as _pp
                import io as _io
                with _pp.open(_io.BytesIO(_fbytes)) as _pdf:
                    _n_pages = len(_pdf.pages)
                if _n_pages > 1:
                    _gate_multipage_msg = (
                        f"El PDF **{_fname}** tiene {_n_pages} páginas. "
                        f"Por ahora solo se procesan planos de **1 página**. "
                        f"Si es un edificio o tiene varias tipologías, próximamente. "
                        f"Pasame un PDF de 1 página (o foto) del plano que querés cotizar."
                    )
                    break
            except Exception as e:
                logging.warning(f"[chat] page count failed for {_fname}: {e}")

    if _gate_multipage_msg:
        _files_note = ", ".join(vf[1] for vf in validated_files)
        _user_entry = {
            "role": "user",
            "content": (message or "") + (
                f"\n\n[archivos adjuntos: {_files_note}]" if _files_note else ""
            ),
        }
        _assistant_entry = {"role": "assistant", "content": _gate_multipage_msg}
        _updated = list(quote.messages or []) + [_user_entry, _assistant_entry]
        await db.execute(
            update(Quote).where(Quote.id == quote_id).values(messages=_updated)
        )
        await db.commit()

        async def _gate_mp_stream():
            yield f"data: {json.dumps({'type': 'text', 'content': _gate_multipage_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

        return StreamingResponse(
            _gate_mp_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # Pass ALL files to Claude (not just the first one)
    plan_bytes, plan_filename, extra_files = _pick_plan_and_extras(validated_files)

    async def event_stream():
        full_response = ""
        try:
            async for chunk in agent_service.stream_chat(
                quote_id=quote_id,
                messages=quote.messages,
                user_message=message,
                plan_bytes=plan_bytes,
                plan_filename=plan_filename,
                extra_files=extra_files,
                db=db,
                request=request,
            ):
                if chunk["type"] == "ping":
                    # SSE keepalive comment — prevents proxy timeout
                    yield ": keepalive\n\n"
                elif chunk["type"] == "text":
                    full_response += chunk["content"]
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "action":
                    # Tool use event (generating docs, uploading, etc.)
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "zone_selector":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "dual_read_result":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "context_analysis":
                    # PR G — card de análisis de contexto ANTES del despiece
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "done":
                    logging.info(f"[SSE] Sending done for quote {quote_id}")
                    yield f"data: {json.dumps(chunk)}\n\n"
                else:
                    logging.warning(f"[SSE] Unknown chunk type: {chunk.get('type')} for quote {quote_id}")
        except Exception as e:
            logging.error(f"SSE stream error for quote {quote_id}: {e}", exc_info=True)
            error_chunk = {"type": "error", "content": f"⚠️ Error inesperado: {str(e)[:200]}. Intentá de nuevo."}
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': '', 'error': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Sprint 4 audit-trail-copy ──────────────────────────────────────────
# GET /api/quotes/{id}/audit-log
# Agrega 3 tablas (audit_events + token_usage + Quote.quote_breakdown)
# en una sola respuesta · destinada al botón "Copiar audit" del topbar +
# página /quotes/{id}/audit para debug/iteración rápida.

_AUDIT_EVENTS_DEFAULT_LIMIT = 200

@router.get("/quotes/{quote_id}/audit-log")
async def get_quote_audit_log(
    quote_id: str,
    request: Request,
    full: bool = Query(default=False, description="Si true, devuelve TODOS los eventos sin truncar"),
    limit: int = Query(default=_AUDIT_EVENTS_DEFAULT_LIMIT, ge=10, le=2000),
    db: AsyncSession = Depends(get_db),
):
    """Endpoint read-only que agrega todo el debugging-relevante de un quote:
    timeline de audit_events, suma de TokenUsage, tools agregados por nombre,
    chat duration derivada de timestamps, snapshot de quote_breakdown.

    `full=true` quita la truncation (default events_total > limit → trunca).
    Errores siempre se devuelven completos en `errors[]` aparte de `events[]`.
    """
    from app.modules.observability.models import AuditEvent
    from app.models.usage import TokenUsage
    from app.modules.agent.schemas import (
        AuditLogResponse,
        AuditLogMeta,
        AuditLogEventItem,
        AuditLogTokensSummary,
        AuditLogToolUsage,
    )
    from collections import defaultdict

    # ── Quote 404 check (patrón existente router.py:2146-2148)
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    # ── Eventos: orden ascendente por created_at (timeline natural)
    events_result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.quote_id == quote_id)
        .order_by(AuditEvent.created_at.asc())
    )
    all_events = list(events_result.scalars().all())
    events_total = len(all_events)
    # Truncation defensiva (debug mode puede generar >150 eventos por quote)
    events_truncated = (not full) and events_total > limit
    visible_events = all_events if full else all_events[:limit]

    # ── Errors (siempre completos · sin trunc)
    error_events = [e for e in all_events if not e.success]

    # ── TokenUsage aggregation
    token_result = await db.execute(
        select(TokenUsage).where(TokenUsage.quote_id == quote_id)
    )
    token_rows = list(token_result.scalars().all())
    tokens_summary = AuditLogTokensSummary(
        input_tokens=sum(t.input_tokens for t in token_rows),
        output_tokens=sum(t.output_tokens for t in token_rows),
        cache_read_tokens=sum(t.cache_read_tokens for t in token_rows),
        cache_write_tokens=sum(t.cache_write_tokens for t in token_rows),
        cost_usd=round(sum(t.cost_usd for t in token_rows), 4),
        iterations=sum(t.iterations for t in token_rows),
        models_used=sorted({t.model for t in token_rows if t.model}),
    )

    # ── Tools used: agregación por tool_name desde eventos agent.tool_result
    tools_agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_ms": 0, "errors": 0})
    for ev in all_events:
        if ev.event_type != "agent.tool_result":
            continue
        tool_name = (ev.payload or {}).get("tool_name") or "unknown"
        tools_agg[tool_name]["count"] += 1
        if ev.elapsed_ms:
            tools_agg[tool_name]["total_ms"] += ev.elapsed_ms
        if not ev.success:
            tools_agg[tool_name]["errors"] += 1
    tools_used = [
        AuditLogToolUsage(
            tool_name=name,
            count=data["count"],
            total_ms=data["total_ms"],
            error_count=data["errors"],
        )
        for name, data in sorted(tools_agg.items())
    ]

    # ── Chat duration derivada de timestamps (lección operativa #1.5
    # del bundle FASE 1): agent.stream_started → último tool_result
    # o quote.calculated, lo que ocurra después.
    chat_duration_ms: Optional[int] = None
    stream_start = next((e for e in all_events if e.event_type == "agent.stream_started"), None)
    if stream_start:
        # Sprint 4 audit-instrumentation-gap-fix: extendido con los terminators
        # de los fast-paths text-only y dual_read. Antes solo cubría el loop
        # agéntico (tool_result/calculated/docs.generated) → text-only y
        # dual_read quedaban con chat_duration_ms=None (CALLS section vacía
        # en el copy plain text). Ahora text_parse.completed y
        # context_analysis.pending y dual_read.completed también cuentan
        # como terminators legítimos de la "call".
        chat_ends = [
            e for e in all_events
            if e.event_type in {
                "agent.tool_result",
                "quote.calculated",
                "docs.generated",
                "text_parse.completed",
                "context_analysis.pending",
                "dual_read.completed",
            }
            and e.created_at >= stream_start.created_at
        ]
        if chat_ends:
            last_end = max(chat_ends, key=lambda e: e.created_at)
            delta = last_end.created_at - stream_start.created_at
            chat_duration_ms = int(delta.total_seconds() * 1000)

    # ── Input message (primer turno del operador) + plan_files derivados
    # del primer chat.message_sent + Quote.source_files (si existe)
    input_message: Optional[str] = None
    plan_files: list[str] = []
    first_chat = next((e for e in all_events if e.event_type == "chat.message_sent"), None)
    if first_chat and first_chat.payload:
        # En debug_only_payload puede venir el message_text; sino solo metadata.
        # No accedemos a debug_only_payload acá (sanitizer).
        pass
    if quote.messages:
        # Quote.messages es lista de {role, content, ...} · primer user message
        try:
            first_user = next(
                (m for m in quote.messages if isinstance(m, dict) and m.get("role") == "user"),
                None,
            )
            if first_user:
                # `content` puede venir como string (turns simples) o como
                # lista de bloques multimodales Anthropic
                # `[{"type":"text","text":"..."}, {"type":"image",...}]`.
                # `(lista)[:2000]` NO rompe — devuelve otra lista — y luego
                # Pydantic la rechaza (input_message: Optional[str]) → 500.
                # Coercionamos a string extrayendo solo los bloques `text`.
                raw = first_user.get("content")
                if isinstance(raw, list):
                    raw = " ".join(
                        b.get("text", "")
                        for b in raw
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                input_message = (raw or "")[:2000] if isinstance(raw, str) else None
        except Exception:
            pass
    if quote.source_files and isinstance(quote.source_files, list):
        plan_files = [
            (f.get("filename") or f.get("name") or "?")
            for f in quote.source_files
            if isinstance(f, dict)
        ][:20]

    # ── Build response
    meta = AuditLogMeta(
        quote_id=quote.id,
        status=quote.status.value if quote.status else "unknown",
        client_name=quote.client_name or None,
        project=quote.project or None,
        material=quote.material,
        total_ars=quote.total_ars,
        total_usd=quote.total_usd,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )

    response = AuditLogResponse(
        meta=meta,
        input_message=input_message,
        plan_files=plan_files,
        events=[AuditLogEventItem.model_validate(e) for e in visible_events],
        events_total=events_total,
        events_truncated=events_truncated,
        chat_duration_ms=chat_duration_ms,
        tokens=tokens_summary,
        tools_used=tools_used,
        quote_breakdown=quote.quote_breakdown,
        errors=[AuditLogEventItem.model_validate(e) for e in error_events],
    )

    # ── Log access (audit del propio audit · ironía controlada)
    await log_event(
        db,
        event_type="audit.log_fetched",
        source="router",
        summary=f"Audit log fetched for {quote_id} ({events_total} events, full={full})",
        request=request,
        quote_id=quote_id,
        payload={"events_total": events_total, "full": full, "errors_count": len(error_events)},
        commit=False,
    )

    return response
