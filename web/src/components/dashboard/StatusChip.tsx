/**
 * Status chip reusable. Mapea status enum a copy en español + clase
 * legacy de operator-shared.css (.status-chip.{draft,sent,expired,lost}).
 */
import type { DashboardStatus } from "@/lib/api";

const LABELS: Record<DashboardStatus, string> = {
  draft: "Borrador",
  sent: "Enviado",
  expired: "Vencido",
  lost: "Perdido",
};

export function StatusChip({ status }: { status: DashboardStatus }) {
  return (
    <span className={`status-chip ${status}`} data-status={status}>
      <span className="dot" />
      {LABELS[status]}
    </span>
  );
}
