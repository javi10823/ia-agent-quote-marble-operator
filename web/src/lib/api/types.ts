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
  /** Sprint 4 paso-1-chips-brief-libre: relajado a opcional. Backend
   * acepta `plan_files=[]` (router.py:2089 default `File([])`). Permite
   * text-only y la ruta "Cargar a mano →" del mockup B sin planFile. */
  planFile: File | null;
  photos?: File[];
  briefText?: string;
  /** Chips opcionales del paso-1-A/B · si vienen poblados, se prependen
   * al `message` enviado al backend como prefix estructurado. */
  cliente?: string;
  ambiente?: string;
  plazo?: string;
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
  /** Sprint 4 paso-1-chips-brief-libre · 10 MB LITERAL del mockup oficial
   * (dz-sub "PDF · máx. 10 MB · podés sumar hasta 5 fotos..."). Backend
   * Railway tiene MAX_FILE_SIZE=10MB (router.py validation loop). Alinear
   * defensa-en-profundidad. */
  PLAN_MAX_BYTES: 10 * 1024 * 1024, // 10 MB
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
  /** Sprint 3 error-states (mockup 15) · Marina marcó este despiece como
   * "esto no me sirve". Cuando true, DespieceView renderea banner error +
   * tabla `.discarded` + RecoveryBlock con 3 caminos. Mock-only · disparado
   * por sufijo `-REJECTED` en el quoteId. Sprint 4 wirea recovery paths. */
  rejected?: boolean;
  /** Sprint 3 error-states (mockup 17) · chat tiene un mensaje flagged.
   * Mock-only · disparado por sufijo `-FLAGGED`. Cuando presente, el
   * DespieceChatPanel carga el preset (4 mensajes con el último flagged
   * + sessionInfo + composerPrefill). */
  chatFlagged?: ChatFlaggedPreset;
}

