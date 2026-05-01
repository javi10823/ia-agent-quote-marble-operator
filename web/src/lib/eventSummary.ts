/**
 * Templates humanos para cada `event_type` que existe en producción.
 *
 * Diseñados para:
 * 1. Legibilidad humana en `/admin/quotes/[id]/audit`.
 * 2. Phase 3 agente leyendo `SELECT event_type, summary FROM audit_events`.
 *
 * Cada template recibe el event COMPLETO (no solo payload). Razón:
 * `success`, `error_message`, `elapsed_ms`, `actor` viven en columnas
 * top-level del row, no en payload.
 *
 * Auditados contra los call-sites reales (grep en api/app/modules/agent/
 * + observability/) — los keys del payload coinciden literal con los
 * que el código emite. Si una key del payload cambia (ej. `tool` → `tool_name`),
 * actualizar acá Y avisar en el PR description.
 *
 * Categorías visuales:
 * - `critical`: ops de negocio + LLM tool I/O. Bold, color principal, ícono ●.
 * - `trivial`: chatter del flow + tracking del propio audit. Muted, opacity
 *   60%, ícono ○.
 * - `error` (override): cualquier event con `success=false`. Override
 *   sobre crítico/trivial → rojo prominente, payload siempre expandido.
 */

import type { AuditEvent } from "@/lib/api";

export type EventCategory = "critical" | "trivial";

const CRITICAL_EVENT_TYPES = new Set<string>([
  "quote.created",
  "quote.calculated",
  "quote.patched",
  "quote.patched_mo",
  "quote.status_changed",
  "quote.reopened",
  "docs.generated",
  "docs.regenerated",
  "agent.tool_called",
  "agent.tool_result",
]);

/** Categoría visual para un event. `success=false` es override sobre
 * todo lo demás (caller decide cómo renderizar el override). */
export function classifyEvent(event: AuditEvent): {
  category: EventCategory;
  isError: boolean;
} {
  const isError = event.success === false;
  const category: EventCategory = CRITICAL_EVENT_TYPES.has(event.event_type)
    ? "critical"
    : "trivial";
  return { category, isError };
}

// ─────────────────────────────────────────────────────────────────────
// Helpers de formato
// ─────────────────────────────────────────────────────────────────────

function formatARS(n: unknown): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return n.toLocaleString("es-AR", { maximumFractionDigits: 0 });
}

function formatUSD(n: unknown): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function asString(x: unknown): string | null {
  return typeof x === "string" && x.length > 0 ? x : null;
}

function asArray(x: unknown): unknown[] {
  return Array.isArray(x) ? x : [];
}

// ─────────────────────────────────────────────────────────────────────
// Templates por event_type
// ─────────────────────────────────────────────────────────────────────

type Template = (event: AuditEvent, payload: Record<string, unknown>) => string;

