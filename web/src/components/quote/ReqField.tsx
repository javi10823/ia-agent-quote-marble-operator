import React from "react";

interface Props {
  label: string;
  value: string;
}

function ReqField({ label, value }: Props) {
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 13 }}>
      <span style={{ color: "var(--t3)", minWidth: 110, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "var(--t1)" }}>{value}</span>
    </div>
  );
}

export default React.memo(ReqField);
