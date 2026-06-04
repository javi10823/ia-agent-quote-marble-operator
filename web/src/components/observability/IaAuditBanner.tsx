/**
 * Banner explicativo `.ia-banner` que aparece en paso-3/paso-4 cuando
 * `body[data-audit="on"]`. Copy LITERAL del mockup 13.
 *
 * Decisión Javi F: IN (cost bajo, valor alto · parte del mockup literal).
 * Fix-up #2: oculto cuando snapshot del quote es vacío (fallback genérico).
 */
"use client";

import { useAuditMode } from "@/lib/hooks/useAuditMode";
import { useAuditEmpty } from "@/lib/hooks/useAuditEmpty";

interface Props {
  quoteId: string;
}

export function IaAuditBanner({ quoteId }: Props) {
  const { auditOn } = useAuditMode();
  const isEmpty = useAuditEmpty(quoteId);
  // Esconder en loading (null) y cuando isEmpty=true (sin datos reales).
  if (!auditOn || isEmpty !== false) return null;
  return (
    <div className="ia-banner" data-testid="ia-audit-banner">
      <div className="vbubble" aria-hidden="true" />
      <div className="text">
        Audit ON: cada respuesta de Valentina te muestra contexto, modelo, tokens y trace_id
        arriba.
        <div className="sub">
          Sólo visible para usuarios con rol dev / QA · togglable desde Configuración
        </div>
      </div>
    </div>
  );
}
