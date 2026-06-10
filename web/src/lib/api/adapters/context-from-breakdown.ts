/**
 * Pure adapter · Sprint 4 paso-2-context-wire-real · Bug 1 fix.
 *
 * Traduce el `quote_breakdown` que devuelve el backend (`GET /api/quotes/{id}`)
 * a un `ContextResponse` que el UI del paso 2 ya consume sin cambios.
 *
 * Precedencia de fuentes dentro del breakdown:
 *
 *   1. `verified_context_analysis` (cuando el operador confirmó el contexto)
 *   2. `context_analysis_pending` (estado pending · habitual al llegar al paso 2)
 *   3. `_brief_analysis_raw` (raw del brief_analyzer · fallback más débil)
 *
 * Mapping backend `source` (8 valores) → ContextOrigin (5 valores):
 *
 *   - "brief" | "brief+rule" | "brief+dual_read" | "quote" → "BRIEF"
 *     · "quote" se mapea a BRIEF por consistencia con tratamiento de
 *       fields operador-input. Semánticamente cuestionable hasta que
 *       Bug 3 (paso-1 project_name extraction) ajuste el setter de
 *       Quote.project · ver deuda explícita en PR description.
 *   - "dual_read" | "rule" | "inferred"                  → "INFERIDO"
 *   - "config_default"                                   → "DEFAULT"
 *   - field no encontrado                                → "FALTA"
 *
 * Pure function · vitest-testable · sin side effects.
 */
import type { ContextField, ContextOrigin, ContextResponse } from "../types";

// ─── Tipos del breakdown que consumimos ───────────────────────────────

interface BreakdownEntry {
  field: string;
  value: string;
  source: string;
  note?: string;
}

interface ContextAnalysis {
  data_known?: BreakdownEntry[];
  assumptions?: BreakdownEntry[];
  tech_detections?: unknown[];
  pending_questions?: unknown[];
}

interface BriefAnalysisRaw {
  client_name?: string | null;
  project?: string | null;
  material?: string | null;
  localidad?: string | null;
  work_types?: string[] | null;
  zocalos?: string | null;
  alzada?: string | null;
  colocacion?: string | null;
  pileta_mentioned?: boolean | null;
  pileta_type?: string | null;
  pileta_count?: number | null;
  pileta_simple_doble?: string | null;
  anafe_mentioned?: boolean | null;
  anafe_count?: number | null;
  regrueso_mentioned?: boolean | null;
  forma_pago?: string | null;
  demora_dias?: string | number | null;
  es_edificio?: boolean | null;
  [key: string]: unknown;
}

export interface QuoteBreakdownLike {
  verified_context_analysis?: ContextAnalysis | null;
  context_analysis_pending?: ContextAnalysis | null;
  _brief_analysis_raw?: BriefAnalysisRaw | null;
  [key: string]: unknown;
}

// ─── Source mapping 8 → 5 ────────────────────────────────────────────

export function mapBackendSourceToOrigin(source: string | null | undefined): ContextOrigin {
  if (!source) return "FALTA";
  // brief variants + quote → BRIEF
  if (source === "brief" || source.startsWith("brief+") || source === "quote") {
    return "BRIEF";
  }
  if (source === "dual_read" || source === "rule" || source === "inferred") {
    return "INFERIDO";
  }
  if (source === "config_default") {
    return "DEFAULT";
  }
  // Fallback defensivo · source desconocido se trata como inferido para
  // no esconderlo como FALTA (que implica "campo vacío").
  return "INFERIDO";
}

// ─── Helpers ──────────────────────────────────────────────────────────

/** Crea un ContextField · null + FALTA cuando no hay valor. */
function field<T extends string | number | boolean | null>(
  value: T,
  origin: ContextOrigin,
): ContextField<T> {
  if (value === null || value === undefined || value === "") {
    return { value: null as T, origin: "FALTA" };
  }
  return { value, origin };
}

/** Busca un field exacto en data_known/assumptions y devuelve {value, source}. */
function findEntry(
  analysis: ContextAnalysis | null | undefined,
  fieldName: string,
): BreakdownEntry | null {
  if (!analysis) return null;
  return (
    analysis.data_known?.find((e) => e.field === fieldName) ??
    analysis.assumptions?.find((e) => e.field === fieldName) ??
    null
  );
}

/** Resuelve un string field con precedencia verified > pending > raw fallback. */
function resolveString(
  verified: ContextAnalysis | null | undefined,
  pending: ContextAnalysis | null | undefined,
  fieldName: string,
  rawFallback: string | null | undefined,
): ContextField<string | null> {
  const entry = findEntry(verified, fieldName) ?? findEntry(pending, fieldName);
  if (entry && entry.value) {
    return field<string | null>(entry.value, mapBackendSourceToOrigin(entry.source));
  }
  if (rawFallback && String(rawFallback).trim()) {
    return field<string | null>(String(rawFallback).trim(), "BRIEF");
  }
  return field<string | null>(null, "FALTA");
}

