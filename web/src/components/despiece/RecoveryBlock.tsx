/**
 * RecoveryBlock · mockup 15 LITERAL.
 *
 * Marina marcó este despiece como "esto no me sirve". Valentina ofrece
 * 3 caminos (A · rehacer con detalle / B · rehacer 1 pieza / C · cargo a
 * mano) + composer feedback texto libre + trace-row con info de telemetría.
 *
 * Sprint 3 error-states · decisión Javi C/D: caminos A/B/C son visual-only
 * en este PR (Sprint 4 wirea recovery real). El composer captura el texto
 * en useState pero NO persiste (decisión D · trace simulado).
 *
 * Reusa clases legacy `.recovery-block`, `.v-msg`, `.recovery-paths`,
 * `.rpath`, `.recovery-composer`, `.trace-row` ya presentes en
 * operator-shared.css (sorpresa positiva FASE 1).
 */
"use client";

import { useState } from "react";

interface Props {
  /** Trace ID del audit-snapshot para el row de telemetría
   * ("Tu feedback se guarda como trace q_8f2a · rejected"). */
  traceId: string;
  /** Callback invocado al click en algún recovery path (visual-only por ahora).
   *  Sprint 4 lo wirea a backend. */
  onPath?: (path: "rehacer-detalle" | "rehacer-pieza" | "cargo-mano") => void;
  /** Callback al enviar feedback texto libre. Mock-only en este PR. */
  onFeedback?: (text: string) => void;
}

export function RecoveryBlock({ traceId, onPath, onFeedback }: Props) {
  const [feedback, setFeedback] = useState("");
  const [sent, setSent] = useState(false);

  const submit = () => {
    if (!feedback.trim()) return;
    onFeedback?.(feedback.trim());
    setSent(true);
  };

  return (
    <div className="recovery-block" data-testid="recovery-block">
      <div className="v-msg">
        <div className="vbubble" />
        <div>
          <div className="name">Valentina · IA</div>
          <div className="body">
            Entendido — tirá esto. ¿Qué te falta o sobra?
            <br />
            <span className="sub">Cuanto más concreta seas, mejor lo rehago.</span>
          </div>
        </div>
      </div>

      <div className="recovery-paths" data-testid="recovery-paths">
        <button
          type="button"
          className="rpath"
          onClick={() => onPath?.("rehacer-detalle")}
          data-testid="rpath-detalle"
        >
          <div className="label">A · Rehacer con detalle</div>
          <div className="desc">
            Decime qué cambia (medidas, voladizos, bachas) y armo otro despiece desde cero.
          </div>
        </button>
        <button
          type="button"
          className="rpath"
          onClick={() => onPath?.("rehacer-pieza")}
          data-testid="rpath-pieza"
        >
          <div className="label">B · Rehacer 1 pieza</div>
          <div className="desc">
            Si sólo está mal R4 (la isla, por ej.), te corrijo esa y dejo el resto.
          </div>
        </button>
        <button
          type="button"
          className="rpath muted"
          onClick={() => onPath?.("cargo-mano")}
          data-testid="rpath-mano"
        >
          <div className="label">C · Cargo a mano</div>
          <div className="desc">Vacío todo y lo hacés vos. Yo me callo hasta que me llames.</div>
        </button>
      </div>

      <div className="recovery-composer" data-testid="recovery-composer">
        <input
          type="text"
          value={feedback}
          onChange={(e) => {
            setFeedback(e.target.value);
            if (sent) setSent(false);
          }}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="O contame qué está mal — texto libre…"
          data-testid="recovery-input"
        />
        <button
          type="button"
          className="btn primary sm"
          onClick={submit}
          disabled={!feedback.trim() || sent}
          data-testid="recovery-send"
        >
          {sent ? "Enviado" : "Enviar feedback"}
        </button>
      </div>

      <div className="trace-row" data-testid="trace-row">
        <span aria-hidden="true">ⓘ</span>
        <span>
          Tu feedback se guarda como{" "}
          <strong>
            trace {traceId} · <span data-testid="trace-status">rejected</span>
          </strong>{" "}
          — el equipo lo revisa para mejorar prompts. Tu nombre no se comparte.
        </span>
      </div>
    </div>
  );
}
