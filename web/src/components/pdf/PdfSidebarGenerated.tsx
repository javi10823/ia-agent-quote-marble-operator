/**
 * Sidebar derecho 360px del paso 5 estado C · mockup 20 LITERAL.
 *
 * 4 secciones:
 *  1. Archivos generados (3 file-rows + filename helper)
 *  2. Descargar (action-stack con 2 botones)
 *  3. Compartir con el cliente (share-grid 2x2)
 *  4. Crear revisión v2 (link discreto · TODO mockup 21)
 *  + Trazabilidad plegable extendida (6 items)
 *
 * Reusa clases legacy `.pdf-sidebar`, `.ps-content`, `.ps-section`, `.lbl`,
 * `.ps-divider`, `.files-list`, `.file-row`, `.file-row.drive`, `.saved-check`,
 * `.f-icon/name/size/path`, `.ps-filename`, `.filename-helper`, `.action-stack`,
 * `.action-btn`, `.ab-content/lbl/helper`, `.share-grid`, `.share-chip`,
 * `.sc-ico/lbl`, `.copied-badge`, `.v2-link`, `.v2-helper`, `.trace-block`.
 * Cero CSS nuevo (sorpresa positiva FASE 1).
 */
"use client";

import { useState } from "react";
import type { PdfGeneratedInfo, PdfTrace } from "@/lib/api";

interface Props {
  /** Filename base (sin extensión) · ej "Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026". */
  baseFilename: string;
  info: PdfGeneratedInfo;
  trace: PdfTrace;
  /** Handler para "Crear revisión v2 →" · visual-only en este PR (mockup 21 lo wirea). */
  onCreateV2?: () => void;
}