const TEMPLATES: Record<string, Template> = {
  // ── Crítico ────────────────────────────────────────────────────────
  "quote.created": (_e, p) =>
    `Quote creado (status=${asString(p.status) ?? "?"})`,

  "quote.calculated": (_e, p) => {
    const mat = asString(p.material) ?? "?";
    const after = formatARS(p.total_ars_after);
    const usd = formatUSD(p.total_usd_after);
    const before = p.total_ars_before;
    const delta =
      typeof before === "number" && Number.isFinite(before)
        ? ` (era $${formatARS(before)})`
        : "";
    return `Cálculo: ${mat} → $${after} ARS / $${usd} USD${delta}`;
  },

  "quote.patched": (_e, p) => {
    const fields = asArray(p.fields).filter((x): x is string => typeof x === "string");
    return `Quote patcheado: ${fields.join(", ") || "sin diff"}`;
  },

  "quote.patched_mo": (_e, p) => {
    const parts: string[] = [];
    const removed = asArray(p.removed).filter((x): x is string => typeof x === "string");
    if (removed.length) parts.push(`removed=${removed.join(",")}`);
    if (p.add_colocacion) parts.push("+colocación");
    const flete = asString(p.add_flete_localidad);
    if (flete) {
      const qty = typeof p.add_flete_qty === "number" ? p.add_flete_qty : 1;
      parts.push(`+flete ${flete}×${qty}`);
    }
    const total = formatARS(p.total_ars_after);
    return `MO patcheado: ${parts.join(", ") || "sin cambios"} → $${total}`;
  },

  "quote.status_changed": (_e, p) =>
    `Status: ${asString(p.from) ?? "?"} → ${asString(p.to) ?? "?"}`,

  "quote.reopened": (_e, p) =>
    `Quote reabierto (kind=${asString(p.kind) ?? "?"})`,

  "docs.generated": (_e, p) => {
    const mat = asString(p.material) ?? "?";
    const driveOk = p.drive_ok === true;
    return `${mat}: PDF generado${driveOk ? " + Drive OK" : " (Drive FAIL)"}`;
  },

  "docs.regenerated": (_e, p) => {
    const driveOk = p.drive_ok === true;
    return `Documentos regenerados${driveOk ? " + Drive OK" : " (Drive FAIL)"}`;
  },

  "agent.tool_called": (_e, p) =>
    `Sonnet llamó ${asString(p.tool) ?? "?"}`,

  "agent.tool_result": (e, p) => {
    const tool = asString(p.tool) ?? "?";
    if (e.success) {
      const ms = typeof e.elapsed_ms === "number" ? ` (${e.elapsed_ms}ms)` : "";
      return `${tool} → OK${ms}`;
    }
    const err = asString(e.error_message) ?? "sin mensaje";
    return `${tool} → ERROR: ${err}`;
  },

  // ── Trivial ────────────────────────────────────────────────────────
  "agent.stream_started": (_e, p) => {
    const prior = typeof p.prior_msgs === "number" ? p.prior_msgs : 0;
    return `Agent stream iniciado (${prior} msgs previos)`;
  },

  "chat.message_sent": (_e, p) => {
    const chars = typeof p.message_chars === "number" ? p.message_chars : 0;
    const planFiles = typeof p.plan_files_count === "number" ? p.plan_files_count : 0;
    const planSuffix = planFiles > 0 ? `, ${planFiles} planos` : "";
    return `Mensaje del operador (${chars} chars${planSuffix})`;
  },

  "audit.cleanup_run": (_e, p) => {
    const rows = typeof p.rows_deleted === "number" ? p.rows_deleted : 0;
    return `Cleanup retention: ${rows} eventos borrados`;
  },

  "audit.global_debug_toggled": (_e, p) =>
    `Debug global: ${asString(p.action) ?? "?"}`,

  "audit.global_debug_shutoff_run": (_e, p) => {
    const rows = typeof p.rows_affected === "number" ? p.rows_affected : 0;
    if (rows === 0) return "Auto-shutoff cron: sin cambios";
    return `Auto-shutoff cron: ${rows} apagado`;
  },

  "audit.global_debug_auto_disabled": (_e, p) =>
    `Debug auto-apagado (${asString(p.reason) ?? "?"})`,
};

/** Devuelve el summary humano para un event. Usa el template del
 * event_type si existe; fallback genérico si no (event_type viejo o
 * nuevo no cubierto). */
export function formatEventSummary(event: AuditEvent): string {
  const template = TEMPLATES[event.event_type];
  const payload = (event.payload || {}) as Record<string, unknown>;
  if (template) {
    try {
      return template(event, payload);
    } catch {
      // Defensivo: si el template falla con un payload inesperado,
      // usar fallback genérico en lugar de crashear el render.
      return event.event_type.replace(/[._]/g, " ");
    }
  }
  // Fallback para event_types no listados.
  return event.event_type.replace(/[._]/g, " ");
}
