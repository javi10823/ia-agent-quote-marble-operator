/**
 * Fila `.row` de la tabla `.etable.cols-mo` · SKU/desc/cant/base/iva/total.
 * Read-only (paso 4 no tiene edit per-row · decisión Javi). Acción "⋯" es
 * placeholder de menú futuro.
 */
import type { LaborRowData } from "@/lib/api";
import { AuditChip } from "./AuditChip";
import { AuditTrail } from "./AuditTrail";

interface Props {
  row: LaborRowData;
  ivaVisible: boolean;
  auditOn: boolean;
}

export function LaborRow({ row, ivaVisible, auditOn }: Props) {
  return (
    <>
      <div className="row" data-testid={`labor-row-${row.sku}`}>
        <div className="cell sku">
          {row.sku}
          {auditOn && row.audit && row.audit.length > 0 && (
            <AuditChip
              title={row.audit
                .filter((a) => a.kind === "CALC" || a.kind === "REGLA")
                .map((a) => a.text)
                .join(" · ")}
            />
          )}
        </div>
        <div className="cell label-cell">
          {row.label}
          {row.sub && <span className="sub">{row.sub}</span>}
        </div>
        <div className="cell num">{row.qty}</div>
        {ivaVisible && <div className="cell num base">{row.basePrice}</div>}
        {ivaVisible && <div className="cell iva">{row.iva}</div>}
        <div className="cell num">{row.total}</div>
        <div className="cell action">⋯</div>
      </div>
      {auditOn && row.audit && row.audit.length > 0 && (
        <div className="row" style={{ background: "transparent" }}>
          <div className="cell" style={{ gridColumn: "1 / -1", padding: "4px 16px 10px" }}>
            <AuditTrail entries={row.audit} />
          </div>
        </div>
      )}
    </>
  );
}
