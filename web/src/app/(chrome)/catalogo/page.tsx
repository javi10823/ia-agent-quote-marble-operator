/**
 * Catálogo · placeholder · Sprint 4 sidebar-and-navigation-fix.
 *
 * Cierra ruta 404 que el item del Sidebar generaba. Backend ya expone
 * `GET /api/catalog` con los 15 JSONs de materiales/MO/sinks. Sub-PR
 * posterior construye la vista de gestión.
 */
export default function CatalogoPage() {
  return (
    <>
      <div className="topbar">
        <div className="crumbs">
          <span className="now">Catálogo</span>
        </div>
      </div>
      <div className="body" data-testid="catalogo-placeholder">
        <p>Próximamente · UI de gestión de catálogos.</p>
        <p style={{ color: "var(--ink-mute)", fontSize: 12, marginTop: 8 }}>
          Backend ya expone <code>GET /api/catalog</code>. Sub-PR posterior construye la vista.
        </p>
      </div>
    </>
  );
}
