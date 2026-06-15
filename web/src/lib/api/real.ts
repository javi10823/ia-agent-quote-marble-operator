/**
 * Client real (HTTP) · Sprint 3 api-integration · B3 incremental.
 *
 * Wirea SOLO las 3 funciones que mapean limpio a endpoints REST del backend
 * Railway: streamChat, listQuotes, getQuoteMetadata. El resto (createDraftQuote
 * + 6 sin endpoint) se queda en mocks.ts (ver index.ts + docs/known-issues.md).
 *
 * Reglas críticas:
 * - `credentials: "include"` en TODOS los fetch (cookie httpOnly cross-origin
 *   railway.app ↔ vercel.app no viaja sin esto).
 * - `handleApiError(response)` ante 401 → clearSession + redirect /login.
 * - Adapters de shape: el backend devuelve schemas distintos a los mocks; el
 *   adapter preserva la signature/tipo que el frontend ya consume. Campos que
 *   el backend no expone se degradan a "—" (em dash), NO a 0/null.
 */
import { handleApiError } from "@/lib/auth";
import {
  ApiError,
  type ChatScope,
  type ChatStreamChunk,
  type CreateDraftQuoteInput,
  type CreateDraftQuoteResponse,
  type DashboardQuote,
  type DashboardStatus,
  type ListQuotesFilters,
  type QuoteHeader,
} from "./types";

// Garantizado no-vacío por el gate USE_REAL_API de index.ts.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

const DEFAULT_TIMEOUT_MS = 30_000;

/** fetch con credentials:include + timeout + 401 handling + merge de signal externo.
 *
 * Sprint 4 ssr-auth (Opción D): `bearerToken` opcional inyecta
 * `Authorization: Bearer <token>` cuando se pasa. SSR (`typeof window ===
 * "undefined"`) lo usa para autenticar con el JWT leído de la cookie
 * httpOnly vercel · client-side sigue dependiendo de la cookie cross-origin
 * de Railway via `credentials: "include"` (no necesita el header).
 */
async function apiFetch(
  path: string,
  init: RequestInit & { signal?: AbortSignal; bearerToken?: string | null } = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), timeoutMs);
  if (init.signal) {
    if (init.signal.aborted) ctrl.abort();
    else init.signal.addEventListener("abort", () => ctrl.abort(), { once: true });
  }
  const { bearerToken, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (bearerToken) headers.set("Authorization", `Bearer ${bearerToken}`);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers,
      credentials: "include",
      signal: ctrl.signal,
    });
    handleApiError(response); // 401 → clearSession + redirect /login?reason=expired
    return response;
  } finally {
    clearTimeout(timeout);
  }
}

/* ─── listQuotes ─────────────────────────────────────────────────────
   GET /api/quotes → array plano de QuoteListResponse.
   Adapter: client_name→client, total_*→amount/currency. Campos que el
   backend NO expone (m2, lastActivityDays, daysToExpire) → "—". */

interface RealQuoteListItem {
  id: string;
  client_name: string;
  project: string;
  material: string | null;
  total_ars: number | null;
  total_usd: number | null;
  status: string;
  created_at: string;
  source?: string | null;
}

function adaptStatus(s: string): DashboardStatus {
  return (["draft", "sent", "expired", "lost"].includes(s) ? s : "draft") as DashboardStatus;
}

/** El backend no expone m2/actividad/vigencia → degradación a em dash. */
const EM_DASH = "—" as unknown as number; // el componente lo renderiza como string; ver known-issues

function adaptListItem(item: RealQuoteListItem): DashboardQuote {
  const currency: "ARS" | "USD" = (item.total_usd ?? 0) > 0 ? "USD" : "ARS";
  const amount = currency === "USD" ? (item.total_usd ?? 0) : (item.total_ars ?? 0);
  return {
    id: item.id,
    // Quote.source del backend ("web" | "operator"). Si el backend no lo
    // manda, resolveQuoteSource cae al prefijo del id (`web-*`).
    source: item.source === "web" ? "web" : item.source === "operator" ? "operator" : undefined,
    client: item.client_name || "Cliente sin identificar",
    clientFull: item.client_name || item.project || "—",
    material: item.material || "—",
    m2: EM_DASH, // backend no expone m² en el listado (Sprint 4: derive-fields)
    currency,
    amount,
    amountSecondary: null,
    status: adaptStatus(item.status),
    lastActivityDays: EM_DASH, // backend no expone updated_at en el listado
    daysToExpire: EM_DASH, // sin policy de vigencia en backend
    sentDate: null,
  } as unknown as DashboardQuote;
}

