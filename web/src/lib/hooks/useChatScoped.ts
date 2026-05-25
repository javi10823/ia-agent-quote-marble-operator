/**
 * Hook que gestiona el chat scoped del paso 2.
 *
 * Persistencia (Master §10 #1): los mensajes se borran al cerrar el
 * panel. open() nuevo arranca con stream vacío. Esto es por diseño —
 * el chat es por-pregunta, no historial persistente.
 *
 * Streaming: cada send() abre un ReadableStream del mock SSE y va
 * concatenando los chunks `text` al mensaje de Valentina hasta
 * recibir `done`. AbortController cancela el stream en curso (cierre
 * de panel o componente desmontado).
 */
"use client";

import { useCallback, useRef, useState } from "react";
import { streamChat, parseSSEContent, type ChatScope } from "../api";
import type { ChatMessage, ChatPanelState } from "../types";

/** Card events del backend real (context_analysis / dual_read_result / zone_selector),
 *  con el `content` ya parseado de su JSON string. Estado preparado para que el
 *  paso 2/3 lo consuma; la UI de cada card llega en sub-PRs siguientes. */
export interface ChatCardEvent {
  type: "context_analysis" | "dual_read_result" | "zone_selector";
  payload: unknown;
}

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * @param targetPieceId  (opcional, scope `despiece`) enfoca el chat en una
 *   pieza puntual — el mock de Valentina responde sobre esa pieza (mockup 06,
 *   chat sobre R2 = bacha). Cambiarlo NO borra el historial; eso sólo pasa al
 *   cerrar (Master §10 #1).
 */
export function useChatScoped(quoteId: string, scope: ChatScope, targetPieceId?: string) {
  const [panelState, setPanelState] = useState<ChatPanelState>("closed");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // FASE 3.4: status transitorio (`action`) + último card event parseado.
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [lastCard, setLastCard] = useState<ChatCardEvent | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const open = useCallback(() => setPanelState("open"), []);

  const close = useCallback(() => {
    abortRef.current?.abort();
    setPanelState("closed");
    setMessages([]); // borra al cerrar (Master §10 #1)
    setLastAction(null);
    setLastCard(null);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
      };
      const valentinaId = makeId();
      const valentinaMsg: ChatMessage = {
        id: valentinaId,
        role: "valentina",
        content: "",
        timestamp: new Date().toISOString(),
        partial: true,
      };
      setMessages((prev) => [...prev, userMsg, valentinaMsg]);
      setPanelState("streaming");
      setLastAction(null);
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const stream = streamChat(quoteId, trimmed, scope, {
          signal: ctrl.signal,
          targetPieceId,
        });
        const reader = stream.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value.type === "text" && value.content) {
            const chunk = value.content;
            setMessages((prev) =>
              prev.map((m) => (m.id === valentinaId ? { ...m, content: m.content + chunk } : m)),
            );
          } else if (value.type === "action") {
            // Status transitorio del tool-use ("📐 Leyendo medidas…").
            setLastAction(value.content ?? null);
          } else if (
            value.type === "context_analysis" ||
            value.type === "dual_read_result" ||
            value.type === "zone_selector"
          ) {
            // Card event: payload viene como JSON string en content → parse.
            // El state queda listo; el refetch de contexto/piezas y la UI de
            // zone_selector llegan en sub-PRs (Sprint 4). Por ahora se expone.
            setLastCard({ type: value.type, payload: parseSSEContent(value) });
            if (value.type === "zone_selector") {
              console.warn("[useChatScoped] zone_selector recibido — UI pendiente (Sprint 4)");
            }
          } else if (value.type === "done") {
            setMessages((prev) =>
              prev.map((m) => (m.id === valentinaId ? { ...m, partial: false } : m)),
            );
          }
        }
      } catch {
        // AbortError o error de stream: marcar como no-partial
        setMessages((prev) =>
          prev.map((m) => (m.id === valentinaId ? { ...m, partial: false } : m)),
        );
      } finally {
        // Si seguimos abiertos, volver a estado open. Si close() ya
        // disparó (panelState='closed'), no pisar el estado.
        setPanelState((curr) => (curr === "streaming" ? "open" : curr));
      }
    },
    [quoteId, scope, targetPieceId],
  );

  return { panelState, messages, lastAction, lastCard, open, close, send };
}
