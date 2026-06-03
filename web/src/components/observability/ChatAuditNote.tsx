/**
 * Note `.audit-note` dentro del chat panel cuando audit mode global está
 * activo. Copy LITERAL del mockup 13.
 *
 * Reusable en CalcChatPanel + DespieceChatPanel.
 */
"use client";

import { useAuditMode } from "@/lib/hooks/useAuditMode";

export function ChatAuditNote() {
  const { auditOn } = useAuditMode();
  if (!auditOn) return null;
  return (
    <div className="audit-note" data-testid="chat-audit-note">
      Audit ON: cada turno se loguea con trace_id.
    </div>
  );
}
