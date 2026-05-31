/**
 * Sección 01 · Material · Sprint 3 paso-4.
 * Filas `.row-line` (incluye descuento arquitecta) + `.subtotal`.
 */
import type { MaterialRow } from "@/lib/api";
import { AuditChip } from "./AuditChip";
import { AuditTrail } from "./AuditTrail";

interface Props {
  rows: MaterialRow[];
  subtotal: string;
  auditOn: boolean;
}

export function CalcSectionMaterial({ rows, subtotal, auditOn }: Props) {
  return (
    <section className="calc-section" data-testid="calc-section-material">
      <div className="sh">
        <span className="num">01</span>
        <span className="ttl">Material</span>
      </div>
      <div className="sb">
        {rows.map((r, i) => (
          <div key={`${r.label}-${i}`}>
            <div className={`row-line${r.variant === "discount" ? " discount" : ""}`}>
              <div className="label-cell">
                {r.variant === "discount" ? (
                  <>
                    <em>Valentina</em> aplicó: {r.label}
                  </>
                ) : (
                  r.label
                )}
                {auditOn && r.audit && r.audit.length > 0 && (
                  <AuditChip
                    title={r.audit
                      .filter((a) => a.kind === "CALC" || a.kind === "REGLA")
                      .map((a) => a.text)
                      .join(" · ")}
                  />
                )}
                {r.sub && <span className="sub">{r.sub}</span>}
              </div>
              <div className="num">{r.qty}</div>
              <div className="num">{r.unit}</div>
              <div className="total">{r.total}</div>
            </div>
            {auditOn && r.audit && r.audit.length > 0 && (
              <div style={{ padding: "4px 0 8px 16px" }}>
                <AuditTrail entries={r.audit} />
              </div>
            )}
          </div>
        ))}
        <div className="subtotal">
          <span className="lbl">Subtotal material</span>
          <span className="val">{subtotal}</span>
        </div>
      </div>
    </section>
  );
}
