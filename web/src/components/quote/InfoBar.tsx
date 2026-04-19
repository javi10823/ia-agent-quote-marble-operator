import React from "react";

interface Props {
  icon: string;
  label: string;
  status: string;
  detail: string;
}

function InfoBar({ icon, label, status, detail }: Props) {
  const isNo = status.includes("NO");
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "10px 14px", borderRadius: 8,
      background: isNo ? "rgba(255,255,255,.02)" : "rgba(217,162,90,0.06)",
      border: `1px solid ${isNo ? "var(--b1)" : "rgba(217,162,90,0.16)"}`,
      fontSize: 12,
    }}>
      <span>{icon}</span>
      <span style={{ fontWeight: 600, color: "var(--t1)" }}>{label} — {status}</span>
      <span style={{ color: "var(--t3)" }}>{detail}</span>
    </div>
  );
}

export default React.memo(InfoBar);
