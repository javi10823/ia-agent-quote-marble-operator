/**
 * Catálogo · lista · sub-PR 22.2.b catalogo-and-dux-importer-ui.
 *
 * Reemplaza el placeholder (#490) por la lista real de los 14 catálogos
 * importables + config. Fetch + search + sort viven en el component
 * cliente (los catálogos son cross-quote · no necesitan SSR aggressive,
 * mismo criterio que /configuracion).
 *
 * Scope CSS: `.catalogo-v2` wrapper · ver globals.css · operator-shared.css
 * INTACTO.
 */
import Link from "next/link";
import { CatalogList } from "@/components/catalog/CatalogList";

export default function CatalogoPage() {
  return (
    <div className="catalogo-v2">
      <div className="topbar">
        <div className="crumbs">
          <span className="now">Catálogo</span>
        </div>
        <Link href="/catalogo/import" className="btn primary" data-testid="catalog-import-cta">
          Importar desde Dux
        </Link>
      </div>
      <div className="body" data-testid="catalogo-page">
        <div className="col">
          <div className="section-head">
            <h2>Catálogos</h2>
            <span className="meta">
              Precios sin IVA · fuente de verdad del cálculo. Para actualizar precios masivos usá
              Importar desde Dux.
            </span>
          </div>
          <CatalogList />
        </div>
      </div>
    </div>
  );
}