export async function listQuotes(
  filters?: ListQuotesFilters,
  options?: { signal?: AbortSignal },
): Promise<DashboardQuote[]> {
  const response = await apiFetch("/api/quotes?limit=200", { signal: options?.signal });
  if (!response.ok)
    throw new ApiError("LIST_QUOTES_FAILED", `GET /api/quotes ${response.status}`, response.status);
  const data = (await response.json()) as RealQuoteListItem[];
  let quotes = data.map(adaptListItem);
  // Filtros client-side (el backend solo pagina, no filtra por status/search).
  if (filters?.statuses && filters.statuses.length > 0) {
    quotes = quotes.filter((q) => filters.statuses!.includes(q.status));
  }
  if (filters?.search) {
    const needle = filters.search.toLowerCase();
    quotes = quotes.filter((q) => q.client.toLowerCase().includes(needle));
  }
  // kpi pre-filters dependen de m2/actividad que el real no expone → no se aplican
  // (la tabla muestra todo; los KPI cards quedan en mock · ver known-issues).
  return quotes;
}

/* ─── getQuoteMetadata ───────────────────────────────────────────────
   GET /api/quotes/{id} → QuoteDetailResponse. m² no está como campo: se
   intenta derivar de quote_breakdown.dual_read_result.sectores[].m2_total. */

interface RealQuoteDetail {
  id: string;
  client_name: string;
  project: string;
  material: string | null;
  status: string;
  quote_breakdown?: {
    dual_read_result?: {
      sectores?: Array<{ m2_total?: { valor?: number } }>;
    };
  } | null;
}

function deriveM2(detail: RealQuoteDetail): number {
  const sectores = detail.quote_breakdown?.dual_read_result?.sectores;
  if (Array.isArray(sectores) && sectores.length > 0) {
    const total = sectores.reduce((sum, s) => sum + (s.m2_total?.valor ?? 0), 0);
    if (total > 0) return Math.round(total * 100) / 100;
  }
  // No derivable → "—" degradado. Cast: el tipo es number pero toLocaleString
  // sobre un string devuelve el string ("— m²"). Ver known-issues + Sprint 4.
  return "—" as unknown as number;
}

/** Placeholder con em dash para SSR sin cookie (ver bloque de doc arriba). */
function ssrFallbackHeader(quoteId: string): QuoteHeader {
  return {
    id: quoteId,
    client: "—",
    clientFull: "—",
    material: "—",
    m2: "—" as unknown as number,
    status: "draft",
  };
}

/**
 * GET /api/quotes/{id} · resiliente para SSR.
 *
 * `/quotes/[id]/layout.tsx` es un async Server Component que hace
 * `await getQuoteMetadata`. En SSR (Node) el fetch NO lleva la cookie
 * httpOnly del browser (auth client-held · PR #463 Opción 1) → 401. Si
 * tiráramos, el Server Component crashea con "Application error" en el
 * 100% de las quotes reales (bug detectado por smoke CFC).
 *
 * Fix: en SSR (`typeof window === "undefined"`) devolvemos un header
 * placeholder ("—") en vez de throw — el chrome shell rendea, la
 * navegación funciona, y el contenido client-side (contexto/despiece)
 * trae sus datos. Client-side los errores SÍ se propagan (el chrome ya
 * está montado y el browser tiene cookie). Sprint 4 (sprint-4/ssr-auth)
 * trae la metadata real en SSR. Ver docs/known-issues.md.
 */
