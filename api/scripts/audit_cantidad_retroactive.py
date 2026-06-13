"""Auditoría retroactiva · sub-PR 22.W cantidad-discount-rule.

Identifica quotes en status SENT/VALIDATED que históricamente NO recibieron
descuento por cantidad pero que bajo la nueva regla (Notion D'Angelo
Regla 14 · sub-PR 22.W) hubieran calificado:

  - Cliente NO-arquitecto (check_architect=False)
  - Quote NO-edificio (is_building=False)
  - total_m2 > min_m2_threshold (default 6)
  - discount_pct == 0 (no manual override aplicado)

READ-ONLY · NO modifica ningún quote · solo reporta. Agos decide qué
hacer con el output (refund, ajuste futuro, ignorar, etc.).

Output: `audit_cantidad_retroactive_YYYYMMDD.csv` en CWD.

Uso:
    cd api
    python -m scripts.audit_cantidad_retroactive [--dry-run]

Sin flags lee la DB con `DATABASE_URL` del .env y escribe CSV. Con
--dry-run solo imprime el resumen en stdout (no escribe archivo).
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permitir correr desde `api/` directamente.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.company_config import get as _cfg
from app.models.quote import Quote, QuoteStatus

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_breakdown_metrics(breakdown: dict | None) -> dict:
    """Extrae `total_m2`, `material_total`, `discount_pct`, `currency` del
    breakdown JSON. Tolerante a quotes viejos sin todos los campos.

    Convención del calculator (ver calculator.py:1894): el breakdown a
    nivel raíz tiene `total_m2`, `material_total`, `discount_pct`,
    `currency`.
    """
    if not isinstance(breakdown, dict):
        return {}
    return {
        "total_m2": _safe_float(breakdown.get("total_m2")),
        "material_total": _safe_float(breakdown.get("material_total")),
        "discount_pct": _safe_float(breakdown.get("discount_pct")),
        "currency": (breakdown.get("currency") or "ARS").upper(),
    }


def _is_architect_client(client_name: str) -> bool:
    """Wrapper defensivo · si `check_architect` falla por env, devuelve
    False (asume NO-arquitecto)."""
    if not client_name:
        return False
    try:
        from app.modules.agent.tools.catalog_tool import check_architect

        result = check_architect(client_name)
        return bool(result.get("found")) and bool(result.get("discount", True))
    except Exception as exc:  # noqa: BLE001
        log.debug("check_architect raised %s · asumiendo no-arquitecto", exc)
        return False


def _calc_hubiera_descontado(metrics: dict) -> int:
    """Monto $ que hubiera bajado el material si se aplicaba la regla
    cantidad (5% USD / 8% ARS) sobre `material_total`. Sigue exactamente
    la lógica del calculator nuevo (línea 1470+)."""
    pct = (
        _cfg("discount.imported_percentage", 5)
        if metrics["currency"] == "USD"
        else _cfg("discount.national_percentage", 8)
    )
    return int(round(metrics["material_total"] * pct / 100))


def audit(*, dry_run: bool = False) -> int:
    """Recorre todos los quotes SENT/VALIDATED y reporta cuáles hubieran
    calificado para cantidad. Devuelve el código de salida (0 = ok).
    """
    # Sync engine sobre DATABASE_URL (el script no es FastAPI async).
    sync_url = (
        settings.DATABASE_URL.replace("+asyncpg", "")
        .replace("postgresql+asyncpg", "postgresql")
    )
    engine = create_engine(sync_url)
    min_m2 = _cfg("discount.min_m2_threshold", 6)
    log.info("Threshold cantidad · total_m2 > %s", min_m2)

    rows: list[dict] = []
    statuses = [QuoteStatus.SENT, QuoteStatus.VALIDATED]
    with Session(engine) as session:
        stmt = select(Quote).where(Quote.status.in_(statuses))
        for quote in session.scalars(stmt):
            metrics = _extract_breakdown_metrics(quote.quote_breakdown)
            if not metrics or metrics["total_m2"] <= min_m2:
                continue
            if metrics["discount_pct"] != 0:
                continue
            if quote.is_building:
                continue
            if _is_architect_client(quote.client_name or ""):
                continue
            hubiera_descontado = _calc_hubiera_descontado(metrics)
            rows.append({
                "quote_id": quote.id,
                "client_name": quote.client_name,
                "project": quote.project,
                "total_m2": round(metrics["total_m2"], 2),
                "currency": metrics["currency"],
                "material_total": int(metrics["material_total"]),
                "hubiera_descontado": hubiera_descontado,
                "status": (
                    quote.status.value
                    if hasattr(quote.status, "value")
                    else str(quote.status)
                ),
                "created_at": (
                    quote.created_at.isoformat()
                    if quote.created_at
                    else ""
                ),
            })

    log.info("Quotes afectados: %d", len(rows))
    log.info(
        "Total $ que clientes pagaron de más (sum_diff): %d",
        sum(r["hubiera_descontado"] for r in rows),
    )

    if dry_run:
        log.info("--dry-run · no se escribe CSV")
        return 0

    if not rows:
        log.info("Nada que reportar · CSV no escrito")
        return 0

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(f"audit_cantidad_retroactive_{today}.csv")
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log.info("CSV escrito · %s (%d rows)", out_path.resolve(), len(rows))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo imprime el resumen · no escribe CSV.",
    )
    args = parser.parse_args()
    return audit(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
