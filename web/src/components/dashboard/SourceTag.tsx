/**
 * SourceTag · chip de canal de origen (web / operador) para la lista del
 * dashboard. Reemplaza el id crudo (UUID `web-…`) que quedaba feo en la
 * lista. Sobrio a propósito: mono micro + hairline, diferenciado por label
 * + peso (web = filled, operador = outline). NO usa `--accent` (reservado a
 * IA) ni `--human` (púrpura) para no romper la semántica de provenance.
 */
import type { DashboardSource } from "@/lib/mocks/dashboardDataset";

const LABEL: Record<DashboardSource, string> = {
  web: "Web",
  operator: "Operador",
};

const TITLE: Record<DashboardSource, string> = {
  web: "Generado por el cliente desde la web",
  operator: "Cargado por el operador",
};

export function SourceTag({ source }: { source: DashboardSource }) {
  return (
    <span
      className={`source-tag ${source}`}
      data-testid={`source-tag-${source}`}
      title={TITLE[source]}
    >
      {LABEL[source]}
    </span>
  );
}