export async function getQuoteMetadata(
  quoteId: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<QuoteHeader> {
  // Sprint 4 ssr-auth (Opción D): en SSR el browser no nos manda la cookie
  // httpOnly cross-origin de Railway. El Server Component caller (layout)
  // lee el JWT con `getServerToken()` de `@/lib/auth-server` y lo pasa por
  // `options.bearerToken`. NO importamos `auth-server` desde acá porque
  // este módulo se incluye en el bundle client y `next/headers` solo
  // existe en server (Next 14 build error).
  //
  // Si no hay token (pre-login / cookie expirada), bearerToken queda null
  // → request sale sin auth → backend 401 → catch degrada graceful con
  // `ssrFallbackHeader` (mismo comportamiento previo a este PR).
  try {
    const response = await apiFetch(`/api/quotes/${encodeURIComponent(quoteId)}`, {
      signal: options?.signal,
      bearerToken: options?.bearerToken ?? null,
    });
    if (response.status === 404) {
      throw new ApiError("QUOTE_NOT_FOUND", `Quote ${quoteId} no encontrado`, 404);
    }
    if (!response.ok) {
      throw new ApiError(
        "GET_QUOTE_FAILED",
        `GET /api/quotes/${quoteId} ${response.status}`,
        response.status,
      );
    }
    const detail = (await response.json()) as RealQuoteDetail;
    return {
      id: detail.id,
      client: detail.client_name || "Cliente sin identificar",
      clientFull: detail.client_name || detail.project || "—",
      material: detail.material || "—",
      m2: deriveM2(detail),
      status: adaptStatus(detail.status) as QuoteHeader["status"],
    };
  } catch (error) {
    // SSR sin cookie → degradación graceful (no crashea el Server Component).
    if (typeof window === "undefined") {
      return ssrFallbackHeader(quoteId);
    }
    // Client-side: error real, propagar (el chrome ya montado lo maneja).
    throw error;
  }
}

/* ─── streamChat ─────────────────────────────────────────────────────
   POST /api/quotes/{id}/chat · multipart/form-data (message + plan_files).
   Response text/event-stream `data: {json}\n\n` + `: keepalive\n\n` comments.
   Mantiene la signature del mock (ReadableStream<ChatStreamChunk>) para que
   useChatScoped y los 50 E2E no cambien. El `scope` no existe en el backend
   (rutea por contenido del message) → se ignora en el body. */

export function streamChat(
  quoteId: string,
  message: string,
  _scope: ChatScope,
  options?: { signal?: AbortSignal; targetPieceId?: string; planFiles?: File[] },
): ReadableStream<ChatStreamChunk> {
  return new ReadableStream<ChatStreamChunk>({
    async start(controller) {
      try {
        const form = new FormData();
        form.append("message", message);
        for (const f of options?.planFiles ?? []) form.append("plan_files", f);

        const response = await apiFetch(
          `/api/quotes/${encodeURIComponent(quoteId)}/chat`,
          { method: "POST", body: form, signal: options?.signal },
          120_000, // SSE long-lived
        );
        if (!response.ok || !response.body) {
          controller.enqueue({
            type: "error",
            content: `Chat falló: ${response.status}`,
          });
          controller.enqueue({ type: "done", error: true });
          controller.close();
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE: eventos separados por blank line. Tolera `: keepalive` comments.
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";
          for (const block of blocks) {
            const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
            if (!dataLine) continue; // comment / keepalive → skip
            const json = dataLine.slice(6);
            try {
              const chunk = JSON.parse(json) as ChatStreamChunk;
              controller.enqueue(chunk);
              if (chunk.type === "done") {
                controller.close();
                return;
              }
            } catch {
              console.warn("[streamChat] SSE parse failed:", json.slice(0, 120));
            }
          }
        }
        controller.enqueue({ type: "done" });
        controller.close();
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          controller.close();
          return;
        }
        controller.enqueue({ type: "error", content: "Error de conexión con el chat" });
        controller.enqueue({ type: "done", error: true });
        controller.close();
      }
    },
  });
}

