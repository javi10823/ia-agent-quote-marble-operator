/**
 * Toolbar del header · AUDIT toggle · Tipo cliente · IVA toggle · ↻ Re-calcular.
 *
 * - AUDIT toggle controla `.aud-trail` per-row + chips `.aud-i` (decisión #1)
 * - Tipo cliente Particular/Edificio es VISUAL-only (decisión #2)
 * - IVA toggle muestra/oculta cols (decisión #3)
 * - ↻ Re-calcular dispara `triggerCalculation` mock
 */
"use client";

import type { CalcToggles } from "@/lib/api";

interface Props {
  toggles: CalcToggles;
  onChange: <K extends keyof CalcToggles>(key: K, value: CalcToggles[K]) => void;
  onRecalculate: () => void;
  busy: boolean;
}

export function CalcToolbar({ toggles, onChange, onRecalculate, busy }: Props) {
  return (
    <div className="right" style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <button
        type="button"
        className={`audit-toggle${toggles.auditOn ? " on" : ""}`}
        onClick={() => onChange("auditOn", !toggles.auditOn)}
        data-testid="audit-toggle"
        data-on={toggles.auditOn}
        style={{
          padding: "6px 10px",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--r-sm)",
          background: toggles.auditOn ? "var(--surface-2)" : "transparent",
          color: toggles.auditOn ? "var(--ink)" : "var(--ink-mute)",
          fontFamily: "var(--mono)",
          fontSize: 10.5,
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          cursor: "pointer",
        }}
      >
        AUDIT {toggles.auditOn ? "ON" : "OFF"}
      </button>

      <div
        className="tipo-toggle"
        data-testid="tipo-toggle"
        data-tipo={toggles.tipoCliente}
        style={{
          display: "flex",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--r-sm)",
          overflow: "hidden",
        }}
      >
        {(["particular", "edificio"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={`tt-btn${toggles.tipoCliente === t ? " on" : ""}`}
            onClick={() => onChange("tipoCliente", t)}
            data-testid={`tipo-${t}`}
            style={{
              padding: "6px 12px",
              background: toggles.tipoCliente === t ? "var(--accent)" : "transparent",
              color: toggles.tipoCliente === t ? "var(--bg)" : "var(--ink-soft)",
              border: "none",
              fontSize: 12,
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      <label
        className="iva-toggle"
        data-testid="iva-toggle"
        style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}
      >
        <input
          type="checkbox"
          checked={toggles.ivaVisible}
          onChange={(e) => onChange("ivaVisible", e.target.checked)}
        />
        <span>Desglose IVA</span>
      </label>

      <button
        type="button"
        className="btn ghost sm"
        onClick={onRecalculate}
        disabled={busy}
        data-testid="recalculate"
      >
        ↻ Re-calcular
      </button>
    </div>
  );
}
