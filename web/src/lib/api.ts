/**
 * Mock client v2 — Sprint 2 paso 1 brief upload.
 *
 * Mock-first per Master §21.7 decisión 4 + endpoint dedicado del paso 1
 * marcado como "P2 · NO EXISTE" en docs/handoff-context/missing-endpoints.md
 * (`POST /api/quotes/{id}/brief`). Este client simula el response de
 * creación de draft con latencia 2-5s y soporte de AbortController.
 * Retorna las cifras canon Cueto-Heredia (Master §13).
 *
 * TODO sprint-3/api-integration: switch al cliente HTTP real cuando
 * el backend implemente el endpoint dedicado, o cuando se decida
 * pasarlo dentro del primer turno del chat (Opción A en
 * missing-endpoints.md).
 */
import { CANONICAL_QUOTE } from "./mocks/canonicalQuote";

export const V2_API_BASE = "/api";

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

function validateInput(input: CreateDraftQuoteInput): void {
  if (!VALIDATION.PLAN_MIME.includes(input.planFile.type as "application/pdf")) {
    throw new ApiError("INVALID_MIME", "El plan debe ser un PDF", 422);
  }
  if (input.planFile.size > VALIDATION.PLAN_MAX_BYTES) {
    throw new ApiError("FILE_TOO_LARGE", "El plan supera 20MB", 413);
  }
  if (input.photos) {
    if (input.photos.length > VALIDATION.PHOTOS_MAX_COUNT) {
      throw new ApiError("TOO_MANY_PHOTOS", "Máximo 5 fotos", 422);
    }
    for (const photo of input.photos) {
      if (!VALIDATION.PHOTO_MIME.includes(photo.type as "image/jpeg" | "image/png")) {
        throw new ApiError("INVALID_PHOTO_MIME", "Las fotos deben ser JPG o PNG", 422);
      }
      if (photo.size > VALIDATION.PHOTO_MAX_BYTES) {
        throw new ApiError("PHOTO_TOO_LARGE", "Cada foto debe ser menor a 5MB", 413);
      }
    }
  }
  if (input.briefText && input.briefText.length > VALIDATION.BRIEF_MAX_CHARS) {
    throw new ApiError("BRIEF_TOO_LONG", "El brief no puede superar 2000 caracteres", 422);
  }
}

/**
 * Crea un draft quote a partir de un PDF + fotos + brief.
 *
 * Mock: simula latencia 2-5s. Si llega `signal.aborted`, rechaza con
 * `AbortError` para que el UI pueda volver al estado B (form cargado).
 */
