/**
 * Tipos compartidos del client v2 · Sprint 3 api-integration.
 *
 * Hogar único de los tipos que consumen mocks.ts + real.ts + el resto del
 * frontend. Si el backend real devuelve un shape distinto, el adapter vive
 * en real.ts — estos tipos NO cambian (el frontend no se entera del switch).
 */
import type { DashboardQuote, DashboardStatus, DashboardCounts } from "../mocks/dashboardDataset";

export type { DashboardQuote, DashboardStatus, DashboardCounts };

export const V2_API_BASE = "/api";

/* ─── Brief / draft (paso 1) ─────────────────────────────────────── */

export interface CreateDraftQuoteInput {
  planFile: File;
  photos?: File[];
  briefText?: string;
}

export interface CreateDraftQuoteResponse {
  id: string;
  status: "draft";
  createdAt: string;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Validaciones declarativas (defensa en profundidad — la UI también valida). */
export const VALIDATION = {
  PLAN_MAX_BYTES: 20 * 1024 * 1024, // 20 MB
  PLAN_MIME: ["application/pdf"] as const,
  PHOTO_MAX_BYTES: 5 * 1024 * 1024, // 5 MB
  PHOTO_MIME: ["image/jpeg", "image/png"] as const,
  PHOTOS_MAX_COUNT: 5,
  BRIEF_MAX_CHARS: 2000,
} as const;

/* ─── Contexto (paso 2) ──────────────────────────────────────────── */

export type ContextOrigin = "BRIEF" | "INFERIDO" | "DEFAULT" | "EDITADO" | "FALTA";

export interface ContextField<T = string | number | boolean | null> {
  value: T;
  origin: ContextOrigin;
  edited?: boolean;
}

export interface ContextData {
  cliente: string | null;
  contacto: string | null;
  localidad: string | null;
  plazo: string | null;
  tipologia: string | null;
  tipo_obra: "particular" | "edificio";
  material: string | null;
  pileta: string | null;
  zocalo: string | null;
  regrueso: string | null;
  anafe: boolean;
}

export type ContextResponse = {
  [K in keyof ContextData]: ContextField<ContextData[K]>;
};

/* ─── Chat scoped (SSE) ──────────────────────────────────────────── */

export type ChatScope = "contexto" | "despiece" | "calculo" | "pdf";

/**
 * Chunk del stream del chat. El backend real (router.py:2355-2380) emite 7
 * tipos. `text` se concatena; `action` es status transitorio; los 3 tipos de
 * card (`context_analysis`, `dual_read_result`, `zone_selector`) traen su
 * payload como **JSON string dentro de `content`** (doble parse → parseSSEContent).
 * `done` cierra el stream; `error` reporta.
 */
export interface ChatStreamChunk {
  type:
    | "text"
    | "action"
    | "context_analysis"
    | "dual_read_result"
    | "zone_selector"
    | "done"
    | "error";
  content?: string;
  /** sólo en `error` del mock legacy. */
  message?: string;
  /** `done` con `error: true` en el error-path del backend. */
  error?: boolean;
}

/** Parsea `content` cuando el event type lo trae como JSON string (card events). */
export function parseSSEContent<T = unknown>(chunk: ChatStreamChunk): T | string {
  if (!chunk.content) return "";
  try {
    return JSON.parse(chunk.content) as T;
  } catch {
    return chunk.content;
  }
}

/* ─── Dashboard ──────────────────────────────────────────────────── */

export interface ListQuotesFilters {
  statuses?: ReadonlyArray<DashboardStatus>;
  search?: string;
  kpi?: "expire-soon" | "no-response";
}

export interface DashboardKpis {
  expireSoon: number;
  noResponse: number;
  pendingAction: number;
  counts: DashboardCounts;
}

/* ─── Quote header (chrome shell) ────────────────────────────────── */

export interface QuoteHeader {
  id: string;
  client: string;
  clientFull: string;
  material: string;
  /** Número (mock) o "—" degradado en modo real (cast en real.ts cuando el
   *  backend no expone m². El componente lo renderiza vía toLocaleString que
   *  en un string devuelve el string tal cual → "— m²"). */
  m2: number;
  status: "draft" | "sent" | "expired" | "lost";
}

/* ─── Piezas / despiece (paso 3) ─────────────────────────────────── */

export interface DetectedSymbol {
  src: string;
  out: string;
}

export type PieceType = "encimera" | "frente" | "zocalo" | "alzada" | "isla" | (string & {});

export interface PieceOptions {
  pileta?: { tipo: "empotrada" | "sobre-mesada" | null; sku?: string };
  anafe?: boolean;
  tomas?: number;
  alzada?: boolean;
  regrueso_mm?: number;
}

export interface Piece {
  id: string;
  type: PieceType;
  label: string;
  sublabel?: string;
  width_mm: number;
  depth_mm: number;
  quantity: number;
  options: PieceOptions;
  detected_symbols?: DetectedSymbol[];
  origin: "IA" | "EDITADO" | "AGREGADO_MANUAL";
  confidence?: number;
  extracted_from?: string;
  edited?: boolean;
}

export interface TimelineStep {
  step: 1 | 2 | 3 | 4;
  label: string;
  state: "pending" | "running" | "done" | "failed";
  detail?: string;
  started_at?: string;
  completed_at?: string;
}

export interface PieceList {
  pieces: Piece[];
  status: "pending" | "inferring" | "done" | "failed";
  timeline: TimelineStep[];
  warnings: string[];
}

/** m² unitario (half-up a 2 decimales, igual que calculator.py). */
export function pieceM2Unit(piece: Pick<Piece, "width_mm" | "depth_mm">): number {
  return Math.round(((piece.width_mm * piece.depth_mm) / 1_000_000) * 100) / 100;
}

/** m² total = m² unitario × cantidad (half-up a 2 decimales). */
export function pieceM2Total(piece: Pick<Piece, "width_mm" | "depth_mm" | "quantity">): number {
  return Math.round(pieceM2Unit(piece) * piece.quantity * 100) / 100;
}

/** Suma de m² total de un set de piezas. */
export function piecesTotalM2(pieces: Piece[]): number {
  return Math.round(pieces.reduce((sum, p) => sum + pieceM2Total(p), 0) * 100) / 100;
}

/* ─── Paso 4 · Cálculo ──────────────────────────────────────────── */

export type CalcStatus = "pending" | "ok" | "error";

export type CalcCurrency = "ARS" | "USD";

export type AuditKind = "SOURCE" | "REGLA" | "CALC" | "IVA" | "SUMA";

/** Una entrada del bloque `.aud-trail` per-row (SOURCE/REGLA/CALC). */
export interface AuditEntry {
  kind: AuditKind;
  text: string;
}

/** Fila genérica de tabla MO (cols: SKU / desc / cant / base / iva / total). */
export interface LaborRowData {
  sku: string;
  label: string;
  sub?: string;
  qty: string; // ej "6,50 m²" o "1" o "4,98 ml"
  basePrice: string; // ej "$49.698"
  iva: string; // ej "×1,21"
  total: string; // ej "$390.875"
  audit?: AuditEntry[];
}

/** Una fila de la sección "material" (sin tabla MO, formato `.row-line`). */
export interface MaterialRow {
  label: string;
  sub?: string;
  qty: string; // ej "6,50 m²"
  unit: string; // ej "USD 249"
  total: string; // ej "USD 1.619" o "−USD 81"
  variant?: "default" | "discount" | "subtotal";
  audit?: AuditEntry[];
}

/** Estado de la sección merma. */
export type MermaStatus = "na" | "aplica" | "error";

export interface MermaSection {
  status: MermaStatus;
  chipLabel: string; // ej "APLICA" / "N/A — Negro Brasil nunca mermea"
  sub?: string;
  /** Cuando aplica: filas de cálculo (placas + sobrante). */
  rows?: MaterialRow[];
  /** Cuando hay sobrante opcional al cliente. */
  sobranteToggle?: { label: string; defaultChecked: boolean };
  /** Cuando hay stock confirmado en taller. */
  stockToggle?: { label: string; defaultChecked: boolean };
  /** Cuando error (estado B): nombre de la fila huérfana + auto-fix CTA. */
  errorRow?: { label: string; detail: string; fixLabel: string };
}

export interface PiletaSection {
  /** Chip de estado: "N/A — pileta empotrada (la trae el cliente)" o "APLICA". */
  chipLabel: string;
  variant: "na" | "info";
  sub?: string;
}

export interface FleteRow {
  zona: string; // ej "Rosario"
  qty: string; // ej "1 viaje"
  basePrice: string;
  total: string;
  audit?: AuditEntry[];
}

/** Totales bi-currency (ARS = MO + flete; USD = material importado). */
export interface GrandTotals {
  ars: { value: string; meta: string };
  usd: { value: string; meta: string };
  /** En estado B (`has-warn`): ARS muestra error-tone con detalle de la merma fantasma. */
  warnDetail?: string;
}

/** Inputs del operador que se persisten al confirmar (mocks-first → sin persist). */
export interface DatosPdfDefaults {
  plazo: string;
  anticipoPct: string;
  saldo: string;
  envio: string;
  notas: string;
  vigenciaDias: string;
}

/** Ajustes de Valentina mostrados en `.calc-banner > .l2 > .adj-list`. */
export interface ValentinaAdjustment {
  text: string;
}

export interface CalculationResult {
  quoteId: string;
  status: CalcStatus;
  /** Resumen línea 1 del calc-banner: "✓ Calculado · {material} · {m²} · Total ARS $… + USD …". */
  bannerSummary: string;
  /** Ajustes que aplicó Valentina (.adj-list). */
  bannerAdjustments: ValentinaAdjustment[];
  /** Sección 01 · Material — filas (incluye descuento arquitecta) + subtotal. */
  material: { rows: MaterialRow[]; subtotal: string };
  /** Sección 02 · Merma / Sobrante. */
  merma: MermaSection;
  /** Sección 03 · Mano de obra (tabla `.etable.cols-mo`). */
  labor: { rows: LaborRowData[]; subtotal: string };
  /** Sección 04 · Piletas (formato compacto). */
  piletas: PiletaSection;
  /** Sección 05 · Flete. */
  flete: FleteRow;
  /** Totales bi-currency. */
  totals: GrandTotals;
  /** Si estado B: detalle del patch-banner (trace + mensaje de Valentina). */
  patchError?: {
    traceId: string;
    msg: string;
  };
  /** Defaults del form datos-pdf. */
  datosPdf: DatosPdfDefaults;
}

/** Toggles UI controlados por CalcToolbar (no afectan el cálculo en este PR).
 * Sprint 3 obs-per-row fix-up #1: `auditOn` removido del state local de useCalculo
 * — ahora vive en `useAuditMode` (TopBar global). El field también se eliminó
 * de esta interfaz porque CalcSection (Material/Merma/Labor/Flete) y LaborRow
 * reciben `auditOn` directo del hook global en CalculoView, no del state de
 * toggles. */
export interface CalcToggles {
  ivaVisible: boolean;
  tipoCliente: "particular" | "edificio";
}

// ─── Sprint 3 observability-per-row · mockup 13 ───
// Banner top global de auditoría · visible cuando body[data-audit="on"].
// Mock-only · backend no expone esta metadata (decisión Javi D).

/** Última llamada al modelo IA — primera columna del audit-tray. */
export interface AuditLastCall {
  model: string;
  scope: string;
  tokensIn: number;
  tokensOut: number;
  latencyMs: number;
}

/** Trazabilidad de la corrida — segunda columna del audit-tray. */
export interface AuditTrace {
  traceId: string;
  promptVersion: string;
  temperature: string;
  cacheHitPct: number;
}

/** Evento en sesión — tercera columna del audit-tray. */
export interface AuditEvent {
  /** Formato HH:MM:SS. */
  timestamp: string;
  /** Dot-notation del evento (ej. "despiece.draft.partial"). */
  name: string;
  /** Detalle opcional. */
  detail?: string;
}

/** Snapshot completo del audit-tray. */
export interface AuditSnapshot {
  lastCall: AuditLastCall;
  trace: AuditTrace;
  events: AuditEvent[];
  /** Fix-up #2: marca el snapshot como sin datos reales (fallback genérico).
   * Cuando es true, AuditTray + IaAuditBanner + ChatAuditNote se ocultan
   * (tray gigante con em-dashes = UX rota). El AUDIT toggle en TopBar y el
   * aud-trail per-row del paso-4 siguen visibles porque tienen datos propios
   * independientes del snapshot. */
  isEmpty?: boolean;
}
