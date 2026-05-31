/**
 * Sección 03 · Mano de obra · Sprint 3 paso-4.
 * `.etable.cols-mo` con cols SKU/desc/cant/base/iva/total + subtotal.
 * `ivaVisible` controla columnas `base` + `iva` (decisión Javi #3).
 */
import type { LaborRowData } from "@/lib/api";
import { LaborRow } from "./LaborRow";
import { AuditChip } from "./AuditChip";

interface Props {
  rows: LaborRowData[];
  subtotal: string;
  auditOn: boolean;
  ivaVisible: boolean;
}

export function CalcSectionLabor({ rows, subtotal, auditOn, ivaVisible }: Props) {
  return (
    <>
      <section className="calc-section" data-testid="calc-section-labor">
        <div className="sh">
          <span className="num">03</span>
          <span className="ttl">Mano de obra</span>
        </div>
      </section>
      <div className={`etable cols-mo${ivaVisible ? "" : " no-iva"}`} data-testid="labor-table">
        <div className="colh">
          <div>SKU</div>
          <div>Descripción</div>
          <div>Cant</div>
          {ivaVisible && <div>Base s/IVA</div>}
          {ivaVisible && <div>×1,21</div>}
          <div>Total c/IVA</div>
          <div />
        </div>
        {rows.map((r) => (
          <LaborRow key={r.sku} row={r} ivaVisible={ivaVisible} auditOn={auditOn} />
        ))}
        <div className="row subtotal-mo">
          <div className="cell" />
          <div className="cell label-cell subtotal-lbl">
            Subtotal mano de obra · {rows.length} ítems
            {auditOn && (
              <AuditChip
                title={`Suma de ${rows.length} SKUs MO base s/IVA · luego ×1,21 = ${subtotal}`}
              />
            )}
          </div>
          <div className="cell" />
          {ivaVisible && <div className="cell" />}
          {ivaVisible && <div className="cell" />}
          <div className="cell num bold">{subtotal}</div>
          <div className="cell" />
        </div>
      </div>
    </>
  );
}
