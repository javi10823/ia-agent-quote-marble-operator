/**
 * Mock client v2 · Sprint 3 api-integration.
 *
 * Movido desde `lib/api.ts` (split en módulos). Comportamiento idéntico —
 * los 50 E2E corren contra estos mocks por default (sin NEXT_PUBLIC_API_URL).
 * Tipos compartidos viven en `./types`.
 *
 * streamChat extendido (FASE 3.2): emite los 4 event types nuevos
 * (action / context_analysis / dual_read_result / zone_selector) ante
 * keywords de trigger, además del streaming de texto.
 */
import { CANONICAL_QUOTE } from "../mocks/canonicalQuote";
import { DASHBOARD_QUOTES, DASHBOARD_COUNTS, type DashboardQuote } from "../mocks/dashboardDataset";
import {
  ApiError,
  VALIDATION,
  piecesTotalM2,
  type ChatScope,
  type ChatStreamChunk,
  type ContextData,
  type ContextField,
  type ContextResponse,
  type CreateDraftQuoteInput,
  type CreateDraftQuoteResponse,
  type DashboardKpis,
  type ListQuotesFilters,
  type Piece,
  type PieceList,
  type QuoteHeader,
  type TimelineStep,
} from "./types";

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
  return { id: CANONICAL_QUOTE.id, status: "draft", createdAt: new Date().toISOString() };
}

/* ─── Contexto ───────────────────────────────────────────────────── */

const _contextStore = new Map<string, ContextResponse>();

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

