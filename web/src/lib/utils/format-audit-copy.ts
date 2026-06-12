/**
 * Sprint 4 audit-trail-copy · pure function que convierte `AuditLogResponse`
 * del backend en un plain text estructurado para clipboard.
 *
 * Formato LITERAL definido en el bundle FASE 1 (sección 1.11). Diseñado
 * para que Javi/Master lo peguen en Claude Code y analicen input, eventos,
 * latencias, errores y output sin parsing extra.
 *
 * Convenciones:
 * - Timestamps relativos al `quote.created_at` (segundos con 3 decimales)
 * - Tokens con thousands separator (toLocaleString)
 * - Tools agregados por nombre con (N×, total_ms)
 * - Errores se reportan separados al final (siempre completos, sin trunc)
 * - JSON breakdown serializado con indent 2 (legible pero copy-pasteable)
 */
import type { AuditLogResponse } from "@/lib/api/types";
import type { AuditSnapshot } from "@/lib/audit-snapshot";

/** Helper: epoch (ms) de un ISO string. */
function epoch(iso: string): number {
  return new Date(iso).getTime();
}

/** Helper: format relativo "+N.NNNs" o "+N.NNNm:N.NNNs" para deltas largos. */
function fmtDelta(deltaMs: number): string {
  const seconds = deltaMs / 1000;
  return `+${seconds.toFixed(3)}s`;
}

/** Helper: format thousands separator con punto (locale ar). */
function fmtNum(n: number): string {
  return n.toLocaleString("es-AR");
}

/** Helper: format ms a "Ns" cuando >1000ms, "Nms" cuando menos. */
function fmtMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

export interface FormatAuditCopyOptions {
  /** Si true incluye el `quote_breakdown` JSON completo · default true.
   * Útil bajar a false en runs con breakdown muy grande. */
  includeBreakdown?: boolean;
  /** Si true incluye solo el header + events timeline (sin tokens/tools/breakdown).
   * Modo "timeline only" del botón "Copiar solo timeline" en la página /audit. */
  timelineOnly?: boolean;
  /** Sprint 4 audit-copy-3-layer-state · snapshot 3-capa del paso actual
   * (adapter output + UI render). Si se provee, append de 2 secciones nuevas.
   * Default null → output IDÉNTICO al actual (backward compat estricta). */
  snapshot?: AuditSnapshot | null;
}

