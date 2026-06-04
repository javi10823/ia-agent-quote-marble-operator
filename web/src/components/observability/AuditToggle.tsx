/**
 * Chip "AUDIT ON/OFF" mono · TopBar right side.
 *
 * Refactor decisión Javi C: el toggle local del paso-4 (CalcToolbar) se
 * remueve · ahora hay un único toggle global que setea body[data-audit]
 * via useAuditMode hook. Persiste en localStorage.
 *
 * Sub-PR Sprint 4 puede moverlo a /config cuando esa ruta exista.
 */
"use client";

import { useAuditMode } from "@/lib/hooks/useAuditMode";

export function AuditToggle() {
  const { auditOn, toggle } = useAuditMode();
  return (
    <button
      type="button"
      className={`audit-toggle${auditOn ? " on" : ""}`}
      onClick={toggle}
      data-testid="audit-toggle"
      data-on={auditOn}
      title={auditOn ? "Audit ON · debug visible" : "Activar audit · debug visible"}
      style={{
        padding: "5px 10px",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--r-sm)",
        background: auditOn ? "var(--surface-2)" : "transparent",
        color: auditOn ? "var(--ink)" : "var(--ink-mute)",
        fontFamily: "var(--mono)",
        fontSize: 10.5,
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        cursor: "pointer",
      }}
    >
      AUDIT {auditOn ? "ON" : "OFF"}
    </button>
  );
}
