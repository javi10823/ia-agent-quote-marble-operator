/**
 * Timeline de las 4 pasadas de Valentina leyendo el plano (mockup 04/05).
 * `.pasadas-timeline` con header + 4 `.step` (done / active / pending / failed).
 */
"use client";

import type { ReactNode } from "react";
import type { TimelineStep } from "@/lib/api";

interface Props {
  steps: TimelineStep[];
  /** Texto del meta a la derecha del header (ej. "4 pasadas · 3 símbolos"). */
  meta?: string;
  title?: ReactNode;
}

function stepClass(state: TimelineStep["state"]): string {
  if (state === "done") return "step done";
  if (state === "running") return "step active";
  return "step";
}

export function DespieceTimeline({ steps, meta, title }: Props) {
  return (
    <div className="pasadas-timeline" data-testid="despiece-timeline">
      <div className="pt-head">
        <span className="vmini" />
        <span className="ttl">
          {title ?? (
            <>
              Cómo <em>Valentina</em> lee el plano
            </>
          )}
        </span>
        {meta && <span className="meta">{meta}</span>}
      </div>
      <div className="steps">
        {steps.map((s) => (
          <div
            className={stepClass(s.state)}
            key={s.step}
            data-testid={`timeline-step-${s.step}`}
            data-state={s.state}
          >
            <div className="num">
              <span className="dot" /> Paso {s.step}
            </div>
            <div className="lbl">{s.label}</div>
            {s.detail && <div className="out">{s.detail}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
