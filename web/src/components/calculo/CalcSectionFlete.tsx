/**
 * Sección 05 · Flete · una sola `.row-line` con zona + viajes.
 */
import type { FleteRow } from "@/lib/api";
import { AuditChip } from "./AuditChip";
import { AuditTrail } from "./AuditTrail";

interface Props {
  flete: FleteRow;
  auditOn: boolean;
}

export function CalcSectionFlete({ flete, auditOn }: Props) {
  return (
    <section className="calc-section" data-testid="calc-section-flete">
      <div className="sh">
        <span className="num">05</span>
        <span className="ttl">Flete</span>
      </div>
      <div className="sb">
        <div className="row-line">
          <div className="label-cell">
            Flete + toma medidas {flete.zona}
            {auditOn && flete.audit && flete.audit.length > 0 && (
              <AuditChip title={flete.audit.map((a) => a.text).join(" · ")} />
            )}
          </div>
          <div className="num">{flete.qty}</div>
          <div className="num">{flete.basePrice}</div>
          <div className="total">{flete.total}</div>
        </div>
        {auditOn && flete.audit && flete.audit.length > 0 && (
          <div style={{ padding: "4px 0 8px 16px" }}>
            <AuditTrail entries={flete.audit} />
          </div>
        )}
      </div>
    </section>
  );
}
