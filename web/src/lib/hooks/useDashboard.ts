/**
 * Hook del dashboard.
 *
 * Coordina:
 *   - load inicial de quotes + KPIs (KPIs todavía expone counts para los
 *     chips · NO se rendereaa como KpiCard band)
 *   - filtros multi-select por status (Set) + search
 *   - re-fetch cuando cambian filtros
 *   - AbortController por fetch en curso
 *
 * Sprint 4 dashboard-redesign cleanup (lección #63 atacar deuda en el
 * mismo sub-PR): removidos `toggleKpi` + `kpiFilter` state · single
 * consumer era KpiCard que se eliminó. `setOnlyStatus` también removido ·
 * FilterChips ahora es multi-select directo via `toggleStatus`.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getDashboardKpis,
  listQuotes,
  type DashboardKpis,
  type DashboardQuote,
  type DashboardStatus,
  type ListQuotesFilters,
} from "../api";

export function useDashboard() {
  const [quotes, setQuotes] = useState<DashboardQuote[]>([]);
  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [statuses, setStatuses] = useState<Set<DashboardStatus>>(new Set());
  const [search, setSearch] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const fetchAbortRef = useRef<AbortController | null>(null);

  // KPIs sólo se cargan una vez al mount (counts para los chips · sin KPI band)
  useEffect(() => {
    let aborted = false;
    const ctrl = new AbortController();
    getDashboardKpis({ signal: ctrl.signal })
      .then((data) => {
        if (!aborted) setKpis(data);
      })
      .catch((err) => {
        if (aborted || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(err instanceof Error ? err.message : "Error KPIs");
      });
    return () => {
      aborted = true;
      ctrl.abort();
    };
  }, []);

  // Quotes se re-fetchean ante cualquier cambio de filtros
  useEffect(() => {
    fetchAbortRef.current?.abort();
    const ctrl = new AbortController();
    fetchAbortRef.current = ctrl;
    setLoading(true);
    setError(null);

    const filters: ListQuotesFilters = {
      statuses: statuses.size > 0 ? Array.from(statuses) : undefined,
      search: search || undefined,
    };

    listQuotes(filters, { signal: ctrl.signal })
      .then((data) => {
        setQuotes(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Error cargando quotes");
        setLoading(false);
      });

    return () => ctrl.abort();
  }, [statuses, search]);

  const toggleStatus = useCallback((status: DashboardStatus) => {
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setStatuses(new Set());
    setSearch("");
  }, []);

  /** True cuando hay al menos 1 filtro activo (chips o search). Usado para
   * mostrar/ocultar el botón "Limpiar". */
  const hasActiveFilters = statuses.size > 0 || search.length > 0;

  return {
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
  };
}
