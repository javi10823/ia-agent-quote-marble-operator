"use client";

/**
 * /admin/observability
 *
 * Vista global de eventos del sistema. Filtros: event_type, actor,
 * success, quote_id, source, fechas. Paginación 50 por página.
 *
 * Solo accesible con JWT logueado. Cualquier user logueado ve todo
 * (acordado con el operador — sin roles ni filtros por actor).
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  fetchAuditCoverage,
  fetchGlobalAudit,
  type AuditEvent,
  type AuditCoverage,
} from "@/lib/api";

const PAGE_SIZE = 50;

const EVENT_TYPES = [
  "quote.created",
  "quote.calculated",
  "quote.patched",
  "quote.patched_mo",
  "quote.status_changed",
  "quote.reopened",
  "docs.generated",
  "docs.regenerated",
  "agent.stream_started",
  "agent.tool_called",
  "agent.tool_result",
  "chat.message_sent",
];

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", { hour12: false });
}

export default function ObservabilityPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [coverage, setCoverage] = useState<AuditCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filtros
  const [eventType, setEventType] = useState("");
  const [actor, setActor] = useState("");
  const [quoteIdFilter, setQuoteIdFilter] = useState("");
  const [source, setSource] = useState("");
  const [successFilter, setSuccessFilter] = useState<"" | "true" | "false">("");

  useEffect(() => {
    fetchAuditCoverage()
      .then(setCoverage)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchGlobalAudit({
      event_type: eventType || undefined,
      actor: actor || undefined,
      quote_id: quoteIdFilter || undefined,
      source: source || undefined,
      success: successFilter === "" ? undefined : successFilter === "true",
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (!cancelled) {
          setEvents(page.events);
          setTotal(page.total);
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
  }, [eventType, actor, quoteIdFilter, source, successFilter, offset]);

  const isEmpty = useMemo(
    () => !loading && events.length === 0 && total === 0,
    [loading, events.length, total],
  );

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100 mb-2">
        Observability
      </h1>
      <p className="text-sm text-zinc-500 mb-6">
        Auditoría operativa del sistema — eventos persistidos en{" "}
        <code className="text-zinc-400">audit_events</code>.
        {coverage?.first_event_date && (
          <>
            {" "}
            Disponible desde{" "}
            <span className="font-mono">
              {formatTs(coverage.first_event_date)}
            </span>{" "}
            · Total: {coverage.total_events.toLocaleString("es-AR")}.
          </>
        )}
      </p>

      {/* Filtros */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <select
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value);
            setOffset(0);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-sm text-zinc-200"
        >
          <option value="">Todos los tipos</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          placeholder="Actor (username)"
          value={actor}
          onChange={(e) => {
            setActor(e.target.value);
            setOffset(0);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-sm text-zinc-200"
        />
        <input
          placeholder="Quote ID"
          value={quoteIdFilter}
          onChange={(e) => {
            setQuoteIdFilter(e.target.value);
            setOffset(0);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-sm text-zinc-200"
        />
        <input
          placeholder="Source (router/agent/...)"
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setOffset(0);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-sm text-zinc-200"
        />
        <select
          value={successFilter}
          onChange={(e) => {
            setSuccessFilter(e.target.value as "" | "true" | "false");
            setOffset(0);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-sm text-zinc-200"
        >
          <option value="">Todos</option>
          <option value="true">Éxito</option>
          <option value="false">Fallos</option>
        </select>
      </div>

      {error && (
        <div className="text-red-400 mb-4">Error: {error}</div>
      )}

      {isEmpty ? (
        <div className="text-zinc-400 p-6 border border-zinc-800 rounded">
          {coverage?.first_event_date ? (
            <>
              Auditoría disponible desde{" "}
              <span className="font-mono">
                {formatTs(coverage.first_event_date)}
              </span>
              . Sin eventos que coincidan con los filtros actuales.
            </>
          ) : (
            <>Aún no hay eventos registrados.</>
          )}
        </div>
      ) : (
        <>
          <div className="text-xs text-zinc-500 mb-2">
            {total.toLocaleString("es-AR")} resultados · página{" "}
            {Math.floor(offset / PAGE_SIZE) + 1} de{" "}
            {Math.max(1, Math.ceil(total / PAGE_SIZE))}
          </div>
          <div className="border border-zinc-800 rounded overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">Hora</th>
                  <th className="px-3 py-2 text-left">Tipo</th>
                  <th className="px-3 py-2 text-left">Source</th>
                  <th className="px-3 py-2 text-left">Actor</th>
                  <th className="px-3 py-2 text-left">Quote</th>
                  <th className="px-3 py-2 text-left">Resumen</th>
                  <th className="px-3 py-2 text-left">ms</th>
                  <th className="px-3 py-2 text-left">OK</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr
                    key={e.id}
                    className="border-t border-zinc-800 text-zinc-300"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {formatTs(e.created_at)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {e.event_type}
                    </td>
                    <td className="px-3 py-2 text-xs text-zinc-500">
                      {e.source}
                    </td>
                    <td className="px-3 py-2 text-xs">{e.actor}</td>
                    <td className="px-3 py-2 text-xs">
                      {e.quote_id ? (
                        <Link
                          href={`/admin/quotes/${e.quote_id}/audit`}
                          className="text-zinc-300 hover:text-zinc-100 underline"
                        >
                          {e.quote_id.slice(0, 8)}…
                        </Link>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">{e.summary}</td>
                    <td className="px-3 py-2 text-xs text-zinc-500">
                      {e.elapsed_ms ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {e.success ? (
                        <span className="text-emerald-500">✓</span>
                      ) : (
                        <span className="text-red-500">✗</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-between mt-4 text-sm">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded text-zinc-200"
            >
              ← Anterior
            </button>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
              className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded text-zinc-200"
            >
              Siguiente →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
