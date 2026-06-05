/**
 * Container client del paso 5 PDF · mockup 18.
 *
 * Coordina:
 * - usePdfForm state (sidebar live-edit) seedeado con `datosPdf` del cálculo
 *   y `envioSeed` del contexto paso-2 (cliente+localidad).
 * - PdfPreviewDoc (PDF inline A4 con datos del state).
 * - PdfSidebar (6 secciones + CTA + trace block).
 * - PdfChatPanel (closed-default · botón "Ayuda con esta sección" lo abre).
 *
 * Wireado SSR Bearer del PR #469: el page server component pasa `quote` y
 * `calculation` ya cargados con auth. Acá solo coordinamos UI.
 */
"use client";

import { useMemo, useState } from "react";
import type { CalculationResult, PdfTrace, QuoteHeader } from "@/lib/api";
import { usePdfForm } from "@/lib/hooks/usePdfForm";
import { formatPdfDate, getPdfFilename } from "@/lib/pdfFormat";
import { PdfPreviewDoc } from "./PdfPreviewDoc";
import { PdfSidebar } from "./PdfSidebar";
import { PdfChatPanel } from "./PdfChatPanel";
import { IaAuditBanner } from "@/components/observability/IaAuditBanner";

interface Props {
  quoteId: string;
  quote: QuoteHeader;
  calculation: CalculationResult;
  trace: PdfTrace;
  /** Seed del textarea Datos de envío · derivado server-side de paso-2
   * (cliente + localidad). Si vacío, el textarea arranca vacío. */
  envioSeed: string;
  /** Fecha del PDF en formato ISO (string). Calculada server-side para evitar
   * hydration mismatch (`new Date()` corriendo con T1 server vs T2 client
   * podría caer en distintos segundos/días → format dd.mm.yyyy distinto).
   * Tests determinísticos pueden pasar override. */
  pdfDateIso: string;
}

export function PdfView({ quoteId, quote, calculation, trace, envioSeed, pdfDateIso }: Props) {
  const { state, update } = usePdfForm({
    vigenciaDias: calculation.datosPdf.vigenciaDias,
    anticipoPct: calculation.datosPdf.anticipoPct,
    plazo: calculation.datosPdf.plazo,
    envio: envioSeed,
    notas: "",
  });
  const [chatOpen, setChatOpen] = useState(false);

  // `pdfDateIso` viene determinístico desde el server (ver pdf/page.tsx).
  // Parse a Date para los helpers · referencia estable mientras la prop no cambie.
  const date = useMemo(() => new Date(pdfDateIso), [pdfDateIso]);
  const fechaFmt = useMemo(() => formatPdfDate(date), [date]);
  const pdfFilename = useMemo(
    () => getPdfFilename({ client: quote.clientFull, material: quote.material, date, ext: "pdf" }),
    [quote.clientFull, quote.material, date],
  );
  const xlsxFilename = useMemo(
    () => getPdfFilename({ client: quote.clientFull, material: quote.material, date, ext: "xlsx" }),
    [quote.clientFull, quote.material, date],
  );

  return (
    <div
      data-testid="pdf-view"
      data-chat-open={chatOpen}
      // Grid 2-col interno (mismo patrón que `.body.pdf-layout` del mockup
      // 18). Aplicado inline para no modificar el `.body.no-chat` del
      // layout chrome shell del Sprint 3 (regla NO tocar [id]/layout).
      // El chat es overlay fixed (heredado del PR #465 fix-up #2) · no ocupa columna.
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 360px",
        gap: 24,
        minHeight: 0,
      }}
    >
      <div className="col">
        <div className="section-head">
          <div>
            <div className="meta">Paso 5 de 5 · Presupuesto PDF</div>
            <h2>Preview del presupuesto</h2>
            <div className="vc-wrap">
              <span className="version-chip draft" data-testid="version-chip">
                <span className="dot" />
                v1 · borrador
              </span>
              <span className="status-mini">aún no enviado</span>
            </div>
          </div>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setChatOpen(true)}
            data-testid="open-chat"
            style={{ marginLeft: "auto" }}
          >
            💬 Ayuda con esta sección
          </button>
        </div>

        <IaAuditBanner quoteId={quoteId} />

        <div className="pdf-stage">
          <div className="pdf-iframe-wrap">
            <PdfPreviewDoc
              quote={quote}
              calculation={calculation}
              trace={trace}
              state={state}
              fechaFmt={fechaFmt}
            />
          </div>
        </div>

        <div className="pdf-stage-helper">Vista previa a tamaño real · A4 · página 1 de 1</div>
      </div>

      <PdfSidebar
        pdfFilename={pdfFilename}
        xlsxFilename={xlsxFilename}
        state={state}
        onChange={update}
        trace={trace}
        onGenerate={() => {
          // Decisión Javi B: visual-only en este PR. Transición a estado B
          // (mockup 19 · confirmar y generar) viene en sub-PR siguiente.
          // Acá solo registramos el intent sin persistir.
        }}
      />

      {chatOpen && <PdfChatPanel quoteId={quoteId} onClose={() => setChatOpen(false)} />}
    </div>
  );
}
