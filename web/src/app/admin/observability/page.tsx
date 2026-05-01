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

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  fetchAuditCoverage,
  fetchGlobalDebugStatus,
  fetchObservabilityQuotes,
  setGlobalDebug,
  type AuditCoverage,
  type GlobalDebugStatus,
  type ObservabilityQuoteRow,
} from "@/lib/api";

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

/** "hace 5 min" / "hace 2h" / "hace 3 días" para timestamps recientes;
 * fecha completa para más viejos. */
function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0 || Number.isNaN(ms)) return new Date(iso).toLocaleString("es-AR", { hour12: false });
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "hace segundos";
  if (min < 60) return `hace ${min} min`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `hace ${hr}h`;
  const days = Math.floor(hr / 24);
  if (days < 7) return `hace ${days} día${days > 1 ? "s" : ""}`;
  return new Date(iso).toLocaleDateString("es-AR");
}

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", { hour12: false });
}

// ─────────────────────────────────────────────────────────────────────
// Bloque de toggle del modo debug global
// ─────────────────────────────────────────────────────────────────────

function GlobalDebugToggle() {
  const [status, setStatus] = useState<GlobalDebugStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      setStatus(await fetchGlobalDebugStatus());
    } catch {
      setStatus(null);
    }
  };

  useEffect(() => {
    refresh();
    // Si el banner global apaga debug (botón "Desactivar" arriba),
    // este toggle también debe re-renderizar inmediato.
    const onChanged = () => refresh();
    window.addEventListener("globaldebug:changed", onChanged);
    return () => window.removeEventListener("globaldebug:changed", onChanged);
  }, []);

  async function handleToggle(mode: "1h" | "end_of_day" | "manual" | "off") {
    if (busy) return;
    if (mode === "manual") {
      const ok = window.confirm(
        "Modo manual no expira automáticamente hasta las 24h. " +
          "Vas a ver un banner rojo en toda la app hasta que lo apagues. " +
          "¿Continuar?"
      );
      if (!ok) return;
    }
    setBusy(true);
    try {
      const next = await setGlobalDebug(mode);
      setStatus(next);
      // Avisar al banner global para que se refresque sin esperar el
      // polling de 30s. Sin esto, el operador prende debug y queda
      // confundido hasta 30s sin ver el banner full-width.
      window.dispatchEvent(new CustomEvent("globaldebug:changed"));
    } catch (e) {
      alert((e as Error).message || "Error al cambiar modo debug");
    } finally {
      setBusy(false);
    }
  }

  const isOn = !!status?.enabled;

  return (
    <div className="border border-zinc-800 rounded p-4 mb-6 bg-zinc-900/40">
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
        Configuración de auditoría
      </div>
      {!isOn ? (
        <>
          <div className="text-sm text-zinc-300 mb-3">
            Estado: <span className="text-zinc-400">⚪ Modo normal</span>{" "}
            <span className="text-zinc-500">
              (payloads truncados a 2-4 KB)
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => handleToggle("1h")}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-sm text-zinc-200 disabled:opacity-50"
            >
              Activar 1 hora
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => handleToggle("end_of_day")}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-sm text-zinc-200 disabled:opacity-50"
            >
              Activar hasta fin del día
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => handleToggle("manual")}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-sm text-zinc-200 disabled:opacity-50"
            >
              Activar manual (24h máx)
            </button>
          </div>
          <p className="text-xs text-zinc-500 mt-3 max-w-2xl">
            Cuando está activo, el sistema captura <code className="text-zinc-400">tool_input</code>,{" "}
            <code className="text-zinc-400">tool_result</code> y el texto completo del brief
            en cada evento (hasta 16 KB), permitiendo reproducir bugs sin Railway logs.
            La sanitización de PII (teléfono, email, dirección, nombre cliente, etc.)
            sigue activa.
          </p>
        </>
      ) : (
        <>
          <div className="text-sm text-zinc-100 mb-3">
            Estado:{" "}
            <span className="text-red-400 font-medium">🔴 DEBUG ACTIVO</span>
            {status?.mode && (
              <span className="text-zinc-400 ml-2">
                · modo {status.mode === "1h" ? "1 hora" : status.mode === "end_of_day" ? "fin del día" : "manual"}
              </span>
            )}
          </div>
          <div className="text-xs text-zinc-500 mb-3 space-y-1">
            {status?.started_at && (
              <div>
                Activado: <span className="font-mono text-zinc-400">{formatTs(status.started_at)}</span>
                {status.started_by && <> por <span className="text-zinc-400">{status.started_by}</span></>}
              </div>
            )}
            {status?.until ? (
              <div>
                Expira: <span className="font-mono text-zinc-400">{formatTs(status.until)}</span>
                {status.remaining_seconds !== null && (
                  <span className="text-zinc-500"> · queda {Math.floor(status.remaining_seconds / 60)} min</span>
                )}
              </div>
            ) : (
              <div>
                Sin expiración fija. Auto-shutoff a las 24h del activado.
              </div>
            )}
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => handleToggle("off")}
            className="px-3 py-1.5 bg-red-600 hover:bg-red-500 rounded text-sm text-white font-medium disabled:opacity-50"
          >
            {busy ? "Desactivando…" : "Desactivar debug"}
          </button>
        </>
      )}
    </div>
  );
}

