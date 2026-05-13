/**
 * Qhead v2 — header del quote (debajo de Topbar).
 *
 * Sprint 2.5 fix-up #2: recibe `quote: QuoteHeader` (derivado de
 * DASHBOARD_QUOTES via getQuoteMetadata) en vez de CANONICAL_QUOTE
 * hardcodeado. Ahora respeta params.id de la URL.
 *
 * Reusa clases legacy `.qhead`, `.meta`, `.eyebrow`, `.actions` de
 * operator-shared.css. El `<h1>` usa `font-family: var(--serif)` que
 * con el bridging de globals.css apunta a `var(--font-serif)` ⇒
 * Fraunces serif italic.
 */
import type { QuoteHeader } from "@/lib/api";

interface QheadProps {
  quote: QuoteHeader;
}

export function Qhead({ quote }: QheadProps) {
  const surfaceFmt = quote.m2.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <header className="qhead">
      <div className="meta">
        <div className="eyebrow">Presupuesto</div>
        <h1>
          {quote.clientFull} — {quote.client}
        </h1>
        <div className="sub">
          {quote.id} · {quote.material} · {surfaceFmt} m²
        </div>
      </div>

      <div className="actions">
        <button type="button" className="btn ghost sm">
          Auditoría
        </button>
        <button type="button" className="btn ghost sm">
          Compartir
        </button>
      </div>
    </header>
  );
}
