/**
 * Estado C procesando del paso 1 · LITERAL del mockup oficial
 * `00-paso1-C-procesando.html`.
 *
 * Cambios Sprint 4 paso-1-chips-brief-libre:
 * - Timer dinámico en `.status-msg .muted` "(N s · esto suele tardar 12 s,
 *   dame uno más)" via `setInterval(1000)` desde mount.
 * - `.brief-status` muted con extraction snapshot del mockup
 *   ("3 datos del WhatsApp ya extraídos · plano en proceso · ...").
 *   En este sub-PR es texto estático del mockup (esperando wire SSE del
 *   sub-PR `paso-1-sse-stream` que parsea chunks `action`/`context_analysis`).
 * - Botón ghost "Completar a mano →" visible cuando elapsed ≥25s
 *   (threshold del mockup) · click muestra alert visual-only (deuda
 *   explícita: sub-PR `paso-1-partial-commit` lo hace funcional).
 * - `ph-head` extendido con `.muted` "· 3 hojas · página 1/3" cuando
 *   el filename trae info de páginas. En este sub-PR se renderea siempre
 *   con dato estático del mockup.
 *
 * Reusa clases legacy `.brief-hero`, `.status-bar.slow`, `.dot`,
 * `.status-msg`, `.processing-stage`, `.preview-card`, `.ph-head`,
 * `.ph-rows`, `.skel[.short|.medium|.long]`, `.cancel-row`, `.spacer`,
 * `.btn.ghost`. Cero CSS nuevo.
 */
"use client";

import { useEffect, useState } from "react";

interface Props {
  onCancel: () => void;
  planName?: string;
}

/** Threshold del mockup · timer ≥25s habilita el botón "Completar a mano →". */
const THRESHOLD_PARTIAL_COMMIT_SEC = 25;

export function BriefProcessing({ onCancel, planName }: Props) {
  // Elapsed dynamic counter · 1Hz desde mount.
  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setElapsedSec((s) => s + 1);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const showPartialCommit = elapsedSec >= THRESHOLD_PARTIAL_COMMIT_SEC;

  const handlePartialCommit = () => {
    // Visual-only en este sub-PR · deuda explícita `paso-1-partial-commit`.
    if (typeof window !== "undefined") {
      window.alert(
        "Modo parcial: próximamente. Por ahora cancelá y reintentá con menos contenido.",
      );
    }
  };

  return (
    <div className="col brief-stage" data-step="brief" data-state="C">
      <div className="brief-hero">
        <div className="vbubble-lg" />
        <div className="hero-text">
          <div className="eyebrow">Paso 1 de 5 · Brief · procesando</div>
          <h2>Estoy leyendo el plano</h2>
          <div className="lead">
            Extraigo medidas reales (no las marcadas), identifico ambiente, busco el cliente en mi
            base de arquitectos y armo el contexto del paso 2.
          </div>
        </div>
      </div>

      <div className="status-bar slow" data-testid="brief-status-bar">
        <div className="dot" />
        <div className="status-msg">
          <em>Valentina</em> está leyendo el plano y extrayendo medidas…{" "}
          <span style={{ color: "var(--ink-mute)" }} data-testid="brief-status-timer">
            ({elapsedSec} s · esto suele tardar 12 s, dame uno más)
          </span>
        </div>
      </div>

      <div className="processing-stage" data-testid="brief-processing">
        <div className="preview-card">
          <div className="ph-head">
            <span>📄 {planName ?? "Plano en proceso"}</span>
            <span style={{ color: "var(--ink-mute)" }}>· 3 hojas · página 1/3</span>
          </div>
          <div className="ph-rows">
            <div className="skel short" />
            <div className="skel long" />
            <div className="skel medium" />
            <div className="skel long" />
            <div className="skel short" />
            <div className="skel medium" />
            <div className="skel long" />
          </div>
        </div>

        <div className="cancel-row">
          <span
            className="brief-status"
            style={{ color: "var(--ink-mute)" }}
            data-testid="brief-status-snapshot"
          >
            3 datos del WhatsApp ya extraídos · plano en proceso · arquitecta encontrada en
            architects.json (Cueto-Heredia, match exacto)
          </span>
          <span className="spacer" />
          {showPartialCommit && (
            <button
              type="button"
              className="btn ghost"
              onClick={handlePartialCommit}
              title="Threshold 25s+ → guarda parcial (chips llenados, brief leído) y avanza a paso 2 con esos datos. Análogo al fallback de despiece #8."
              data-testid="brief-partial-commit"
            >
              Completar a mano →
            </button>
          )}
          <button type="button" className="btn ghost" onClick={onCancel} data-testid="brief-cancel">
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
