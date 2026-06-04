/**
 * Note `.audit-note` dentro del chat panel cuando audit mode global está
 * activo. Copy LITERAL del mockup 13.
 *
 * Reusable en CalcChatPanel + DespieceChatPanel.
 * Fix-up #2: oculto cuando snapshot del quote es vacío (fallback genérico).
 */
"use client";

import { useAuditMode } from "@/lib/hooks/useAuditMode";
import { useAuditEmpty } from "@/lib/hooks/useAuditEmpty";

interface Props {
  quoteId: string;
}

export function ChatAuditNote({ quoteId }: Props) {
  const { auditOn } = useAuditMode();
  const isEmpty = useAuditEmpty(quoteId);
  if (!auditOn || isEmpty !== false) return null;
  return (
    <div className="audit-note" data-testid="chat-audit-note">
      Audit ON: cada turno se loguea con trace_id.
    </div>
  );
}
