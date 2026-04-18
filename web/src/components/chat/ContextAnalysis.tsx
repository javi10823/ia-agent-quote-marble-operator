"use client";
import React, { useState } from "react";
import CopyButton from "./CopyButton";

interface DataRow {
  field: string;
  value: string;
  source: string;
  note?: string;
}

interface PendingQuestionOption {
  value: string;
  label: string;
}

interface PendingQuestion {
  id: string;
  label: string;
  question: string;
  type: string;
  options?: PendingQuestionOption[];
  detail_placeholder?: string;
}

interface PendingAnswer {
  id: string;
  value: string;
  detail?: string;
}

interface TechDetectionOption {
  value: string;
  label: string;
}

interface TechDetection {
  field: string;
  label: string;
  value: string | null;
  display: string;
  options: TechDetectionOption[];
  source: string;
  confidence: number;
  status: "verified" | "needs_confirmation";
}

export interface ContextAnalysisData {
  data_known: DataRow[];
  assumptions: DataRow[];
  tech_detections?: TechDetection[];
  pending_questions: PendingQuestion[];
  sector_summary?: string | null;
}

interface Props {
  data: ContextAnalysisData;
  onConfirm: (payload: { answers: PendingAnswer[]; corrections: Record<string, string> }) => void;
}

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  brief: { label: "del brief", cls: "bg-acc/10 text-acc border-acc/30" },
  quote: { label: "del quote", cls: "bg-grn/10 text-grn border-grn/30" },
  rule: { label: "regla D'Angelo", cls: "bg-amb/10 text-amb border-amb/30" },
  "brief+rule": { label: "brief + regla", cls: "bg-amb/10 text-amb border-amb/30" },
  config_default: { label: "default", cls: "bg-white/5 text-t3 border-b1" },
  inferred: { label: "inferido", cls: "bg-white/5 text-t3 border-b1" },
  dual_read: { label: "del plano", cls: "bg-grn/10 text-grn border-grn/30" },
};

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  verified: { label: "confirmado", cls: "bg-grn/15 text-grn border-grn/40" },
  needs_confirmation: { label: "confirmar", cls: "bg-amb/15 text-amb border-amb/40" },
};

