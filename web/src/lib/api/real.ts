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
