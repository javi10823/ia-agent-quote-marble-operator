/**
 * Chat scoped 480px del paso 5 PDF · Sprint 4 paso-5-pdf-preview.
 *
 * Closed-default (decisión Javi · mockup 18 no lo muestra abierto, pero
 * el pattern UX del flow exige que exista · idem paso-3/paso-4).
 * Reusa `useChatScoped` ya wireado del PR #464.
 *
 * Scope label "📌 paso 5 · presupuesto PDF". Sin sim-table ni "Aplicar al
 * breakdown" en este PR (consistente con paso-4 decisión #6).
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useChatScoped } from "@/lib/hooks/useChatScoped";
import { ChatAuditNote } from "@/components/observability/ChatAuditNote";

interface Props {
  quoteId: string;
  onClose: () => void;
}

const SUGGESTIONS = [
  "¿Por qué la vigencia es 7 días?",
  "¿Cambio el anticipo a 70/30?",
  "¿Qué pongo en plazo si la obra está terminada?",
];

export function PdfChatPanel({ quoteId, onClose }: Props) {
  const { messages, send, panelState } = useChatScoped(quoteId, "pdf");
  const isStreaming = panelState === "streaming";
  const [draft, setDraft] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  const submit = () => {
    const text = draft.trim();
    if (!text || isStreaming) return;
    setDraft("");
    send(text);
  };

  return (
    <aside className="chat" data-testid="pdf-chat-panel" data-panel-state={panelState}>
      <div className="head">
        <div className="vbubble" />
        <div>
          <div className="title">Ayuda con PDF</div>
          <div className="sub">📌 paso 5 · presupuesto PDF · scope full</div>
        </div>
        <button
          type="button"
          className="x-btn"
          onClick={onClose}
          data-testid="chat-close"
          aria-label="cerrar"
        >
          ✕
        </button>
      </div>
      <div className="scope">
        <span className="lbl">Lo que veo</span>
        <span className="pill">PDF v1 borrador</span>
        <span className="pill">5 secciones del cálculo</span>
      </div>
      <ChatAuditNote quoteId={quoteId} />

      <div className="stream" ref={streamRef} data-testid="chat-stream">
        {messages.length === 0 && (
          <div
            className="font-mono"
            style={{ color: "var(--ink-mute)", fontSize: 12, textAlign: "center" }}
            data-testid="chat-empty"
          >
            Hacé una pregunta o usá una sugerencia.
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <div className="msg u" key={m.id} data-testid="chat-msg-user">
              {m.content}
            </div>
          ) : (
            <div className="msg v" key={m.id} data-testid="chat-msg-valentina">
              <div className="name">Valentina</div>
              <div className="body">{m.content}</div>
            </div>
          ),
        )}
      </div>

      <div className="sugs">
        {SUGGESTIONS.map((s) => (
          <span
            className="sug"
            key={s}
            role="button"
            tabIndex={0}
            onClick={() => !isStreaming && send(s)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                if (!isStreaming) send(s);
              }
            }}
          >
            {s}
          </span>
        ))}
      </div>

      <div className="composer">
        <div className="field">
          <input
            type="text"
            placeholder="Preguntá sobre el PDF…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            disabled={isStreaming}
            data-testid="chat-input"
          />
          <button
            type="button"
            className="send"
            onClick={submit}
            disabled={isStreaming || !draft.trim()}
            data-testid="chat-send"
          >
            Enviar
          </button>
        </div>
        <div className="hint">Borra al cerrar · sobre el PDF v1 actual</div>
      </div>
    </aside>
  );
}
