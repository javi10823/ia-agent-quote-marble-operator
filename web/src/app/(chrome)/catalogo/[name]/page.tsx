/**
 * Catálogo · viewer · sub-PR 22.2.b catalogo-and-dux-importer-ui.
 *
 * Viewer JSON read-only + versiones anteriores (backups) con restore.
 * SIN editor manual (decisión Agos · Marina usa Dux import para precios
 * masivos). Fetch en el component cliente.
 */
import Link from "next/link";
import { CatalogViewer } from "@/components/catalog/CatalogViewer";

export default function CatalogoViewerPage({ params }: { params: { name: string } }) {
  const name = decodeURIComponent(params.name);
  return (
    <div className="catalogo-v2">
      <div className="topbar">
        <div className="crumbs">
          <Link href="/catalogo">Catálogo</Link>
          <span className="sep">/</span>
          <span className="now mono">{name}</span>
        </div>
      </div>
      <div className="body" data-testid="catalogo-viewer-page">
        <CatalogViewer name={name} />
      </div>
    </div>
  );
}
