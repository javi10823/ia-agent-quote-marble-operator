"use client";

/**
 * /admin/quotes/[id]/audit
 *
 * Timeline COMPLETO del quote con jerarquía visual (crítico/trivial/error)
 * y 2 modos de copiado:
 *
 *   1. "Copiar bundle completo" → todos los events del quote.
 *      < 50 KB → clipboard.writeText.
 *      ≥ 50 KB → fallback a download `.txt` (para tickets / Slack).
 *
 *   2. "Copiar selección (N)" → solo events con checkbox marcado.
 *      Para casos donde el operador quiere mandar solo el bug específico
 *      sin el contexto completo del flow.
 *
 * Política compartida desde Phase 2: events con `debug_payload=true`
 * NUNCA exponen su payload en bundles compartibles. El placeholder
 * los preserva en el timeline pero el contenido vive solo en la UI
 * (login JWT requerido).
 */

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import {
  fetchQuoteAudit,
  type AuditEvent,
  type AuditTimeline,
} from "@/lib/api";
import { classifyEvent, formatEventSummary } from "@/lib/eventSummary";

const MAX_BUNDLE_BYTES = 50 * 1024;
const DEBUG_PAYLOAD_PLACEHOLDER =
  "<debug payload available in /admin/quotes/X/audit, NOT included in bundle>";

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", { hour12: false });
}

// ─────────────────────────────────────────────────────────────────────
// Bundle building
// ─────────────────────────────────────────────────────────────────────

function buildBundle(
  timeline: AuditTimeline,
  events: AuditEvent[],
  scope: "all" | "selection",
): string {
  const total = timeline.events.length;
  const header =
    `# Audit bundle — quote ${timeline.quote_id}\n` +
    `Generado: ${new Date().toISOString()}\n` +
    `Scope: ${scope === "all" ? "completo" : `selección (${events.length} de ${total})`}\n` +
    `Total events del quote: ${total}\n\n## Timeline\n`;

  let body = "";
  for (const e of events) {
    const summary = formatEventSummary(e);
    const ms = e.elapsed_ms != null ? `  ms=${e.elapsed_ms}` : "";
    const ok = e.success ? "ok" : "FAIL";
    const turn = e.turn_index != null ? `  turn=${e.turn_index}` : "";
    let payloadStr: string;
    if (e.debug_payload) {
      payloadStr = DEBUG_PAYLOAD_PLACEHOLDER;
    } else {
      try {
        payloadStr = JSON.stringify(e.payload);
      } catch {
        payloadStr = "<unserializable>";
      }
    }
    body +=
      `[${formatTs(e.created_at)}] ${e.event_type}  actor=${e.actor}  ` +
      `${ok}${ms}${turn}\n  ${summary}\n  payload: ${payloadStr}\n\n`;
  }
  return header + body;
}

/** Si excede 50 KB, descarga `.txt`. Devuelve la modalidad usada
 * para mostrar feedback. */
async function copyOrDownload(
  text: string,
  filename: string,
): Promise<"clipboard" | "download" | "error"> {
  const bytes = new TextEncoder().encode(text).length;
  if (bytes < MAX_BUNDLE_BYTES) {
    try {
      await navigator.clipboard.writeText(text);
      return "clipboard";
    } catch {
      // Fallback a download si el clipboard falla (ej. preview MCP).
    }
  }
  try {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return "download";
  } catch {
    return "error";
  }
}

// ─────────────────────────────────────────────────────────────────────
// EventCard — render de un evento con jerarquía visual
// ─────────────────────────────────────────────────────────────────────

