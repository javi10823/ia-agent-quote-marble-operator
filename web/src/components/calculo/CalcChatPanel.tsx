/**
 * Chat scoped 480px del paso 4 (mockup 09).
 *
 * Reusa `useChatScoped` ya wireado real del PR #464. Scope label
 * "📌 paso 4 · cálculo". El chat es scope full o por sección (no
 * per-item, decisión paso-4). Sin sim-table ni "Aplicar al breakdown"
 * en este PR (decisión Javi #6 · Sprint 4).
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useChatScoped } from "@/lib/hooks/useChatScoped";

interface Props {
  quoteId: string;
  onClose: () => void;
}

const SUGGESTIONS = [
  "¿Qué pasa si saco el zócalo?",
  "¿Cuánto sale con Negro Brasil?",
  "Explicame el descuento arquitecta",
];

export function CalcChatPanel({ quoteId, onClose }: Props) {
  const { messages, lastAction, send, panelState } = useChatScoped(quoteId, "calculo");
  const [draft, setDraft] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);
  const isStreaming = panelState === "streaming";

  useEffect(() => {
    if (streamRef.current) streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [messages]);

  function submit() {
    const text = draft.trim();
    if (!text || isStreaming) return;
    send(text);
    setDraft("");
  }

  return (
    <aside className="chat" data-testid="calc-chat-panel" data-panel-state={panelState}>
      <div className="head">
        <div className="vbubble" />
        <div>
          <div className="title">Ayuda con Cálculo</div>
          <div className="sub">📌 paso 4 · cálculo · scope full</div>
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
        <span className="pill">5 secciones del cálculo</span>
        <span className="pill">Totales ARS + USD</span>
      </div>
      {lastAction && (
        <div
          data-testid="chat-action"
          style={{
            padding: "8px 16px",
            background: "var(--surface-2)",
            color: "var(--ink-soft)",
            fontFamily: "var(--mono)",
            fontSize: 11,
            borderBottom: "1px solid var(--line)",
          }}
        >
          {lastAction}
        </div>
      )}
      <div className="stream" ref={streamRef} data-testid="chat-stream">
        {messages.length === 0 && (
          <div
            style={{ color: "var(--ink-mute)", fontSize: 12, textAlign: "center", padding: 20 }}
            data-testid="chat-empty"
          >
            Hacé una pregunta o usá una sugerencia.
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="msg user" data-testid="chat-msg-user">
              {m.content}
            </div>
          ) : (
            <div key={m.id} className="msg v" data-testid="chat-msg-valentina">
              <div className="name">Valentina</div>
              <div className="body">{m.content}</div>
            </div>
          ),
        )}
      </div>
      <div className="sugs">
        {SUGGESTIONS.map((s) => (
          <span
            key={s}
            className="sug"
            data-testid="chat-suggestion"
            role="button"
            tabIndex={0}
            onClick={() => !isStreaming && send(s)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !isStreaming) send(s);
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
            placeholder="Preguntá sobre el cálculo…"
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
        <div className="hint">Borra al cerrar · respuestas usan el breakdown completo</div>
      </div>
    </aside>
  );
}
