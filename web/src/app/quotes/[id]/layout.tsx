/**
 * Layout del quote · chrome shell aplicado.
 *
 * Wraps las 5 rutas de pasos (`/quotes/[id]/{brief,contexto,
 * despiece,calculo,pdf}`) con sidebar + topbar + qhead + stepper.
 *
 * Sprint 2.5 fix-up #2: server component async que resuelve el quote
 * via `getQuoteMetadata(params.id)` (lookup contra DASHBOARD_QUOTES).
 * Antes usaba CANONICAL_QUOTE hardcodeado — provocaba que el Qhead
 * y Topbar siempre mostraran datos de PRES-018 sin importar la URL.
 */
import { Sidebar } from "@/components/chrome/Sidebar";
import { Topbar } from "@/components/chrome/Topbar";
import { Qhead } from "@/components/chrome/Qhead";
import { Stepper } from "@/components/chrome/Stepper";
import { AuditTray } from "@/components/observability/AuditTray";
import { getQuoteMetadata } from "@/lib/api";

export default async function QuoteLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  const quote = await getQuoteMetadata(params.id);

  return (
    <div className="page">
      <Sidebar />
      <main className="main">
        <Topbar quote={quote} />
        {/* Sprint 3 observability · banner top global gateado por
            body[data-audit="on"] (CSS · useAuditMode). */}
        <AuditTray quoteId={params.id} />
        <Qhead quote={quote} />
        <Stepper />
        <div className="body no-chat">{children}</div>
      </main>
    </div>
  );
}