/* ─── createDraftQuote · Sprint 4 paso-1-real ──────────────────────────
   Wire real del paso 1 brief upload. Secuencia 2-calls al backend Railway:

     1) POST /api/quotes (JSON)              → crea Quote shell con UUID + status=draft
     2) POST /api/quotes/{id}/chat (multipart) → multipart con message=briefText +
        plan_files=[planFile, ...photos]. Backend SSE-streamea progreso del
        agente. Drainemos el stream completo INTERNAMENTE (no exponemos al
        frontend en este sub-PR · UX = BriefProcessing skeleton existente · sub-PR
        siguiente `paso-1-sse-stream` agrega progress real al usuario).

   Mantiene la signature contractual del mock:
   `createDraftQuote(input, options) → {id, status:"draft", createdAt}`.
   El hook `useBriefUpload` no necesita cambios. */

interface RealCreateQuoteResponse {
  id: string;
}

export async function createDraftQuote(
  input: CreateDraftQuoteInput,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<CreateDraftQuoteResponse> {
  const { signal, bearerToken } = options ?? {};

  // ── Paso 1) POST /api/quotes → quote_id
  // Body opcional `{status}` se omite · backend default = "draft".
  // Timeout corto (10s) · el endpoint solo crea un UUID en DB · si esto falla
  // ya hay un problema serio (DB down, auth invalida, etc.).
  const createResponse = await apiFetch(
    "/api/quotes",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
      signal,
      bearerToken,
    },
    10_000,
  );
  if (!createResponse.ok) {
    throw new ApiError(
      "CREATE_QUOTE_FAILED",
      `POST /api/quotes falló (${createResponse.status}). Reintentá en unos segundos.`,
      createResponse.status,
    );
  }
  const { id } = (await createResponse.json()) as RealCreateQuoteResponse;
  if (!id) {
    throw new ApiError("CREATE_QUOTE_MALFORMED", "Backend no devolvió quote id.", 502);
  }

  // ── Paso 2) POST /api/quotes/{id}/chat → SSE drained
  // Multipart con message=briefText + plan_files. El backend acepta
  // `plan_files=[]` (router.py:2089 default `File([])`), así que el field
  // se omite cuando `planFile` viene null (ruta "Cargar a mano →" o
  // text-only del mockup paso 1).
  const form = new FormData();
  // Sprint 4 paso-1-chips-brief-libre: prefix LITERAL con chips opcionales
  // del paso 1 A/B cuando vienen poblados · el agente parsea el message
  // completo y extrae al contexto del paso 2.
  const chipParts: string[] = [];
  if (input.cliente?.trim()) chipParts.push(`Cliente: ${input.cliente.trim()}`);
  if (input.ambiente?.trim()) chipParts.push(`Ambiente: ${input.ambiente.trim()}`);
  if (input.plazo?.trim()) chipParts.push(`Plazo: ${input.plazo.trim()}`);
  const chipsPrefix = chipParts.length ? `${chipParts.join(" · ")}\n\n` : "";
  // Backend requiere `message` no-vacío como Form(...). Si el operador NO
  // tipeó nada, pasamos un texto mínimo descriptivo · el agente igual usa los
  // archivos/chips para inferir contexto.
  const briefBody = input.briefText?.trim() || "Procesá este brief y armá presupuesto.";
  form.append("message", `${chipsPrefix}${briefBody}`);
  // planFile opcional · skip si null (ruta carga manual / text-only).
  if (input.planFile) {
    form.append("plan_files", input.planFile);
  }
  for (const photo of input.photos ?? []) {
    form.append("plan_files", photo);
  }

  // SSE long-lived · el procesamiento agéntico (Sonnet + tools + posible
  // dual-read Opus) puede tomar 30-90s. Timeout 180s con headroom.
  const chatResponse = await apiFetch(
    `/api/quotes/${encodeURIComponent(id)}/chat`,
    { method: "POST", body: form, signal, bearerToken },
    180_000,
  );
  if (!chatResponse.ok || !chatResponse.body) {
    throw new ApiError(
      "BRIEF_PROCESS_FAILED",
      `POST /api/quotes/{id}/chat falló (${chatResponse.status}). Reintentá.`,
      chatResponse.status,
    );
  }

  // Drain del stream · cazamos chunks `error` y `done.error=true` para
  // surface el problema al hook como ApiError. Los demás chunks (text, action,
  // context_analysis, dual_read_result) se descartan · el contexto poblado lo
  // lee el page server-side del paso 2 directo del backend.
  const reader = chatResponse.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamError: string | null = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        const json = dataLine.slice(6);
        try {
          const chunk = JSON.parse(json) as ChatStreamChunk;
          if (chunk.type === "error") {
            streamError = chunk.content ?? chunk.message ?? "El agente reportó un error.";
          }
          if (chunk.type === "done") {
            if (chunk.error) {
              throw new ApiError(
                "BRIEF_AGENT_ERROR",
                streamError ?? "El agente no pudo procesar el brief.",
                502,
              );
            }
            // Stream cerrado limpio · seguir adelante.
            return {
              id,
              status: "draft",
              createdAt: new Date().toISOString(),
            };
          }
        } catch (parseErr) {
          if (parseErr instanceof ApiError) throw parseErr;
          // Línea SSE malformada · skip en silencio (consistente con streamChat).
          console.warn("[createDraftQuote] SSE parse failed:", json.slice(0, 120));
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  // Stream terminó sin `done` explícito (corte de conexión) · si hubo error
  // intermedio lo surface; si no, asumimos done implícito.
  if (streamError) {
    throw new ApiError("BRIEF_AGENT_ERROR", streamError, 502);
  }
  return {
    id,
    status: "draft",
    createdAt: new Date().toISOString(),
  };
}

/* ─── getAuditLog · Sprint 4 audit-trail-copy ─────────────────────────
   GET /api/quotes/{id}/audit-log → AuditLogResponse.

   Bearer SSR via apiFetch · timeout largo (60s) porque puede agregar
   miles de eventos. `full=true` quita la truncation (default 200 events).
*/

import type { AuditLogResponse } from "./types";

export async function getAuditLog(
  quoteId: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null; full?: boolean },
): Promise<AuditLogResponse> {
  const { signal, bearerToken, full } = options ?? {};
  const qs = full ? "?full=true" : "";
  const response = await apiFetch(
    `/api/quotes/${encodeURIComponent(quoteId)}/audit-log${qs}`,
    { signal, bearerToken },
    60_000,
  );
  if (response.status === 404) {
    throw new ApiError("AUDIT_LOG_NOT_FOUND", `Quote ${quoteId} no encontrado`, 404);
  }
  if (!response.ok) {
    throw new ApiError(
      "AUDIT_LOG_FAILED",
      `GET /api/quotes/{id}/audit-log falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as AuditLogResponse;
}

/* ─── getContextForQuote · Sprint 4 paso-2-context-wire-real (Bug 1 fix) ──
   GET /api/quotes/{id} → QuoteDetailResponse · adapter sobre el breakdown.

   El backend devuelve `quote_breakdown` como JSON-libre dentro del response.
   El adapter `breakdownToContext()` (pure function) traduce el shape backend
   (`context_analysis_pending` / `verified_context_analysis` / `_brief_analysis_raw`)
   al shape `ContextResponse` que el UI del paso 2 ya consume.

   Manejo de errores:
   - 404 → ApiError CONTEXT_QUOTE_NOT_FOUND
   - 5xx → ApiError CONTEXT_LOAD_FAILED
   - response sin breakdown → adapter devuelve fields FALTA (preserva
     current "—" behavior · no crashea)
*/

import { breakdownToContext, type QuoteBreakdownLike } from "./adapters/context-from-breakdown";
import type { ContextResponse } from "./types";

interface RealQuoteDetailResponse {
  id: string;
  quote_breakdown?: QuoteBreakdownLike | null;
  [key: string]: unknown;
}

export async function getContextForQuote(
  quoteId: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<ContextResponse> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    `/api/quotes/${encodeURIComponent(quoteId)}`,
    { signal, bearerToken },
    30_000,
  );
  if (response.status === 404) {
    throw new ApiError("CONTEXT_QUOTE_NOT_FOUND", `Quote ${quoteId} no encontrado`, 404);
  }
  if (!response.ok) {
    throw new ApiError(
      "CONTEXT_LOAD_FAILED",
      `GET /api/quotes/{id} falló (${response.status})`,
      response.status,
    );
  }
  const detail = (await response.json()) as RealQuoteDetailResponse;
  // Adapter tolera breakdown null/undefined → devuelve todos los fields
  // como FALTA (preserva el current "—" behavior del UI).
  return breakdownToContext(detail.quote_breakdown ?? null);
}

/* ─── getCatalogConfig / updateCatalogConfig · sub-PR 22.2.a ──────────
   GET /api/catalog/config → CatalogConfig blob.
   PUT /api/catalog/config { content } → { ok, catalog }.

   Endpoint backend ya existe (catalog/router.py · ALLOWED). PUT dispara
   3 invalidaciones de cache module-level en el worker actual · caveat
   multi-worker: otros workers tardan unos segundos. */

import type { CatalogConfig } from "./types";

export async function getCatalogConfig(options?: {
  signal?: AbortSignal;
  bearerToken?: string | null;
}): Promise<CatalogConfig> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(`/api/catalog/config`, { signal, bearerToken }, 15_000);
  if (!response.ok) {
    throw new ApiError(
      "CONFIG_LOAD_FAILED",
      `GET /api/catalog/config falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as CatalogConfig;
}

export async function updateCatalogConfig(
  content: CatalogConfig,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<{ ok: boolean; catalog: string }> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    `/api/catalog/config`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
      signal,
      bearerToken,
    },
    20_000,
  );
  if (!response.ok) {
    throw new ApiError(
      "CONFIG_SAVE_FAILED",
      `PUT /api/catalog/config falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as { ok: boolean; catalog: string };
}

/* ─── Catálogo · viewer + Dux importer + backups (sub-PR 22.2.b) ──────
   Wire directo contra los 8 endpoints de catalog/router.py. Mismo patrón
   que getCatalogConfig: apiFetch + bearerToken opcional (SSR) + ApiError
   con code semántico. Los multipart (import) NO setean Content-Type (el
   browser lo arma con el boundary). */

import type {
  CatalogBackup,
  CatalogContent,
  CatalogMeta,
  ImportApplyResponse,
  ImportPreview,
  RestoreBackupResponse,
} from "./types";

type AuthOpts = { signal?: AbortSignal; bearerToken?: string | null };

export async function listCatalogs(options?: AuthOpts): Promise<CatalogMeta[]> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(`/api/catalog/`, { signal, bearerToken }, 15_000);
  if (!response.ok) {
    throw new ApiError(
      "CATALOG_LIST_FAILED",
      `GET /api/catalog/ falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as CatalogMeta[];
}

export async function getCatalog(name: string, options?: AuthOpts): Promise<CatalogContent> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    `/api/catalog/${encodeURIComponent(name)}`,
    { signal, bearerToken },
    15_000,
  );
  if (!response.ok) {
    throw new ApiError(
      response.status === 404 ? "CATALOG_NOT_FOUND" : "CATALOG_LOAD_FAILED",
      `GET /api/catalog/${name} falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as CatalogContent;
}

export async function listBackups(name: string, options?: AuthOpts): Promise<CatalogBackup[]> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    `/api/catalog/backups/${encodeURIComponent(name)}`,
    { signal, bearerToken },
    15_000,
  );
  if (!response.ok) {
    throw new ApiError(
      "BACKUPS_LIST_FAILED",
      `GET /api/catalog/backups/${name} falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as CatalogBackup[];
}

export async function restoreBackup(
  backupId: number,
  options?: AuthOpts,
): Promise<RestoreBackupResponse> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    `/api/catalog/backups/${backupId}/restore`,
    { method: "POST", signal, bearerToken },
    20_000,
  );
  if (!response.ok) {
    throw new ApiError(
      response.status === 404 ? "BACKUP_NOT_FOUND" : "RESTORE_FAILED",
      `POST /api/catalog/backups/${backupId}/restore falló (${response.status})`,
      response.status,
    );
  }
  return (await response.json()) as RestoreBackupResponse;
}