export function PdfSidebarGenerated({ baseFilename, info, trace, onCreateV2 }: Props) {
  const [copied, setCopied] = useState(false);

  const handleDownloadPdf = () => {
    if (typeof window !== "undefined") window.open(info.pdfUrl, "_blank");
  };
  const handleDownloadExcel = () => {
    if (typeof window !== "undefined") window.open(info.excelUrl, "_blank");
  };
  const handleOpenDrive = () => {
    if (typeof window !== "undefined") window.open(info.driveUrl, "_blank");
  };
  const handleCopyLink = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(info.pdfUrl);
      }
    } catch {
      // best-effort · ambientes sin clipboard API simplemente muestran el badge igual
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  const handleEmail = () => {
    if (typeof window !== "undefined") {
      const subject = encodeURIComponent("Presupuesto D'Angelo Marmolería");
      const body = encodeURIComponent(`Hola,\n\nTe paso el presupuesto:\n${info.pdfUrl}\n\nSaludos,\nMarina`);
      window.open(`mailto:?subject=${subject}&body=${body}`, "_blank");
    }
  };
  const handleWhatsApp = () => {
    if (typeof window !== "undefined") {
      const msg = encodeURIComponent(`Hola, te paso el presupuesto: ${info.pdfUrl}`);
      window.open(`https://wa.me/?text=${msg}`, "_blank");
    }
  };

  return (
    <aside className="pdf-sidebar" data-testid="pdf-sidebar-generated">
      <div className="ps-content">
        {/* ── 1 · Archivos generados ── */}
        <div className="ps-section" data-testid="ps-section-files-generated">
          <div className="lbl">Archivos generados</div>
          <div className="files-list">
            <div className="file-row" data-testid="file-row-pdf">
              <span className="saved-check" aria-hidden="true">
                ✓
              </span>
              <span className="f-icon">📄</span>
              <span className="f-name">PDF (cliente)</span>
              <span className="f-size">{info.pdfSizeKb} KB</span>
            </div>
            <div className="file-row" data-testid="file-row-xlsx">
              <span className="saved-check" aria-hidden="true">
                ✓
              </span>
              <span className="f-icon">📊</span>
              <span className="f-name">Excel (taller)</span>
              <span className="f-size">{info.excelSizeKb} KB</span>
            </div>
            <div className="file-row drive" data-testid="file-row-drive">
              <span className="saved-check" aria-hidden="true">
                ✓
              </span>
              <span className="f-icon">🗂</span>
              <span className="f-name">Subidos a Drive</span>
              <span className="f-path">{info.driveFolderPath}</span>
            </div>
          </div>
          <div className="ps-filename mt-8" data-testid="generated-filename">
            {baseFilename}
            <span className="filename-helper">
              mismo nombre · .pdf + .xlsx · inmutables una vez generados
            </span>
          </div>
        </div>

        <div className="ps-divider" />

        {/* ── 2 · Descargar ── */}
        <div className="ps-section" data-testid="ps-section-download">
          <div className="lbl">Descargar</div>
        </div>
        <div className="action-stack">
          <button
            type="button"
            className="action-btn primary"
            onClick={handleDownloadPdf}
            data-testid="action-download-pdf"
          >
            <span className="ico" aria-hidden="true">
              ↓
            </span>
            <span className="ab-content">
              <span className="ab-lbl">Descargar PDF</span>
              <span className="ab-helper">
                {info.pdfSizeKb} KB · A4 · 1 página · para el cliente
              </span>
            </span>
          </button>
          <button
            type="button"
            className="action-btn"
            onClick={handleDownloadExcel}
            data-testid="action-download-excel"
          >
            <span className="ico" aria-hidden="true">
              ↓
            </span>
            <span className="ab-content">
              <span className="ab-lbl">Descargar Excel</span>
              <span className="ab-helper">
                {info.excelSizeKb} KB · taller · Sergio/Agos pueden modificar
              </span>
            </span>
          </button>
        </div>

        <div className="ps-divider" />

        {/* ── 3 · Compartir con el cliente ── */}
        <div className="ps-section" data-testid="ps-section-share">
          <div className="lbl">
            Compartir con el cliente <span className="lbl-sub">(solo PDF)</span>
          </div>
        </div>
        <div className="share-grid">
          <button
            type="button"
            className="share-chip"
            onClick={handleCopyLink}
            data-testid="share-copy-link"
          >
            <svg
              className="sc-ico"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="9" y="9" width="11" height="11" rx="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            <span className="sc-lbl">Copiar link</span>
            <span
              className={`copied-badge${copied ? " show" : ""}`}
              data-testid="copied-badge"
              aria-live="polite"
            >
              ✓
            </span>
          </button>
          <button
            type="button"
            className="share-chip"
            onClick={handleEmail}
            data-testid="share-email"
          >
            <svg
              className="sc-ico"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="m22 7-10 5L2 7" />
            </svg>
            <span className="sc-lbl">Email</span>
          </button>
          <button
            type="button"
            className="share-chip"
            onClick={handleWhatsApp}
            data-testid="share-whatsapp"
          >
            <svg
              className="sc-ico"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
            </svg>
            <span className="sc-lbl">WhatsApp</span>
          </button>
          <button
            type="button"
            className="share-chip"
            onClick={handleOpenDrive}
            data-testid="share-drive"
          >
            <svg
              className="sc-ico"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span className="sc-lbl">Abrir en Drive</span>
          </button>
        </div>

        <div className="ps-divider" />

        {/* ── 4 · Crear revisión v2 (link discreto · TODO mockup 21) ── */}
        <div
          className="v2-link"
          role="button"
          tabIndex={0}
          data-testid="v2-link"
          onClick={() => onCreateV2?.()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onCreateV2?.();
            }
          }}
        >
          <span className="ico" aria-hidden="true">
            ↻
          </span>
          <span>
            <strong>Crear revisión v2 →</strong>
            <span className="v2-helper">
              para corregir errores · re-genera PDF + Excel + sube a Drive · audit log
            </span>
          </span>
        </div>

        {/* ── Trazabilidad plegable extendida ── */}
        <details className="trace-block" data-testid="trace-block-generated">
          <summary>Trazabilidad</summary>
          <div className="trace-list">
            <span className="k">trace_id</span>
            <span data-testid="trace-id-generated">{trace.traceId}</span>
            <span className="k">prompt_v</span>
            <span>{trace.promptVersion}</span>
            <span className="k">inputs_hash</span>
            <span>{trace.inputsHash}</span>
            <span className="k">generado</span>
            <span data-testid="trace-generated-at">
              {info.generatedAtDisplay} · {info.generatedBy}
            </span>
            <span className="k">drive_id</span>
            <span data-testid="trace-drive-id">{info.driveId}</span>
            <span className="k">snapshot</span>
            <span>{trace.snapshot}</span>
          </div>
        </details>
      </div>
    </aside>
  );
}
