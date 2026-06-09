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
      const text = formatAuditCopy(audit);
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

  return (
    <button
      type="button"
      className="ico-btn"
      title={title}
      onClick={handleClick}
      data-testid="audit-copy-button"
      data-state={state}
      disabled={state === "loading"}
      style={{ minWidth: 28 }}
    >
      <span style={{ fontSize: 13, lineHeight: 1, whiteSpace: "nowrap" }}>{label}</span>
    </button>
  );
}
