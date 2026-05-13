/**
 * ChatPanel — chat scoped 480px (mockup 03-C).
 *
 * Estructura legacy operator-shared.css:
 *   .chat
 *     .head      → vbubble + título "Ayuda con Contexto" + close
 *     .scope     → "Lo que veo" + pills (scope · campos editados)
 *     .stream    → mensajes user/valentina
 *     .sugs      → 3 chips de sugerencia rápida
 *     .composer  → input + botón send
 */
"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage, ChatPanelState } from "@/lib/types";
import { UserMessage } from "./UserMessage";
import { ValentinaMessage } from "./ValentinaMessage";

interface Props {
  messages: ChatMessage[];
  panelState: ChatPanelState;
  editedCount: number;
  onSend: (text: string) => void;
  onClose: () => void;
}

const SUGGESTIONS = [
  "¿Por qué pusiste anafe?",
  "¿Cómo aplicás el descuento de la arquitecta?",
  "Apoyo vs empotrada en cocina",
];

export function ChatPanel({ messages, panelState, editedCount, onSend, onClose }: Props) {
  const [draft, setDraft] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);
  const isStreaming = panelState === "streaming";

  // Auto-scroll al fondo cuando llegan mensajes
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [messages]);

  function submit() {
    const text = draft.trim();
    if (!text || isStreaming) return;
    onSend(text);
    setDraft("");
  }

  return (
    <aside className="chat" data-testid="chat-panel" data-panel-state={panelState}>
      <div className="head">
        <div className="vbubble" />
        <div>
          <div className="title">Ayuda con Contexto</div>
          <div className="sub">Scoped · viendo 11 campos</div>
        </div>
        <button
          type="button"
          className="x-btn"
          onClick={onClose}
          data-testid="chat-close"
          aria-label="cerrar chat"
        >
          ✕
        </button>
      </div>

      <div className="scope">
        <span className="lbl">Lo que veo</span>
        <span className="pill">Contexto · 11 campos</span>
        {editedCount > 0 && <span className="pill scope-pill-human">{editedCount} editados</span>}
        <span className="pill">Brief original</span>
      </div>

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
        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserMessage key={msg.id} message={msg} />
          ) : (
            <ValentinaMessage key={msg.id} message={msg} />
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
            onClick={() => !isStreaming && onSend(s)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                if (!isStreaming) onSend(s);
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
            placeholder="Preguntale algo a Valentina sobre el contexto…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
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
        <div className="hint">Borra al cerrar · respuestas usan el contexto de los 11 campos</div>
      </div>
    </aside>
  );
}