export function formatAuditCopy(
  audit: AuditLogResponse,
  options: FormatAuditCopyOptions = {},
): string {
  const { includeBreakdown = true, timelineOnly = false, snapshot = null } = options;
  const lines: string[] = [];
  const createdEpoch = epoch(audit.meta.created_at);

  // ─── Header ────────────────────────────────────────────────────────
  lines.push(`QUOTE AUDIT · ${audit.meta.quote_id}`);
  lines.push(
    `created: ${audit.meta.created_at} · status: ${audit.meta.status}` +
      (audit.meta.client_name ? ` · client: ${audit.meta.client_name}` : ""),
  );
  if (audit.meta.project) lines.push(`project: ${audit.meta.project}`);
  if (audit.meta.material) {
    const totalsParts: string[] = [];
    if (audit.meta.total_ars != null) totalsParts.push(`$${fmtNum(audit.meta.total_ars)} ARS`);
    if (audit.meta.total_usd != null) totalsParts.push(`USD ${fmtNum(audit.meta.total_usd)}`);
    const totals = totalsParts.length ? ` · total: ${totalsParts.join(" + ")}` : "";
    lines.push(`material: ${audit.meta.material}${totals}`);
  }
  lines.push("");

  // ─── INPUT ─────────────────────────────────────────────────────────
  lines.push("INPUT");
  if (audit.input_message) {
    // Truncamos a 500 chars para legibilidad · el JSON completo va en
    // QUOTE_BREAKDOWN cuando aplica.
    const trimmed = audit.input_message.length > 500
      ? `${audit.input_message.slice(0, 500)}...`
      : audit.input_message;
    lines.push(`brief_text: "${trimmed.replace(/\n/g, " ")}"`);
  } else {
    lines.push("brief_text: (none)");
  }
  lines.push(
    `plan_files: [${audit.plan_files.map((f) => `"${f}"`).join(", ") || ""}]`,
  );
  lines.push("");

  // ─── EVENTS timeline ──────────────────────────────────────────────
  lines.push(
    `EVENTS (timeline · ${audit.events_total} total${audit.events_truncated ? ` · trunc to ${audit.events.length}` : ""})`,
  );
  for (const ev of audit.events) {
    const delta = epoch(ev.created_at) - createdEpoch;
    const okMark = ev.success ? "" : " ✗";
    const elapsed = ev.elapsed_ms != null ? ` · elapsed=${fmtMs(ev.elapsed_ms)}` : "";
    const error = ev.error_message ? ` · error="${ev.error_message}"` : "";
    const summary = ev.summary ? ` · ${ev.summary}` : "";
    lines.push(`[${fmtDelta(delta)}] ${ev.event_type}${okMark}${elapsed}${summary}${error}`);
  }
  if (audit.events_truncated) {
    lines.push(`... +${audit.events_total - audit.events.length} más (usar ?full=true)`);
  }
  lines.push("");

  if (timelineOnly) {
    return lines.join("\n");
  }

  // ─── CALLS aggregated ────────────────────────────────────────────
  lines.push("CALLS");
  if (audit.chat_duration_ms != null) {
    lines.push(`POST /api/quotes/{id}/chat · ${fmtMs(audit.chat_duration_ms)}`);
  }
  if (audit.tools_used.length > 0) {
    lines.push("  ↳ tools used:");
    for (const t of audit.tools_used) {
      const err = t.error_count > 0 ? ` · errors=${t.error_count}` : "";
      lines.push(`     · ${t.tool_name} (${t.count}×, ${fmtMs(t.total_ms)})${err}`);
    }
  }
  const tk = audit.tokens;
  if (tk.input_tokens > 0 || tk.output_tokens > 0) {
    const cache =
      tk.cache_read_tokens > 0 ? ` · cache_read=${fmtNum(tk.cache_read_tokens)}` : "";
    lines.push(
      `  ↳ tokens: ${fmtNum(tk.input_tokens)} in / ${fmtNum(tk.output_tokens)} out${cache} · cost_usd=$${tk.cost_usd.toFixed(4)} · iterations=${tk.iterations}`,
    );
    if (tk.models_used.length > 0) {
      lines.push(`  ↳ models: ${tk.models_used.join(", ")}`);
    }
  }
  lines.push("");

  // ─── QUOTE_BREAKDOWN snapshot ─────────────────────────────────────
  if (includeBreakdown && audit.quote_breakdown) {
    lines.push("QUOTE_BREAKDOWN (snapshot)");
    try {
      lines.push(JSON.stringify(audit.quote_breakdown, null, 2));
    } catch {
      lines.push("(serialization failed)");
    }
    lines.push("");
  }

  // ─── ERRORS (siempre completos · sin trunc) ───────────────────────
  lines.push(`ERRORS (${audit.errors.length})`);
  if (audit.errors.length === 0) {
    lines.push("none");
  } else {
    for (const err of audit.errors) {
      const delta = epoch(err.created_at) - createdEpoch;
      lines.push(
        `[${fmtDelta(delta)}] ${err.event_type} · ${err.summary}${err.error_message ? ` · error="${err.error_message}"` : ""}`,
      );
    }
  }
  lines.push("");

  // ─── Capa 2+3 · ADAPTER OUTPUT + UI RENDER (Sprint 4 audit-copy-3-layer) ──
  // Solo si el paso actual registró un snapshot (ver audit-snapshot.ts).
  // Sin snapshot → estas secciones se omiten · output idéntico al previo.
  if (snapshot) {
    const SEP = "═══════════════════════════════════════════════";

    if (snapshot.contextResponse) {
      lines.push(SEP);
      lines.push(`[ADAPTER OUTPUT · ContextResponse · ${snapshot.step}]`);
      lines.push(SEP);
      for (const [key, f] of Object.entries(snapshot.contextResponse)) {
        const val = f?.value;
        const valStr = val === null || val === undefined ? "null" : JSON.stringify(val);
        lines.push(`${key}: {value=${valStr}, origin="${f?.origin ?? "?"}"}`);
      }
      lines.push("");
    }

    if (snapshot.uiRender && snapshot.uiRender.length > 0) {
      lines.push(SEP);
      lines.push(`[UI RENDER · ${snapshot.step}]`);
      lines.push(SEP);
      for (const section of snapshot.uiRender) {
        lines.push(`${section.title.toUpperCase()} (${section.fields.length} campos):`);
        for (const fld of section.fields) {
          lines.push(`  ${fld.label}: "${fld.displayValue}" · ${fld.origin}`);
        }
      }
      lines.push("");
    }
  }

  // ─── Footer ──────────────────────────────────────────────────────
  const totalDuration =
    audit.events.length > 0
      ? epoch(audit.events[audit.events.length - 1].created_at) - createdEpoch
      : 0;
  lines.push("---");
  lines.push(
    `End audit · ${audit.events_total} events · ${audit.tools_used.length} tool types · ${audit.errors.length} errors · total ${fmtDelta(totalDuration)}`,
  );

  return lines.join("\n");
}

/** Latencia → severidad para coloring CSS en la página /audit. Bundle 1.11. */
export type LatencySeverity = "ok" | "watch" | "slow" | "alert";

export function latencySeverity(ms: number): LatencySeverity {
  if (ms < 5_000) return "ok";
  if (ms < 15_000) return "watch";
  if (ms < 30_000) return "slow";
  return "alert";
}
