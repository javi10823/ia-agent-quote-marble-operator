/**
 * Catálogo · import Dux · sub-PR 22.2.b catalogo-and-dux-importer-ui.
 *
 * Full page del importador Dux · 3 estados (upload → preview → apply).
 * El backend genera backups automáticos al aplicar (safety net). Toda la
 * lógica vive en el component cliente (multipart + estado de máquina).
 */
import Link from "next/link";
import { CatalogImport } from "@/components/catalog/CatalogImport";

export default function CatalogoImportPage() {
  return (
    <div className="catalogo-v2">
      <div className="topbar">
        <div className="crumbs">
          <Link href="/catalogo">Catálogo</Link>
          <span className="sep">/</span>
          <span className="now">Importar desde Dux</span>
        </div>
      </div>
      <div className="body" data-testid="catalogo-import-page">
        <CatalogImport />
      </div>
    </div>
  );
}
