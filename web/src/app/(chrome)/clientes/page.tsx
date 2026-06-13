/**
 * Clientes · placeholder · Sprint 4 sidebar-and-navigation-fix.
 *
 * Cierra ruta 404. Backend no expone CRUD de clientes todavía · sub-PR
 * posterior agrega endpoints + vista.
 */
export default function ClientesPage() {
  return (
    <>
      <div className="topbar">
        <div className="crumbs">
          <span className="now">Clientes</span>
        </div>
      </div>
      <div className="body" data-testid="clientes-placeholder">
        <p>Próximamente · UI de gestión de clientes.</p>
        <p style={{ color: "var(--ink-mute)", fontSize: 12, marginTop: 8 }}>
          Backend sin endpoints de clientes todavía · sub-PR posterior los agrega.
        </p>
      </div>
    </>
  );
}
