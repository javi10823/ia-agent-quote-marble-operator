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
import type {
  CalculationResult,
  PdfGeneratedInfo,
  PdfTrace,
  PdfV2RevisionData,
  Piece,
  QuoteHeader,
} from "@/lib/api";
import {
  getPdfV2DiffData,
  triggerPdfGeneration,
  triggerPdfV2Generation,
} from "@/lib/api";
import { usePdfForm } from "@/lib/hooks/usePdfForm";
import { formatPdfDate, getPdfFilename } from "@/lib/pdfFormat";
import { PdfPreviewDoc } from "./PdfPreviewDoc";
import { PdfSidebar } from "./PdfSidebar";
import { PdfChatPanel } from "./PdfChatPanel";
import { PdfConfirmModal } from "./PdfConfirmModal";
import { PdfConfirmV2Modal } from "./PdfConfirmV2Modal";
import { PdfDiffDrawer } from "./PdfDiffDrawer";
import { PdfGenBanner } from "./PdfGenBanner";
import { PdfSidebarGenerated } from "./PdfSidebarGenerated";
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
  /** Piezas del paso-3 para renderizar las sub-filas `row-piece` debajo del
   * row-material en el PDF. Carga server-side via `listPiecesForQuote`. */
  pieces: Piece[];
  /** Texto del campo "Proyecto" del grid cliente del PDF · proviene de la
   * tipología del paso-2 (`ContextResponse.tipologia`). Fallback al `client`
   * del QuoteHeader cuando el contexto no expone tipología. */
  proyecto: string;
  /** Sprint 4 paso-5-c-generado · null → estado A (preview · sidebar editable
   * + modal). Cuando viene poblado: estado C (gen-banner + sidebar generated
   * + chip final). Server carga via `getPdfGeneratedInfo(quoteId)` que
   * resuelve canon cuando el quoteId termina en `-GENERATED` o cuando el
   * store de sesión tiene info post-triggerPdfGeneration. */
  initialGenerated?: PdfGeneratedInfo | null;
  /** Sprint 4 paso-5-d-revision-v2 · true cuando el quoteId termina en
   * `-REVISING` · arranca con drawer abierto + 3-col layout · v1 oficial
   * permanece intacta hasta confirmar v2. */
  initialRevising?: boolean;
  /** Diff data v1↔v2 cargada SSR cuando initialRevising · null → fetch on demand
   * cuando el usuario abre el drawer click "Crear revisión v2 →" del sidebar
   * generated. */
  initialDiffData?: PdfV2RevisionData | null;
}