// ─── Adapter principal ───────────────────────────────────────────────

export function breakdownToContext(breakdown: QuoteBreakdownLike | null | undefined): ContextResponse {
  const verified = breakdown?.verified_context_analysis ?? null;
  const pending = breakdown?.context_analysis_pending ?? null;
  const raw: BriefAnalysisRaw = breakdown?._brief_analysis_raw ?? {};

  // ── Cliente
  const cliente = resolveString(verified, pending, "Cliente", raw.client_name);

  // ── Contacto · NO está en backend canon (deuda · backend no extrae
  // phone/email del brief). Siempre FALTA hasta sub-PR posterior.
  const contacto = field<string | null>(null, "FALTA");

  // ── Localidad
  const localidad = resolveString(verified, pending, "Localidad", raw.localidad);

  // ── Material
  const material = resolveString(verified, pending, "Material", raw.material);

  // ── Tipología · derivada de work_types[] del raw (eg "cocina, baño")
  let tipologia: ContextField<string | null>;
  const workTypes = raw.work_types;
  if (Array.isArray(workTypes) && workTypes.length > 0) {
    tipologia = field<string | null>(workTypes.join(", "), "BRIEF");
  } else {
    tipologia = resolveString(verified, pending, "Tipo de trabajo", null);
  }

  // ── Tipo de obra · particular | edificio (es_edificio bool del raw)
  let tipoObra: ContextField<"particular" | "edificio">;
  if (raw.es_edificio === true) {
    tipoObra = { value: "edificio", origin: "BRIEF" };
  } else if (raw.es_edificio === false) {
    tipoObra = { value: "particular", origin: "BRIEF" };
  } else {
    tipoObra = { value: "particular", origin: "DEFAULT" };
  }

  // ── Plazo · de assumptions "Demora" o raw.demora_dias
  const plazoEntry = findEntry(verified, "Demora") ?? findEntry(pending, "Demora");
  let plazo: ContextField<string | null>;
  if (plazoEntry?.value) {
    plazo = field<string | null>(plazoEntry.value, mapBackendSourceToOrigin(plazoEntry.source));
  } else if (raw.demora_dias) {
    plazo = field<string | null>(
      typeof raw.demora_dias === "number" ? `${raw.demora_dias} días` : String(raw.demora_dias),
      "BRIEF",
    );
  } else {
    plazo = field<string | null>(null, "FALTA");
  }

  // ── Pileta · assumptions "Pileta" o derivar de raw.pileta_*
  const piletaEntry = findEntry(verified, "Pileta") ?? findEntry(pending, "Pileta");
  let pileta: ContextField<string | null>;
  if (piletaEntry?.value) {
    pileta = field<string | null>(piletaEntry.value, mapBackendSourceToOrigin(piletaEntry.source));
  } else if (raw.pileta_type) {
    pileta = field<string | null>(raw.pileta_type, "BRIEF");
  } else if (raw.pileta_mentioned === true) {
    pileta = field<string | null>("mencionada", "BRIEF");
  } else {
    pileta = field<string | null>(null, "FALTA");
  }

  // ── Zócalo · assumptions "Zócalos" o raw.zocalos
  const zocaloEntry = findEntry(verified, "Zócalos") ?? findEntry(pending, "Zócalos");
  let zocalo: ContextField<string | null>;
  if (zocaloEntry?.value) {
    zocalo = field<string | null>(zocaloEntry.value, mapBackendSourceToOrigin(zocaloEntry.source));
  } else if (raw.zocalos) {
    zocalo = field<string | null>(raw.zocalos, "BRIEF");
  } else {
    zocalo = field<string | null>(null, "FALTA");
  }

  // ── Regrueso · raw.regrueso_mentioned (bool → "Sí"/"No"/FALTA)
  let regrueso: ContextField<string | null>;
  if (raw.regrueso_mentioned === true) {
    regrueso = field<string | null>("Sí", "BRIEF");
  } else if (raw.regrueso_mentioned === false) {
    regrueso = field<string | null>("No", "DEFAULT");
  } else {
    regrueso = field<string | null>(null, "FALTA");
  }

  // ── Anafe · boolean directo
  let anafe: ContextField<boolean>;
  if (raw.anafe_mentioned === true) {
    anafe = { value: true, origin: "BRIEF" };
  } else if (raw.anafe_mentioned === false) {
    anafe = { value: false, origin: "DEFAULT" };
  } else {
    anafe = { value: false, origin: "FALTA" };
  }

  return {
    cliente,
    contacto,
    localidad,
    plazo,
    tipologia,
    tipo_obra: tipoObra,
    material,
    pileta,
    zocalo,
    regrueso,
    anafe,
  };
}
