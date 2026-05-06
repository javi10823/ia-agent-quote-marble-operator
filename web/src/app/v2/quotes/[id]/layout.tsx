/**
 * Layout del quote v2 — chrome shell aplicado.
 *
 * Wraps las 5 rutas de pasos (`/v2/quotes/[id]/{brief,contexto,
 * despiece,calculo,pdf}`) con sidebar + topbar + qhead + stepper.
 * Estructura HTML matchea la que `chrome.js` legacy inyectaba en
 * los mockups: `.page > {.sidebar, .main > .topbar/.qhead/.stepper/.body}`.
 *
 * Viewport-fixed (Master §20.2): el media query de operator-shared.css
 * `@media (min-width: 1024px)` hace que `.page` sea altura fija
 * de viewport y `.body` sea el único elemento scrolleable.
 *
 * Sprint 2: usa CANONICAL_QUOTE hardcodeado (Master §13). El `id`
 * del path NO se resuelve a un fetch real — eso es state management,
 * va en sub-PRs siguientes.
 */
import { Sidebar } from "@/components/v2/chrome/Sidebar";
import { Topbar } from "@/components/v2/chrome/Topbar";
import { Qhead } from "@/components/v2/chrome/Qhead";
import { Stepper } from "@/components/v2/chrome/Stepper";
import { CANONICAL_QUOTE } from "@/lib/v2/mocks/canonicalQuote";

export default function V2QuoteLayout({
  children,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  // En Sprint 2, ignoramos `params.id` y siempre usamos el quote canon.
  // El sub-PR de state management resolverá el id contra la API real.
  const quote = CANONICAL_QUOTE;

  return (
    <div className="page">
      <Sidebar />
      <main className="main">
        <Topbar quote={quote} />
        <Qhead quote={quote} />
        <Stepper />
        <div className="body no-chat">{children}</div>
      </main>
    </div>
  );
}
