/**
 * Container del dashboard · Sprint 4 dashboard-redesign (sub-PR 22.1.b).
 *
 * Rediseño según 5 decisiones Javi:
 *   1. Filter chips multi-select (multiple chips activos simultáneo)
 *   2. Buscador responsive (desktop + mobile · antes no había mobile)
 *   3. Header 2 filas: saludo+search+CTA · meta count debajo
 *   4. KPIs PERMANENTES fuera (KpiCard eliminado · sub-PR cleanup paralelo)
 *   5. Columnas tabla mantenidas (sin cambios a QuoteTable)
 *
 * Cambios estructurales vs Sprint 2.5:
 *   - Single layout responsive (NO dual render `.dashboard-mobile` + `.dashboard-desktop`)
 *     · cambio de pixel breakpoint via CSS in globals.css (≤767 mobile)
 *   - Search en HEADER (antes en aside lateral)
 *   - Filter chips bajo header (antes checkbox vertical en aside)
 *   - Tabla full-width (antes grid 220px + 1fr con aside)
 *   - "Limpiar" condicional (solo cuando hay filtros activos · `hasActiveFilters`)
 *   - Mobile lista de cards usa el MISMO QuoteListItem que antes
 *
 * CSS scope:
 *   - operator-shared.css: INTACTO estricto (0 cambios)
 *   - globals.css: +6 LOC media query para responsive del nuevo layout
 *   - Clases reusadas: `.mfilter-chips`, `.mfilter-chip.active`, `.quote-table`,
 *     `.btn.primary`, `.btn.ghost.sm`, `.eyebrow`, `.font-serif`, `.font-mono`
 */
"use client";

import Link from "next/link";
import { useDashboard } from "@/lib/hooks/useDashboard";
import { FilterChips } from "./FilterChips";
import { QuoteListItem } from "./QuoteListItem";
import { QuoteTable } from "./QuoteTable";

export function DashboardView() {
  const {
    quotes,
    kpis,
    statuses,
    search,
    loading,
    error,
    hasActiveFilters,
    setSearch,
    toggleStatus,
    clearAll,
  } = useDashboard();

  if (error) {
    return (
      <section style={{ padding: "32px 24px" }} data-testid="dashboard-error">
        <p style={{ color: "var(--error)" }}>{error}</p>
      </section>
    );
  }

  // Counts seguros para los chips mientras KPIs cargan (evita layout shift)
  const counts = kpis?.counts ?? { all: 0, draft: 0, sent: 0, expired: 0, lost: 0 };

  return (
    <section data-testid="dashboard" className="dashboard-v2">
      {/* ─────── HEADER · 2 filas ─────── */}
      <header className="dashboard-head" data-testid="dashboard-head">
        {/* Fila 1: saludo · buscador · CTA */}
        <div className="row-greet-actions">
          <div className="dh-greet">
            <div className="eyebrow">Presupuestos</div>
            <h1
              className="font-serif"
              style={{
                fontStyle: "italic",
                fontSize: 28,
                margin: "4px 0 0",
                letterSpacing: "-0.3px",
              }}
            >
              Hola Marina
            </h1>
          </div>
          <div className="dh-actions">
            <input
              type="text"
              placeholder="Buscar cliente…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="search-input"
              className="input"
              style={{
                padding: "8px 12px",
                minWidth: 240,
              }}
            />
            <Link href="/quotes/new" className="btn primary" data-testid="cta-new-quote">
              + Nuevo presupuesto
            </Link>
          </div>
        </div>
        {/* Fila 2: meta count */}
        {kpis && (
          <div
            className="dh-meta"
            data-testid="dashboard-meta"
            style={{
              color: "var(--ink-soft)",
              fontSize: 13,
              marginTop: 8,
            }}
          >
            Tenés <strong>{counts.all}</strong> presupuesto
            {counts.all === 1 ? "" : "s"} · ordenados por última actividad ↓
          </div>
        )}
      </header>

      {/* ─────── FILTRO chips + Limpiar ─────── */}
      <div className="dashboard-filterbar" data-testid="dashboard-filterbar">
        <FilterChips counts={counts} active={statuses} onToggle={toggleStatus} />
        {hasActiveFilters && (
          <button
            type="button"
            className="btn ghost sm"
            onClick={clearAll}
            data-testid="clear-filters"
            style={{ marginLeft: 8, flexShrink: 0 }}
          >
            Limpiar
          </button>
        )}
      </div>

      {/* ─────── Results count ─────── */}
      <div
        className="dashboard-results-meta"
        style={{
          padding: "12px 24px 8px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          fontSize: 12,
          color: "var(--ink-mute)",
        }}
      >
        <div data-testid="results-count">
          <strong style={{ color: "var(--ink)", fontWeight: 500 }}>{quotes.length}</strong>{" "}
          resultado{quotes.length === 1 ? "" : "s"}
        </div>
      </div>

      {/* ─────── DESKTOP table · MOBILE cards ─────── */}
      <div className="dashboard-list-desktop" data-testid="dashboard-list-desktop">
        <QuoteTable quotes={quotes} loading={loading} />
      </div>
      <div className="dashboard-list-mobile" data-testid="dashboard-list-mobile">
        {loading && quotes.length === 0 && (
          <div style={{ padding: 16 }}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skel long" style={{ marginBottom: 12 }} />
            ))}
          </div>
        )}
        {!loading && quotes.length === 0 && (
          <p
            className="font-mono"
            style={{
              padding: 24,
              textAlign: "center",
              color: "var(--ink-mute)",
              fontSize: 12,
            }}
            data-testid="mobile-empty"
          >
            No hay presupuestos que cumplan con los filtros.
          </p>
        )}
        {quotes.map((q) => (
          <QuoteListItem key={q.id} quote={q} />
        ))}
      </div>
    </section>
  );
}
