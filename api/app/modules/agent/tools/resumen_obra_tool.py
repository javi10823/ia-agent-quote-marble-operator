"""Consolidated site summary ("resumen de obra") generation.

Builds a single PDF that consolidates N quotes of the same client + project,
attaches the generated file back to each quote's `resumen_obra` field, and
invalidates their email_draft cache so it regenerates on next read.

Invoked from the operator web dashboard after multi-select.
The chatbot flow is NOT affected.

Contract:
- Min 1, max 20 quotes
- All quotes must be status = validated
- All quotes must share client_name (case-insensitive, trimmed)
- Notes: optional, max 1000 chars, sanitized for PDF
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.static import OUTPUT_DIR
from app.models.quote import Quote, QuoteStatus


MAX_QUOTES = 20
MAX_NOTES_LEN = 1000


class ResumenObraError(Exception):
    """Validation / generation error with user-safe message."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def _sanitize_notes(raw: str | None) -> str:
    """Trim, strip control chars, cap length. Never raises."""
    if not raw:
        return ""
    s = str(raw).strip()
    if len(s) > MAX_NOTES_LEN:
        raise ResumenObraError(400, f"Las notas superan {MAX_NOTES_LEN} caracteres.")
    # Drop ASCII control chars (except \n and \t)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    return s


