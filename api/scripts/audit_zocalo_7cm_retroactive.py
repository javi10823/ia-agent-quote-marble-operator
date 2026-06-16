"""Auditoría retroactiva · sprint-4/zocalo-config-unification (bug zócalo 7cm).

Identifica quotes que pudieron quedar afectados por el bug del zócalo de 7cm:
el agent leía `default_zocalo_height` del bloque `ai_engine.*` (donde la key
no existe) → caía SIEMPRE al fallback hardcodeado 0.07 → cuando el brief NO
especificaba alto de zócalo, se aplicaron 7cm en vez del default master 5cm.
Sobre-cobro ≈ 40% en el m² del zócalo (material; la MO de zócalo, si aplica,
se reporta aparte como nota · NO se suma al diff por defecto).

HEURÍSTICA de detección (read-only · no hay forma 100% de saber si el brief
especificó zócalo desde el breakdown):
  - Se escanean los labels de piezas del breakdown (`sectors[].pieces[]`)
    buscando zócalos (`"<ml>ML X <alto> ZOC"`).
  - Se marca AFECTADO si algún zócalo tiene alto == 0.07 (fingerprint del
    fallback · el master es 0.05 · 7cm explícito en brief es raro).
  - Cada fila queda para revisión manual de Javi/Agos antes de cualquier
    acción comercial (la columna `nota_heuristica` lo recuerda).

Fórmula del exceso (material):
    extra_m2 = sum(ml_zocalo) × (0.07 − 0.05)
    diff_financiero = round(extra_m2 × material_price_unit)   [en la moneda del quote]

READ-ONLY · solo SELECT · NO modifica NADA en la DB. `--dry-run` imprime
resumen sin escribir CSV.

Uso:
    cd api
    python -m scripts.audit_zocalo_7cm_retroactive --dry-run
    python -m scripts.audit_zocalo_7cm_retroactive --since 2026-04-01
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quote import Quote, QuoteStatus

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

DEFAULT_SINCE = "2026-04-01"  # repo init · pre-agent no existe nada
MASTER_ZOCALO = 0.05
BUG_ZOCALO = 0.07

# Label de zócalo del calculator: f"{largo:.2f}ML X {dim2:.2f} ZOC"
_ZOC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ML\s*X\s*(\d+\.\d+)\s*ZOC", re.IGNORECASE)


def _iter_piece_labels(bd: dict):
    """Yield los labels de pieza (string) de todos los sectores del breakdown."""
    for sector in bd.get("sectors") or []:
        for piece in sector.get("pieces") or []:
            if isinstance(piece, str):
                yield piece
            elif isinstance(piece, dict):
                yield str(piece.get("label", ""))


def _extract_zocalos_7cm(bd: dict) -> list[tuple[float, float]]:
    """Devuelve [(ml, alto)] de zócalos con alto == 0.07 (fingerprint del bug)."""
    found = []
    for label in _iter_piece_labels(bd):
        for m in _ZOC_RE.finditer(label):
            ml = float(m.group(1))
            alto = round(float(m.group(2)), 2)
            if alto == BUG_ZOCALO:
                found.append((ml, alto))
    return found


def _pdf_emitido(quote: Quote) -> tuple[bool, str]:
    """(emitido_al_cliente, fecha_emision_iso) · best-effort."""
    emitido = quote.status == QuoteStatus.SENT or bool(quote.pdf_url) or bool(quote.drive_pdf_url)
    fecha = ""
    ro = quote.resumen_obra if isinstance(quote.resumen_obra, dict) else None
    if ro and ro.get("generated_at"):
        fecha = str(ro["generated_at"])
    return emitido, fecha


def audit(*, since: str, dry_run: bool) -> int:
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
    cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    engine = create_engine(sync_url)
    log.info(
        "Audit zócalo 7cm · universo: created_at >= %s · zócalos con alto==0.07 "
        "(fingerprint del fallback) · READ-ONLY", since,
    )

    rows: list[dict] = []
    with Session(engine) as session:
        stmt = select(Quote).where(Quote.created_at >= cutoff)
        for quote in session.scalars(stmt):
            bd = quote.quote_breakdown
            if not isinstance(bd, dict):
                continue
            zocs = _extract_zocalos_7cm(bd)
            if not zocs:
                continue
            total_ml = round(sum(ml for ml, _ in zocs), 2)
            if total_ml <= 0:
                continue
            price_unit = float(bd.get("material_price_unit") or 0)
            currency = (bd.get("material_currency") or "ARS").upper()
            m2_zocalo = round(total_ml * BUG_ZOCALO, 2)
            extra_m2 = total_ml * (BUG_ZOCALO - MASTER_ZOCALO)
            diff_financiero = int(round(extra_m2 * price_unit))
            monto_total = quote.total_usd if currency == "USD" else quote.total_ars
            emitido, fecha_emision = _pdf_emitido(quote)
            rows.append({
                "quote_id": quote.id,
                "client_name": quote.client_name,
                "project": quote.project,
                "fecha_creacion": quote.created_at.isoformat() if quote.created_at else "",
                "fecha_emision_pdf": fecha_emision,
                "status": quote.status.value if hasattr(quote.status, "value") else str(quote.status),
                "pdf_emitido_cliente": "SI" if emitido else "no",
                "currency": currency,
                "monto_total": int(monto_total) if monto_total else 0,
                "ml_zocalo_total": total_ml,
                "m2_zocalo": m2_zocalo,
                "diff_financiero_material": diff_financiero,
                "nota_heuristica": "Revisar brief: confirmar que NO especificaba alto de zócalo antes de refacturar",
            })

    rows.sort(key=lambda r: r["diff_financiero_material"], reverse=True)
    total_diff = sum(r["diff_financiero_material"] for r in rows)
    emitidos = [r for r in rows if r["pdf_emitido_cliente"] == "SI"]

    log.info("Quotes afectados (heurística): %d · de los cuales emitidos al cliente: %d",
             len(rows), len(emitidos))
    by_cur: dict[str, int] = {}
    for r in rows:
        by_cur[r["currency"]] = by_cur.get(r["currency"], 0) + r["diff_financiero_material"]
    for cur, tot in by_cur.items():
        log.info("  Exceso material total %s: %s", cur, tot)
    log.info("Top 5 por exceso:")
    for r in rows[:5]:
        log.info("  - %s · %s · %s %s · %s", r["quote_id"], r["client_name"],
                 r["diff_financiero_material"], r["currency"], r["status"])

    if dry_run:
        log.info("--dry-run · no se escribe CSV (total_diff acumulado mixto: %s)", total_diff)
        return 0
    if not rows:
        log.info("Nada que reportar · CSV no escrito")
        return 0

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(f"audit_zocalo_7cm_{today}.csv")
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log.info("CSV escrito · %s (%d rows)", out_path.resolve(), len(rows))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default=DEFAULT_SINCE, help=f"Cutoff created_at (default {DEFAULT_SINCE})")
    parser.add_argument("--dry-run", action="store_true", help="Solo resumen · no escribe CSV.")
    args = parser.parse_args()
    return audit(since=args.since, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