export async function createDraftQuote(
  input: CreateDraftQuoteInput,
  options?: { signal?: AbortSignal },
): Promise<CreateDraftQuoteResponse> {
  validateInput(input);

  const latency = 2000 + Math.random() * 3000;
  await new Promise<void>((resolve, reject) => {
    if (options?.signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timeout = setTimeout(resolve, latency);
    options?.signal?.addEventListener("abort", () => {
      clearTimeout(timeout);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });

  return {
    id: CANONICAL_QUOTE.id,
    status: "draft",
    createdAt: new Date().toISOString(),
  };
}

/* ════════════════════════════════════════════════════════════════════════
   Sprint 2 paso-2-contexto · mock client de contexto + chat scoped
   ════════════════════════════════════════════════════════════════════════
   Endpoints `PATCH /api/v1/quotes/{id}/context` y `POST /api/v1/quotes/{id}/chat`
   marcados como missing/parcial en docs/handoff-context/missing-endpoints.md.
   El mock cubre la brecha temporal hasta sprint-3/api-integration. */

/** Origen del valor de cada campo del contexto (Master §10 data model). */
export type ContextOrigin =
  | "BRIEF" // extraído del brief original (PDF + textarea)
  | "INFERIDO" // inferido por Valentina al cruzar catálogos / regla
  | "DEFAULT" // valor por defecto (ej. zócalo 5cm)
  | "EDITADO" // Marina lo tocó manualmente
  | "FALTA"; // no extraído ni inferido — requiere input humano

export interface ContextField<T = string | number | boolean | null> {
  value: T;
  origin: ContextOrigin;
  edited?: boolean;
}

/** Los 11 campos del contexto (Master §6 mockup 01-A).
 *  Sprint 2.5 fix-up: campos string admiten `null` para representar
 *  `origin: 'FALTA'` (quotes sin canon definido en CONTEXT_BY_QUOTE_ID).
 */
export interface ContextData {
  cliente: string | null; // arquitecta / razón social
  contacto: string | null; // teléfono / email
  localidad: string | null; // obra · ciudad
  plazo: string | null; // desde confirmación de medidas
  tipologia: string | null; // cocina, baño, mesa
  tipo_obra: "particular" | "edificio";
  material: string | null; // piedra o engineered
  pileta: string | null; // tipo + origen
  zocalo: string | null; // contra pared · si/no + alto
  regrueso: string | null; // borde frontal grueso
  anafe: boolean; // define MO ANAFE en paso 3
}

export type ContextResponse = {
  [K in keyof ContextData]: ContextField<ContextData[K]>;
};

/** In-memory store para que updates persistan dentro de la sesión del browser. */
const _contextStore = new Map<string, ContextResponse>();

/** Reset helper (útil para tests / reset entre quotes en dev). */
export function _resetContextStore() {
  _contextStore.clear();
}

async function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

/**
 * GET context para un quote. Mock indexa por quoteId via CONTEXT_BY_QUOTE_ID
 * (PRES-2026-018 → Cueto-Heredia, PRES-2026-017 → Pereyra) con fallback
 * a CANONICAL_CONTEXT_GENERIC para quotes del dataset sin canon definido.
 *
 * Fix BLOCKER del Visual Check del PR #460 — antes devolvía siempre
 * CANONICAL_CONTEXT (Cueto-Heredia) sin importar el quoteId.
 */
export async function getContextForQuote(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<ContextResponse> {
  await delay(150 + Math.random() * 200, options?.signal);
  const existing = _contextStore.get(quoteId);
  if (existing) return existing;
  // Lazy import para evitar circular en build (canonicalQuote re-importa types).
  const { CONTEXT_BY_QUOTE_ID, CANONICAL_CONTEXT_GENERIC } = await import("./mocks/canonicalQuote");
  const base = CONTEXT_BY_QUOTE_ID[quoteId] ?? CANONICAL_CONTEXT_GENERIC;
  const seeded = JSON.parse(JSON.stringify(base)) as ContextResponse;
  _contextStore.set(quoteId, seeded);
  return seeded;
}

/**
 * PATCH parcial del contexto. Marca cada campo recibido como
 * `origin: 'EDITADO'` + `edited: true` (regla Master §4 #3).
 */
export async function updateContextForQuote(
  quoteId: string,
  partial: Partial<ContextData>,
  options?: { signal?: AbortSignal },
): Promise<ContextResponse> {
  await delay(120 + Math.random() * 180, options?.signal);
  const current = await getContextForQuote(quoteId);
  // Cast a Record para permitir asignación dinámica por key — la mapped
  // type ContextResponse rechaza writes heterogéneos sin narrowing.
  const next = { ...current } as Record<keyof ContextData, ContextField>;
  for (const k of Object.keys(partial) as (keyof ContextData)[]) {
    const value = partial[k];
    if (value === undefined) continue;
    next[k] = {
      value: value as string | number | boolean | null,
      origin: "EDITADO",
      edited: true,
    };
  }
  const result = next as ContextResponse;
  _contextStore.set(quoteId, result);
  return result;
}

/* ─── Chat scoped streaming (mock SSE via ReadableStream) ─────────── */

export type ChatScope = "contexto" | "despiece" | "calculo" | "pdf";

export interface ChatStreamChunk {
  type: "text" | "done" | "error";
  content?: string;
  message?: string;
}

/** Frases canónicas rioplatenses para mock — varían según scope.
 *  `targetPieceId` (opcional) enfoca la respuesta del scope `despiece`
 *  en una pieza puntual (mockup 06 · chat sobre R2 = bacha). */
function pickResponse(scope: ChatScope, message: string, targetPieceId?: string): string {
  const lower = message.toLowerCase();
  if (scope === "despiece") {
    if (targetPieceId === "R2" || lower.includes("bacha") || lower.includes("pileta")) {
      return "Sí, da con margen pero ajustado. Una bacha doble entra en 65cm de ancho útil; si va undermount con rebaje 45° te recomiendo +2cm en R2 y recalculo el m².";
    }
    if (lower.includes("inglete") || lower.includes("corte") || lower.includes("45")) {
      return "El INGLETE del plano lo traduje a CORTE45 donde se unen los brazos de la mesada. Es un corte a 45° — lo cargo como MO en el paso 4.";
    }
    if (lower.includes("zócalo") || lower.includes("zocalo") || lower.includes("alzada")) {
      return "El zócalo y la alzada los calculo por ml real de cada lado. Si alguno no va, lo sacás de la tabla y recalculo el m² total.";
    }
    if (lower.includes("toma")) {
      return "Detecté 2 TOMAS en la alzada (símbolo del plano). Cada toma suma una línea de MO en el paso 4. Si son más o menos, editás la pieza y se ajusta.";
    }
    return "Te ayudo con el despiece. Click en la fila de la pieza que quieras revisar y te explico de dónde saqué cada medida.";
  }
  if (scope === "contexto") {
    if (lower.includes("anafe")) {
      return "Marqué anafe porque en el plano se ve el dibujo del símbolo en la mesada. Si no es así, lo desmarcás vos y se recalcula la MO en el paso 3.";
    }
    if (lower.includes("descuento") || lower.includes("arquitec")) {
      return "Cueto-Heredia matchea con architects.json (5% sobre material importado). Lo aplico solo en el material que sea importado, no sobre la MO ni el flete.";
    }
    if (lower.includes("pileta") || lower.includes("bacha")) {
      return "Inferí pileta empotrada porque el brief dice que la trae el cliente. Si fuera apoyada cambia el corte y tengo que rehacer despiece.";
    }
    if (lower.includes("material") || lower.includes("silestone")) {
      return "Silestone Blanco Norte salió del brief textual. Es engineered importado, así que aplica descuento arquitecta y NO tiene merma cero (sintéticos sí mermean a diferencia de Negro Brasil).";
    }
  }
  return "Te puedo ayudar con eso. Decime qué campo querés revisar y te explico de dónde lo saqué.";
}

/**
 * Mock SSE del chat scoped — emite chunks de texto cada 50-100ms para
 * simular streaming token-por-token. Soporta abort via signal.
 */
export function streamChat(
  _quoteId: string,
  message: string,
  scope: ChatScope,
  options?: { signal?: AbortSignal; targetPieceId?: string },
): ReadableStream<ChatStreamChunk> {
  const text = pickResponse(scope, message, options?.targetPieceId);
  const tokens = text.split(/(\s+)/); // split conservando whitespace

  return new ReadableStream<ChatStreamChunk>({
    async start(controller) {
      try {
        for (const token of tokens) {
          await delay(50 + Math.random() * 50, options?.signal);
          controller.enqueue({ type: "text", content: token });
        }
        controller.enqueue({ type: "done" });
        controller.close();
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          controller.close();
          return;
        }
        controller.enqueue({ type: "error", message: "stream-error" });
        controller.close();
      }
    },
  });
}

/* ════════════════════════════════════════════════════════════════════════
   Sprint 2.5 switch-to-main · mock dashboard
   ════════════════════════════════════════════════════════════════════════
   Endpoint `GET /api/v1/quotes` para listado del dashboard. Marcado como
   missing en docs/handoff-context/missing-endpoints.md (P1 listing). El mock
   sirve `DASHBOARD_QUOTES` con filtros por status + search. */

import type { DashboardQuote, DashboardStatus, DashboardCounts } from "./mocks/dashboardDataset";
import { DASHBOARD_QUOTES, DASHBOARD_COUNTS } from "./mocks/dashboardDataset";

export interface ListQuotesFilters {
  /** Si vacío o ausente, devuelve todos. */
  statuses?: ReadonlyArray<DashboardStatus>;
  /** Subcadena buscada en `client` (case-insensitive). */
  search?: string;
  /** Pre-filter aplicado por KPI cards del desktop. */
  kpi?: "expire-soon" | "no-response";
}

function matchesFilters(quote: DashboardQuote, filters?: ListQuotesFilters): boolean {
  if (!filters) return true;
  if (filters.statuses && filters.statuses.length > 0) {
    if (!filters.statuses.includes(quote.status)) return false;
  }
  if (filters.search) {
    const needle = filters.search.toLowerCase();
    if (!quote.client.toLowerCase().includes(needle)) return false;
  }
  if (filters.kpi === "expire-soon") {
    const expireSoon =
      (quote.status === "sent" && (quote.daysToExpire ?? 999) <= 7) || quote.status === "expired";
    if (!expireSoon) return false;
  }
  if (filters.kpi === "no-response") {
    if (quote.status !== "sent" || quote.lastActivityDays <= 5) return false;
  }
  return true;
}

export async function listQuotes(
  filters?: ListQuotesFilters,
  options?: { signal?: AbortSignal },
): Promise<DashboardQuote[]> {
  await delay(200 + Math.random() * 300, options?.signal);
  return DASHBOARD_QUOTES.filter((q) => matchesFilters(q, filters));
}

export interface DashboardKpis {
  expireSoon: number;
  noResponse: number;
  pendingAction: number;
  counts: DashboardCounts;
}

export async function getDashboardKpis(options?: { signal?: AbortSignal }): Promise<DashboardKpis> {
  await delay(100 + Math.random() * 150, options?.signal);
  const expireSoonQuotes = DASHBOARD_QUOTES.filter(
    (q) => (q.status === "sent" && (q.daysToExpire ?? 999) <= 7) || q.status === "expired",
  );
  const noResponseQuotes = DASHBOARD_QUOTES.filter(
    (q) => q.status === "sent" && q.lastActivityDays > 5,
  );
  const pendingAction = new Set([
    ...expireSoonQuotes.map((q) => q.id),
    ...noResponseQuotes.map((q) => q.id),
  ]).size;
  return {
    expireSoon: expireSoonQuotes.length,
    noResponse: noResponseQuotes.length,
    pendingAction,
    counts: DASHBOARD_COUNTS,
  };
}

export type { DashboardQuote, DashboardStatus, DashboardCounts };

/* ════════════════════════════════════════════════════════════════════════
   Sprint 2.5 fix-up #2 · QuoteHeader metadata por quoteId
   ════════════════════════════════════════════════════════════════════════
   El Qhead + Topbar del chrome shell mostraban siempre datos de
   CANONICAL_QUOTE (PRES-2026-018 · Cueto-Heredia) sin importar el
   params.id de la URL. Fix arquitectónico: getQuoteMetadata deriva
   de DASHBOARD_QUOTES (single source of truth del listado) + fallback
   GENERIC para IDs no presentes en el dataset. */

export interface QuoteHeader {
  id: string;
  client: string;
  clientFull: string;
  material: string;
  m2: number;
  status: "draft" | "sent" | "expired" | "lost";
}

const GENERIC_QUOTE_HEADER: Omit<QuoteHeader, "id"> = {
  client: "Cliente sin identificar",
  clientFull: "PROYECTO SIN ASIGNAR",
  material: "—",
  m2: 0,
  status: "draft",
};

export async function getQuoteMetadata(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<QuoteHeader> {
  await delay(80 + Math.random() * 120, options?.signal);
  const found = DASHBOARD_QUOTES.find((q) => q.id === quoteId);
  if (found) {
    return {
      id: found.id,
      client: found.client,
      clientFull: found.clientFull,
      material: found.material,
      m2: found.m2,
      status: found.status,
    };
  }
  return { id: quoteId, ...GENERIC_QUOTE_HEADER };
}

/** Texto del banner Valentina del paso 2 — por quoteId. */
export async function getValentinaBriefSummary(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<string> {
  await delay(60 + Math.random() * 100, options?.signal);
  const { BRIEF_SUMMARY_BY_QUOTE_ID, BRIEF_SUMMARY_GENERIC } =
    await import("./mocks/canonicalQuote");
  return BRIEF_SUMMARY_BY_QUOTE_ID[quoteId] ?? BRIEF_SUMMARY_GENERIC;
}

/* ════════════════════════════════════════════════════════════════════════
   Sprint 3 paso-3-despiece · mock client de piezas (despiece)
   ════════════════════════════════════════════════════════════════════════
   Espeja el tool backend `list_pieces` (api/.../quote_engine/calculator.py),
   que recibe piezas con `largo`/`prof|alto` en METROS + `quantity` y devuelve
   labels + m² determinísticos. Como el endpoint dedicado del paso 3 todavía
   no existe (sprint-3/api-integration hace el switch a HTTP real), este mock
   cubre la brecha sirviendo las cifras canon del despiece Cueto-Heredia
   (mockup 04-despiece-A · Master §13).

   Discrepancias mockup ↔ contract documentadas (gana el mockup · Master §14):
   - El mockup muestra cm ("Largo (cm)" 285); el contract usa metros (largo
     2.85). El tipo `Piece` usa `width_mm`/`depth_mm` (mm) como unidad canónica
     interna → la UI divide /10 para mostrar cm. m² = width_mm·depth_mm / 1e6.
   - El mockup tiene columna `Cant.` y labels descriptivos + símbolos del plano
     (.det-sym) que NO están en el interface base del prompt. Se extienden
     `Piece` con `quantity`, `label`, `sublabel`, `detected_symbols` (el backend
     ya maneja `quantity` y `description`). */

/** Símbolo detectado en el plano y su traducción a SKU/operación.
 *  Mockup 04-despiece: INGLETE→CORTE45, DESAGUE→AGUJEROAPOYO, 2 TOMAS→TOMAS. */
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
  id: string; // "R1", "R2", ...
  type: PieceType;
  /** Label descriptivo del mockup (ej. "Mesada perimetral · brazo izq"). */
  label: string;
  /** Sub-texto bajo el label (ej. "contra pared norte"). */
  sublabel?: string;
  width_mm: number; // columna "Largo" del mockup (cm × 10)
  depth_mm: number; // columna "Ancho" del mockup (cm × 10)
  quantity: number; // columna "Cant." del mockup
  options: PieceOptions;
  /** Símbolos del plano (.det-sym) — sólo presentes en piezas origin=IA. */
  detected_symbols?: DetectedSymbol[];
  origin: "IA" | "EDITADO" | "AGREGADO_MANUAL";
  confidence?: number; // 0..1, sólo si origin=IA
  extracted_from?: string; // referencia al plano (ej. "plan_p1_z2")
  edited?: boolean; // true si Marina lo tocó
}

export interface TimelineStep {
  step: 1 | 2 | 3 | 4;
  label: string;
  state: "pending" | "running" | "done" | "failed";
  /** Texto de salida de la pasada (.out del mockup). */
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

/** In-memory store para que edits/add/delete persistan en la sesión del browser. */
const _piecesStore = new Map<string, PieceList>();

/** Reset helper (tests / reset entre quotes en dev). */
export function _resetPiecesStore() {
  _piecesStore.clear();
}

function deepClonePieces(pieces: Piece[]): Piece[] {
  return JSON.parse(JSON.stringify(pieces)) as Piece[];
}

/** Clona la lista devuelta para que el caller (hook) NUNCA comparta refs con
 *  `_piecesStore` — si las compartiera, una mutación del store (push/replace)
 *  se duplicaría con el append optimista del hook. */
function clonePieceList(list: PieceList): PieceList {
  return JSON.parse(JSON.stringify(list)) as PieceList;
}

function buildDoneTimeline(count: number, totalM2: number): TimelineStep[] {
  return [
    { step: 1, label: "Inventario", state: "done", detail: "piezas identificadas desde el plano" },
    { step: 2, label: "Paredes y libres", state: "done", detail: "perímetro vs piezas libres" },
    { step: 3, label: "Medidas", state: "done", detail: "cotas en mm convertidas a cm" },
    {
      step: 4,
      label: "Verificación",
      state: "done",
      detail: `${count} piezas confirmadas · ${totalM2.toFixed(2)} m²`,
    },
  ];
}

function buildFailedTimeline(): TimelineStep[] {
  return [
    { step: 1, label: "Inventario", state: "failed", detail: "sin brief ni contexto" },
    { step: 2, label: "Paredes y libres", state: "pending" },
    { step: 3, label: "Medidas", state: "pending" },
    { step: 4, label: "Verificación", state: "pending" },
  ];
}

async function seedPieceList(quoteId: string): Promise<PieceList> {
  const { PIECES_BY_QUOTE_ID, TIMELINE_BY_QUOTE_ID } = await import("./mocks/canonicalQuote");
  const canon = PIECES_BY_QUOTE_ID[quoteId];
  if (canon && canon.length > 0) {
    const pieces = deepClonePieces(canon);
    const total = piecesTotalM2(pieces);
    return {
      pieces,
      status: "done",
      timeline: TIMELINE_BY_QUOTE_ID[quoteId] ?? buildDoneTimeline(pieces.length, total),
      warnings: [],
    };
  }
  // Sin canon definido → Valentina no pudo inferir (empty state · mockup 16).
  return {
    pieces: [],
    status: "failed",
    timeline: buildFailedTimeline(),
    warnings: ["Valentina no pudo proponer un despiece — cargá el brief o completá a mano."],
  };
}

/**
 * GET piezas del despiece para un quote. Indexa por quoteId via
 * PIECES_BY_QUOTE_ID (PRES-2026-018 → Cueto-Heredia 5 piezas, PRES-2026-017 →
 * Pereyra) con fallback a empty (`status: 'failed'`) para quotes sin canon.
 *
 * Lección Sprint 2.5 (fix-up #2 del PR #460): TODO lookup indexa por quoteId.
 * NUNCA devolver siempre las piezas de PRES-018.
 */
export async function listPiecesForQuote(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<PieceList> {
  await delay(500 + Math.random() * 300, options?.signal);
  const existing = _piecesStore.get(quoteId);
  if (existing) return clonePieceList(existing);
  const seeded = await seedPieceList(quoteId);
  _piecesStore.set(quoteId, seeded);
  return clonePieceList(seeded);
}

async function ensureList(quoteId: string): Promise<PieceList> {
  const existing = _piecesStore.get(quoteId);
  if (existing) return existing;
  const seeded = await seedPieceList(quoteId);
  _piecesStore.set(quoteId, seeded);
  return seeded;
}

/**
 * PATCH parcial de una pieza. Marca `edited: true` y, si era propuesta de la
 * IA, `origin: 'EDITADO'` (regla Master §4 #1 — la edición humana no se pisa).
 */
export async function updatePieceForQuote(
  quoteId: string,
  pieceId: string,
  partial: Partial<Piece>,
  options?: { signal?: AbortSignal },
): Promise<Piece> {
  await delay(120 + Math.random() * 160, options?.signal);
  const list = await ensureList(quoteId);
  const idx = list.pieces.findIndex((p) => p.id === pieceId);
  if (idx === -1) {
    throw new ApiError("PIECE_NOT_FOUND", `Pieza ${pieceId} no existe en ${quoteId}`, 404);
  }
  const current = list.pieces[idx];
  const nextOrigin = current.origin === "AGREGADO_MANUAL" ? current.origin : "EDITADO";
  const updated: Piece = {
    ...current,
    ...partial,
    id: current.id,
    origin: nextOrigin,
    edited: true,
  };
  list.pieces[idx] = updated;
  _piecesStore.set(quoteId, list);
  return { ...updated };
}

/** Próximo id "R{n}" libre dentro del set. */
function nextPieceId(pieces: Piece[]): string {
  let max = 0;
  for (const p of pieces) {
    const m = /^R(\d+)$/.exec(p.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `R${max + 1}`;
}

/** Agrega una pieza manual (origin=AGREGADO_MANUAL, sin confidence/IA). */
export async function addPieceForQuote(
  quoteId: string,
  piece: Omit<Piece, "id" | "origin" | "confidence" | "extracted_from">,
  options?: { signal?: AbortSignal },
): Promise<Piece> {
  await delay(120 + Math.random() * 160, options?.signal);
  const list = await ensureList(quoteId);
  const created: Piece = {
    ...piece,
    id: nextPieceId(list.pieces),
    origin: "AGREGADO_MANUAL",
    edited: true,
  };
  list.pieces.push(created);
  _piecesStore.set(quoteId, list);
  return { ...created };
}

/** Elimina una pieza del set. */
export async function deletePieceForQuote(
  quoteId: string,
  pieceId: string,
  options?: { signal?: AbortSignal },
): Promise<void> {
  await delay(120 + Math.random() * 160, options?.signal);
  const list = await ensureList(quoteId);
  list.pieces = list.pieces.filter((p) => p.id !== pieceId);
  _piecesStore.set(quoteId, list);
}

/**
 * Re-corre la inferencia de Valentina.
 * - `mode: 'all'` (default) → descarta TODO y re-siembra desde el canon.
 * - `mode: 'keep-edits'` → re-siembra IA pero preserva las piezas editadas /
 *   manuales por id (Master §10 #10 — las ediciones no se pisan al re-generar).
 */
export async function regenerateDespiece(
  quoteId: string,
  options?: { signal?: AbortSignal; mode?: "all" | "keep-edits" },
): Promise<PieceList> {
  await delay(700 + Math.random() * 500, options?.signal);
  const fresh = await seedPieceList(quoteId);
  if (options?.mode === "keep-edits") {
    const previous = _piecesStore.get(quoteId);
    const kept = (previous?.pieces ?? []).filter(
      (p) => p.edited === true || p.origin === "AGREGADO_MANUAL",
    );
    const keptIds = new Set(kept.map((p) => p.id));
    fresh.pieces = [...fresh.pieces.filter((p) => !keptIds.has(p.id)), ...kept];
  }
  _piecesStore.set(quoteId, fresh);
  return clonePieceList(fresh);
}
