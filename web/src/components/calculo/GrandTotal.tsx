/**
 * Grand total bi-currency (ARS = MO + flete; USD = material importado).
 * Variantes `.has-warn` (estado B) y `.has-sim` (chat con simulación).
 */
import type { GrandTotals } from "@/lib/api";

interface Props {
  totals: GrandTotals;
  hasSim?: boolean;
}

export function GrandTotal({ totals, hasSim }: Props) {
  const variant = totals.warnDetail ? " has-warn" : hasSim ? " has-sim" : "";
  return (
    <section className={`grand-total${variant}`} data-testid="grand-total">
      <div className="col" data-testid="grand-total-ars">
        <div className="lbl">
          ARS <span className="sub">MO + flete</span>
        </div>
        <div className="val">{totals.ars.value}</div>
        <div className="meta">{totals.ars.meta}</div>
        {totals.warnDetail && (
          <div className="error-tone" style={{ marginTop: 6, fontSize: 12 }}>
            {totals.warnDetail}
          </div>
        )}
      </div>
      <div className="div" aria-hidden="true" />
      <div className="col" data-testid="grand-total-usd">
        <div className="lbl">
          USD <span className="sub">material (importado)</span>
        </div>
        <div className="val">{totals.usd.value}</div>
        <div className="meta">{totals.usd.meta}</div>
      </div>
    </section>
  );
}
