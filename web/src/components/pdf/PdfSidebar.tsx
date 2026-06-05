/**
 * Sidebar derecho 360px del paso 5 PDF · mockup 18.
 *
 * 6 secciones: Archivos a generar · Vigencia · Anticipo · Plazo · Datos
 * envío · Notas internas. CTA bottom "Generar PDF v1 →" (visual-only ·
 * decisión Javi B: persist y transición a estado B viene en sub-PR siguiente).
 * Trazabilidad plegable abajo.
 *
 * Reusa clases legacy `.pdf-sidebar`, `.ps-content`, `.ps-section`,
 * `.ps-filename`, `.ps-input`, `.ps-suffix`, `.ps-textarea`, `.ps-divider`,
 * `.ps-cta`, `.helper-c`. Cero CSS nuevo (sorpresa positiva FASE 1).
 */
"use client";

import type { PdfTrace } from "@/lib/api";
import type { PdfFormState } from "@/lib/hooks/usePdfForm";
import { PdfSidebarSection } from "./PdfSidebarSection";
import { PdfTraceBlock } from "./PdfTraceBlock";

interface Props {
  /** Filename auto-generado del PDF (pre-calculado en el container). */
  pdfFilename: string;
  /** Filename del XLSX (mismo client+material+date, ext distinta). */
  xlsxFilename: string;
  state: PdfFormState;
  onChange: <K extends keyof PdfFormState>(key: K, value: PdfFormState[K]) => void;
  trace: PdfTrace;
  onGenerate: () => void;
}

export function PdfSidebar({
  pdfFilename,
  xlsxFilename,
  state,
  onChange,
  trace,
  onGenerate,
}: Props) {
  return (
    <aside className="pdf-sidebar" data-testid="pdf-sidebar">
      <div className="ps-content">
        <PdfSidebarSection label="Archivos a generar" testId="ps-section-files">
          <div className="ps-filename" data-testid="ps-filename-pdf">
            📄 {pdfFilename}
          </div>
          <div className="ps-filename mt-6" data-testid="ps-filename-xlsx">
            📊 {xlsxFilename}
            <span className="filename-helper">
              Se generan PDF (cliente) + Excel (taller) con el mismo nombre · ambos suben a Drive
              automático
            </span>
          </div>
        </PdfSidebarSection>

        <div className="ps-divider" />

        <PdfSidebarSection label="Vigencia del presupuesto" testId="ps-section-vigencia">
          <div className="ps-suffix">
            <input
              className="ps-input"
              type="number"
              min={1}
              max={60}
              value={state.vigenciaDias}
              onChange={(e) => onChange("vigenciaDias", e.target.value)}
              data-testid="ps-input-vigencia"
            />
            <span className="unit">días desde hoy</span>
          </div>
        </PdfSidebarSection>

        <PdfSidebarSection
          label="Anticipo"
          testId="ps-section-anticipo"
          helperTodo="⚠ confirmar default real con D'Angelo (¿50/50 o 70/30?)"
        >
          <div className="ps-suffix">
            <input
              className="ps-input"
              type="number"
              min={0}
              max={100}
              value={state.anticipoPct}
              onChange={(e) => onChange("anticipoPct", e.target.value)}
              data-testid="ps-input-anticipo"
            />
            <span className="unit">% a la firma</span>
          </div>
        </PdfSidebarSection>

        <PdfSidebarSection label="Plazo de entrega" testId="ps-section-plazo">
          <textarea
            className="ps-textarea"
            rows={2}
            value={state.plazo}
            onChange={(e) => onChange("plazo", e.target.value)}
            data-testid="ps-input-plazo"
          />
        </PdfSidebarSection>

        <PdfSidebarSection
          label="Datos de envío"
          testId="ps-section-envio"
          helper="Auto-completado desde paso 2 (Localidad + Cliente). Editá para sumar dirección exacta, contacto en obra, horario, etc."
        >
          <textarea
            className="ps-textarea"
            rows={3}
            value={state.envio}
            onChange={(e) => onChange("envio", e.target.value)}
            data-testid="ps-input-envio"
          />
        </PdfSidebarSection>

        <PdfSidebarSection
          label="Notas internas"
          labelSub="(no aparecen en el PDF)"
          testId="ps-section-notas"
        >
          <textarea
            className="ps-textarea"
            rows={2}
            placeholder="Recordatorios para vos · ej: 'cliente quería en 2 semanas, le dije que no'"
            value={state.notas}
            onChange={(e) => onChange("notas", e.target.value)}
            data-testid="ps-input-notas"
          />
        </PdfSidebarSection>

        <div className="ps-divider" />
      </div>

      <div className="ps-cta">
        <button
          type="button"
          className="btn primary"
          onClick={onGenerate}
          data-testid="generate-pdf"
        >
          Generar PDF v1 →
        </button>
        <div className="helper-c">
          una vez generado, queda inmutable · revisiones se hacen como v2
        </div>
      </div>

      <PdfTraceBlock trace={trace} />
    </aside>
  );
}
