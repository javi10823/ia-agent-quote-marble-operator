/**
 * Sección 02 · Merma / Sobrante · Sprint 3 paso-4.
 * 3 modos: na · aplica (con sobrante/stock toggles) · error (estado B).
 */
"use client";

import { useState } from "react";
import type { MermaSection } from "@/lib/api";
import { AuditChip } from "./AuditChip";
import { AuditTrail } from "./AuditTrail";

interface Props {
  merma: MermaSection;
  auditOn: boolean;
  onFix?: () => void;
}

export function CalcSectionMerma({ merma, auditOn, onFix }: Props) {
  const [sobrante, setSobrante] = useState(merma.sobranteToggle?.defaultChecked ?? false);
  const [stock, setStock] = useState(merma.stockToggle?.defaultChecked ?? false);

  return (
    <section
      className={`calc-section${merma.status === "error" ? " has-error" : ""}`}
      data-testid="calc-section-merma"
      data-merma-status={merma.status}
    >
      <div className="sh">
        <span className="num">02</span>
        <span className="ttl">Merma / Sobrante</span>
        {merma.status === "aplica" && <span className="chip-info">{merma.chipLabel}</span>}
        {merma.status === "na" && <span className="chip-na">{merma.chipLabel}</span>}
        {merma.status === "error" && <span className="chip-error">{merma.chipLabel}</span>}
      </div>
      <div className="sb">
        {merma.sub && (
          <p className="sub" style={{ marginBottom: 10 }}>
            {merma.sub}
          </p>
        )}
        {merma.rows?.map((r, i) => (
          <div key={`${r.label}-${i}`}>
            <div className="row-line">
              <div className="label-cell">
                {r.label}
                {auditOn && r.audit && r.audit.length > 0 && (
                  <AuditChip title={r.audit.map((a) => a.text).join(" · ")} />
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
        {merma.errorRow && (
          <div className="merma-row-error" data-testid="merma-row-error">
            <div className="label-cell">
              {merma.errorRow.label}
              <span className="sub">{merma.errorRow.detail}</span>
            </div>
            <button type="button" className="fix-btn" onClick={onFix} data-testid="merma-fix">
              {merma.errorRow.fixLabel}
            </button>
          </div>
        )}
        {merma.sobranteToggle && (
          <label
            className="sobrante-opt"
            style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}
          >
            <input
              type="checkbox"
              checked={sobrante}
              onChange={(e) => setSobrante(e.target.checked)}
              data-testid="sobrante-toggle"
            />
            <span className="sobrante-lbl">{merma.sobranteToggle.label}</span>
          </label>
        )}
        {merma.stockToggle && (
          <label
            className="merma-stock"
            style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8 }}
          >
            <input
              type="checkbox"
              checked={stock}
              onChange={(e) => setStock(e.target.checked)}
              data-testid="stock-toggle"
            />
            <span>{merma.stockToggle.label}</span>
          </label>
        )}
      </div>
    </section>
  );
}
