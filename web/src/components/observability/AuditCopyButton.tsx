/**
 * Sprint 4 audit-trail-copy · CTA persistente del topbar para copiar el
 * audit completo del quote actual al clipboard.
 *
 * Flow:
 *   1. Click → fetch `GET /api/quotes/{id}/audit-log` (real o mock según
 *      USE_REAL_API gate)
 *   2. Format con `formatAuditCopy()` → plain text estructurado
 *   3. navigator.clipboard.writeText() · try-catch con fallback gracioso
 *   4. State badge "Copiado ✓" durante 2000ms (patrón existente
 *      PdfSidebarGenerated.tsx · NO toast library)
 *
 * Visible solo cuando `quoteId` está disponible (Topbar lo recibe del
 * `[id]/layout.tsx` Server Component). En rutas sin quote contexto
 * (e.g., /quotes/new, /), el botón no se renderea.
 *
 * Reusa clase legacy `.ico-btn` del topbar. Cero CSS nuevo.
 */
"use client";

import { useState } from "react";
import { getAuditLog } from "@/lib/api";
import { formatAuditCopy } from "@/lib/utils/format-audit-copy";
import { getSnapshot } from "@/lib/audit-snapshot";

interface Props {
  quoteId: string;
}

type CopyState = "idle" | "loading" | "copied" | "error";

export function AuditCopyButton({ quoteId }: Props) {
  const [state, setState] = useState<CopyState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleClick = async () => {
    if (state === "loading") return;
    setState("loading");
    setErrorMsg(null);
    try {
      const audit = await getAuditLog(quoteId);
      // Sprint 4 audit-copy-3-layer-state · snapshot del paso actual (adapter
      // output + UI render) si el paso lo registró. getSnapshot valida que
      // el quoteId matchee (anti-stale) · null → audit copy sin las 2
      // secciones nuevas (backward compat).
      const snapshot = getSnapshot(quoteId);
      const text = formatAuditCopy(audit, { snapshot });
      try {
        if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
        }
      } catch {
        // best-effort · ambientes sin clipboard API igual muestran el badge
      }
      setState("copied");
      setTimeout(() => setState("idle"), 2000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "No se pudo cargar el audit";
      setErrorMsg(msg);
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  };

  const label =
    state === "loading"
      ? "…"
      : state === "copied"
        ? "✓ Copiado"
        : state === "error"
          ? "✗ Error"
          : "📋";

  const title =
    state === "error" && errorMsg
      ? `Error: ${errorMsg}`
      : "Copiar audit del quote actual al clipboard";

  // Fix-up overflow: `.topbar .ico-btn` del shared CSS hardcodea
  // `width:32px; height:32px; display:grid; place-items:center`. Cuando
  // state cambia a "copied"/"error" el label se ensancha ("✓ Copiado")
  // y desborda el botón, montándose sobre el AuditToggle vecino. Inline
  // override en state expanded: ancho auto + padding horizontal para que
  // el botón crezca a contenido. En idle preservamos 32×32 del ico-btn.
  const isExpanded = state !== "idle";
  const expandedStyle: React.CSSProperties = isExpanded
    ? {
        width: "auto",
        minWidth: 32,
        padding: "0 10px",
        whiteSpace: "nowrap",
      }
    : {};

  return (
    <button
      type="button"
      className="ico-btn"
      title={title}
      onClick={handleClick}
      data-testid="audit-copy-button"
      data-state={state}
      disabled={state === "loading"}
      style={expandedStyle}
    >
      <span style={{ fontSize: 13, lineHeight: 1, whiteSpace: "nowrap" }}>{label}</span>
    </button>
  );
}
