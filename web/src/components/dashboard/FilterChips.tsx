/**
 * Chips de filtro multi-select por status · Sprint 4 dashboard-redesign.
 *
 * Antes: single-select con pseudo-status "Todos" (FilterChips mobile-only).
 * Ahora: multi-select via `active: Set<DashboardStatus>` + `onToggle`,
 * reusado en desktop + mobile (single layout responsive).
 *
 * Reusa clases legacy `.mfilter-chips` y `.mfilter-chip.active` de
 * operator-shared.css · prefijo `m*` despista pero el estilo es genérico
 * (chips pill con `overflow-x: auto` para mobile · wraps natural en desktop).
 *
 * "Todos" pseudo-status removido · el estado vacío `Set` ya es "todos los
 * statuses". El botón "Limpiar" en DashboardView cubre la UX de reset.
 */
"use client";

import type { DashboardStatus } from "@/lib/api";
import type { DashboardCounts } from "@/lib/mocks/dashboardDataset";

interface FilterDef {
  id: DashboardStatus;
  label: string;
}

const FILTERS: FilterDef[] = [
  { id: "draft", label: "Borrador" },
  { id: "sent", label: "Enviado" },
  { id: "expired", label: "Vencido" },
  { id: "lost", label: "Perdido" },
];

interface Props {
  counts: DashboardCounts;
  active: Set<DashboardStatus>;
  onToggle: (status: DashboardStatus) => void;
}

export function FilterChips({ counts, active, onToggle }: Props) {
  return (
    <div className="mfilter-chips" data-testid="filter-chips">
      {FILTERS.map((f) => {
        const isActive = active.has(f.id);
        return (
          <button
            key={f.id}
            type="button"
            className={`mfilter-chip${isActive ? " active" : ""}`}
            data-testid={`filter-chip-${f.id}`}
            data-active={isActive}
            aria-pressed={isActive}
            onClick={() => onToggle(f.id)}
          >
            {f.label}
            <span className="count">{counts[f.id]}</span>
          </button>
        );
      })}
    </div>
  );
}
