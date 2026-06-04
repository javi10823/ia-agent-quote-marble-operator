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
import { getQuoteDisplayName, getQuoteDisplaySub } from "@/lib/qheadFallback";

interface QheadProps {
  quote: QuoteHeader;
}

export function Qhead({ quote }: QheadProps) {
  // Sprint 3 qhead-empty-title · cuando el m² es "—" degradado a string en
  // real.ts ssrFallbackHeader (backend no expone m²), `toLocaleString` sobre
  // el string devuelve el mismo string. El helper getQuoteDisplaySub detecta
  // el em-dash y oculta el campo en lugar de renderear "web-XXX · — · — m²".
  const surfaceFmt = quote.m2.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const title = getQuoteDisplayName(quote);
  const sub = getQuoteDisplaySub(quote, surfaceFmt);

  return (
    <header className="qhead">
      <div className="meta">
        <div className="eyebrow">Presupuesto</div>
        <h1 data-testid="qhead-title">{title}</h1>
        <div className="sub" data-testid="qhead-sub">
          {sub}
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
