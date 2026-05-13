/**
 * Chips de filtro horizontales para mobile (mockup 23) + sidebar
 * desktop variant.
 *
 * Reusa clases legacy `.mfilter-chips` y `.mfilter-chip.active` de
 * operator-shared.css.
 */
"use client";

import type { DashboardStatus } from "@/lib/api";
import type { DashboardCounts } from "@/lib/mocks/dashboardDataset";

interface FilterDef {
  id: DashboardStatus | "all";
  label: string;
}

const FILTERS: FilterDef[] = [
  { id: "all", label: "Todos" },
  { id: "draft", label: "Borrador" },
  { id: "sent", label: "Enviado" },
  { id: "expired", label: "Vencido" },
  { id: "lost", label: "Perdido" },
];

interface Props {
  counts: DashboardCounts;
  active: DashboardStatus | null;
  onSelect: (status: DashboardStatus | null) => void;
}

export function FilterChips({ counts, active, onSelect }: Props) {
  return (
    <div className="mfilter-chips" data-testid="filter-chips">
      {FILTERS.map((f) => {
        const isActive = f.id === "all" ? active === null : active === f.id;
        const count = f.id === "all" ? counts.all : counts[f.id];
        return (
          <button
            key={f.id}
            type="button"
            className={`mfilter-chip${isActive ? " active" : ""}`}
            data-testid={`filter-chip-${f.id}`}
            data-active={isActive}
            onClick={() => onSelect(f.id === "all" ? null : f.id)}
          >
            {f.label}
            <span className="count">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
