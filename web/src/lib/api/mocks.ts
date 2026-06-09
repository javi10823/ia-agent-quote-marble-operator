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
  // Sprint 4 ssr-auth: `bearerToken` se acepta en la signature compartida
  // con real.ts pero el mock lo ignora (no hace fetch al backend).
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<QuoteHeader> {
  await delay(80 + Math.random() * 120, options?.signal);

  // Sprint 4 paso-5-c-generado · sufijo `-GENERATED` en el quoteId hereda
  // los datos del baseId pero retorna `status: "sent"` para que el SSR del
  // paso-5 renderee el estado C en lugar del A. Mock-only trigger E2E
  // (mismo patrón que `-ERROR` del paso-4 PR #465 y `-REJECTED`/`-FLAGGED`
  // del despiece PR #468).
  const generatedSuffix = "-GENERATED";
  const baseIdForGenerated = quoteId.endsWith(generatedSuffix)
    ? quoteId.slice(0, -generatedSuffix.length)
    : null;
  if (baseIdForGenerated) {
    const base = DASHBOARD_QUOTES.find((q) => q.id === baseIdForGenerated);
    if (base) {
      return {
        id: quoteId,
        client: base.client,
        clientFull: base.clientFull,
        material: base.material,
        m2: base.m2,
        status: "sent",
      };
    }
  }

  // Sprint 4 paso-5-d-revision-v2 · sufijo `-REVISING` hereda del baseId
  // con status "sent" (v1 sigue oficial). El SSR seedea el estado D directo
  // via `getPdfGeneratedInfo` (v1 canon presente) + `initialRevising=true`
  // en `PdfView` que renderea el drawer al primer paint.
  const revisingSuffix = "-REVISING";
  const baseIdForRevising = quoteId.endsWith(revisingSuffix)
    ? quoteId.slice(0, -revisingSuffix.length)
    : null;
  if (baseIdForRevising) {
    const base = DASHBOARD_QUOTES.find((q) => q.id === baseIdForRevising);
    if (base) {
      return {
        id: quoteId,
        client: base.client,
        clientFull: base.clientFull,
        material: base.material,
        m2: base.m2,
        status: "sent",
      };
    }
  }

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

  // Sprint 3 error-states · sufijos de trigger E2E (mismo patrón que -ERROR
  // del paso-4 PR #465). El canónico (PRES-2026-018) provee los datos base.
  const isRejected = quoteId.endsWith("-REJECTED");
  const isFlagged = quoteId.endsWith("-FLAGGED");
  const baseId = isRejected
    ? quoteId.slice(0, -"-REJECTED".length)
    : isFlagged
      ? quoteId.slice(0, -"-FLAGGED".length)
      : quoteId;

  const canon = PIECES_BY_QUOTE_ID[baseId] ?? PIECES_BY_QUOTE_ID[quoteId];
  if (canon && canon.length > 0) {
    const pieces = deepClonePieces(canon);
    const total = piecesTotalM2(pieces);
    const base: PieceList = {
      pieces,
      status: "done",
      timeline: TIMELINE_BY_QUOTE_ID[baseId] ?? buildDoneTimeline(pieces.length, total),
      warnings: [],
    };
    if (isRejected) base.rejected = true;
    if (isFlagged) {
      // Preset del chat flagged · mockup 17 literal (4 mensajes sobre R5).
      const { CHAT_FLAGGED_PRESET_018 } = await import("../mocks/canonicalQuote");
      base.chatFlagged = CHAT_FLAGGED_PRESET_018;
    }
    return base;
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
  // Fix-up #2 · marca snapshot como vacío · esconde tray/banner/note (UX
  // rota mostrar 3 cols de em-dash + 0 tokens + 0 eventos). El AUDIT toggle
  // y el aud-trail per-row del paso-4 NO dependen de este flag.
  isEmpty: true,
};

/**
 * Snapshot del audit-tray para un quote. Mock-only · fallback gracioso para
 * IDs desconocidos (UUID/web-XXX) que devuelve el snapshot generic en em-dash
 * con `isEmpty: true`. Sprint 4: wire al backend cuando exponga la metadata.
 */
export async function getAuditSnapshot(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").AuditSnapshot> {
  await delay(120 + Math.random() * 120, options?.signal);

  // Sprint 3 error-states · sufijos heredan el snapshot del baseId con
  // marcador adicional `· rejected` en el trace (decisión Javi G del mockup
  // 15: "Tu feedback se guarda como trace q_8f2a · rejected").
  const isRejected = quoteId.endsWith("-REJECTED");
  const isFlagged = quoteId.endsWith("-FLAGGED");
  if (isRejected || isFlagged) {
    const baseId = quoteId.slice(0, -(isRejected ? "-REJECTED" : "-FLAGGED").length);
    const base = _auditByQuote[baseId];
    if (base) {
      const clone: import("./types").AuditSnapshot = JSON.parse(JSON.stringify(base));
      if (isRejected) clone.trace.traceId = `${clone.trace.traceId} · rejected`;
      if (isFlagged) clone.trace.traceId = `${clone.trace.traceId} · flagged`;
      return clone;
    }
  }

  // Sprint 4 paso-5-c-generado · sufijo `-GENERATED` hereda el snapshot del
  // baseId · sin marcador adicional. Permite que el AuditTray siga visible
  // en estado C cuando el usuario activa AUDIT ON.
  if (quoteId.endsWith("-GENERATED")) {
    const baseId = quoteId.slice(0, -"-GENERATED".length);
    const base = _auditByQuote[baseId];
    if (base) {
      return JSON.parse(JSON.stringify(base)) as import("./types").AuditSnapshot;
    }
  }

  // Sprint 4 paso-5-d-revision-v2 · sufijo `-REVISING` también hereda del
  // baseId (estado D usa el mismo trace_id v1 que el AuditTray exhibe).
  if (quoteId.endsWith("-REVISING")) {
    const baseId = quoteId.slice(0, -"-REVISING".length);
    const base = _auditByQuote[baseId];
    if (base) {
      return JSON.parse(JSON.stringify(base)) as import("./types").AuditSnapshot;
    }
  }

  return _auditByQuote[quoteId] ?? _auditGeneric;
}

// ─── Sprint 4 paso-5-pdf-preview · mockup 18 ─────────────────────────────
// Trace del PDF v1 con fallback gracioso para IDs desconocidos (UUID/web-XXX).
export async function getPdfTrace(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").PdfTrace> {
  await delay(100 + Math.random() * 120, options?.signal);
  const { PDF_TRACE_BY_QUOTE_ID, CANONICAL_PDF_TRACE_GENERIC } =
    await import("../mocks/canonicalQuote");
  return PDF_TRACE_BY_QUOTE_ID[quoteId] ?? CANONICAL_PDF_TRACE_GENERIC;
}

// ─── Sprint 4 paso-5-c-generado · mockup 20 ────────────────────────────────
// Mock del POST /api/quotes/{id}/generate. Mock-only · wire real al endpoint
// del backend en sprint-4/paso-5-pdf-real-wire posterior (requiere
// quote.quote_breakdown persistido en DB · paso-1-real).

const _generatedStore = new Map<string, import("./types").PdfGeneratedInfo>();

export function _resetGeneratedStore() {
  _generatedStore.clear();
}

const _generatedByQuote: Record<string, import("./types").PdfGeneratedInfo> = {
  "PRES-2026-018": {
    pdfUrl: "/quotes/2026/PRES-2026-018/Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.pdf",
    excelUrl: "/quotes/2026/PRES-2026-018/Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.xlsx",
    driveUrl: "https://drive.google.com/drive/folders/PRES-2026-018-mock",
    driveFolderPath: "/Presupuestos/2026/05-mayo/",
    pdfSizeKb: 926,
    excelSizeKb: 142,
    generatedAtIso: "2026-05-03T18:42:00-03:00",
    generatedAtDisplay: "03.05.2026 18:42",
    generatedBy: "Marina",
    traceId: "op-2026-0847-a3f9c1",
    driveId: "1aB2cD…xZ9",
  },
  "PRES-2026-017": {
    pdfUrl: "/quotes/2026/PRES-2026-017/Familia Pereyra - Silestone Blanco Norte - 03.05.2026.pdf",
    excelUrl: "/quotes/2026/PRES-2026-017/Familia Pereyra - Silestone Blanco Norte - 03.05.2026.xlsx",
    driveUrl: "https://drive.google.com/drive/folders/PRES-2026-017-mock",
    driveFolderPath: "/Presupuestos/2026/05-mayo/",
    pdfSizeKb: 718,
    excelSizeKb: 124,
    generatedAtIso: "2026-04-22T11:08:00-03:00",
    generatedAtDisplay: "22.04.2026 11:08",
    generatedBy: "Marina",
    traceId: "op-2026-0792-c4e2b8",
    driveId: "1xY9zT…aQ4",
  },
};

const _generatedGeneric: import("./types").PdfGeneratedInfo = {
  pdfUrl: "/quotes/2026/generated/quote.pdf",
  excelUrl: "/quotes/2026/generated/quote.xlsx",
  driveUrl: "https://drive.google.com/drive/folders/quote-mock",
  driveFolderPath: "/Presupuestos/2026/05-mayo/",
  pdfSizeKb: 800,
  excelSizeKb: 130,
  generatedAtIso: new Date(2026, 4, 3, 12, 0, 0).toISOString(),
  generatedAtDisplay: "03.05.2026 12:00",
  generatedBy: "—",
  traceId: "—",
  driveId: "—",
};

/**
 * Dispara la generación del PDF/Excel + upload a Drive. Mock-only.
 *
 * - `-ERROR` suffix en quoteId → throw (E2E del error path del modal).
 * - cualquier otro id → 800-1500ms delay + retorna info canónica o genérica
 *   (fallback gracioso para IDs desconocidos).
 *
 * Side effect: guarda en `_generatedStore` para que `getPdfGeneratedInfo`
 * la sirva en SSR del estado C.
 */
export async function triggerPdfGeneration(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").PdfGeneratedInfo> {
  await delay(800 + Math.random() * 700, options?.signal);
  if (quoteId.endsWith("-ERROR")) {
    throw new Error(
      "No se pudo generar el presupuesto · servicio Drive caído (mock-only).",
    );
  }
  const baseId = quoteId.endsWith("-GENERATED") ? quoteId.slice(0, -"-GENERATED".length) : quoteId;
  const info = _generatedByQuote[baseId] ?? _generatedGeneric;
  _generatedStore.set(quoteId, info);
  return info;
}

/**
 * Lookup del estado generado · sin delay porque corre en SSR junto con
 * `getQuoteMetadata`. Devuelve null cuando el quote nunca disparó generate
 * en esta sesión · el estado C SSR se sirve del canon por baseId cuando el
 * suffix `-GENERATED` está presente (mock determinístico).
 */
export async function getPdfGeneratedInfo(
  quoteId: string,
  _options?: { signal?: AbortSignal },
): Promise<import("./types").PdfGeneratedInfo | null> {
  // 1) State persistido en sesión (post-triggerPdfGeneration).
  const stored = _generatedStore.get(quoteId);
  if (stored) return stored;
  // 2) Trigger E2E SSR · `-GENERATED` suffix resuelve canon directamente.
  if (quoteId.endsWith("-GENERATED")) {
    const baseId = quoteId.slice(0, -"-GENERATED".length);
    return _generatedByQuote[baseId] ?? _generatedGeneric;
  }
  // 3) Sprint 4 paso-5-d-revision-v2 · sufijo `-REVISING` también seedea v1
  // generado · el estado D muestra v1 oficial intacta + drawer comparando v2.
  if (quoteId.endsWith("-REVISING")) {
    const baseId = quoteId.slice(0, -"-REVISING".length);
    return _generatedByQuote[baseId] ?? _generatedGeneric;
  }
  return null;
}

// ─── Sprint 4 paso-5-d-revision-v2 · mockup 21 ─────────────────────────────
// Datos canon del side-by-side diff del drawer. 6 rows literales del mockup
// para PRES-2026-018 · 4 con cambio (Vigencia, Datos envío, Notas, Subtotal
// MO) + 2 sin cambio (Anticipo, Plazo). Mock-only · sub-PR
// `paso-5-v2-editable` posterior wirea inputs editables al sidebar.

const _v2DiffByQuote: Record<string, import("./types").PdfV2RevisionData> = {
  "PRES-2026-018": {
    diffCount: 4,
    unchangedCount: 2,
    rows: [
      {
        field: "Vigencia",
        v1Value: "7 días",
        v2Value: "15 días",
        trace: "↳ era 7 días",
        display: "mono",
      },
      {
        field: "Anticipo",
        v1Value: "50%",
        v2Value: "50%",
        display: "mono",
      },
      {
        field: "Plazo entrega",
        v1Value: "10–12 días hábiles",
        v2Value: "10–12 días hábiles",
        display: "mono",
      },
      {
        field: "Datos de envío",
        v1Value: "Belgrano, CABA · 4° piso (con ascensor)",
        v2Value:
          "Belgrano, CABA · 4° piso · ascensor de servicio · contacto en obra: Marcos +54 11 6234-9087",
        trace: "↳ ampliado: ascensor de servicio + contacto",
        display: "text",
      },
      {
        field: "Notas internas",
        v1Value: "— vacío",
        v2Value: "cliente pidió piso anti-mancha · agregar a producción",
        trace: "↳ nuevo · antes vacío",
        display: "text",
        v1Empty: true,
      },
      {
        field: "Subtotal MO",
        v1Value: "$494.190",
        v2Value: "$498.450",
        trace: "↳ era $494.190 · +$4.260 · corrección manual de colocación",
        display: "mono",
        variant: "money",
      },
    ],
    summary: [
      { field: "Vigencia", prev: "7 →", outcome: "15 días" },
      {
        field: "Datos de envío",
        outcome: "ampliados con ascensor de servicio y contacto en obra",
      },
      { field: "Notas internas", outcome: "agregadas (anti-mancha)" },
      { field: "Subtotal MO", prev: "corrección manual", outcome: "+$4.260" },
    ],
  },
  "PRES-2026-017": {
    diffCount: 1,
    unchangedCount: 5,
    rows: [
      { field: "Vigencia", v1Value: "10 días", v2Value: "10 días", display: "mono" },
      { field: "Anticipo", v1Value: "60%", v2Value: "60%", display: "mono" },
      { field: "Plazo entrega", v1Value: "15 días hábiles", v2Value: "15 días hábiles", display: "mono" },
      { field: "Datos de envío", v1Value: "Rosario, zona sur", v2Value: "Rosario, zona sur", display: "text" },
      { field: "Notas internas", v1Value: "— vacío", v2Value: "— vacío", display: "text", v1Empty: true },
      {
        field: "Subtotal MO",
        v1Value: "$258.430",
        v2Value: "$262.190",
        trace: "↳ +$3.760 · ajuste de flete",
        display: "mono",
        variant: "money",
      },
    ],
    summary: [{ field: "Subtotal MO", prev: "ajuste flete", outcome: "+$3.760" }],
  },
};

const _v2DiffGeneric: import("./types").PdfV2RevisionData = {
  diffCount: 0,
  unchangedCount: 0,
  rows: [],
  summary: [],
};

/** Devuelve el diff side-by-side canon para el estado D · fallback gracioso
 * a generic vacío para IDs desconocidos. Soporta sufijo `-REVISING`.
 *
 * Fix-up PR #474 bug 2: tolerar formas cortas del ID (`PRES-018` →
 * `PRES-2026-018`). Sin esto, una URL con la forma corta caía al genérico
 * vacío y la tabla mostraba "0 con cambio · 0 sin cambio". */
export async function getPdfV2DiffData(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").PdfV2RevisionData> {
  await delay(80 + Math.random() * 120, options?.signal);
  const stripped = quoteId.endsWith("-REVISING")
    ? quoteId.slice(0, -"-REVISING".length)
    : quoteId;
  // Lookup directo · luego intentar normalizar PRES-018 → PRES-2026-018.
  const direct = _v2DiffByQuote[stripped];
  if (direct) return direct;
  const shortMatch = /^PRES-(\d{3})$/.exec(stripped);
  if (shortMatch) {
    const candidate = `PRES-2026-${shortMatch[1]}`;
    if (_v2DiffByQuote[candidate]) return _v2DiffByQuote[candidate];
  }
  return _v2DiffGeneric;
}

/** Mock del flow de generación v2 · misma signature que `triggerPdfGeneration`
 * (PR #473) pero retorna info con filenames suffix `v2.pdf/v2.xlsx`. */
export async function triggerPdfV2Generation(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<import("./types").PdfGeneratedInfo> {
  await delay(800 + Math.random() * 700, options?.signal);
  if (quoteId.endsWith("-ERROR")) {
    throw new Error("No se pudo generar v2 · servicio Drive caído (mock-only).");
  }
  const baseId = quoteId.endsWith("-REVISING")
    ? quoteId.slice(0, -"-REVISING".length)
    : quoteId;
  const v1 = _generatedByQuote[baseId] ?? _generatedGeneric;
  // Variante v2: filenames con suffix " v2" antes de la extensión + nuevo traceId.
  const v2: import("./types").PdfGeneratedInfo = {
    ...v1,
    pdfUrl: v1.pdfUrl.replace(/\.pdf$/i, " v2.pdf"),
    excelUrl: v1.excelUrl.replace(/\.xlsx$/i, " v2.xlsx"),
    generatedAtIso: "2026-05-05T12:18:00-03:00",
    generatedAtDisplay: "05.05.2026 12:18",
    traceId: v1.traceId.replace(/-a3f9c1$/, "-b9d2e7"),
  };
  _generatedStore.set(quoteId, v2);
  return v2;
}
