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
  // PR #485 (sub-PR Bug 5) · schema ternary post-migración. Antes
  // estos eran `*_mentioned: bool` y este adapter los leía como tal —
  // el sub-PR Bug 7 (este) corrige el mismatch. `pulido` no tiene UI
  // row hoy (ContextData no tiene field separado), se ignora.
  frentin?: "yes" | "no" | null;
  regrueso?: "yes" | "no" | null;
  pulido?: "yes" | "no" | null;
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

/** Combina frentin + regrueso ternary en 1 string para el row UI
 * "Frentín / Regrueso" (mapea al field `regrueso` de ContextData).
 *
 * Matriz confirmada con operador · sub-PR Bug 7:
 *
 *   frentin | regrueso | output
 *   ----------------------------------------------------------
 *   null    | null     | null
 *   no      | no       | "No lleva"
 *   yes     | yes      | "Frentín + Regrueso"
 *   yes     | no       | "Frentín: Sí · Regrueso: No"
 *   no      | yes      | "Frentín: No · Regrueso: Sí"
 *   yes     | null     | "Frentín: Sí · Regrueso: —"
 *   null    | yes      | "Frentín: — · Regrueso: Sí"
 *   no      | null     | "Frentín: No · Regrueso: —"
 *   null    | no       | "Frentín: — · Regrueso: No"
 *
 * Razón del formato explícito en disjoint: Marina necesita ver AMBOS
 * valores cuando difieren — el formato compacto ("No lleva") solo es
 * legible cuando ambos coinciden.
 */
export function combineFrentinRegrueso(
  frentin: "yes" | "no" | null,
  regrueso: "yes" | "no" | null,
): string | null {
  if (frentin === null && regrueso === null) return null;
  if (frentin === "no" && regrueso === "no") return "No lleva";
  if (frentin === "yes" && regrueso === "yes") return "Frentín + Regrueso";
  // Disjoint · formato explícito.
  const fLabel =
    frentin === "yes" ? "Sí" : frentin === "no" ? "No" : "—";
  const rLabel =
    regrueso === "yes" ? "Sí" : regrueso === "no" ? "No" : "—";
  return `Frentín: ${fLabel} · Regrueso: ${rLabel}`;
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

  // ── Pileta · assumptions con name canónico del backend o derivar de raw
  // PR #485-followup (Bug 7): el backend NO emite assumption "Pileta"
  // sin sufijo. Emite 4 fields con nombres específicos. Probamos en
  // orden de prioridad operativa:
  //   1. "Pileta — montaje" — echo del brief con pileta_type explícito
  //      (post bug 4 fix · PR #484). Es la fuente más confiable cuando
  //      el operador declara apoyo/empotrada.
  //   2. "Pileta (tipo de montaje)" — regla D'Angelo cocina→empotrada
  //      (líneas 218-223 de context_analyzer.py).
  //   3. fallback a raw.pileta_type (el brief crudo).
  const piletaEntry =
    findEntry(verified, "Pileta — montaje") ??
    findEntry(pending, "Pileta — montaje") ??
    findEntry(verified, "Pileta (tipo de montaje)") ??
    findEntry(pending, "Pileta (tipo de montaje)");
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

  // ── Frentín / Regrueso · UI combina ambos en 1 row (label "Frentín
  // / Regrueso" mapeado al field `regrueso` de ContextData).
  //
  // Post PR #485 el schema del backend es ternary:
  //   raw.frentin:  "yes" | "no" | null
  //   raw.regrueso: "yes" | "no" | null
  //
  // Matriz de combinación (confirmada con operador · sub-PR Bug 7):
  //   null/null  → null + FALTA
  //   no/no      → "No lleva"
  //   yes/yes    → "Frentín + Regrueso"
  //   disjoint   → "Frentín: X · Regrueso: Y" (explícito sin ambigüedad)
  //
  // Razón: en casos disjoint el formato explícito previene que Marina
  // confunda cuál campo dijo qué. Ambos visibles siempre.
  const regrueso = field<string | null>(
    combineFrentinRegrueso(raw.frentin ?? null, raw.regrueso ?? null),
    raw.frentin === undefined && raw.regrueso === undefined ? "FALTA"
      : raw.frentin === null && raw.regrueso === null ? "FALTA"
        : "BRIEF",
  );

  // ── Anafe · boolean directo
  //
  // ⚠️ Deuda documentada (sub-PR Bug 7): cuando `anafe_mentioned ===
  // undefined`, devolvemos `value: false, origin: "FALTA"`. La UI
  // renderea `value=false` como "No" y `origin=FALTA` como chip → el
  // operador ve "No + FALTA simultáneo" (inconsistente). El type
  // `boolean` no admite null, por eso no podemos representar "sin
  // valor". El fix requiere migrar a `boolean | null` + refactor
  // de la UI row anafe — scope separado coordinado con maqueta.
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