export default function ObservabilityPage() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<ObservabilityQuoteRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [coverage, setCoverage] = useState<AuditCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filtros
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [actor, setActor] = useState("");
  const [hasErrors, setHasErrors] = useState(false);
  const [hasDebug, setHasDebug] = useState(false);

  // Debounce del search input — 300ms.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(searchInput);
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchInput]);

  useEffect(() => {
    fetchAuditCoverage()
      .then(setCoverage)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchObservabilityQuotes({
      q: debouncedSearch || undefined,
      actor: actor || undefined,
      has_errors: hasErrors || undefined,
      has_debug: hasDebug || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (!cancelled) {
          setQuotes(page.quotes);
          setTotal(page.total);
          setLoading(false);
          setError(null);
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
  }, [debouncedSearch, actor, hasErrors, hasDebug, offset]);

  const isEmpty = useMemo(
    () => !loading && quotes.length === 0 && total === 0,
    [loading, quotes.length, total],
  );

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100 mb-2">
        Observability
      </h1>
      <p className="text-sm text-zinc-500 mb-6">
        Auditoría operativa del sistema — quotes con eventos en{" "}
        <code className="text-zinc-400">audit_events</code>.
        {coverage?.first_event_date && (
          <>
            {" "}
            Disponible desde{" "}
            <span className="font-mono">
              {new Date(coverage.first_event_date).toLocaleString("es-AR", { hour12: false })}
            </span>
            {" · "}
            {coverage.total_events.toLocaleString("es-AR")} eventos totales.
          </>
        )}
      </p>

      <GlobalDebugToggle />

      {/* Filtros */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6 items-center">
        <input
          placeholder="🔍 Buscar (quote_id o cliente)…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="md:col-span-2 bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200"
        />
        <input
          placeholder="Actor (username)"
          value={actor}
          onChange={(e) => {
            setActor(e.target.value);
            setOffset(0);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200"
        />
        <div className="flex items-center gap-3 text-sm text-zinc-300">
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={hasErrors}
              onChange={(e) => {
                setHasErrors(e.target.checked);
                setOffset(0);
              }}
              className="accent-red-500"
            />
            <span>solo errores</span>
          </label>
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={hasDebug}
              onChange={(e) => {
                setHasDebug(e.target.checked);
                setOffset(0);
              }}
              className="accent-orange-500"
            />
            <span>solo debug</span>
          </label>
          {loading && <span className="text-xs text-zinc-500 ml-auto">cargando…</span>}
        </div>
      </div>

      {error && <div className="text-red-400 mb-4">Error: {error}</div>}

      {isEmpty ? (
        <div className="text-zinc-400 p-6 border border-zinc-800 rounded">
          {coverage?.first_event_date ? (
            <>No hay quotes que matcheen los filtros actuales.</>
          ) : (
            <>Aún no hay eventos registrados.</>
          )}
        </div>
      ) : (
        <>
          <div className="text-xs text-zinc-500 mb-2">
            {total.toLocaleString("es-AR")} quote{total !== 1 ? "s" : ""} · página{" "}
            {Math.floor(offset / PAGE_SIZE) + 1} de{" "}
            {Math.max(1, Math.ceil(total / PAGE_SIZE))}
          </div>
          <div className="border border-zinc-800 rounded overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">Quote</th>
                  <th className="px-3 py-2 text-left">Cliente</th>
                  <th className="px-3 py-2 text-left">Actor</th>
                  <th className="px-3 py-2 text-right">Events</th>
                  <th className="px-3 py-2 text-left">Errores</th>
                  <th className="px-3 py-2 text-left">Debug</th>
                  <th className="px-3 py-2 text-left">Últ. act.</th>
                </tr>
              </thead>
              <tbody>
                {quotes.map((q) => (
                  <tr
                    key={q.quote_id}
                    onClick={() =>
                      router.push(`/admin/quotes/${q.quote_id}/audit`)
                    }
                    className="border-t border-zinc-800 text-zinc-300 hover:bg-zinc-900/50 cursor-pointer"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {q.quote_id.slice(0, 12)}…
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {q.client_name || <span className="text-zinc-600">—</span>}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {q.actor || <span className="text-zinc-600">—</span>}
                    </td>
                    <td className="px-3 py-2 text-xs text-right">
                      {q.events_count}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {q.errors_count > 0 ? (
                        <span className="px-1.5 py-0.5 bg-red-500/20 text-red-300 rounded text-[10px] font-medium">
                          ⚠ {q.errors_count}
                        </span>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {q.has_debug_payloads ? (
                        <span className="text-orange-400" title="contiene events con debug payload">🔴</span>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-zinc-500">
                      {formatRelative(q.last_event_at)}
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
