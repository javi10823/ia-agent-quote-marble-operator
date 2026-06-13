/**
 * Modal de confirmación pre-save · sub-PR 22.2.a config-ui-page.
 *
 * Reusa el pattern de PdfConfirmModal (paso destructivo · ESC cierra,
 * click backdrop no cierra). Muestra tabla antes/después de los fields
 * que cambiaron · si nada cambió, el caller no debe abrirlo.
 *
 * Cero CSS nuevo · todas las clases vienen de operator-shared.css.
 */
"use client";

import { useEffect, useState } from "react";

export interface DiffRow {
  label: string;
  before: string;
  after: string;
}

interface Props {
  rows: DiffRow[];
  onCancel: () => void;
  /** Async handler que dispara PUT a backend. Si throw → banner error. */
  onConfirm: () => Promise<void>;
}

export function ConfigDiffModal({ rows, onCancel, onConfirm }: Props) {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel, loading]);

  const handleConfirm = async () => {
    if (loading) return;
    setErrorMsg(null);
    setLoading(true);
    try {
      await onConfirm();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "No se pudo guardar la configuración.");
      setLoading(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      data-testid="config-diff-backdrop"
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="modal w-520"
        role="dialog"
        aria-modal="true"
        aria-labelledby="config-diff-title"
        data-testid="config-diff-modal"
      >
        <div className="m-head">
          <div className="eyebrow">Confirmá los cambios</div>
          <h3 id="config-diff-title">Vas a actualizar la configuración</h3>
        </div>

        <div className="m-body">
          <table
            data-testid="config-diff-table"
            style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}
          >
            <thead>
              <tr style={{ color: "var(--ink-mute)", textAlign: "left" }}>
                <th style={{ padding: "6px 8px", fontWeight: 500 }}>Campo</th>
                <th style={{ padding: "6px 8px", fontWeight: 500 }}>Antes</th>
                <th style={{ padding: "6px 8px", fontWeight: 500 }}>Después</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.label}
                  data-testid={`diff-row-${r.label}`}
                  style={{ borderTop: "1px solid var(--border)" }}
                >
                  <td style={{ padding: "8px" }}>{r.label}</td>
                  <td style={{ padding: "8px", color: "var(--ink-mute)" }}>
                    <span className="mono-inline">{r.before}</span>
                  </td>
                  <td style={{ padding: "8px", color: "var(--ink)" }}>
                    <span className="mono-inline">{r.after}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="audit-note mt-14" data-testid="config-diff-warning">
            <span className="warn-icon-amber" aria-hidden="true">
              ⚠
            </span>{" "}
            Aplica a presupuestos NUEVOS · los que están en draft retienen los valores actuales en
            su breakdown.
          </div>

          {errorMsg && (
            <div
              role="alert"
              data-testid="config-error-banner"
              style={{
                marginTop: 14,
                padding: "10px 14px",
                borderRadius: 6,
                border: "1px solid var(--error)",
                background: "color-mix(in oklch, var(--error) 12%, transparent)",
                color: "var(--error)",
                fontSize: 13,
                lineHeight: 1.4,
              }}
            >
              {errorMsg}
            </div>
          )}
        </div>

        <div className="m-foot">
          <button
            type="button"
            className="btn ghost"
            onClick={onCancel}
            disabled={loading}
            data-testid="config-modal-cancel"
          >
            Cancelar
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={handleConfirm}
            disabled={loading}
            data-testid="config-modal-confirm"
            data-loading={loading ? "true" : "false"}
          >
            {loading ? (
              <span data-testid="config-modal-spinner">Guardando…</span>
            ) : errorMsg ? (
              "Reintentar"
            ) : (
              "Guardar cambios"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
