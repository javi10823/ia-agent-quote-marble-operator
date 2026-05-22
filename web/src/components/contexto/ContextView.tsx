/**
 * Container del paso 2 — coordina ContextForm + ChatPanel.
 *
 * Layout: el chrome [id]/layout.tsx renderea el children dentro de
 * `<div class="body no-chat">` (one-column padding). Acá montamos
 * un grid interno que alterna 1 col / 2 cols (1fr 480px) según el
 * panelState del chat. Así no necesitamos modificar el layout del
 * chrome (regla absoluta del PR #456).
 */
"use client";

import { useEffect, useState } from "react";
import { useContextForm } from "@/lib/hooks/useContextForm";
import { useChatScoped } from "@/lib/hooks/useChatScoped";
import { getValentinaBriefSummary } from "@/lib/api";
import { ContextForm } from "./ContextForm";
import { ChatPanel } from "./ChatPanel";

interface Props {
  quoteId: string;
}

export function ContextView({ quoteId }: Props) {
  const { context, state, error, updateField, isDirty, editedCount } = useContextForm(quoteId);
  const chat = useChatScoped(quoteId, "contexto");
  const chatOpen = chat.panelState !== "closed";

  // Sprint 2.5 fix-up #2: banner Valentina deriva del lookup por quoteId
  // en BRIEF_SUMMARY_BY_QUOTE_ID (antes hardcodeado a Cueto-Heredia).
  const [briefSummary, setBriefSummary] = useState<string | null>(null);
  useEffect(() => {
    let aborted = false;
    const ctrl = new AbortController();
    getValentinaBriefSummary(quoteId, { signal: ctrl.signal })
      .then((s) => {
        if (!aborted) setBriefSummary(s);
      })
      .catch(() => {
        /* silent · summary es opcional */
      });
    return () => {
      aborted = true;
      ctrl.abort();
    };
  }, [quoteId]);

  if (state === "loading" && !context) {
    return (
      <div className="col" data-testid="context-loading">
        <div className="section-head">
          <div>
            <div className="meta">Paso 2 de 5 · Contexto</div>
            <h2>Cargando contexto…</h2>
          </div>
        </div>
        <div className="ph-rows">
          <div className="skel long" />
          <div className="skel medium" />
          <div className="skel long" />
          <div className="skel short" />
          <div className="skel long" />
        </div>
      </div>
    );
  }

  if (state === "error" || !context) {
    return (
      <div className="col" data-testid="context-error">
        <div className="section-head">
          <h2>No pude cargar el contexto</h2>
        </div>
        <p className="font-mono" style={{ fontSize: 12, color: "var(--error)" }}>
          {error ?? "Error desconocido"}
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="context-view"
      data-chat-open={chatOpen ? "true" : "false"}
      style={{
        display: "grid",
        gridTemplateColumns: chatOpen ? "1fr 480px" : "1fr",
        gap: 24,
        minHeight: 0,
      }}
    >
      <ContextForm
        quoteId={quoteId}
        context={context}
        briefSummary={briefSummary}
        isDirty={isDirty}
        editedCount={editedCount}
        saving={state === "saving"}
        onUpdateField={updateField}
        onOpenChat={chat.open}
        chatOpen={chatOpen}
      />
      {chatOpen && (
        <ChatPanel
          messages={chat.messages}
          panelState={chat.panelState}
          editedCount={editedCount}
          onSend={chat.send}
          onClose={chat.close}
        />
      )}
    </div>
  );
}
