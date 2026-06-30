/**
 * Topbar v2 — chrome shell.
 *
 * Barra superior de 56px con breadcrumb + status chip + ico-buttons.
 * Reusa clases legacy `.topbar`, `.crumbs`, `.right`, `.ico-btn`,
 * `.status-chip` de operator-shared.css.
 *
 * Sprint 2: ico-buttons sin onClick, status chip estático del
 * `quote.status`. Interactividad real (notificaciones, ajustes,
 * cambio de status) en sub-PRs siguientes.
 */
import type { QuoteHeader } from "@/lib/api";
import { AuditToggle } from "@/components/observability/AuditToggle";
import { AuditCopyButton } from "@/components/observability/AuditCopyButton";
import { DeriveMaterialButton } from "@/components/quote/DeriveMaterialButton";

interface TopbarProps {
  quote: QuoteHeader;
}

export function Topbar({ quote }: TopbarProps) {
  return (
    <div className="topbar">
      <div className="crumbs">
        <span>Presupuestos</span>
        <span className="sep">/</span>
        <span className="now">
          {quote.id} · {quote.client}
        </span>
      </div>

      <div className="right">
        {/* Sprint 4 derive-material-ui-wire · clonar quote con otro material.
            Disabled mientras quote.material esté vacío o "—". */}
        <DeriveMaterialButton quoteId={quote.id} currentMaterial={quote.material} />

        {/* Sprint 4 audit-trail-copy · CTA Copiar audit del quote actual al
            clipboard. Persistente en TODOS los pasos del quote ([id]/layout
            provee `quote: QuoteHeader` con id). */}
        <AuditCopyButton quoteId={quote.id} />

        {/* Sprint 3 observability · audit toggle global (refactor decisión Javi C). */}
        <AuditToggle />

        {/* Status chip — `.status-chip.draft` (color amarillento muted) */}
        <span className={`status-chip ${quote.status}`}>
          <span className="dot" />
          {quote.status}
        </span>

        {/* Ico button · notificaciones (placeholder, no onClick) */}
        <button type="button" className="ico-btn" title="Notificaciones">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <path d="M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9zM10 21a2 2 0 004 0" />
          </svg>
        </button>

        {/* Ico button · ajustes (placeholder, no onClick) */}
        <button type="button" className="ico-btn" title="Ajustes">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19 12a7 7 0 00-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 00-2-1.2L14 3h-4l-.5 2.6a7 7 0 00-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 005 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 002 1.2L10 21h4l.5-2.6a7 7 0 002-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