def _normalize_client(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _validate_quotes(
    quotes: list[Quote],
    requested_ids: list[str],
    force_same_client: bool = False,
) -> None:
    """Raise ResumenObraError on any contract violation.

    Client-name matching is layered:
      1. Exact normalized match (old strict behavior).
      2. Else fuzzy match via client_match.are_fuzzy_same_client — covers
         variants like "Estudio MUNGE" vs "Munge".
      3. Else, if force_same_client=True, the operator explicitly confirmed
         they are the same client → allow anyway.
    """
    from app.modules.agent.tools.client_match import are_fuzzy_same_client

    found_ids = {q.id for q in quotes}
    missing = [qid for qid in requested_ids if qid not in found_ids]
    if missing:
        raise ResumenObraError(404, f"Presupuestos no encontrados: {missing}")

    non_validated = [
        q.id for q in quotes if q.status != QuoteStatus.VALIDATED
    ]
    if non_validated:
        raise ResumenObraError(
            400,
            f"Todos los presupuestos deben estar validados. "
            f"No validados: {non_validated}",
        )

    if len(quotes) <= 1:
        return

    anchor_name = quotes[0].client_name
    normalized_anchor = _normalize_client(anchor_name)
    distinct_raw: set[str] = {anchor_name or ""}
    fuzzy_ok = True
    for q in quotes[1:]:
        distinct_raw.add(q.client_name or "")
        if _normalize_client(q.client_name) == normalized_anchor:
            continue
        if are_fuzzy_same_client(q.client_name, anchor_name):
            continue
        fuzzy_ok = False

    if fuzzy_ok:
        return
    if force_same_client:
        return
    raise ResumenObraError(
        400,
        "Todos los presupuestos deben ser del mismo cliente. "
        f"Detectados: {sorted(distinct_raw)}. "
        "Si confirmás que son el mismo, reintentá con force_same_client=true.",
    )


def _collect_material_row(q: Quote) -> dict[str, Any] | None:
    """Flatten a quote's calc into a single material row for the summary.

    Returns None if the quote has no usable calc data (fail-soft: the quote
    contributes to client totals but not to the material breakdown).
    """
    bd = q.quote_breakdown or {}
    if not isinstance(bd, dict):
        return None

    # Edificios: calc_results keyed by material name
    calc_results = bd.get("calc_results") or {}
    if isinstance(calc_results, dict) and calc_results:
        # Operator-web quotes are 1 material per PR #145 rule, but legacy or
        # chatbot quotes may have several. Emit one row per material.
        rows = []
        for mat_name, mr in calc_results.items():
            if not isinstance(mr, dict) or not mr.get("ok"):
                continue
            rows.append({
                "name": mr.get("catalog_name", mat_name),
                "m2": mr.get("m2", 0),
                "currency": mr.get("currency", "USD"),
                "price_unit": mr.get("price_unit", 0),
                "subtotal": mr.get("material_total", 0),
                "discount_pct": mr.get("discount_pct", 0),
                "discount_amount": mr.get("discount_amount", 0),
                "net": mr.get("material_net", 0),
            })
        return {"rows": rows}

    # Standard residential: single material flat fields on breakdown
    mat_name = bd.get("material_name") or q.material or ""
    m2 = bd.get("material_m2") or 0
    price = bd.get("material_price_unit") or 0
    cur = bd.get("material_currency") or "USD"
    disc_pct = bd.get("discount_pct") or 0
    if m2 and price and mat_name:
        subtotal = round(m2 * price)
        disc_amount = round(subtotal * disc_pct / 100) if disc_pct else 0
        return {
            "rows": [{
                "name": mat_name,
                "m2": m2,
                "currency": cur,
                "price_unit": price,
                "subtotal": subtotal,
                "discount_pct": disc_pct,
                "discount_amount": disc_amount,
                "net": subtotal - disc_amount,
            }]
        }
    return None


def _build_resumen_data(
    quotes: list[Quote], notes: str
) -> dict[str, Any]:
    """Shape the dict expected by _generate_resumen_obra_pdf from N quotes."""
    # PR #17 — nombre canónico del cliente: usar el MÁS CORTO del grupo.
    # Cuando el dashboard agrupa variantes como "Estudio 72" y
    # "Estudio 72 — Fideicomiso Ventus" (mismo cliente, nombre largo con
    # proyecto embebido), el PDF del resumen usa la forma "núcleo" para
    # que el cliente lo vea consistente. Si hay empate de longitud, cae
    # al que aparece primero (determinístico por orden de entrada).
    _candidates = [q.client_name.strip() for q in quotes if (q.client_name or "").strip()]
    client_name = min(_candidates, key=len) if _candidates else ""
    project = next((q.project for q in quotes if q.project), "")

    material_rows: list[dict] = []
    material_names: list[str] = []
    mo_items_all: list[dict] = []
    # Bug 1 fix: track seen MO keys to deduplicate identical items across quotes.
    # MO represents physical work (material-independent), so when 3 quotes share
    # the same labor it should appear once, not 3x.
    mo_seen: set[tuple] = set()
    total_mat_ars = 0
    total_mat_usd = 0
    grand_total_ars = 0
    grand_total_usd = 0
    # Bug 4 fix: collect plazo from all quotes, pick most specific.
    plazo_candidates: list[str] = []

    for q in quotes:
        info = _collect_material_row(q) or {}
        for row in info.get("rows", []):
            material_rows.append(row)
            material_names.append(row["name"])
            if row["currency"] == "ARS":
                total_mat_ars += row["net"]
            else:
                total_mat_usd += row["net"]

        bd = q.quote_breakdown or {}
        if isinstance(bd, dict):
            for mo in bd.get("mo_items") or []:
                desc = mo.get("description") or mo.get("desc", "")
                qty = mo.get("quantity") or mo.get("qty", 1)
                price = mo.get("unit_price") or mo.get("price", 0)
                # Bug 3 fix: use persisted total from the individual quote's
                # mo_items instead of recalculating price * qty, which can
                # produce rounding differences (e.g. $62,119 vs $61,939).
                total = mo.get("total", 0)
                key = (desc, qty, price)
                if key not in mo_seen:
                    mo_seen.add(key)
                    mo_items_all.append({
                        "desc": desc,
                        "qty": qty,
                        "price": price,
                        "total": total,
                    })
            # Bug 4: collect plazo
            _plazo = bd.get("delivery_days") or bd.get("plazo") or ""
            if isinstance(_plazo, str) and _plazo.strip():
                plazo_candidates.append(_plazo.strip())

        grand_total_ars += q.total_ars or 0
        grand_total_usd += q.total_usd or 0

    # Bug 2 fix: compute mo_total from the deduplicated items, not from
    # summing each quote's mo_total (which would triple-count).
    mo_total = sum(item["total"] for item in mo_items_all)

    # Bug 4 fix: prefer the most specific plazo — skip "A confirmar" if
    # there's a concrete value like "40 dias".
    _VAGUE_PLAZOS = {"a confirmar", ""}
    specific = [p for p in plazo_candidates if p.lower() not in _VAGUE_PLAZOS]
    plazo = specific[0] if specific else (plazo_candidates[0] if plazo_candidates else "")

    return {
        "client_name": client_name,
        "project": project,
        "materials": material_rows,
        "material_names": sorted(set(material_names)),
        "mo_items": mo_items_all,
        "mo_total": mo_total,
        "plazo": plazo,
        "total_mat_ars": total_mat_ars,
        "total_mat_usd": total_mat_usd,
        "grand_total_ars": grand_total_ars,
        "grand_total_usd": grand_total_usd,
        "notes": notes,
    }


def _safe_filename(client_name: str, project: str) -> str:
    base = f"{client_name} - {project} - Resumen Obra".strip()
    base = re.sub(r"[/\\:*?\"<>|]", "-", base)
    date_str = datetime.now().strftime("%d.%m.%Y")
    return f"{base} - {date_str}.pdf"


async def _upload_to_drive_safe(pdf_path: Path, subfolder: str) -> dict:
    """Upload wrapper that returns {} on failure instead of raising."""
    try:
        from app.modules.agent.tools.drive_tool import (
            upload_single_file_to_drive,
        )
        r = await upload_single_file_to_drive(str(pdf_path), subfolder)
        if r.get("ok"):
            return {
                "file_id": r.get("file_id"),
                "drive_url": r.get("drive_url"),
                "drive_download_url": r.get("drive_download_url"),
            }
    except Exception as e:
        logging.warning(f"[resumen-obra] Drive upload failed: {e}")
    return {}


async def generate_resumen_obra(
    db: AsyncSession,
    quote_ids: list[str],
    notes_raw: str | None,
    force_same_client: bool = False,
) -> dict:
    """Validate, generate PDF, upload, persist — atomic-ish.

    Returns { pdf_url, drive_url (optional), quote_ids, generated_at,
              client_name, project, notes }.

    Raises ResumenObraError on contract violations. Drive upload failure does
    NOT raise — it just means drive_url is absent; the local PDF is still
    generated and persisted.
    """
    if not isinstance(quote_ids, list) or not quote_ids:
        raise ResumenObraError(400, "quote_ids no puede estar vacío.")
    if len(quote_ids) > MAX_QUOTES:
        raise ResumenObraError(
            400, f"Máximo {MAX_QUOTES} presupuestos por resumen."
        )
    # Dedup + preserve order
    seen: set[str] = set()
    deduped = [q for q in quote_ids if not (q in seen or seen.add(q))]

    notes = _sanitize_notes(notes_raw)

    # Load quotes
    result = await db.execute(select(Quote).where(Quote.id.in_(deduped)))
    quotes = list(result.scalars().all())
    _validate_quotes(quotes, deduped, force_same_client=force_same_client)

    # Order quotes to match requested order for deterministic output
    by_id = {q.id: q for q in quotes}
    quotes = [by_id[qid] for qid in deduped]

    data = _build_resumen_data(quotes, notes)

    # Output dir: use the first quote's folder as anchor
    anchor_id = deduped[0]
    out_dir = OUTPUT_DIR / anchor_id
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(data["client_name"], data["project"])
    pdf_path = out_dir / filename

    # Generate PDF (import late to avoid circular)
    from app.modules.agent.tools.document_tool import (
        _generate_resumen_obra_pdf,
    )
    await asyncio.to_thread(_generate_resumen_obra_pdf, pdf_path, data)

    # Upload to Drive (non-fatal)
    drive_info = await _upload_to_drive_safe(
        pdf_path, data["client_name"] or "Sin cliente"
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    pdf_url = f"/files/{anchor_id}/{filename}"
    drive_url = drive_info.get("drive_url") or None

    record = {
        "pdf_url": pdf_url,
        "drive_url": drive_url,
        "drive_file_id": drive_info.get("file_id"),
        "notes": notes,
        "generated_at": generated_at,
        "quote_ids": deduped,
        "client_name": data["client_name"],
        "project": data["project"],
    }

    # PR #18 — normalizar client_name en DB al nombre canónico del resumen.
    # Antes: el dashboard mostraba variantes distintas ("Estudio 72" vs
    # "Estudio 72 — Fideicomiso Ventus") aunque todas pertenecían al mismo
    # cliente consolidado. Ahora todos los presupuestos del grupo quedan
    # con el mismo client_name → lista unificada + menos confusión.
    canonical_name = data["client_name"]

    # Persist: attach record to each quote; invalidate email_draft; unify name.
    for qid in deduped:
        _values: dict = {"resumen_obra": record, "email_draft": None}
        if canonical_name:
            _values["client_name"] = canonical_name
        await db.execute(
            update(Quote)
            .where(Quote.id == qid)
            .values(**_values)
        )
    await db.commit()

    return record
