/**
 * Modal de confirmación pre-generación · mockup 19 LITERAL.
 *
 * "Única excepción al 'no usar modals' — paso destructivo irreversible"
 * (comentario del mockup). Marina hace click en "Generar PDF v1 →" del
 * sidebar (estado A · PR #470) y ve este modal para confirmar antes de
 * disparar la generación real.
 *
 * Patrones literales del mockup:
 * - ESC cierra · click backdrop NO cierra (porque es destructivo)
 * - role="dialog" + aria-labelledby para a11y
 * - 2 actions footer: Cancelar (ghost) + Generar v1 → (primary)
 *
 * Visual-only en este sub-PR: "Generar v1 →" sólo cierra el modal y
 * dispara `onConfirm()`. El flujo de generación real + transición a
 * estado generado viene en sub-PR siguiente (mockup 20 paso-5-c-generado).
 *
 * Reusa clases legacy `.modal-backdrop`, `.modal.w-520`, `.m-head`,
 * `.m-body`, `.m-foot`, `.modal-mono-blob`, `.modal-ul`, `.mono-inline`,
 * `.warn-icon-amber`, `.audit-note.mt-14`, `.impact`, `.eyebrow` · todas
 * ya presentes en operator-shared.css (cero CSS nuevo).
 */
"use client";

import { useEffect } from "react";

interface Props {
  pdfFilename: string;
  xlsxFilename: string;
  onCancel: () => void;
  /** Disparado en click "Generar v1 →". Visual-only en este PR · el caller
   * sólo cierra el modal. El flow de generación real es mockup 20. */
  onConfirm: () => void;
}

export function PdfConfirmModal({ pdfFilename, xlsxFilename, onCancel, onConfirm }: Props) {
  // ESC cierra · click-outside NO (per mockup literal: "paso destructivo").
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div
      className="modal-backdrop"
      data-testid="pdf-confirm-backdrop"
      // Click backdrop intencionalmente NO cierra (mockup literal):
      // "click-outside NO (botón destructivo)". El handler vacío evita que
      // un click accidental dispare otros listeners globales del body.
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="modal w-520"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pdf-confirm-title"
        data-testid="pdf-confirm-modal"
      >
        <div className="m-head">
          <div className="eyebrow">Confirmá antes de generar</div>
          <h3 id="pdf-confirm-title">Vas a generar v1 del presupuesto</h3>
        </div>

        <div className="m-body">
          <div className="impact">
            <div>
              <div className="lbl">Archivos</div>
              <div className="modal-mono-blob" data-testid="modal-filenames">
                📄 {pdfFilename}
                <br />
                📊 {xlsxFilename}
              </div>
            </div>
          </div>

          <ul className="modal-ul">
            <li>
              Se guardan en <span className="mono-inline">/quotes/2026/</span> local y se suben a
              Drive <span className="mono-inline">/Presupuestos/2026/05-mayo/</span>
            </li>
            <li>
              El presupuesto pasa al estado <strong>&quot;enviado&quot;</strong> — cambios futuros
              se registran como <strong>v2</strong>
            </li>
            <li>
              Se loggea en el audit log con <span className="mono-inline">trace_id</span> + hash de
              inputs
            </li>
          </ul>

          <div className="audit-note mt-14" data-testid="modal-warning">
            <span className="warn-icon-amber" aria-hidden="true">
              ⚠
            </span>{" "}
            Acción irreversible · para corregir errores después, generás una v2
          </div>
        </div>

        <div className="m-foot">
          <button type="button" className="btn ghost" onClick={onCancel} data-testid="modal-cancel">
            Cancelar
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={onConfirm}
            data-testid="modal-confirm"
          >
            Generar v1 →
          </button>
        </div>
      </div>
    </div>
  );
}
