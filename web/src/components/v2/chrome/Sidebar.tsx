/**
 * Sidebar v2 — chrome shell.
 *
 * Versión React de la sidebar que `chrome.js` (legacy DOM injector)
 * inyectaba en los mockups. Reusa las clases CSS de operator-shared.css
 * (`.sidebar`, `.brand`, `.nav-h`, `.nav-i`) — NO redefinimos estilos.
 *
 * Sprint 2 chrome-refactor: nav items son `<div>` no clickeables
 * (no hay routing real entre secciones todavía). El item actual
 * (Presupuestos) tiene la clase `.on` para el highlight. Click
 * handlers + Link real vienen en sub-PRs siguientes.
 */
export function Sidebar() {
  return (
    <aside className="sidebar">
      {/* Brand · "D'Angelo Operator" en serif itálica */}
      <div className="brand">
        <span className="dot" />
        D&apos;Angelo Operator
      </div>

      {/* Sección principal */}
      <div className="nav-h">Principal</div>
      <div className="nav-i on" data-v2-nav="quotes">
        <span>Presupuestos</span>
        <span className="badge">18</span>
      </div>
      <div className="nav-i" data-v2-nav="clients">
        <span>Clientes</span>
        <span className="badge">42</span>
      </div>

      {/* Sección sistema */}
      <div className="nav-h">Sistema</div>
      <div className="nav-i" data-v2-nav="catalog">
        <span>Catálogo</span>
      </div>
      <div className="nav-i" data-v2-nav="settings">
        <span>Configuración</span>
      </div>

      {/* Spacer empuja el CTA + avatar al fondo */}
      <div style={{ flex: 1 }} />

      {/* CTA "+ Nuevo presupuesto" · placeholder no clickeable */}
      <div
        className="nav-i"
        style={{
          border: "1px dashed var(--line-strong)",
          justifyContent: "center",
          color: "var(--accent)",
        }}
        data-v2-nav="new-quote"
      >
        + Nuevo presupuesto
      </div>

      {/* User avatar · "M" de Marina */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: 10,
          marginTop: 6,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 999,
            background: "var(--surface-2)",
            display: "grid",
            placeItems: "center",
            fontFamily: "var(--mono)",
            fontSize: 11,
            color: "var(--ink-soft)",
          }}
        >
          M
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>Marina · operadora</div>
      </div>
    </aside>
  );
}
