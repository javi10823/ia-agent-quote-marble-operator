/**
 * CatalogList · sub-PR 22.2.b · lista de catálogos con search + sort.
 *
 * Fetch client-side (GET /api/catalog/ vía api layer · mock/real switch).
 * Orden default por categoría: materiales → granito → servicios → config.
 * Click en fila → /catalogo/[name].
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listCatalogs } from "@/lib/api";
import type { CatalogMeta } from "@/lib/api/types";

type SortKey = "default" | "name" | "item_count" | "last_updated";

/** materiales(0) → granito(1) → servicios(2) → config/otros(3). */
function categoryRank(name: string): number {
  if (name.startsWith("materials-granito")) return 1;
  if (name.startsWith("materials-")) return 0;
  if (["labor", "delivery-zones", "sinks"].includes(name)) return 2;
  return 3;
}

/** dd/mm/yyyy → epoch para ordenar; null/inválido → 0. */
function parseUpdated(s: string | null): number {
  if (!s) return 0;
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s);
  if (!m) return 0;
  return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1])).getTime();
}

export function CatalogList() {
  const [catalogs, setCatalogs] = useState<CatalogMeta[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("default");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listCatalogs();
        if (!cancelled) setCatalogs(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Error desconocido");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    if (!catalogs) return [];
    const q = query.trim().toLowerCase();
    const filtered = q ? catalogs.filter((c) => c.name.toLowerCase().includes(q)) : catalogs;
    const sorted = [...filtered];
    sorted.sort((a, b) => {
      switch (sort) {
        case "name":
          return a.name.localeCompare(b.name);
        case "item_count":
          return b.item_count - a.item_count;
        case "last_updated":
          return parseUpdated(b.last_updated) - parseUpdated(a.last_updated);
        default:
          return categoryRank(a.name) - categoryRank(b.name) || a.name.localeCompare(b.name);
      }
    });
    return sorted;
  }, [catalogs, query, sort]);

  if (error) {
    return (
      <div data-testid="catalog-list-error" role="alert" style={{ color: "var(--error)" }}>
        No pude cargar los catálogos: {error}
      </div>
    );
  }

  if (!catalogs) {
    return (
      <div data-testid="catalog-list-loading" style={{ color: "var(--ink-mute)" }}>
        Cargando catálogos…
      </div>
    );
  }

  return (
    <div data-testid="catalog-list">
      <div className="catalog-toolbar">
        <input
          className="input"
          type="search"
          placeholder="Buscar catálogo…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          data-testid="catalog-search"
          aria-label="Buscar catálogo"
        />
        <select
          className="input"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          data-testid="catalog-sort"
          aria-label="Ordenar catálogos"
        >
          <option value="default">Orden por categoría</option>
          <option value="name">Nombre (A→Z)</option>
          <option value="item_count">Ítems (mayor primero)</option>
          <option value="last_updated">Actualización (reciente primero)</option>
        </select>
      </div>

      {visible.length === 0 ? (
        <p data-testid="catalog-list-empty" style={{ color: "var(--ink-mute)", marginTop: 12 }}>
          No hay catálogos que coincidan con “{query}”.
        </p>
      ) : (
        <ul className="catalog-rows" data-testid="catalog-rows">
          {visible.map((c) => (
            <li key={c.name}>
              <Link
                href={`/catalogo/${encodeURIComponent(c.name)}`}
                className="catalog-row"
                data-testid={`catalog-row-${c.name}`}
              >
                <span className="catalog-row-name mono">{c.name}</span>
                <span className="catalog-row-count">{c.item_count} ítems</span>
                <span className="catalog-row-updated meta">
                  {c.last_updated ? `Act. ${c.last_updated}` : "—"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
