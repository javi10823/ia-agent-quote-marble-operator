"""Auditoría retroactiva · sub-PR paso-5-pdf-real-wire (Bug 1).

Identifica quotes en status SENT/VALIDATED que pudieron haber sido
afectados por el Bug 1 (descuento de material aplicado 2× en PDFs
edificio + Excel renderers). El bug aplicaba cuando:

  1. El quote tenía `discount_pct > 0`.
  2. El PDF generado era edificio (Edificio PDF) o el Excel renderer
     consumía `material_total` como bruto, cuando en realidad era NET
     post-descuento (calculator.py:1915 guarda NET).
  3. El renderer aplicaba descuento de nuevo sobre el NET → cliente
     recibía un PDF con un descuento mayor del que correspondía →
     facturó MENOS de lo que correspondía cobrar (D'Angelo pierde).

Fórmula del exceso descontado (lo que faltó cobrar):

    Calculator guardaba: net = bruto × (1 - p)
    PDF mostraba: net × (1 - p) = bruto × (1 - p)²
    Esperado: net (es decir, bruto × (1 - p))

    Exceso = net - bruto × (1 - p)² = net - net × (1 - p) = net × p
    O equivalente: bruto × p × (1 - p)

READ-ONLY · NO modifica ningún quote · solo reporta. Agos decide qué
hacer con el output (refacturar, ignorar, etc.).

Output: `audit_pdf_discount_double_count_YYYYMMDD.csv`.

Uso:
    cd api
    python -m scripts.audit_pdf_discount_double_count [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import logging
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


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_metrics(quote: Quote) -> dict | None:
    """Extrae métricas del breakdown · None si quote no clasifica."""
    bd = quote.quote_breakdown
    if not isinstance(bd, dict):
        return None
    discount_pct = _safe_float(bd.get("discount_pct"))
    if discount_pct <= 0:
        return None
    # `material_total` del breakdown legacy (calculator guarda NET).
    # Si ya tiene `material_total_bruto` (post-fix), el quote fue
    # generado con la corrección · NO califica para audit retro.
    if "material_total_bruto" in bd:
        return None
    material_total_net = _safe_float(bd.get("material_total"))
    if material_total_net <= 0:
        return None
    is_edificio = bool(bd.get("is_edificio"))
    if not is_edificio:
        # El Bug 1 solo afecta a edificio PDF y al Excel del flujo
        # standard (que también pasa por _generate_excel · línea 1112).
        # El standard `_generate_pdf` NO tenía el bug (recalculaba
        # bruto desde m² × precio).
        # Para conservar el universo afectable, incluimos NO-edificio
        # si el quote tiene Excel generado (asumimos que sí, todos
        # los quotes lo generan).
        pass
    return {
        "discount_pct": discount_pct,
        "material_total_net": material_total_net,
        "currency": (bd.get("material_currency") or "ARS").upper(),
        "is_edificio": is_edificio,
        "total_m2": _safe_float(bd.get("material_m2")),
    }


def _calc_exceso(metrics: dict) -> int:
    """Exceso descontado = material_total_net × discount_pct/100."""
    p = metrics["discount_pct"] / 100.0
    return int(round(metrics["material_total_net"] * p))


def audit(*, dry_run: bool = False) -> int:
    sync_url = (
        settings.DATABASE_URL.replace("+asyncpg", "")
        .replace("postgresql+asyncpg", "postgresql")
    )
    engine = create_engine(sync_url)
    log.info(
        "Audit Bug 1 PDF discount double-count · universo: SENT + VALIDATED · "
        "discount_pct > 0 · breakdown legacy sin `material_total_bruto`",
    )

    rows: list[dict] = []
    statuses = [QuoteStatus.SENT, QuoteStatus.VALIDATED]
    with Session(engine) as session:
        stmt = select(Quote).where(Quote.status.in_(statuses))
        for quote in session.scalars(stmt):
            metrics = _extract_metrics(quote)
            if metrics is None:
                continue
            exceso = _calc_exceso(metrics)
            rows.append({
                "quote_id": quote.id,
                "client_name": quote.client_name,
                "project": quote.project,
                "total_m2": round(metrics["total_m2"], 2),
                "currency": metrics["currency"],
                "discount_pct": metrics["discount_pct"],
                "material_total_net": int(metrics["material_total_net"]),
                "exceso_descontado": exceso,
                "is_edificio": metrics["is_edificio"],
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
    total_exceso = sum(r["exceso_descontado"] for r in rows)
    log.info(
        "Total $ exceso descontado (cliente pagó MENOS de lo que debía): %s",
        total_exceso,
    )

    # Top 5 por exceso.
    top5 = sorted(rows, key=lambda r: r["exceso_descontado"], reverse=True)[:5]
    log.info("Top 5 quotes por exceso descontado:")
    for r in top5:
        log.info(
            "  - %s · %s · %s$ · %s · %s",
            r["quote_id"],
            r["client_name"],
            r["exceso_descontado"],
            r["currency"],
            r["status"],
        )

    if dry_run:
        log.info("--dry-run · no se escribe CSV")
        return 0

    if not rows:
        log.info("Nada que reportar · CSV no escrito")
        return 0

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(f"audit_pdf_discount_double_count_{today}.csv")
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
        help="Solo imprime resumen · no escribe CSV.",
    )
    args = parser.parse_args()
    return audit(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
