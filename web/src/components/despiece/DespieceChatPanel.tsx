/**
 * Chat scoped 480px del paso 3 (mockup 06).
 *
 * Dos modos:
 *   - Paso completo: title "Ayuda con Despiece", ve las N piezas.
 *   - Pieza puntual (focusedPiece): title "R2 · …", ve sólo esa pieza
 *     (mockup 06 · chat sobre la bacha).
 *
 * Reusa los presentational `UserMessage` / `ValentinaMessage` del paso 2 +
 * la estructura legacy `.chat` (head/scope/stream/sugs/composer). No reusa
 * el `ChatPanel` del paso 2 porque ese tiene copy/scope hardcodeados del
 * contexto; mantenerlos separados evita regresión del Sprint 2.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import type { Piece } from "@/lib/api";
import type { ChatMessage, ChatPanelState } from "@/lib/types";
import { UserMessage } from "@/components/contexto/UserMessage";
import { ValentinaMessage } from "@/components/contexto/ValentinaMessage";
import { ChatAuditNote } from "@/components/observability/ChatAuditNote";

interface Props {
  messages: ChatMessage[];
  panelState: ChatPanelState;
  pieceCount: number;
  editedCount: number;
  focusedPiece: Piece | null;
  onSend: (text: string) => void;
  onClose: () => void;
}

const STEP_SUGGESTIONS = [
  "¿Por qué partiste la mesada en 3?",
  "¿Qué es CORTE45?",
  "¿El zócalo va por separado?",
];

const PIECE_SUGGESTIONS = ["¿La bacha entra en este ancho?", "¿Qué bacha asumiste?", "Ver corte"];

export function DespieceChatPanel({
  messages,
  panelState,
  pieceCount,
  editedCount,
  focusedPiece,
  onSend,
  onClose,
}: Props) {
  const [draft, setDraft] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);
  const isStreaming = panelState === "streaming";
  const focused = focusedPiece !== null;

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

  const suggestions = focused ? PIECE_SUGGESTIONS : STEP_SUGGESTIONS;

  return (
    <aside
      className="chat"
      data-testid="chat-panel"
      data-panel-state={panelState}
      data-scope={focused ? "piece" : "step"}
    >
      <div className="head">
        <div className="vbubble" />
        <div>
          <div className="title">
            {focused ? `${focusedPiece.id} · ${focusedPiece.label}` : "Ayuda con Despiece"}
          </div>
          <div className="sub">
            {focused ? "Scoped · enfocado en 1 pieza" : `Scoped · viendo ${pieceCount} piezas`}
          </div>
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
        {focused ? (
          <span className="pill scope-pill-focus" data-testid="chat-scope-focus">
            {focusedPiece.id} · {focusedPiece.width_mm / 10}×{focusedPiece.depth_mm / 10}
          </span>
        ) : (
          <span className="pill">Despiece · {pieceCount} piezas</span>
        )}
        {editedCount > 0 && <span className="pill scope-pill-human">{editedCount} editadas</span>}
        <span className="pill">Contexto confirmado</span>
      </div>
      <ChatAuditNote />

      <div className="stream" ref={streamRef} data-testid="chat-stream">
        {messages.length === 0 && (
          <div
            className="font-mono"
            style={{ color: "var(--ink-mute)", fontSize: 12, textAlign: "center" }}
            data-testid="chat-empty"
          >
            {focused
              ? `Preguntá lo que quieras sobre ${focusedPiece.id}.`
              : "Hacé una pregunta o usá una sugerencia."}
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
        {suggestions.map((s) => (
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
            placeholder={
              focused ? `Preguntá sobre ${focusedPiece.id}…` : "Preguntá sobre el despiece…"
            }
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
        <div className="hint">
          Borra al cerrar · {focused ? "ve sólo esta pieza" : "ve las piezas del despiece"}
        </div>
      </div>
    </aside>
  );
}