/** Lee `detail` del error 400 del backend (mensajes user-friendly de
    encoding/formato) y lo propaga como mensaje del ApiError. */
async function _errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

export async function importPreview(file: File, options?: AuthOpts): Promise<ImportPreview> {
  const { signal, bearerToken } = options ?? {};
  const form = new FormData();
  form.append("file", file);
  // Parser sincrónico sin timeout backend → damos 60s holgados (caveat PR).
  const response = await apiFetch(
    `/api/catalog/import-preview`,
    { method: "POST", body: form, signal, bearerToken },
    60_000,
  );
  if (!response.ok) {
    throw new ApiError(
      "IMPORT_PREVIEW_FAILED",
      await _errorDetail(response, `import-preview falló (${response.status})`),
      response.status,
    );
  }
  return (await response.json()) as ImportPreview;
}

export async function importApply(
  input: {
    file: File;
    catalogs: string[];
    includeNew: boolean;
    sourceFile: string;
  },
  options?: AuthOpts,
): Promise<ImportApplyResponse> {
  const { signal, bearerToken } = options ?? {};
  const form = new FormData();
  form.append("file", input.file);
  form.append("catalogs", JSON.stringify(input.catalogs));
  form.append("include_new", String(input.includeNew));
  form.append("source_file", input.sourceFile);
  const response = await apiFetch(
    `/api/catalog/import-apply`,
    { method: "POST", body: form, signal, bearerToken },
    60_000,
  );
  if (!response.ok) {
    throw new ApiError(
      "IMPORT_APPLY_FAILED",
      await _errorDetail(response, `import-apply falló (${response.status})`),
      response.status,
    );
  }
  return (await response.json()) as ImportApplyResponse;
}

