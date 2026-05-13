/**
 * Hook del dashboard · Sprint 2.5.
 *
 * Coordina:
 *   - load inicial de quotes + KPIs
 *   - filtros (statuses + search + kpi pre-filter)
 *   - re-fetch cuando cambian filtros
 *   - AbortController por fetch en curso
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

export type KpiFilter = "expire-soon" | "no-response" | null;

export function useDashboard() {
  const [quotes, setQuotes] = useState<DashboardQuote[]>([]);
  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [statuses, setStatuses] = useState<Set<DashboardStatus>>(new Set());
  const [search, setSearch] = useState<string>("");
  const [kpiFilter, setKpiFilter] = useState<KpiFilter>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const fetchAbortRef = useRef<AbortController | null>(null);

  // KPIs sólo se cargan una vez al mount
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
      kpi: kpiFilter ?? undefined,
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
  }, [statuses, search, kpiFilter]);

  const toggleStatus = useCallback((status: DashboardStatus) => {
    setKpiFilter(null); // filtro manual cancela KPI pre-filter
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }, []);

  const setOnlyStatus = useCallback((status: DashboardStatus | null) => {
    setKpiFilter(null);
    setStatuses(status ? new Set([status]) : new Set());
  }, []);

  const toggleKpi = useCallback((kpi: Exclude<KpiFilter, null>) => {
    setStatuses(new Set()); // KPI pre-filter cancela filtros manuales
    setKpiFilter((prev) => (prev === kpi ? null : kpi));
  }, []);

  const clearAll = useCallback(() => {
    setStatuses(new Set());
    setSearch("");
    setKpiFilter(null);
  }, []);

  return {
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
  };
}
