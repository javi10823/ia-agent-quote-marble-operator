"use client";
// PR #355 — Operator-assist: candidatas sugeridas para revisión.
//
// Bloque que aparece cuando el backend recuperó candidatas del pool
// (rescue normal o deep expansion) pero el LLM las rechazó visualmente
// y dejó `largo_m=null`. Mostramos al operador las opciones para que
// decida con el plano delante.
//
// Contrato:
// - El click en "Usar/Probar como largo" SOLO copia el valor al input
//   del largo del tramo. NO confirma, NO cambia status. El tramo queda
//   DUDOSO hasta que el operador confirme explícitamente.
// - El componente no renderiza nada si no hay tramos con candidatas.
import React from "react";

export interface SuggestedCandidate {
  valor: number;
  source: string;                 // "expanded_rescue" | "expanded_deep"
  label: "mas_probable" | "baja_confianza";
  origin_desc: string;
  warning: string | null;
  score: number;
}

export interface TramoWithSuggestions {
  // PR #357 — binding estable por `regionId` (tramo.id del backend).
  // Antes usábamos (sectorIdx, tramoIdx) que dependía del orden del
  // flatMap y podía mapear mal al tramo equivocado. regionId es único
  // cross-sector (R1, R2, R3 del topology) y no depende del render.
  regionId: string;
  tramoDescripcion: string;
  candidates: SuggestedCandidate[];
}

interface Props {
  tramos: TramoWithSuggestions[];
  /** Aplica la candidata al tramo cuyo `id === regionId`. El handler
   *  en el caller es responsable de resolver regionId → tramo y
   *  ejecutar la mutación (ver `applyCandidate()` en lib/). */
  onApply: (regionId: string, valor: number) => void;
}

type LabelMeta = {
  badge: string;
  badgeClass: string;
  buttonText: string;
  buttonClass: string;
};

const LABEL_META: Record<"mas_probable" | "baja_confianza", LabelMeta> = {
  mas_probable: {
    badge: "MÁS PROBABLE",
    // Verde tenue. Diseño V3 no tiene una variable verde en el index, usamos
    // tailwind green-400 con background sutil.
    badgeClass:
      "bg-[rgba(52,211,153,0.12)] text-[#34d399] border-[rgba(52,211,153,0.25)]",
    buttonText: "Usar como largo",
    // Primary — destaca como acción confiada.
    buttonClass:
      "bg-acc-bg border border-acc/40 text-acc hover:bg-[rgba(166,197,255,0.22)]",
  },
  baja_confianza: {
    badge: "BAJA CONFIANZA",
    badgeClass: "bg-amb-bg text-amb border-amb/30",
    buttonText: "Probar como largo",
    // Outlined — destaca que es tentativo, operador tiene que revisar.
    buttonClass:
      "border border-b1 text-t1 hover:bg-[rgba(255,255,255,0.04)]",
  },
};

const subtitleFor = (candidates: SuggestedCandidate[]): string => {
  const n = candidates.length;
  if (n === 0) return "";
  if (n === 1) {
    return candidates[0].label === "baja_confianza"
      ? "1 candidata · baja confianza"
      : "1 candidata";
  }
  return `${n} candidatas`;
};

const formatMeters = (v: number): string =>
  // Usamos coma decimal (es-AR) para consistencia con el resto del UI.
  v.toFixed(2).replace(".", ",");

export default function SuggestedCandidates({
  tramos,
  onApply,
}: Props) {
  if (tramos.length === 0) return null;

  return (
    <div
      className="mx-5 mb-4 p-4 rounded-xl border border-b1 bg-[rgba(255,255,255,0.02)]"
      data-testid="suggested-candidates-block"
    >
      <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-acc mb-1">
        Candidatas sugeridas para revisión
      </h4>
      <p className="text-[12px] italic text-t3 mb-4 leading-[1.4]">
        Revisá antes de aplicar. Las opciones con menor confianza requieren
        verificación visual en el plano.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {tramos.map((t) => (
          <div
            key={t.regionId}
            className="p-3.5 rounded-xl border border-b1 bg-[rgba(255,255,255,0.015)]"
            data-testid={`suggested-card-${t.regionId}`}
          >
            <div className="text-[13px] text-t1 font-medium">
              Región {t.regionId} · {t.tramoDescripcion}
            </div>
            <div className="text-[11px] text-t3 mb-3">
              {subtitleFor(t.candidates)}
            </div>
            <div className="flex flex-col gap-3.5">
              {t.candidates.map((c, i) => {
                const meta = LABEL_META[c.label] ?? LABEL_META.baja_confianza;
                const isLast = i === t.candidates.length - 1;
                // PR #357 — closure estable sobre regionId y valor de
                // ESTA iteración. Aunque React normalmente lo hace bien,
                // lo capturamos explícito en variables locales para
                // evitar cualquier ambigüedad de scope si el componente
                // se refactoriza en el futuro.
                const regionIdForClick = t.regionId;
                const valorForClick = c.valor;
                return (
                  <div
                    key={i}
                    className={`flex flex-col gap-1.5 ${
                      isLast ? "" : "pb-3 border-b border-b1"
                    }`}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[18px] font-semibold text-t1">
                        {formatMeters(c.valor)} m
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold uppercase tracking-wide ${meta.badgeClass}`}
                      >
                        {meta.badge}
                      </span>
                    </div>
                    <div className="text-[12px] text-t2">{c.origin_desc}</div>
                    {c.warning && (
                      <div className="text-[11px] text-amb flex items-start gap-1.5">
                        <span aria-hidden>⚠</span>
                        <span>{c.warning}</span>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => onApply(regionIdForClick, valorForClick)}
                      className={`self-start mt-1 px-3 py-1.5 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${meta.buttonClass}`}
                      data-testid={`apply-${t.regionId}-${c.valor}`}
                    >
                      {meta.buttonText}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
