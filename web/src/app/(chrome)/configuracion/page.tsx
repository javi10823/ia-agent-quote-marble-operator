/**
 * Configuración · placeholder · Sprint 4 sidebar-and-navigation-fix.
 *
 * Cierra ruta 404. Defaults editables (zócalo, alzada, plazo, anticipo,
 * IVA toggles, etc.) vienen en sub-PR posterior de UI editable.
 */
export default function ConfiguracionPage() {
  return (
    <>
      <div className="topbar">
        <div className="crumbs">
          <span className="now">Configuración</span>
        </div>
      </div>
      <div className="body" data-testid="configuracion-placeholder">
        <p>Próximamente · UI de configuración.</p>
        <p style={{ color: "var(--ink-mute)", fontSize: 12, marginTop: 8 }}>
          Defaults editables (zócalo, alzada, plazo, anticipo) en sub-PR posterior.
        </p>
      </div>
    </>
  );
}
