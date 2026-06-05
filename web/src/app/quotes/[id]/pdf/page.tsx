/**
 * Paso 5 · PDF preview · Sprint 4 paso-5-pdf-preview (mockup 18).
 *
 * Server Component que carga en paralelo: metadata del quote, calculation
 * del paso-4, contexto del paso-2 (para auto-fill de "Datos de envío"),
 * y trace del PDF. Todo con Bearer token SSR del PR #469.
 *
 * Fallback gracioso (lección Sprint 3): si alguna carga falla, degradamos
 * a placeholders en lugar de crashear el Server Component (idem fix-up
 * SSR del PR #464).
 */
import {
  getCalculationForQuote,
  getContextForQuote,
  getPdfTrace,
  getQuoteMetadata,
  listPiecesForQuote,
} from "@/lib/api";
import { getServerToken } from "@/lib/auth-server";
import { getEnvioSeed } from "@/lib/pdfFormat";
import { PdfView } from "@/components/pdf/PdfView";

export default async function PdfPage({ params }: { params: { id: string } }) {
  const bearerToken = getServerToken();
  // Cargas en paralelo. `Promise.allSettled` evita que un fallo individual
  // rompa toda la página · degradamos campos faltantes.
  // Fix-up #1: agregamos `listPiecesForQuote` para las sub-filas `row-piece`
  // del PDF (template HTML del backend las renderea con cada pieza del despiece).
  const [metaR, calcR, ctxR, traceR, piecesR] = await Promise.allSettled([
    getQuoteMetadata(params.id, { bearerToken }),
    getCalculationForQuote(params.id),
    getContextForQuote(params.id),
    getPdfTrace(params.id),
    listPiecesForQuote(params.id),
  ]);

  if (metaR.status === "rejected" || calcR.status === "rejected" || traceR.status === "rejected") {
    return (
      <div className="col" data-testid="pdf-error">
        <div className="section-head">
          <h2>No pude cargar el PDF preview</h2>
        </div>
        <p className="font-mono" style={{ fontSize: 12, color: "var(--error)" }}>
          Faltó alguna de las cargas previas (quote / cálculo / trace). Volvé al paso 4 para
          recalcular o reintentá esta página.
        </p>
      </div>
    );
  }

  const quote = metaR.value;
  const calculation = calcR.value;
  const trace = traceR.value;
  const ctx = ctxR.status === "fulfilled" ? ctxR.value : null;
  const envioSeed = ctx
    ? getEnvioSeed({ cliente: ctx.cliente?.value ?? null, localidad: ctx.localidad?.value ?? null })
    : "";
  // Fix-up #1: piezas para sub-filas row-piece + tipologia para campo
  // "Proyecto" del grid cliente (template HTML del backend).
  const pieces = piecesR.status === "fulfilled" ? piecesR.value.pieces : [];
  const proyecto =
    (ctx?.tipologia?.value && String(ctx.tipologia.value)) || quote.client || "";

  // Sprint 4 paso-5 · `pdfDateIso` calculado server-side y pasado como
  // string al client → evita hydration mismatch por `new Date()` corriendo
  // con timestamps distintos en server vs client (T1 vs T2 difieren en ms
  // y pueden caer en segundos/minutos distintos → format dd.mm.yyyy puede
  // diferir en la frontera de día). El client lo parsea con `new Date(iso)`
  // que es determinístico.
  const pdfDateIso = new Date().toISOString();

  return (
    <PdfView
      quoteId={params.id}
      quote={quote}
      calculation={calculation}
      trace={trace}
      envioSeed={envioSeed}
      pdfDateIso={pdfDateIso}
      pieces={pieces}
      proyecto={proyecto}
    />
  );
}
