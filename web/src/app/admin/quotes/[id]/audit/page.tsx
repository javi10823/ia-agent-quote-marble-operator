"use client";

/**
 * /admin/quotes/[id]/audit
 *
 * Timeline ascendente de eventos del quote. Bundle copy = últimos 20
 * eventos en formato markdown (≤4000 chars). Empty state dinámico
 * usando first_event_date del backend.
 *
 * Solo accesible con JWT logueado (cualquier user). Nunca expuesto
 * al chat público / frontend del cliente.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import {
  fetchQuoteAudit,
  type AuditEvent,
  type AuditTimeline,
} from "@/lib/api";

const MAX_BUNDLE_EVENTS = 20;
const MAX_BUNDLE_CHARS = 4000;

function formatTs(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("es-AR", { hour12: false });
}

// Phase 2 — política acordada: el bundle copy NUNCA expone payloads
// de events grabados con `debug_payload=true`. Se ven en la UI con
// login (auth JWT), pero no se exfiltran al pegar el bundle en
// tickets/Slack externos.
const DEBUG_PAYLOAD_PLACEHOLDER =
  "<debug payload available in /admin/observability, NOT included in bundle>";

function buildBundle(timeline: AuditTimeline): string {
  // Últimos 20 (no primeros+últimos). Razón acordada: para debugging
  // operativo, casi siempre importa el tramo final.
  const events = timeline.events.slice(-MAX_BUNDLE_EVENTS);
  const header =
    `# Audit bundle — quote ${timeline.quote_id}\n` +
    `Generado: ${new Date().toISOString()}\n` +
    `Total eventos en quote: ${timeline.events.length} ` +
    `(mostrando últimos ${events.length})\n\n## Eventos\n`;

  let body = "";
  for (const e of events) {
    const ms = e.elapsed_ms != null ? `  ms=${e.elapsed_ms}` : "";
    const ok = e.success ? "ok" : "FAIL";
    const turn = e.turn_index != null ? `  turn=${e.turn_index}` : "";
    let payloadStr: string;
    if (e.debug_payload) {
      // Política Phase 2: nunca exponer payloads completos en bundles
      // compartibles. La timeline del evento sí aparece (operador puede
      // saber QUÉ pasó), pero el payload va a la UI con auth.
      payloadStr = DEBUG_PAYLOAD_PLACEHOLDER;
    } else {
      try {
        payloadStr = JSON.stringify(e.payload).slice(0, 200);
      } catch {
        payloadStr = "<unserializable>";
      }
    }
    const line =
      `[${formatTs(e.created_at)}] ${e.event_type}  actor=${e.actor}  ` +
      `${ok}${ms}${turn}\n  ${e.summary}\n  payload: ${payloadStr}\n`;
    if ((header + body + line).length > MAX_BUNDLE_CHARS) break;
    body += line;
  }
  return header + body;
}

function EventCard({ event }: { event: AuditEvent }) {
  const [expanded, setExpanded] = useState(false);
  const dot = event.success ? "bg-emerald-500" : "bg-red-500";
  return (
    <div className="border-l-2 border-zinc-700 pl-4 py-2">
      <div className="flex items-baseline gap-3 text-sm">
        <span className={`inline-block w-2 h-2 rounded-full ${dot}`}></span>
        <span className="font-mono text-xs text-zinc-400">
          {formatTs(event.created_at)}
        </span>
        <span className="font-mono text-xs px-2 py-0.5 bg-zinc-800 rounded text-zinc-300">
          {event.event_type}
        </span>
        <span className="text-xs text-zinc-500">
          {event.source} · {event.actor}
          {event.elapsed_ms != null ? ` · ${event.elapsed_ms}ms` : ""}
        </span>
      </div>
      <div className="text-sm text-zinc-200 mt-1">{event.summary}</div>
      {event.error_message && (
        <div className="text-xs text-red-400 mt-1 font-mono">
          {event.error_message}
        </div>
      )}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-zinc-500 hover:text-zinc-300 mt-1"
      >
        {expanded ? "Ocultar payload" : "Ver payload"}
        {event.payload_truncated && " (truncado)"}
      </button>
      {expanded && (
        <pre className="text-xs text-zinc-400 mt-2 p-2 bg-zinc-900 rounded overflow-x-auto">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function QuoteAuditPage() {
  const params = useParams<{ id: string }>();
  const quoteId = params.id;
  const [timeline, setTimeline] = useState<AuditTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

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

  const bundle = useMemo(
    () => (timeline ? buildBundle(timeline) : ""),
    [timeline],
  );

  async function copyBundle() {
    try {
      await navigator.clipboard.writeText(bundle);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("error");
    }
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
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            Auditoría · {quoteId.slice(0, 8)}…
          </h1>
          <Link
            href={`/quote/${quoteId}`}
            className="text-sm text-zinc-500 hover:text-zinc-300"
          >
            ← Volver al quote
          </Link>
        </div>
        {hasEvents && (
          <button
            type="button"
            onClick={copyBundle}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-sm text-zinc-200"
          >
            {copyState === "copied"
              ? "✓ Copiado"
              : copyState === "error"
                ? "Error al copiar"
                : `Copiar bundle (últimos ${Math.min(MAX_BUNDLE_EVENTS, timeline.events.length)})`}
          </button>
        )}
      </div>

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
            <EventCard key={e.id} event={e} />
          ))}
        </div>
      )}
    </div>
  );
}
