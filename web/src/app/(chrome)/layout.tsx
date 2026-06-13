/**
 * Chrome layout · route group `(chrome)` · Sprint 4 sidebar-and-navigation-fix.
 *
 * Cierra deuda heredada Sprint 2.5 chrome-refactor: el promote de
 * `v2/page.tsx` a `app/page.tsx` dejó el dashboard SIN sidebar porque
 * no había layout entre root y page. Resultado: Sidebar solo aparecía
 * en /quotes/* (que tienen sus propios layouts) y no en /.
 *
 * Solución: route group `(chrome)` que NO altera URLs (paréntesis =
 * grouping silencioso) pero comparte este layout con / · /catalogo ·
 * /configuracion · /clientes. Cada page del grupo hereda Sidebar
 * global.
 *
 * Caveat HTML5: `<main>` va acá (chrome) porque DashboardView pasó a
 * `<section>` para evitar `<main>` anidado. Los /quotes/* siguen
 * teniendo su propio layout con `<main>` (route distinta · no entra
 * al grupo).
 */
import { Sidebar } from "@/components/chrome/Sidebar";

export default function ChromeLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="page">
      <Sidebar />
      <main className="main">{children}</main>
    </div>
  );
}
