/**
 * Chrome shell light para `/v2/quotes/new` (paso 1).
 *
 * No hay quote todavía, entonces NO renderea Qhead ni Stepper —
 * solo Sidebar + Topbar minimalista + body. Esto evita reutilizar
 * el layout `[id]/layout.tsx` que asume CANONICAL_QUOTE.
 *
 * Reusa las clases legacy de operator-shared.css (.page, .main,
 * .topbar, .crumbs, .body.no-chat) sin modificar.
 */
import Link from "next/link";
import { Sidebar } from "@/components/v2/chrome/Sidebar";

export default function NewQuoteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="page">
      <Sidebar />
      <main className="main">
        <div className="topbar">
          <div className="crumbs">
            <Link href="/v2">Presupuestos</Link>
            <span className="sep">/</span>
            <span className="now">Nuevo</span>
          </div>
        </div>
        <div className="body no-chat">{children}</div>
      </main>
    </div>
  );
}