export async function getContextForQuote(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<ContextResponse> {
  await delay(150 + Math.random() * 200, options?.signal);
  const existing = _contextStore.get(quoteId);
  if (existing) return existing;
  const { CONTEXT_BY_QUOTE_ID, CANONICAL_CONTEXT_GENERIC } =
    await import("../mocks/canonicalQuote");
  const base = CONTEXT_BY_QUOTE_ID[quoteId] ?? CANONICAL_CONTEXT_GENERIC;
  const seeded = JSON.parse(JSON.stringify(base)) as ContextResponse;
  _contextStore.set(quoteId, seeded);
  return seeded;
}

export async function updateContextForQuote(
  quoteId: string,
  partial: Partial<ContextData>,
  options?: { signal?: AbortSignal },
): Promise<ContextResponse> {
  await delay(120 + Math.random() * 180, options?.signal);
  const current = await getContextForQuote(quoteId);
  const next = { ...current } as Record<keyof ContextData, ContextField>;
  for (const k of Object.keys(partial) as (keyof ContextData)[]) {
    const value = partial[k];
    if (value === undefined) continue;
    next[k] = { value: value as string | number | boolean | null, origin: "EDITADO", edited: true };
  }
  const result = next as ContextResponse;
  _contextStore.set(quoteId, result);
  return result;
}

/* ─── Chat scoped (mock SSE via ReadableStream) ──────────────────── */

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

/** Card events plausibles según keywords del mensaje (matchean shapes reales). */
function mockCardEvents(scope: ChatScope, message: string): ChatStreamChunk[] {
  const lower = message.toLowerCase();
  const events: ChatStreamChunk[] = [];
  if (lower.includes("plano") || lower.includes("leé") || lower.includes("medidas")) {
    events.push({ type: "action", content: "📐 Leyendo medidas del plano…" });
    events.push({
      type: "dual_read_result",
      content: JSON.stringify({
        sectores: [
          { id: "S1", tipo: "cocina", tramos: [], m2_total: { valor: 6.5, status: "ok" } },
        ],
        requires_human_review: false,
        source: "DUAL",
        view_type: "planta",
      }),
    });
  }
  if (scope === "contexto" && (lower.includes("contexto") || lower.includes("analiz"))) {
    events.push({
      type: "context_analysis",
      content: JSON.stringify({
        data_known: ["cliente", "material"],
        assumptions: ["pileta empotrada"],
        tech_detections: [{ field: "anafe" }],
        pending_questions: [],
        sector_summary: "cocina U + isla",
      }),
    });
  }
  if (lower.includes("zona") || lower.includes("dónde") || lower.includes("donde")) {
    events.push({
      type: "zone_selector",
      content: JSON.stringify({
        image_url: "/files/mock/page_1.jpg",
        page_num: 1,
        instruction: "Dibujá un rectángulo sobre la zona a revisar.",
      }),
    });
  }
  return events;
}

export function streamChat(
  _quoteId: string,
  message: string,
  scope: ChatScope,
  options?: { signal?: AbortSignal; targetPieceId?: string },
): ReadableStream<ChatStreamChunk> {
  const text = pickResponse(scope, message, options?.targetPieceId);
  const tokens = text.split(/(\s+)/);
  const cards = mockCardEvents(scope, message);

  return new ReadableStream<ChatStreamChunk>({
    async start(controller) {
      try {
        // Card events de tool-use ANTES del texto (igual que el backend real).
        for (const card of cards) {
          await delay(60 + Math.random() * 60, options?.signal);
          controller.enqueue(card);
        }
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

/* ─── Dashboard ──────────────────────────────────────────────────── */

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

/* ─── Quote header ───────────────────────────────────────────────── */

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

export async function getValentinaBriefSummary(
  quoteId: string,
  _options?: { signal?: AbortSignal },
): Promise<string> {
  await delay(60 + Math.random() * 100, _options?.signal);
  const { BRIEF_SUMMARY_BY_QUOTE_ID, BRIEF_SUMMARY_GENERIC } =
    await import("../mocks/canonicalQuote");
  return BRIEF_SUMMARY_BY_QUOTE_ID[quoteId] ?? BRIEF_SUMMARY_GENERIC;
}

/* ─── Piezas / despiece ──────────────────────────────────────────── */

const _piecesStore = new Map<string, PieceList>();

export function _resetPiecesStore() {
  _piecesStore.clear();
}

function deepClonePieces(pieces: Piece[]): Piece[] {
  return JSON.parse(JSON.stringify(pieces)) as Piece[];
}

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
  const { PIECES_BY_QUOTE_ID, TIMELINE_BY_QUOTE_ID } = await import("../mocks/canonicalQuote");
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
  return {
    pieces: [],
    status: "failed",
    timeline: buildFailedTimeline(),
    warnings: ["Valentina no pudo proponer un despiece — cargá el brief o completá a mano."],
  };
}

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

function nextPieceId(pieces: Piece[]): string {
  let max = 0;
  for (const p of pieces) {
    const m = /^R(\d+)$/.exec(p.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `R${max + 1}`;
}

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

/* ─── Cálculo (paso 4) ───────────────────────────────────────────── */

const _calcStore = new Map<string, import("./types").CalculationResult>();

export function _resetCalcStore() {
  _calcStore.clear();
}

/**
 * GET calculation para un quote. Fallback gracioso desde el inicio
 * (lección Sprint 3 día 3): IDs desconocidos (UUIDs del backend real,
 * web-XXX, etc.) → `CANONICAL_CALCULATION_GENERIC` en lugar de undefined.
 *
 * Sprint 4 wire chat-driven: el backend produce `dual_read_result` +
 * `context_analysis` durante el chat; el cálculo se deriva. Por ahora
 * mock con cifras del mockup 07-paso4-A-v4.
 */
export async function getCalculationForQuote(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").CalculationResult> {
  await delay(180 + Math.random() * 220, options?.signal);
  const cached = _calcStore.get(quoteId);
  if (cached) return cached;
  const {
    CALCULATIONS_BY_QUOTE_ID,
    CANONICAL_CALCULATION_GENERIC,
    CANONICAL_CALCULATION_018_PATCH_ERROR,
  } = await import("../mocks/canonicalQuote");
  // Trigger E2E del estado B (mockup 08 · validation error post-PATCH).
  // En backend real lo dispara el server con un patch inconsistente; acá
  // un sufijo `-ERROR` en el quoteId lo alcanza desde tests.
  if (quoteId.endsWith("-ERROR")) {
    const seeded = JSON.parse(
      JSON.stringify(CANONICAL_CALCULATION_018_PATCH_ERROR),
    ) as import("./types").CalculationResult;
    seeded.quoteId = quoteId;
    _calcStore.set(quoteId, seeded);
    return seeded;
  }
  const base = CALCULATIONS_BY_QUOTE_ID[quoteId] ?? CANONICAL_CALCULATION_GENERIC;
  const seeded = JSON.parse(JSON.stringify(base)) as import("./types").CalculationResult;
  _calcStore.set(quoteId, seeded);
  return seeded;
}

/** Simula re-cálculo (toolbar "↻ Re-calcular"). */
export async function triggerCalculation(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").CalculationResult> {
  await delay(800 + Math.random() * 400, options?.signal);
  _calcStore.delete(quoteId);
  return getCalculationForQuote(quoteId, options);
}

/** Auto-fix del estado B (botón "✕ Eliminar merma"). */
export async function applyAutoFix(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").CalculationResult> {
  await delay(300 + Math.random() * 200, options?.signal);
  const { CANONICAL_CALCULATION_018 } = await import("../mocks/canonicalQuote");
  const fresh = JSON.parse(
    JSON.stringify(CANONICAL_CALCULATION_018),
  ) as import("./types").CalculationResult;
  fresh.quoteId = quoteId;
  _calcStore.set(quoteId, fresh);
  return fresh;
}

// ─── Sprint 3 observability-per-row · mockup 13 ───
// Audit snapshot mock con fallback gracioso desde el inicio.
// Datos LITERALES del mockup 13-audit-banner-on.html (model claude-sonnet-4,
// tokens 1842/612, latency 4.2s, trace q_8f2a, prompt despiece.v3.2,
// temp 0.2 seed fixed, cache 84%, 4 eventos del despiece flow).

const _auditByQuote: Record<string, import("./types").AuditSnapshot> = {
  "PRES-2026-018": {
    lastCall: {
      model: "claude-sonnet-4",
      scope: "despiece · 5 piezas + contexto confirmado",
      tokensIn: 1842,
      tokensOut: 612,
      latencyMs: 4200,
    },
    trace: {
      traceId: "q_8f2a",
      promptVersion: "despiece.v3.2",
      temperature: "0.2 · seed fixed",
      cacheHitPct: 84,
    },
    events: [
      { timestamp: "10:04:12", name: "contexto.confirm" },
      { timestamp: "10:04:14", name: "despiece.draft.start" },
      { timestamp: "10:04:18", name: "despiece.draft.partial", detail: "5/7" },
      { timestamp: "10:04:22", name: "despiece.draft.calc", detail: "R6, R7" },
    ],
  },
  "PRES-2026-017": {
    lastCall: {
      model: "claude-sonnet-4",
      scope: "calculo · particular · IVA on",
      tokensIn: 1124,
      tokensOut: 389,
      latencyMs: 2800,
    },
    trace: {
      traceId: "q_4c1e",
      promptVersion: "calculo.v2.4",
      temperature: "0.2 · seed fixed",
      cacheHitPct: 72,
    },
    events: [
      { timestamp: "09:51:08", name: "contexto.confirm" },
      { timestamp: "09:51:09", name: "despiece.confirm" },
      { timestamp: "09:51:11", name: "calculo.draft.start" },
      { timestamp: "09:51:13", name: "calculo.draft.done", detail: "OK" },
    ],
  },
};

const _auditGeneric: import("./types").AuditSnapshot = {
  lastCall: {
    model: "—",
    scope: "—",
    tokensIn: 0,
    tokensOut: 0,
    latencyMs: 0,
  },
  trace: {
    traceId: "—",
    promptVersion: "—",
    temperature: "—",
    cacheHitPct: 0,
  },
  events: [],
};

/**
 * Snapshot del audit-tray para un quote. Mock-only · fallback gracioso para
 * IDs desconocidos (UUID/web-XXX) que devuelve el snapshot generic en em-dash.
 * Sprint 4: wire al backend cuando exponga la metadata real.
 */
export async function getAuditSnapshot(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").AuditSnapshot> {
  await delay(120 + Math.random() * 120, options?.signal);
  return _auditByQuote[quoteId] ?? _auditGeneric;
}