/* ─── PDF real wire · sub-PR paso-5-pdf-real-wire ─────────────────────
   POST /api/quotes/{id}/generate    → PdfGeneratedInfo (gen v1)
   POST /api/quotes/{id}/regenerate  → PdfGeneratedInfo (gen v2 / refresh)
   GET  /api/quotes/{id}             → PdfGeneratedInfo | null (SSR estado C)
   getPdfV2DiffData queda en MOCK · no hay endpoint backend equivalente
   (mockup 21 paso-5-d-revision-v2 · sub-PR posterior abre el endpoint).

   Adapter de shape: backend devuelve `{ok, pdf_url, excel_url, drive_url}`
   snake_case + sin metadatos UI (pdfSizeKb, generatedBy, traceId, etc).
   El adapter mapea camelCase y degrada lo faltante a "—" o defaults
   conservadores (timestamp current). El UI ya muestra "—" cuando los
   placeholders aparecen (pattern de getQuoteMetadata real).

   Error mapping: el backend solo expone status code + detail string. El
   handler `_mapPdfError` traduce a codes UI-friendly (PDF_TIMEOUT,
   DRIVE_QUOTA, BREAKDOWN_MISSING, GENERIC) para que el modal renderee
   mensajes en español específicos.
*/

import type { PdfGeneratedInfo } from "./types";