function EventCard({
  event,
  selected,
  onToggleSelect,
}: {
  event: AuditEvent;
  selected: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const { category, isError } = classifyEvent(event);
  // Errores: payload SIEMPRE visible (no colapsable). Otros: colapsado por default.
  const [expanded, setExpanded] = useState(isError);

  const summary = formatEventSummary(event);

  // Estilos según categoría / error.
  const containerStyle = isError
    ? "border-l-[3px] border-red-500 bg-red-500/5 pl-4"
    : "border-l-2 border-zinc-700 pl-4";

  const eventTypeStyle = isError
    ? "bg-red-500/20 text-red-300 font-semibold"
    : category === "critical"
      ? "bg-zinc-800 text-zinc-200 font-medium"
      : "bg-zinc-900 text-zinc-500";

  const summaryStyle = isError
    ? "text-red-200 font-medium"
    : category === "critical"
      ? "text-zinc-100"
      : "text-zinc-400";

  const dotIcon = isError
    ? "🔴"
    : category === "critical"
      ? event.success === false
        ? "●"
        : "●"
      : "○";
  const dotColor = isError
    ? "text-red-500"
    : category === "critical"
      ? "text-emerald-500"
      : "text-zinc-600";

  const opacity = category === "trivial" && !isError ? "opacity-60" : "";

  return (
    <div className={`py-2.5 ${containerStyle} ${opacity}`}>
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(event.id)}
          onClick={(e) => e.stopPropagation()}
          className="mt-1 accent-zinc-400 cursor-pointer"
          aria-label={`Seleccionar ${event.event_type}`}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 text-sm flex-wrap">
            <span className={`text-base leading-none ${dotColor}`}>{dotIcon}</span>
            <span className="font-mono text-xs text-zinc-500 shrink-0">
              {formatTs(event.created_at)}
            </span>
            <span
              className={`font-mono text-xs px-2 py-0.5 rounded ${eventTypeStyle}`}
            >
              {event.event_type}
            </span>
            <span className="text-xs text-zinc-500">
              {event.source} · {event.actor}
              {event.elapsed_ms != null ? ` · ${event.elapsed_ms}ms` : ""}
            </span>
          </div>
          <div className={`text-sm mt-1 ${summaryStyle}`}>{summary}</div>
          {event.error_message && (
            <div className="text-xs text-red-300 mt-1 font-mono">
              {event.error_message}
            </div>
          )}
          {/* Errores: payload siempre visible. Otros: toggleable. */}
          {isError ? (
            <pre className="text-xs text-zinc-300 mt-2 p-2 bg-zinc-900 rounded overflow-x-auto">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="text-xs text-zinc-500 hover:text-zinc-300 mt-1 bg-transparent border-0 p-0 cursor-pointer"
              >
                {expanded ? "Ocultar payload" : "Ver payload"}
                {event.payload_truncated && " (truncado)"}
                {event.debug_payload && " (debug)"}
              </button>
              {expanded && (
                <pre className="text-xs text-zinc-400 mt-2 p-2 bg-zinc-900 rounded overflow-x-auto">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────

export default function QuoteAuditPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const quoteId = params.id;
  const [timeline, setTimeline] = useState<AuditTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchQuoteAudit(quoteId)
      .then((data) => {
        if (!cancelled) {
          setTimeline(data);
          setLoading(false);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [quoteId]);

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    if (!timeline) return;
    setSelectedIds(new Set(timeline.events.map((e) => e.id)));
  }

  function deselectAll() {
    setSelectedIds(new Set());
  }

  const allSelected = useMemo(() => {
    if (!timeline) return false;
    return timeline.events.length > 0 && selectedIds.size === timeline.events.length;
  }, [timeline, selectedIds]);

  async function handleCopyAll() {
    if (!timeline) return;
    const text = buildBundle(timeline, timeline.events, "all");
    const filename = `audit-${quoteId.slice(0, 12)}-${new Date().toISOString().slice(0, 10)}.txt`;
    const result = await copyOrDownload(text, filename);
    if (result === "clipboard") setFeedback("✓ Bundle completo copiado al portapapeles");
    else if (result === "download") setFeedback("📥 Bundle descargado como archivo (excede 50 KB)");
    else setFeedback("Error al copiar/descargar");
    setTimeout(() => setFeedback(null), 3000);
  }

  async function handleCopySelection() {
    if (!timeline || selectedIds.size === 0) return;
    const events = timeline.events.filter((e) => selectedIds.has(e.id));
    const text = buildBundle(timeline, events, "selection");
    const filename = `audit-${quoteId.slice(0, 12)}-selection-${new Date().toISOString().slice(0, 10)}.txt`;
    const result = await copyOrDownload(text, filename);
    if (result === "clipboard") setFeedback(`✓ ${events.length} evento${events.length !== 1 ? "s" : ""} copiados`);
    else if (result === "download") setFeedback("📥 Selección descargada como archivo");
    else setFeedback("Error al copiar/descargar");
    setTimeout(() => setFeedback(null), 3000);
  }

  if (loading) {
    return <div className="p-8 text-zinc-400">Cargando auditoría…</div>;
  }
  if (error) {
    return <div className="p-8 text-red-400">Error: {error}</div>;
  }
  if (!timeline) return null;

  const hasEvents = timeline.coverage.has_events_for_quote;
  const firstEventDate = timeline.coverage.first_event_date;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-2 flex-wrap gap-3">
        <div>
          <button
            type="button"
            onClick={() => router.back()}
            className="text-sm text-zinc-500 hover:text-zinc-300 bg-transparent border-0 p-0 cursor-pointer mb-1"
          >
            ← Volver
          </button>
          <h1 className="text-2xl font-semibold text-zinc-100">
            Auditoría · <span className="font-mono text-base text-zinc-400">{quoteId.slice(0, 12)}…</span>
          </h1>
        </div>
        {hasEvents && (
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleCopyAll}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-sm text-zinc-200"
              title="Copia los 50 primeros KB; si excede, descarga .txt"
            >
              📋 Copiar bundle completo
            </button>
            <button
              type="button"
              onClick={handleCopySelection}
              disabled={selectedIds.size === 0}
              title={selectedIds.size === 0 ? "Seleccioná al menos un evento" : ""}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed rounded text-sm text-zinc-200"
            >
              📋 Copiar selección ({selectedIds.size})
            </button>
          </div>
        )}
      </div>

      {feedback && (
        <div className="text-xs text-zinc-300 bg-zinc-800 px-3 py-2 rounded mb-3">
          {feedback}
        </div>
      )}

      {hasEvents && (
        <div className="text-xs text-zinc-500 mb-3 flex items-center gap-3">
          <span>{timeline.events.length} eventos</span>
          <button
            type="button"
            onClick={allSelected ? deselectAll : selectAll}
            className="bg-transparent border-0 p-0 text-zinc-500 hover:text-zinc-300 cursor-pointer"
          >
            {allSelected ? "Deseleccionar todos" : "Seleccionar todos"}
          </button>
        </div>
      )}

      {!hasEvents ? (
        <div className="text-zinc-400 p-6 border border-zinc-800 rounded">
          {firstEventDate ? (
            <>
              Auditoría disponible desde{" "}
              <span className="font-mono">{formatTs(firstEventDate)}</span>.
              Quotes anteriores no tienen registro de auditoría.
            </>
          ) : (
            <>Aún no hay eventos registrados en el sistema.</>
          )}
        </div>
      ) : (
        <div className="space-y-1">
          {timeline.events.map((e) => (
            <EventCard
              key={e.id}
              event={e}
              selected={selectedIds.has(e.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
