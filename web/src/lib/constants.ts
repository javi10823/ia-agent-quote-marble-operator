import type React from "react";

// ── File upload limits ─────────────────────────────────────────────────────
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
export const MAX_FILES = 5;
export const VALID_FILE_TYPES = ["application/pdf", "image/jpeg", "image/jpg", "image/png", "image/webp"];

// ── Timeouts (ms) ──────────────────────────────────────────────────────────
export const CONNECT_TIMEOUT = 60_000;
export const STALL_TIMEOUT = 90_000;

export const STATUS: Record<string, { label: string; bg: string; color: string }> = {
  draft: { label: "Borrador", bg: "var(--amb2)", color: "var(--amb)" },
  validated: { label: "Validado", bg: "var(--grn2)", color: "var(--grn)" },
  sent: { label: "Enviado", bg: "var(--acc2)", color: "var(--acc)" },
};

export const backBtnStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 6,
  border: "1px solid var(--b1)", background: "transparent",
  color: "var(--t2)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
};

export const badgeStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  padding: "2px 8px", borderRadius: 999, fontSize: 10, fontWeight: 600,
};

export const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse",
  border: "1px solid var(--b1)", borderRadius: 8, overflow: "hidden",
};

export const thStyle: React.CSSProperties = {
  padding: "8px 12px", fontSize: 11, fontWeight: 600,
  color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.05em",
  background: "rgba(255,255,255,.03)", borderBottom: "1px solid var(--b1)",
  textAlign: "left",
};

export const tdStyle: React.CSSProperties = {
  padding: "9px 12px", fontSize: 13, color: "var(--t2)",
  borderBottom: "1px solid rgba(255,255,255,.04)",
};