interface RealGenerateResponse {
  ok?: boolean;
  pdf_url?: string | null;
  excel_url?: string | null;
  drive_url?: string | null;
  drive_file_id?: string | null;
  error?: string | null;
  detail?: string | null;
}

interface RealQuoteWithDocs {
  id: string;
  pdf_url?: string | null;
  excel_url?: string | null;
  drive_url?: string | null;
  drive_file_id?: string | null;
  updated_at?: string | null;
  client_name?: string | null;
  [key: string]: unknown;
}

// EM_DASH legacy del adapter de listQuotes (línea 91) es `as number` para
// degradar m². Acá usamos string puro · campos faltantes del backend se
// renderean como "—" en el UI sin cast.
const EM_DASH_STR = "—";

function _displayTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
  } catch {
    return EM_DASH_STR;
  }
}

function _adaptToPdfInfo(
  raw: RealGenerateResponse | RealQuoteWithDocs,
  fallbackIso?: string,
): PdfGeneratedInfo | null {
  const pdfUrl = raw.pdf_url ?? "";
  if (!pdfUrl) return null;
  const generatedAtIso =
    ("updated_at" in raw && typeof raw.updated_at === "string" ? raw.updated_at : fallbackIso) ??
    new Date().toISOString();
  return {
    pdfUrl,
    excelUrl: raw.excel_url ?? "",
    driveUrl: raw.drive_url ?? "",
    driveFolderPath: EM_DASH_STR,
    pdfSizeKb: 0,
    excelSizeKb: 0,
    generatedAtIso,
    generatedAtDisplay: _displayTimestamp(generatedAtIso),
    generatedBy: EM_DASH_STR,
    traceId: EM_DASH_STR,
    driveId: raw.drive_file_id ?? EM_DASH_STR,
  };
}

