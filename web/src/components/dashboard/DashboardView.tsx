/**
 * Container del dashboard · Sprint 2.5.
 *
 * Render único que adapta layout via CSS responsive:
 *   - Desktop (≥768px): KPI band + sidebar filtros + tabla
 *   - Mobile  (<768px):  chips filter horizontales + lista vertical + FAB
 *
 * Decisión: una sola implementación con clases legacy responsive
 * (`.mfilter-chips` ya tiene su propio breakpoint en operator-shared.css).
 * Las dos vistas se renderean siempre pero se ocultan via inline media
 * query (más simple que useMediaQuery con SSR hydration). El layout
 * `.dashboard-desktop` se muestra ≥768px, `.dashboard-mobile` muestra
 * <768px.
 */
"use client";

import Link from "next/link";
import { useDashboard } from "@/lib/hooks/useDashboard";
import type { DashboardStatus } from "@/lib/api";
import { FilterChips } from "./FilterChips";
import { KpiCard } from "./KpiCard";
import { QuoteListItem } from "./QuoteListItem";
import { QuoteTable } from "./QuoteTable";

const STATUS_FILTERS: { id: DashboardStatus; label: string }[] = [
  { id: "draft", label: "Borrador" },
  { id: "sent", label: "Enviado" },
  { id: "expired", label: "Vencido" },
  { id: "lost", label: "Perdido" },
];

export function DashboardView() {
  const {
    quotes,
    kpis,
    statuses,
    search,
    kpiFilter,
    loading,
    error,
    setSearch,
    toggleStatus,
    setOnlyStatus,
    toggleKpi,
    clearAll,
  } = useDashboard();

  // Filtro activo para mobile chips (1-status max, o null para "Todos")
  const mobileActive: DashboardStatus | null = statuses.size === 1 ? Array.from(statuses)[0] : null;

  if (error) {
    return (
      <section style={{ padding: "32px 24px" }} data-testid="dashboard-error">
        <p style={{ color: "var(--error)" }}>{error}</p>
      </section>
    );
  }

  return (
    <section data-testid="dashboard">
      {/* ─────── DESKTOP ─────── */}
      <section
        data-testid="dashboard-desktop"
        style={{ padding: "32px 32px 24px" }}
        className="dashboard-desktop"
      >
        <header
          className="dashboard-head"
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 24,
            marginBottom: 24,
          }}
        >
          <div className="dh-meta" style={{ flex: 1 }}>
            <div className="eyebrow">Presupuestos</div>
            <h1
              className="font-serif"
              style={{
                fontStyle: "italic",
                fontSize: 28,
                margin: "4px 0 6px",
                letterSpacing: "-0.3px",
              }}
            >
              Hola Marina
            </h1>
            {kpis && (
              <div style={{ color: "var(--ink-soft)", fontSize: 13 }}>
                Tenés <strong>{kpis.pendingAction}</strong> presupuesto
                {kpis.pendingAction === 1 ? "" : "s"} que requier
                {kpis.pendingAction === 1 ? "e" : "en"} acción
              </div>
            )}
          </div>
          <Link href="/quotes/new" className="btn primary" data-testid="cta-new-quote">
            + Nuevo presupuesto
          </Link>
        </header>

        {kpis && (
          <section
            className="kpi-band"
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 16,
              marginBottom: 24,
            }}
          >
            <KpiCard
              testId="kpi-expire-soon"
              label="Vencidos próximos 7 días"
              value={kpis.expireSoon}
              sub="Acción: renovar vigencia o reenviar"
              variant="urgent"
              active={kpiFilter === "expire-soon"}
              onClick={() => toggleKpi("expire-soon")}
            />
            <KpiCard
              testId="kpi-no-response"
              label="Enviados sin respuesta >5 días"
              value={kpis.noResponse}
              sub="Acción: follow-up por WhatsApp"
              variant="warn"
              active={kpiFilter === "no-response"}
              onClick={() => toggleKpi("no-response")}
            />
          </section>
        )}

        <section
          className="dash-body"
          style={{
            display: "grid",
            gridTemplateColumns: "220px 1fr",
            gap: 24,
            alignItems: "start",
          }}
        >
          <aside
            className="dash-filters"
            style={{ display: "flex", flexDirection: "column", gap: 20 }}
          >
            <div className="filter-group">
              <div
                className="filter-lbl font-mono"
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                  color: "var(--ink-mute)",
                  marginBottom: 8,
                }}
              >
                Buscador
              </div>
              <input
                type="text"
                placeholder="Cliente…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                data-testid="search-input"
                className="input"
                style={{ width: "100%", padding: "8px 10px" }}
              />
            </div>
            <div className="filter-group">
              <div
                className="filter-lbl font-mono"
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                  color: "var(--ink-mute)",
                  marginBottom: 8,
                }}
              >
                Estado
              </div>
              {STATUS_FILTERS.map((s) => {
                const checked = statuses.has(s.id);
                return (
                  <label
                    key={s.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "4px 0",
                      cursor: "pointer",
                      color: checked ? "var(--ink)" : "var(--ink-soft)",
                    }}
                  >
                    <input
                      type="checkbox"
                      data-testid={`status-filter-${s.id}`}
                      checked={checked}
                      onChange={() => toggleStatus(s.id)}
                    />
                    <span style={{ fontSize: 13 }}>{s.label}</span>
                    <span
                      className="font-mono"
                      style={{
                        marginLeft: "auto",
                        fontSize: 11,
                        color: "var(--ink-mute)",
                      }}
                    >
                      {kpis?.counts[s.id] ?? 0}
                    </span>
                  </label>
                );
              })}
            </div>
            <button
              type="button"
              className="btn ghost sm"
              onClick={clearAll}
              data-testid="clear-filters"
            >
              Limpiar filtros
            </button>
          </aside>

          <div className="dash-main">
            <div
              className="dash-toolbar"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: 12,
                fontSize: 12,
                color: "var(--ink-mute)",
              }}
            >
              <div data-testid="results-count">
                <strong>{quotes.length}</strong> resultado
                {quotes.length === 1 ? "" : "s"}
              </div>
              <div className="font-mono">ordenado por última actividad ↓</div>
            </div>
            <QuoteTable quotes={quotes} loading={loading} />
          </div>
        </section>
      </section>

      {/* ─────── MOBILE ─────── */}
      <section
        data-testid="dashboard-mobile"
        className="dashboard-mobile"
        style={{ padding: "20px 0 80px" }}
      >
        <header style={{ padding: "0 16px 12px" }}>
          <div
            className="font-mono"
            style={{
              fontSize: 10,
              color: "var(--ink-mute)",
              letterSpacing: "0.5px",
              textTransform: "uppercase",
            }}
          >
            Presupuestos
          </div>
          <h1
            className="font-serif"
            style={{
              fontStyle: "italic",
              fontSize: 22,
              margin: "4px 0",
              letterSpacing: "-0.3px",
            }}
          >
            Hola Marina
          </h1>
        </header>

        {kpis && (
          <FilterChips counts={kpis.counts} active={mobileActive} onSelect={setOnlyStatus} />
        )}

        <div data-testid="mobile-list" style={{ marginTop: 8 }}>
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

        <Link
          href="/quotes/new"
          data-testid="mobile-fab"
          className="btn primary"
          style={{
            position: "fixed",
            right: 16,
            bottom: 24,
            zIndex: 10,
            boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
          }}
        >
          + Nuevo
        </Link>
      </section>
    </section>
  );
}