export function PdfView({
  quoteId,
  quote,
  calculation,
  trace,
  envioSeed,
  pdfDateIso,
  pieces,
  proyecto,
  initialGenerated = null,
  initialRevising = false,
  initialDiffData = null,
}: Props) {
  const { state, update } = usePdfForm({
    vigenciaDias: calculation.datosPdf.vigenciaDias,
    anticipoPct: calculation.datosPdf.anticipoPct,
    plazo: calculation.datosPdf.plazo,
    envio: envioSeed,
    notas: "",
  });
  const [chatOpen, setChatOpen] = useState(false);
  // Sprint 4 paso-5-confirmar-modal · mockup 19. Marina abre el modal con el
  // botón "Generar PDF v1 →" del sidebar · ESC o "Cancelar" lo cierran.
  // "Generar v1 →" del modal también cierra acá (visual-only) · el flujo de
  // generación real + transición a estado generado viene en el sub-PR
  // siguiente del mockup 20 (paso-5-c-generado).
  const [confirmOpen, setConfirmOpen] = useState(false);
  // Sprint 4 paso-5-c-generado · estado del PDF generado. SSR-seedeado cuando
  // el quoteId resuelve a status="sent" (mock: suffix `-GENERATED`). El click
  // "Generar v1 →" del modal puebla esto post-success y dispara la transición
  // visual A → C sin reload de página.
  const [generated, setGenerated] = useState<PdfGeneratedInfo | null>(initialGenerated);
  const isGenerated = generated !== null;

  // Sprint 4 paso-5-d-revision-v2 (mockup 21) · estado D = revisión v2 en curso.
  // SSR-seedeado cuando quoteId termina en `-REVISING`. Click "Crear revisión v2 →"
  // del sidebar generated también lo activa (fetch on demand del diff).
  const [revising, setRevising] = useState<boolean>(initialRevising);
  const [diffData, setDiffData] = useState<PdfV2RevisionData | null>(initialDiffData);
  const [confirmV2Open, setConfirmV2Open] = useState(false);
  // Carga lazy del diff cuando el usuario abre el drawer sin SSR-seed.
  const handleCreateV2 = async () => {
    if (!diffData) {
      try {
        const data = await getPdfV2DiffData(quoteId);
        setDiffData(data);
      } catch {
        // fallback gracioso: igual abrimos el drawer con diff vacío
        setDiffData({ rows: [], summary: [], diffCount: 0, unchangedCount: 0 });
      }
    }
    setRevising(true);
  };
  const handleCancelRevising = () => {
    setRevising(false);
    setConfirmV2Open(false);
  };

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
  // Filenames con suffix " v2" para el modal de confirmación v2 (mockup 21).
  const pdfFilenameV2 = useMemo(
    () => pdfFilename.replace(/\.pdf$/i, " v2.pdf"),
    [pdfFilename],
  );
  const xlsxFilenameV2 = useMemo(
    () => xlsxFilename.replace(/\.xlsx$/i, " v2.xlsx"),
    [xlsxFilename],
  );

  return (
    <div
      data-testid="pdf-view"
      data-chat-open={chatOpen}
      data-state={revising ? "D" : isGenerated ? "C" : "A"}
      // Grid 2-col (estado A/C) o 3-col (estado D · drawer 400px lateral).
      // Inline para no modificar el `.body.no-chat` del chrome shell del Sprint 3.
      // El chat es overlay fixed (heredado del PR #465 fix-up #2) · no ocupa columna.
      style={{
        display: "grid",
        gridTemplateColumns: revising ? "1fr 360px 400px" : "1fr 360px",
        gap: 24,
        minHeight: 0,
      }}
    >
      <div className="col">
        <div className="section-head">
          <div>
            <div className="meta">Paso 5 de 5 · Presupuesto PDF</div>
            <h2>{isGenerated || revising ? "Presupuesto generado" : "Preview del presupuesto"}</h2>
            <div className="vc-wrap">
              {revising ? (
                <>
                  <span className="version-chip final" data-testid="version-chip-v1">
                    <span className="dot" />v1 · oficial
                  </span>
                  <span className="version-chip draft" data-testid="version-chip-v2">
                    <span className="dot" />v2 · borrador
                  </span>
                  <span className="status-mini">
                    comparando cambios · v1 sigue activa hasta generar v2
                  </span>
                </>
              ) : (
                <>
                  <span
                    className={`version-chip ${isGenerated ? "final" : "draft"}`}
                    data-testid="version-chip"
                  >
                    <span className="dot" />
                    {isGenerated ? "v1 · enviado" : "v1 · borrador"}
                  </span>
                  <span className="status-mini">
                    {isGenerated
                      ? `guardado en /quotes/2026/ · hace 2 min`
                      : "aún no enviado"}
                  </span>
                </>
              )}
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

        {revising && generated && (
          <PdfGenBanner
            variant="amber-revision"
            revisionSub="v1 (enviada hace 2 días) sigue siendo la versión oficial. Esto es borrador editable."
            traceId={generated.traceId}
          />
        )}
        {!revising && isGenerated && generated && (
          <PdfGenBanner
            variant="green"
            generatedAtDisplay={generated.generatedAtDisplay}
            generatedBy={generated.generatedBy}
            traceId={generated.traceId}
          />
        )}

        <IaAuditBanner quoteId={quoteId} />

        <div className="pdf-stage">
          <div className="pdf-iframe-wrap">
            <PdfPreviewDoc
              quote={quote}
              calculation={calculation}
              trace={trace}
              state={state}
              fechaFmt={fechaFmt}
              pieces={pieces}
              proyecto={proyecto}
            />
          </div>
        </div>

        <div className="pdf-stage-helper">Vista previa a tamaño real · A4 · página 1 de 1</div>
      </div>

      {isGenerated && generated ? (
        <PdfSidebarGenerated
          baseFilename={pdfFilename.replace(/\.pdf$/i, "")}
          info={generated}
          trace={trace}
          onCreateV2={handleCreateV2}
        />
      ) : (
        <PdfSidebar
          pdfFilename={pdfFilename}
          xlsxFilename={xlsxFilename}
          state={state}
          onChange={update}
          trace={trace}
          onGenerate={() => setConfirmOpen(true)}
        />
      )}

      {revising && diffData && (
        <PdfDiffDrawer
          rows={diffData.rows}
          summary={diffData.summary}
          diffCount={diffData.diffCount}
          unchangedCount={diffData.unchangedCount}
          onClose={() => setRevising(false)}
          onCancel={handleCancelRevising}
          onGenerateV2={() => setConfirmV2Open(true)}
          generating={confirmV2Open}
        />
      )}

      {confirmV2Open && diffData && (
        <PdfConfirmV2Modal
          pdfFilename={pdfFilenameV2}
          xlsxFilename={xlsxFilenameV2}
          changeSummary={diffData.summary}
          onCancel={() => setConfirmV2Open(false)}
          onConfirm={async () => {
            const info = await triggerPdfV2Generation(quoteId);
            setGenerated(info);
            setRevising(false);
            setConfirmV2Open(false);
          }}
        />
      )}

      {chatOpen && <PdfChatPanel quoteId={quoteId} onClose={() => setChatOpen(false)} />}

      {confirmOpen && (
        <PdfConfirmModal
          pdfFilename={pdfFilename}
          xlsxFilename={xlsxFilename}
          onCancel={() => setConfirmOpen(false)}
          onConfirm={async () => {
            // Sprint 4 paso-5-c-generado · dispara la generación real (mock)
            // y transiciona a estado C en success. Si throw → el modal renderea
            // banner error + Reintentar.
            const info = await triggerPdfGeneration(quoteId);
            setGenerated(info);
            setConfirmOpen(false);
          }}
        />
      )}
    </div>
  );
}