function SourceBadge({ source }: { source: string }) {
  const meta = SOURCE_BADGE[source] || SOURCE_BADGE.inferred;
  return (
    <span className={`text-[10px] uppercase tracking-[0.08em] px-1.5 py-0.5 rounded border ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

export default function ContextAnalysis({ data, onConfirm }: Props) {
  const [answers, setAnswers] = useState<Record<string, PendingAnswer>>({});
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [editingField, setEditingField] = useState<string | null>(null);

  const techDetections = data.tech_detections || [];
  // Un tech_detection se comporta como answer auto-aplicado: inicialmente
  // con value detectado, el operador puede cambiarlo inline con radio.
  const [techAnswers, setTechAnswers] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const d of techDetections) if (d.value) init[d.field] = d.value;
    return init;
  });

  const questions = data.pending_questions || [];

  // Preguntas dependientes de isla: si el operador dijo "no" a isla_presence,
  // las preguntas de profundidad + patas quedan no-aplicables. Las marcamos
  // como auto-respondidas para no bloquear Confirmar, y las ocultamos.
  const islaPresenceValue = answers["isla_presence"]?.value;
  const islaNotApplicable = islaPresenceValue === "no";
  const hiddenIfNoIsla = new Set(["isla_profundidad", "isla_patas"]);

  const allAnswered = questions.every(q => {
    if (islaNotApplicable && hiddenIfNoIsla.has(q.id)) return true;
    return answers[q.id]?.value;
  });

  // Markdown para "Copiar" — refleja el contenido de la card estructurado:
  // datos, asunciones, preguntas pendientes. Útil para pegar en otra
  // conversación, email, o debug.
  const contextMarkdown = (() => {
    const lines: string[] = ["## Análisis de contexto"];
    if (data.sector_summary) lines.push(`_${data.sector_summary}_`);
    lines.push("");

    if (data.data_known.length > 0) {
      lines.push("### Datos que tengo");
      data.data_known.forEach(row => {
        const v = corrections[row.field] ?? row.value;
        lines.push(`- **${row.field}**: ${v} _(${row.source})_`);
      });
      lines.push("");
    }

    if (techDetections.length > 0) {
      lines.push("### Detectado en plano / brief");
      techDetections.forEach(d => {
        const picked = d.options.find(o => o.value === techAnswers[d.field]);
        lines.push(`- **${d.label}**: ${picked?.label || d.display} _(${d.source}, ${Math.round(d.confidence * 100)}%)_`);
      });
      lines.push("");
    }

    if (data.assumptions.length > 0) {
      lines.push("### Reglas / defaults que aplico");
      data.assumptions.forEach(row => {
        lines.push(`- **${row.field}**: ${row.value} _(${row.source})_`);
        if (row.note) lines.push(`  - _${row.note}_`);
      });
      lines.push("");
    }

    if (questions.length > 0) {
      lines.push(`### Preguntas bloqueantes (${questions.length})`);
      questions.forEach(q => {
        lines.push(`- ${q.question}`);
        const ans = answers[q.id];
        if (ans?.value) {
          const picked = q.options?.find(o => o.value === ans.value);
          lines.push(`  - Respuesta: ${picked?.label || ans.value}${ans.detail ? ` (${ans.detail})` : ""}`);
        }
      });
    }

    return lines.join("\n");
  })();

  const handleConfirm = () => {
    // Filtrar answers dependientes de isla cuando presence=no (no aplica).
    const filteredAnswers = Object.values(answers).filter(a => {
      if (islaNotApplicable && hiddenIfNoIsla.has(a.id)) return false;
      return true;
    });
    // tech_detections con valor definido se envían como answers (mismo id
    // dispatch en backend). Si el operador corrigió el radio inline, va su
    // valor; si no, va el detectado por defecto.
    const techAsAnswers: PendingAnswer[] = techDetections
      .filter(d => techAnswers[d.field] !== undefined && techAnswers[d.field] !== null)
      .map(d => ({ id: d.field, value: techAnswers[d.field] }));
    onConfirm({
      answers: [...filteredAnswers, ...techAsAnswers],
      corrections,
    });
  };

  const renderRow = (row: DataRow, editable = true) => (
    <div key={row.field} className="grid grid-cols-[140px_1fr_auto] gap-3 items-start py-2 border-t border-b1/50">
      <div className="text-[12px] text-t3 uppercase tracking-[0.06em]">{row.field}</div>
      <div className="text-[13px] text-t1">
        {editingField === row.field ? (
          <input
            autoFocus
            defaultValue={corrections[row.field] ?? row.value}
            onBlur={(e) => {
              const v = e.target.value.trim();
              if (v && v !== row.value) {
                setCorrections(prev => ({ ...prev, [row.field]: v }));
              }
              setEditingField(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.currentTarget.blur(); }
              else if (e.key === "Escape") { setEditingField(null); }
            }}
            className="w-full bg-s1 border border-acc/60 rounded px-2 py-1 text-[13px] text-t1 outline-none"
          />
        ) : (
          <span
            className={editable ? "cursor-text hover:text-t1 transition-colors" : ""}
            onDoubleClick={() => editable && setEditingField(row.field)}
            title={editable ? "Doble-click para corregir" : undefined}
          >
            {corrections[row.field] ?? row.value}
          </span>
        )}
        {row.note && <div className="text-[11px] text-t3 mt-0.5 italic">{row.note}</div>}
      </div>
      <SourceBadge source={row.source} />
    </div>
  );

  return (
    <div className="my-2 w-full rounded-2xl border border-b1 bg-s1 overflow-hidden shadow-[0_20px_40px_-20px_rgba(0,0,0,0.5)]">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 bg-gradient-to-b from-s3 to-s2 border-b border-b1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-acc bg-acc-bg border border-acc/30 px-2 py-1 rounded-md">
          🔍 Análisis de contexto
        </span>
        <h3 className="text-[15px] font-semibold text-t1">
          Paso previo al despiece
        </h3>
        {data.sector_summary && (
          <span className="ml-auto text-[12px] text-t3 font-mono hidden md:inline">
            {data.sector_summary}
          </span>
        )}
        <CopyButton
          text={contextMarkdown}
          label="Copiar contexto"
          className={`${data.sector_summary ? "md:ml-3" : "ml-auto"} hidden sm:inline-flex`}
        />
        <CopyButton
          text={contextMarkdown}
          label="Copiar contexto"
          iconOnly
          className="ml-auto sm:hidden"
        />
      </div>

      <div className="p-5">
        <p className="text-[12px] text-t3 mb-4 leading-[1.55]">
          Antes de medir el plano, validemos lo que sé del trabajo. Corregí lo que esté mal
          con doble-click y respondé las preguntas bloqueantes.
        </p>

        {/* Datos leídos */}
        {data.data_known.length > 0 && (
          <div className="mb-5">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-grn mb-2">
              📋 Datos que tengo
            </h4>
            <div>
              {data.data_known.map(row => renderRow(row))}
            </div>
          </div>
        )}

        {/* Detecciones técnicas del plano/brief */}
        {techDetections.length > 0 && (
          <div className="mb-5">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-grn mb-2">
              🔎 Detectado en plano / brief
            </h4>
            <div className="flex flex-col gap-2">
              {techDetections.map((d) => {
                const current = techAnswers[d.field];
                const statusMeta = STATUS_BADGE[d.status] || STATUS_BADGE.needs_confirmation;
                const sourceMeta = SOURCE_BADGE[d.source] || SOURCE_BADGE.inferred;
                return (
                  <div key={d.field} className="py-2 border-t border-b1/50">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[12px] text-t3 uppercase tracking-[0.06em]">{d.label}</span>
                      <span className={`text-[10px] uppercase tracking-[0.08em] px-1.5 py-0.5 rounded border ${sourceMeta.cls}`}>
                        {sourceMeta.label}
                      </span>
                      <span className={`text-[10px] uppercase tracking-[0.08em] px-1.5 py-0.5 rounded border ${statusMeta.cls}`}>
                        {statusMeta.label}
                      </span>
                      <span className="text-[10px] text-t3 ml-auto font-mono">
                        {Math.round(d.confidence * 100)}%
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {d.options.map((opt) => (
                        <label
                          key={opt.value}
                          className={`flex items-center gap-1.5 text-[12px] cursor-pointer px-2.5 py-1 rounded-md border transition ${
                            current === opt.value
                              ? "border-acc bg-acc/10 text-t1"
                              : "border-b1 bg-transparent text-t2 hover:border-b2"
                          }`}
                        >
                          <input
                            type="radio"
                            name={`tech-${d.field}`}
                            checked={current === opt.value}
                            onChange={() => setTechAnswers(prev => ({ ...prev, [d.field]: opt.value }))}
                          />
                          <span>{opt.label}</span>
                        </label>
                      ))}
                    </div>
                    {d.status === "needs_confirmation" && (
                      <div className="text-[11px] text-t3 mt-1 italic">
                        {d.display}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Asunciones */}
        {data.assumptions.length > 0 && (
          <div className="mb-5">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-amb mb-2">
              ✨ Reglas / defaults que aplico
            </h4>
            <div>
              {data.assumptions.map(row => renderRow(row))}
            </div>
          </div>
        )}

        {/* Preguntas bloqueantes */}
        {questions.length > 0 && (
          <div className="mb-5 p-4 rounded-xl border border-amb/30 bg-amb-bg">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-amb mb-3">
              ⚠ Preguntas bloqueantes ({questions.length})
            </h4>
            <div className="flex flex-col gap-4">
              {questions.map((q) => {
                const current = answers[q.id];
                // Ocultar preguntas dependientes cuando isla_presence=no
                if (islaNotApplicable && hiddenIfNoIsla.has(q.id)) return null;
                return (
                  <div key={q.id} className="flex flex-col gap-2">
                    <div className="text-[13px] text-t1 leading-[1.5]">{q.question}</div>
                    <div className="flex flex-col gap-1.5">
                      {q.options?.map((opt) => (
                        <label
                          key={opt.value}
                          className={`flex items-start gap-2 text-[12px] cursor-pointer px-2.5 py-1.5 rounded-md border transition ${
                            current?.value === opt.value
                              ? "border-acc bg-acc/10 text-t1"
                              : "border-b1 bg-transparent text-t2 hover:border-b2"
                          }`}
                        >
                          <input
                            type="radio"
                            name={`q-${q.id}`}
                            checked={current?.value === opt.value}
                            onChange={() => setAnswers(prev => ({
                              ...prev,
                              [q.id]: { id: q.id, value: opt.value, detail: current?.detail },
                            }))}
                            className="mt-0.5"
                          />
                          <span>{opt.label}</span>
                        </label>
                      ))}
                      {current?.value === "custom" && q.detail_placeholder && (
                        <input
                          type="text"
                          placeholder={q.detail_placeholder}
                          value={current?.detail || ""}
                          onChange={(e) => setAnswers(prev => ({
                            ...prev,
                            [q.id]: { ...(prev[q.id] || { id: q.id, value: "custom" }), detail: e.target.value },
                          }))}
                          className="mt-1 w-full px-2.5 py-1.5 bg-s1 border border-b2 rounded-md text-[12px] text-t1 focus:border-acc/50 outline-none"
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2 px-5 py-4 border-t border-b1 bg-s2">
        <button
          className="flex-1 py-2.5 px-4 rounded-xl text-[13px] font-semibold bg-acc hover:bg-acc-hover text-white transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-acc"
          onClick={handleConfirm}
          disabled={!allAnswered}
          title={!allAnswered ? "Respondé las preguntas pendientes primero" : undefined}
        >
          {allAnswered
            ? "Confirmar contexto — seguir al despiece"
            : `Respondé ${questions.length - Object.values(answers).filter(a => a.value).length} pregunta(s)`}
        </button>
      </div>
    </div>
  );
}
