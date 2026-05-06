/**
 * Qhead v2 — header del quote (debajo de Topbar).
 *
 * Reusa clases legacy `.qhead`, `.meta`, `.eyebrow`, `.actions` de
 * operator-shared.css. El `<h1>` usa `font-family: var(--serif)` que
 * con el bridging de globals.css apunta a `var(--font-serif)` ⇒
 * Fraunces serif italic.
 *
 * Sprint 2: action buttons son placeholders sin onClick.
 */
import type { CanonicalQuote } from "@/lib/v2/mocks/canonicalQuote";

interface QheadProps {
  quote: CanonicalQuote;
}

export function Qhead({ quote }: QheadProps) {
  // Formateo m² con coma decimal (locale es-AR)
  const surfaceFmt = quote.material.surface.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <header className="qhead">
      <div className="meta">
        <div className="eyebrow">Presupuesto</div>
        {/* H1 en Fraunces serif italic — fix NICE-TO-HAVE 1 verifica
            que esto NO caiga al fallback Georgia. */}
        <h1>
          {quote.project.address} — {quote.client.name}
        </h1>
        <div className="sub">
          {quote.id} · {quote.material.name} · {surfaceFmt} m²
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
