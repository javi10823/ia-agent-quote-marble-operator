/**
 * Modal de confirmación pre-generación v2 · mockup 21 LITERAL (segmento
 * `.modal-backdrop.v2-confirm-modal`).
 *
 * Mismo patrón destructivo que `PdfConfirmModal` (PR #472):
 * - ESC cierra · click backdrop NO cierra
 * - role="dialog" + aria-labelledby
 * - Footer: Cancelar (ghost) + Generar v2 → (primary)
 *
 * Diferencias justificadas vs v1:
 * - Title con chip inline `<span class="version-chip draft inline">v2</span>`
 * - 4 items en `.modal-ul` (Drive, v1 intacta, v3 futuro, audit log v1↔v2)
 * - `audit-note.purple` con resumen de cambios (en vez de warning amber)
 * - Filenames suffix " v2.pdf" / " v2.xlsx"
 *
 * Reusa clases legacy ya presentes en operator-shared.css (cero CSS nuevo).
 */
"use client";

import { useEffect, useState } from "react";
import type { PdfV2ChangeSummary } from "@/lib/api/types";

interface Props {
  /** PDF filename con suffix " v2.pdf". */
  pdfFilename: string;
  /** Excel filename con suffix " v2.xlsx". */
  xlsxFilename: string;
  /** Resumen de cambios v1↔v2 mostrado en `.audit-note.purple`. */
  changeSummary: PdfV2ChangeSummary[];
  onCancel: () => void;
  /** Disparo async de la generación v2 · throw → banner error + Reintentar. */
  onConfirm: () => Promise<void>;
}

export function PdfConfirmV2Modal({
  pdfFilename,
  xlsxFilename,
  changeSummary,
  onCancel,
  onConfirm,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel, loading]);

  const handleGenerate = async () => {
    if (loading) return;
    setErrorMsg(null);
    setLoading(true);
    try {
      await onConfirm();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "No se pudo generar v2.");
      setLoading(false);
    }
  };

  return (
    <div
      className="modal-backdrop v2-confirm-modal"
      data-testid="pdf-confirm-v2-backdrop"
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="modal w-520"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pdf-confirm-v2-title"
        data-testid="pdf-confirm-v2-modal"
      >
        <div className="m-head">
          <div className="eyebrow">Confirmá antes de generar</div>
          <h3 id="pdf-confirm-v2-title" className="m-title">
            Vas a generar{" "}
            <span className="version-chip draft inline">
              <span className="dot" />v2
            </span>{" "}
            del presupuesto
          </h3>
        </div>

        <div className="m-body">
          <div className="impact">
            <div>
              <div className="lbl">Archivos a generar</div>
              <div className="modal-mono-blob" data-testid="modal-v2-filenames">
                📄 {pdfFilename}
                <br />
                📊 {xlsxFilename}
              </div>
            </div>
          </div>

          <ul className="modal-ul">
            <li>
              Se generan nuevos PDF + Excel y se suben a Drive{" "}
              <span className="mono-inline">/Presupuestos/2026/05-mayo/</span>
            </li>
            <li>
              <strong>v1 queda intacta</strong> en historial inmutable — sigue accesible
            </li>
            <li>
              Cambios futuros = <strong>v3</strong> (versionado lineal)
            </li>
            <li>
              Audit log entry con diff completo v1↔v2 +{" "}
              <span className="mono-inline">trace_id</span>
            </li>
          </ul>

          {changeSummary.length > 0 && (
            <div className="audit-note purple" data-testid="modal-v2-summary">
              <div className="an-lbl">cambios resumidos</div>
              <ul className="modal-ul tight">
                {changeSummary.map((c, i) => (
                  <li key={`${c.field}-${i}`}>
                    {c.field}:{" "}
                    {c.prev && <span className="mono-inline">{c.prev} </span>}
                    {c.outcome.startsWith("+") || c.outcome.includes("$") ? (
                      <span className="mono-inline">{c.outcome}</span>
                    ) : (
                      c.outcome
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {errorMsg && (
            <div
              role="alert"
              data-testid="modal-v2-error-banner"
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
            className="btn ghost m-cancel"
            onClick={onCancel}
            disabled={loading}
            data-testid="modal-v2-cancel"
          >
            Cancelar
          </button>
          <button
            type="button"
            className="btn primary m-confirm"
            onClick={handleGenerate}
            disabled={loading}
            data-testid="modal-v2-confirm"
            data-loading={loading ? "true" : "false"}
          >
            {loading ? (
              <span data-testid="modal-v2-spinner">Generando…</span>
            ) : errorMsg ? (
              "Reintentar"
            ) : (
              "Generar v2 →"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