async function _readErrorBody(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.error === "string") return data.error;
  } catch {
    /* response no es JSON · cae al statusText */
  }
  return response.statusText || `HTTP ${response.status}`;
}

/** Mapea el status + detail del backend a un code UI-friendly. El modal
 * `PdfConfirmModal` consume el `code` para mostrar mensaje en español
 * específico (PDF_TIMEOUT → "está tardando...", BREAKDOWN_MISSING →
 * "falta procesar el contexto", etc). */
function _mapPdfError(status: number, detail: string): { code: string; message: string } {
  const lower = detail.toLowerCase();
  if (status === 504 || lower.includes("timeout")) {
    return { code: "PDF_TIMEOUT", message: detail };
  }
  if (
    lower.includes("drive") &&
    (lower.includes("quota") || lower.includes("límite") || lower.includes("limite"))
  ) {
    return { code: "DRIVE_QUOTA", message: detail };
  }
  if (
    status === 400 &&
    (lower.includes("quote_breakdown") ||
      lower.includes("datos de cálculo") ||
      lower.includes("datos de calculo"))
  ) {
    return { code: "BREAKDOWN_MISSING", message: detail };
  }
  if (status === 404) {
    return { code: "QUOTE_NOT_FOUND", message: detail };
  }
  return { code: "PDF_GENERIC", message: detail };
}

async function _doGenerateRequest(
  path: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<PdfGeneratedInfo> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    path,
    { method: "POST", signal, bearerToken },
    90_000, // PDF + Drive upload puede tardar
  );
  if (!response.ok) {
    const detail = await _readErrorBody(response);
    const { code, message } = _mapPdfError(response.status, detail);
    throw new ApiError(code, message, response.status);
  }
  const data = (await response.json()) as RealGenerateResponse;
  if (!data.ok) {
    const { code, message } = _mapPdfError(500, data.error ?? "Error desconocido");
    throw new ApiError(code, message, 500);
  }
  const adapted = _adaptToPdfInfo(data);
  if (!adapted) {
    throw new ApiError("PDF_NO_URL", "El backend respondió ok pero sin pdf_url", 500);
  }
  return adapted;
}

export async function triggerPdfGeneration(
  quoteId: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<PdfGeneratedInfo> {
  return _doGenerateRequest(`/api/quotes/${encodeURIComponent(quoteId)}/generate`, options);
}

export async function triggerPdfV2Generation(
  quoteId: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<PdfGeneratedInfo> {
  // /regenerate refresca PDF sin recalcular · semánticamente v2 (cambios
  // editoriales del operador sin tocar números del calculator).
  return _doGenerateRequest(`/api/quotes/${encodeURIComponent(quoteId)}/regenerate`, options);
}

export async function getPdfGeneratedInfo(
  quoteId: string,
  options?: { signal?: AbortSignal; bearerToken?: string | null },
): Promise<PdfGeneratedInfo | null> {
  const { signal, bearerToken } = options ?? {};
  const response = await apiFetch(
    `/api/quotes/${encodeURIComponent(quoteId)}`,
    { signal, bearerToken },
    20_000,
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiError(
      "PDF_INFO_LOAD_FAILED",
      `GET /api/quotes/{id} falló (${response.status})`,
      response.status,
    );
  }
  const quote = (await response.json()) as RealQuoteWithDocs;
  return _adaptToPdfInfo(quote);
}
