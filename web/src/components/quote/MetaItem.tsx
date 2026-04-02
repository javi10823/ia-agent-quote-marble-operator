import React from "react";

interface Props {
  label: string;
  value: string;
  highlight?: boolean;
}

function MetaItem({ label, value, highlight }: Props) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: highlight ? 600 : 400, color: highlight ? "var(--t1)" : "var(--t2)" }}>{value}</div>
    </div>
  );
}

export default React.memo(MetaItem);
