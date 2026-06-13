/**
 * Sidebar v2 · chrome shell.
 *
 * Versión React de la sidebar que `chrome.js` (legacy DOM injector)
 * inyectaba en los mockups. Reusa las clases CSS de operator-shared.css
 * (`.sidebar`, `.brand`, `.nav-h`, `.nav-i`) — NO redefinimos estilos.
 *
 * Sprint 3 auth: botón de logout al pie (Opción 1 · client-side).
 *
 * Sprint 4 sidebar-and-navigation-fix:
 * - Items pasan de `<div>` no-clickeables a `<Link>` de Next.js
 *   (prefetching + SSR + a11y nativa · NO usar button + router.push)
 * - `usePathname()` calcula el `.on` dinámico según la ruta activa
 *   (antes "Presupuestos" siempre hardcoded como activo)
 * - Cierra deuda Sprint 2 chrome-refactor comentada en este header
 *   por 5+ sub-PRs sin atacarse hasta ahora (lección operativa #63)
 */
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
  badge?: string;
  /** Predicate sobre pathname para activar `.on`. Cuando undefined,
   * usa equality estricta con `href`. */
  isActive?: (pathname: string) => boolean;
}

const NAV_PRINCIPAL: NavItem[] = [
  {
    href: "/",
    label: "Presupuestos",
    badge: "18",
    // "/" activa también cuando el operador está dentro de un quote
    // (/quotes/{id}/*) o creando uno (/quotes/new) · contexto sigue
    // siendo "Presupuestos".
    isActive: (p) => p === "/" || p.startsWith("/quotes"),
  },
  {
    href: "/clientes",
    label: "Clientes",
    badge: "42",
    isActive: (p) => p.startsWith("/clientes"),
  },
];

const NAV_SISTEMA: NavItem[] = [
  {
    href: "/catalogo",
    label: "Catálogo",
    isActive: (p) => p.startsWith("/catalogo"),
  },
  {
    href: "/configuracion",
    label: "Configuración",
    isActive: (p) => p.startsWith("/configuracion"),
  },
];

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname() ?? "";

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  function renderItem(item: NavItem) {
    const active = (item.isActive ?? ((p) => p === item.href))(pathname);
    return (
      <Link
        key={item.href}
        href={item.href}
        className={`nav-i${active ? " on" : ""}`}
        data-v2-nav={item.href}
        data-testid={`sidebar-nav-${item.href.replace(/\//g, "") || "home"}`}
        aria-current={active ? "page" : undefined}
      >
        <span>{item.label}</span>
        {item.badge && <span className="badge">{item.badge}</span>}
      </Link>
    );
  }

  return (
    <aside className="sidebar">
      {/* Brand · "D'Angelo Operator" en serif itálica */}
      <div className="brand">
        <span className="dot" />
        D&apos;Angelo Operator
      </div>

      {/* Sección principal */}
      <div className="nav-h">Principal</div>
      {NAV_PRINCIPAL.map(renderItem)}

      {/* Sección sistema */}
      <div className="nav-h">Sistema</div>
      {NAV_SISTEMA.map(renderItem)}

      {/* Spacer empuja el CTA + avatar al fondo */}
      <div style={{ flex: 1 }} />

      {/* CTA "+ Nuevo presupuesto" · Sprint 4 (PR #481 lo wireó).
          Sigue siendo button (no Link) porque el estilo dashed
          override se aplica mejor inline · navega via router. */}
      <button
        type="button"
        className="nav-i"
        style={{
          border: "1px dashed var(--line-strong)",
          justifyContent: "center",
          color: "var(--accent)",
          background: "transparent",
          width: "100%",
          textAlign: "center",
          cursor: "pointer",
          font: "inherit",
        }}
        data-v2-nav="new-quote"
        data-testid="sidebar-new-quote-cta"
        onClick={() => router.push("/quotes/new")}
      >
        + Nuevo presupuesto
      </button>

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

      {/* Logout · Sprint 3 auth */}
      <button
        type="button"
        onClick={handleLogout}
        data-testid="logout-button"
        className="nav-i"
        style={{
          width: "100%",
          background: "transparent",
          border: 0,
          font: "inherit",
          textAlign: "left",
          color: "var(--ink-mute)",
        }}
      >
        <span>Cerrar sesión</span>
      </button>
    </aside>
  );
}
