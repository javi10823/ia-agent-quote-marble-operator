/**
 * Drawer side-by-side de revisión v2 · mockup 21 LITERAL.
 *
 * Componente reusable `.diff-drawer[data-mode="interactive"]` que se monta
 * a la derecha del PDF preview cuando el estado del paso 5 es "revising"
 * (estado D). Compara v1 (oficial · ya enviada) vs v2 (borrador editable
 * pendiente de generar).
 *
 * Layout esperado: ancho fijo 400px, ocupa la columna 3 del grid 3-col
 * que adopta `PdfView` cuando `state === "revising"`.
 *
 * Inputs: visual-only en este sub-PR · no edita realmente · sub-PR posterior
 * `paso-5-v2-editable` wirea inputs al sidebar v2 borrador.
 *
 * Reusa clases legacy del scope confirmado en CSS audit (FASE 1):
 * `.diff-drawer`, `.dd-head`, `.dd-title-wrap`, `.dd-title`, `.dd-sub`,
 * `.dd-close`, `.dd-banner`, `.dd-banner-ico`, `.dd-banner-text`,
 * `.dd-banner-strong`, `.dd-banner-sub`, `.dd-section`, `.dd-section-head`,
 * `.dd-section-title`, `.dd-diff-count`, `.dd-table`, `.dd-row`,
 * `.dd-row-head`, `.dd-row.diff`, `.dd-row.diff.money`, `.dd-col-field`,
 * `.dd-col-v1`, `.dd-col-v2`, `.dd-val`, `.dd-val.mono`, `.dd-val.diff`,
 * `.dd-val.empty`, `.dd-trace`, `.dd-summary`, `.dd-bul`, `.dd-chip-count`,
 * `.dd-cta`, `.dd-cancel`, `.dd-generate-v2`, `.mono`, `.prev`, `.outcome`.
 */
"use client";

import type { PdfV2DiffRow, PdfV2ChangeSummary } from "@/lib/api/types";

interface Props {
  rows: PdfV2DiffRow[];
  summary: PdfV2ChangeSummary[];
  diffCount: number;
  unchangedCount: number;
  onClose: () => void;
  onCancel: () => void;
  onGenerateV2: () => void;
  generating?: boolean;
}

export function PdfDiffDrawer({
  rows,
  summary,
  diffCount,
  unchangedCount,
  onClose,
  onCancel,
  onGenerateV2,
  generating = false,
}: Props) {
  return (
    <aside
      className="diff-drawer"
      data-mode="interactive"
      data-testid="pdf-diff-drawer"
    >
      {/* ── Header ── */}
      <div className="dd-head">
        <div className="dd-title-wrap">
          <h3 className="dd-title">Revisión v2</h3>
          <span className="dd-sub">comparar con v1 antes de generar</span>
        </div>
        <button
          type="button"
          className="dd-close"
          aria-label="Cerrar drawer"
          onClick={onClose}
          data-testid="dd-close"
        >
          ×
        </button>
      </div>

      {/* ── Banner amber dentro del drawer ── */}
      <div className="dd-banner">
        <span className="dd-banner-ico" aria-hidden="true">
          ⚠
        </span>
        <div className="dd-banner-text">
          <span className="dd-banner-strong">v1 sigue siendo la versión oficial.</span>
          <span className="dd-banner-sub">
            Enviada al cliente hace 2 días. Hasta que generes v2, esto es solo
            borrador editable — nada se mandó.
          </span>
        </div>
      </div>

      {/* ── Tabla side-by-side · cambios detectados ── */}
      <div className="dd-section">
        <div className="dd-section-head">
          <span className="dd-section-title">Cambios detectados</span>
          <span className="dd-diff-count" data-testid="dd-diff-count">
            {diffCount} con cambio · {unchangedCount} sin cambio
          </span>
        </div>

        <div className="dd-table">
          <div className="dd-row dd-row-head">
            <span className="dd-col-field">Campo</span>
            <span className="dd-col-v1">v1</span>
            <span className="dd-col-v2">v2 (editable)</span>
          </div>

          {rows.map((row, i) => {
            const isDiff = row.v1Value !== row.v2Value;
            const isMoney = row.variant === "money";
            const monoClass = row.display === "mono" ? " mono" : "";
            return (
              <div
                key={`${row.field}-${i}`}
                className={`dd-row${isDiff ? " diff" : ""}${
                  isDiff && isMoney ? " money" : ""
                }`}
                data-testid={`dd-row-${row.field.toLowerCase().replace(/\s+/g, "-")}`}
                data-diff={isDiff ? "true" : "false"}
              >
                <span className="dd-col-field">{row.field}</span>
                <span className="dd-col-v1">
                  <span
                    className={`dd-val${monoClass}${row.v1Empty ? " empty" : ""}`}
                  >
                    {row.v1Value}
                  </span>
                </span>
                <span className="dd-col-v2">
                  <span className={`dd-val${monoClass}${isDiff ? " diff" : ""}`}>
                    {row.v2Value}
                  </span>
                  {isDiff && row.trace && (
                    <span className="dd-trace">{row.trace}</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Resumen ── */}
      {summary.length > 0 && (
        <div className="dd-section">
          <div className="dd-section-head">
            <span className="dd-section-title">Resumen</span>
            <span className="dd-chip-count" data-testid="dd-chip-count">
              {summary.length} cambio{summary.length === 1 ? "" : "s"}
            </span>
          </div>
          <ul className="dd-summary">
            {summary.map((c, i) => (
              <li key={`${c.field}-${i}`}>
                <span className="dd-bul">·</span> {c.field}:{" "}
                {c.prev && <span className="mono prev">{c.prev}</span>}{" "}
                <span
                  className={
                    c.outcome.startsWith("+") || /\$/.test(c.outcome)
                      ? "mono outcome"
                      : "outcome"
                  }
                >
                  {c.outcome}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── CTAs ── */}
      <div className="dd-cta">
        <button
          type="button"
          className="btn ghost dd-cancel"
          onClick={onCancel}
          disabled={generating}
          data-testid="dd-cancel"
        >
          Cancelar revisión
        </button>
        <button
          type="button"
          className="btn primary dd-generate-v2"
          onClick={onGenerateV2}
          disabled={generating}
          data-testid="dd-generate-v2"
        >
          Generar v2 →
        </button>
      </div>
    </aside>
  );
}
