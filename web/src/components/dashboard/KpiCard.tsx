/**
 * KPI card reusable · variantes `.urgent` `.warn` de operator-shared.css.
 *
 * Click → toggle de filtro KPI en el dashboard. Si está activo, agrega
 * clase `.active` para visual de selección.
 */
"use client";

interface Props {
  label: string;
  value: number | string;
  sub: string;
  variant: "urgent" | "warn";
  active: boolean;
  onClick: () => void;
  testId: string;
}

export function KpiCard({ label, value, sub, variant, active, onClick, testId }: Props) {
  return (
    <button
      type="button"
      className={`kpi-card ${variant}${active ? " active" : ""}`}
      onClick={onClick}
      data-testid={testId}
      data-active={active}
      style={{
        textAlign: "left",
        background: "transparent",
        font: "inherit",
        color: "inherit",
      }}
    >
      <div className="kpi-lbl">{label}</div>
      <div className="kpi-val">{value}</div>
      <div className="kpi-sub">{sub}</div>
      <div className="kpi-action">→ Filtrar tabla</div>
    </button>
  );
}
