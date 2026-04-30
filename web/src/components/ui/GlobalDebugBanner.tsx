"use client";

/**
 * GlobalDebugBanner — banner sticky full-width que aparece cuando el
 * modo debug global está ACTIVO. Imposible de ignorar visualmente.
 *
 * Reglas (acordadas con el operador):
 * - ROJO apagado (#DC2626), texto blanco. NO neón, NO amarillo.
 * - NO botón de cerrar. Solo "Desactivar" → POST off.
 * - Polling cada 30s para detectar auto-shutoff del cron.
 * - Countdown actualiza cada segundo client-side.
 * - Modo manual sin `until` → muestra "manual" sin countdown.
 * - Si NO está activo, NO renderiza nada.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchGlobalDebugStatus,
  setGlobalDebug,
  type GlobalDebugStatus,
} from "@/lib/api";

const POLL_INTERVAL_MS = 30_000;

function formatRemaining(seconds: number): string {
  if (seconds <= 0) return "expirando…";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function GlobalDebugBanner() {
  const [status, setStatus] = useState<GlobalDebugStatus | null>(null);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const lastFetchedAt = useRef<number>(0);

  const refresh = useCallback(async () => {
    try {
      const s = await fetchGlobalDebugStatus();
      setStatus(s);
      lastFetchedAt.current = Date.now();
    } catch {
      // Silencio: si falla la consulta (login expirado, etc.), no
      // bloquear el resto de la app — banner queda oculto.
      setStatus(null);
    }
  }, []);

  // Polling al montar + cada 30s.
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  // Tick por segundo para el countdown.
  useEffect(() => {
    if (!status?.enabled) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [status?.enabled]);

  if (!status?.enabled) return null;

  // Recalcular remaining basado en `until` + tick local. Si pasó del
  // `until`, fuerzo refresh inmediato (cron ya debería haberlo apagado).
  let remainingSec: number | null = null;
  if (status.until) {
    const untilMs = new Date(status.until).getTime();
    remainingSec = Math.max(0, Math.floor((untilMs - Date.now()) / 1000));
    if (remainingSec === 0 && Date.now() - lastFetchedAt.current > 5_000) {
      refresh();
    }
  }
  // Tick consumed para evitar warning de "tick is unused".
  void tick;

  const modeLabel =
    status.mode === "1h"
      ? "1 hora"
      : status.mode === "end_of_day"
        ? "fin del día"
        : "manual (24h máx)";

  async function handleDisable() {
    if (busy) return;
    setBusy(true);
    try {
      await setGlobalDebug("off");
      await refresh();
    } catch {
      // Mostrar feedback mínimo si falla.
      alert("No se pudo desactivar el modo debug. Intentá de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="alert"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 9999,
        background: "#DC2626",
        color: "white",
        padding: "10px 18px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        fontSize: 13,
        fontWeight: 500,
        borderBottom: "1px solid rgba(0,0,0,0.2)",
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 14 }}>🔴</span>
        <span style={{ fontWeight: 600 }}>MODO DEBUG GLOBAL ACTIVO</span>
        <span style={{ opacity: 0.85, fontWeight: 400 }}>
          · captura completa de payloads ({modeLabel})
          {remainingSec !== null && (
            <span style={{ fontFamily: "var(--font-mono)", marginLeft: 8 }}>
              · queda {formatRemaining(remainingSec)}
            </span>
          )}
          {status.started_by && (
            <span style={{ opacity: 0.7, marginLeft: 8 }}>
              · activado por {status.started_by}
            </span>
          )}
        </span>
      </div>
      <button
        type="button"
        onClick={handleDisable}
        disabled={busy}
        style={{
          background: "rgba(255,255,255,0.15)",
          color: "white",
          border: "1px solid rgba(255,255,255,0.4)",
          padding: "5px 12px",
          fontSize: 12,
          fontWeight: 500,
          borderRadius: 4,
          cursor: busy ? "not-allowed" : "pointer",
          opacity: busy ? 0.6 : 1,
        }}
      >
        {busy ? "Desactivando…" : "Desactivar"}
      </button>
    </div>
  );
}