/** Sprint 3 error-states (mockup 17) · preset del chat flagged. */
export interface ChatFlaggedPreset {
  /** Mensajes del stream pre-existente (4 mock). El último es flagged. */
  messages: Array<{
    id: string;
    role: "user" | "valentina";
    content: string;
    timestamp: string;
    /** Solo para el último mensaje de Valentina · marca flagged en el UI. */
    flagged?: boolean;
    /** Etiqueta de timestamp relativo del mockup ("14:23 · hace 30s"). */
    relativeTs?: string;
  }>;
  /** Sesión info del header del chat ("4 mensajes · primer turno hace 8 min"). */
  sessionInfo: string;
  /** Sesión info del banner sobre la tabla ("CHAT ABIERTO SOBRE R5 · HACE 8 MIN"). */
  sessionContext: string;
  /** ID de la pieza referida por el chat (para el .row-chat-ref de la tabla). */
  pieceRefId: string;
  /** Texto pre-cargado del composer (último mensaje user). */
  composerPrefill: string;
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

// ─── Sprint 4 paso-5-pdf-preview · mockup 18 ─────────────────────────────
// Datos del bloque Trazabilidad plegable del sidebar. Mock-only · Sprint 5
// wirea al backend cuando exponga trace_id + inputs_hash de la corrida real.

/** Trazabilidad del PDF v1 · mostrada en `<details class="trace-block">`. */
export interface PdfTrace {
  traceId: string;
  promptVersion: string;
  inputsHash: string;
  /** Snapshot de los JSON consumidos para el cálculo (ej. "materials.json @ 03.05 · architects.json @ 02.05"). */
  snapshot: string;
}

// ─── Sprint 4 paso-5-c-generado · mockup 20 ────────────────────────────────
// Estado C · "v1 generado y enviado". Mock-only en este sub-PR · wire real al
// endpoint POST /api/quotes/{id}/generate del backend en sprint-4/paso-5-pdf-
// real-wire posterior (requiere paso-1-real para que el quote tenga
// quote_breakdown persistido en DB).

/** Info devuelta por `triggerPdfGeneration` y mostrada en el estado C. */
export interface PdfGeneratedInfo {
  pdfUrl: string;
  excelUrl: string;
  driveUrl: string;
  /** Ruta de carpeta de Drive · ej "/Presupuestos/2026/05-mayo/". */
  driveFolderPath: string;
  pdfSizeKb: number;
  excelSizeKb: number;
  /** ISO timestamp del momento de generación. */
  generatedAtIso: string;
  /** Texto display para el banner: "03.05.2026 18:42". */
  generatedAtDisplay: string;
  /** Usuario que generó (ej "Marina"). */
  generatedBy: string;
  /** Trace_id del audit log · matchea el de getAuditSnapshot cuando aplica. */
  traceId: string;
  /** Drive file id mostrado en el trace-block plegable. */
  driveId: string;
}

// ─── Sprint 4 paso-5-d-revision-v2 · mockup 21 ─────────────────────────────
// Estado D · "Revisión v2 (drawer diff side-by-side)". Mock-only · edición
// v2 visual-only en este sub-PR. Wire real backend en sub-PR posterior
// (paso-5-pdf-real-wire) · inputs editables en (paso-5-v2-editable).

/** Fila de la tabla diff side-by-side del drawer. */
export interface PdfV2DiffRow {
  /** Label del campo (ej "Vigencia", "Subtotal MO"). */
  field: string;
  /** Valor v1 formateado para display. */
  v1Value: string;
  /** Valor v2 formateado para display. Si igual a v1 → row sin clase `.diff`. */
  v2Value: string;
  /** Cuando difiere · explicación breve "↳ era ..." mostrada bajo el valor v2. */
  trace?: string;
  /** Tipo de valor para clases auxiliares (`.dd-val.mono` para números/dates,
   * default sin mono para textos largos como "Datos de envío"). */
  display?: "mono" | "text";
  /** Variante de la row (`.dd-row.money` para subtotales). */
  variant?: "default" | "money";
  /** Para casos vacío→texto · marca el lado v1 como `.dd-val.empty`. */
  v1Empty?: boolean;
}

/** Lista de cambios resumidos del mockup 21 · sección Resumen del drawer y
 * del modal confirmar v2 (`.audit-note.purple` con `.modal-ul.tight`). */
export interface PdfV2ChangeSummary {
  /** Texto liso del cambio · admite markup ligero via `prev` y `outcome`. */
  field: string;
  /** "7 →" (antes) opcional. */
  prev?: string;
  /** "15 días" (después) · highlight visual. */
  outcome: string;
}

/** Datos canon del estado D para un quoteId. Mock-only. */
export interface PdfV2RevisionData {
  /** 6 rows del side-by-side. */
  rows: PdfV2DiffRow[];
  /** Resumen para sección "Resumen" y modal v2. */
  summary: PdfV2ChangeSummary[];
  /** Count de cambios (4 con cambio · 2 sin cambio en el canon). */
  diffCount: number;
  unchangedCount: number;
}

/* ─── Sprint 4 audit-trail-copy · GET /api/quotes/{id}/audit-log ─────── */

export interface AuditLogEventItem {
  created_at: string;
  event_type: string;
  source: string;
  summary: string;
  payload: Record<string, unknown>;
  success: boolean;
  error_message?: string | null;
  elapsed_ms?: number | null;
  turn_index?: number | null;
  request_id?: string | null;
}

export interface AuditLogTokensSummary {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number;
  iterations: number;
  models_used: string[];
}

export interface AuditLogToolUsage {
  tool_name: string;
  count: number;
  total_ms: number;
  error_count: number;
}

export interface AuditLogMeta {
  quote_id: string;
  status: string;
  client_name?: string | null;
  project?: string | null;
  material?: string | null;
  total_ars?: number | null;
  total_usd?: number | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLogResponse {
  meta: AuditLogMeta;
  input_message?: string | null;
  plan_files: string[];
  events: AuditLogEventItem[];
  events_total: number;
  events_truncated: boolean;
  chat_duration_ms?: number | null;
  tokens: AuditLogTokensSummary;
  tools_used: AuditLogToolUsage[];
  quote_breakdown?: Record<string, unknown> | null;
  errors: AuditLogEventItem[];
}

/* ─── CatalogConfig · Sprint 4 sub-PR 22.2.a config-ui-page ──────────
   Shape del catálogo `config` (api/catalog/config.json). Frontend
   GET/PUT del blob completo, pero solo edita las 6 keys del scope. */

export interface CatalogConfigMeasurements {
  default_depth: number;
  default_zocalo_height: number;
  default_alzada_height: number;
  tall_zocalo_threshold?: number;
  [k: string]: unknown;
}

export interface CatalogConfigDefaults {
  colocacion_particulares: boolean;
  delivery_zone_sku: string;
  forma_pago: string;
  [k: string]: unknown;
}

export interface CatalogConfigDiscount {
  imported_percentage?: number;
  national_percentage?: number;
  building_percentage?: number;
  building_min_m2_threshold?: number;
  min_m2_threshold?: number;
  [k: string]: unknown;
}

export interface CatalogConfigMerma {
  small_piece_threshold_m2?: number;
  [k: string]: unknown;
}

export interface CatalogConfig {
  measurements: CatalogConfigMeasurements;
  defaults: CatalogConfigDefaults;
  discount?: CatalogConfigDiscount;
  merma?: CatalogConfigMerma;
  [k: string]: unknown;
}

/** Campos editables desde /configuracion.
 *
 * Sub-PR 22.2.a · 6 fields (mesada + operativos).
 * Sub-PR 22.2.a.III · +6 fields (descuentos + costing).
 *
 * El nombre del field es flat (camel-ish) · el path JSON real al que
 * mapea está documentado en `extractEditableFields` / `applyEditableFields`.
 */
export interface ConfigEditableFields {
  // 22.2.a · mesada
  default_depth: number;
  default_zocalo_height: number;
  default_alzada_height: number;
  // 22.2.a · operativos
  colocacion_particulares: boolean;
  delivery_zone_sku: string;
  forma_pago: string;
  // 22.2.a.III · descuentos
  discount_imported_percentage: number;
  discount_national_percentage: number;
  discount_building_percentage: number;
  discount_building_min_m2_threshold: number;
  discount_min_m2_threshold: number;
  // 22.2.a.III · costing
  merma_small_piece_threshold_m2: number;
}

export const CONFIG_EDITABLE_KEYS: ReadonlyArray<keyof ConfigEditableFields> = [
  "default_depth",
  "default_zocalo_height",
  "default_alzada_height",
  "colocacion_particulares",
  "delivery_zone_sku",
  "forma_pago",
  "discount_imported_percentage",
  "discount_national_percentage",
  "discount_building_percentage",
  "discount_building_min_m2_threshold",
  "discount_min_m2_threshold",
  "merma_small_piece_threshold_m2",
];

function _num(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function extractEditableFields(cfg: CatalogConfig): ConfigEditableFields {
  return {
    default_depth: _num(cfg.measurements?.default_depth, 0.6),
    default_zocalo_height: _num(cfg.measurements?.default_zocalo_height, 0.05),
    default_alzada_height: _num(cfg.measurements?.default_alzada_height, 0.6),
    colocacion_particulares: cfg.defaults?.colocacion_particulares ?? true,
    delivery_zone_sku: cfg.defaults?.delivery_zone_sku ?? "ENVIOROS",
    forma_pago: cfg.defaults?.forma_pago ?? "Contado",
    discount_imported_percentage: _num(cfg.discount?.imported_percentage, 5),
    discount_national_percentage: _num(cfg.discount?.national_percentage, 8),
    discount_building_percentage: _num(cfg.discount?.building_percentage, 18),
    discount_building_min_m2_threshold: _num(cfg.discount?.building_min_m2_threshold, 15),
    discount_min_m2_threshold: _num(cfg.discount?.min_m2_threshold, 6),
    merma_small_piece_threshold_m2: _num(cfg.merma?.small_piece_threshold_m2, 1.0),
  };
}

/** Devuelve un nuevo blob con los fields del UI aplicados sobre el
 * blob original (preserva todas las keys que NO edita el UI). */
export function applyEditableFields(
  base: CatalogConfig,
  edits: ConfigEditableFields,
): CatalogConfig {
  return {
    ...base,
    measurements: {
      ...(base.measurements ?? {}),
      default_depth: edits.default_depth,
      default_zocalo_height: edits.default_zocalo_height,
      default_alzada_height: edits.default_alzada_height,
    },
    defaults: {
      ...(base.defaults ?? {}),
      colocacion_particulares: edits.colocacion_particulares,
      delivery_zone_sku: edits.delivery_zone_sku,
      forma_pago: edits.forma_pago,
    },
    discount: {
      ...(base.discount ?? {}),
      imported_percentage: edits.discount_imported_percentage,
      national_percentage: edits.discount_national_percentage,
      building_percentage: edits.discount_building_percentage,
      building_min_m2_threshold: edits.discount_building_min_m2_threshold,
      min_m2_threshold: edits.discount_min_m2_threshold,
    },
    merma: {
      ...(base.merma ?? {}),
      small_piece_threshold_m2: edits.merma_small_piece_threshold_m2,
    },
  };
}
