// Llamamos DIRECTO al backend (cross-origin) en vez de pasar por el
// rewrite de Next.js. Motivo: el rewrite con destino externo en Vercel
// a veces proxyea y a veces redirige (depende del endpoint, headers,
// etc.) — ingobernable. Con cross-origin explícito + CORS configurado
// en el backend + SameSite=None en el cookie, todo flow es predecible:
//   POST /api/auth/login desde vercel.app → railway.app
//   → Set-Cookie con domain=railway.app, SameSite=None
//   → subsecuentes fetches desde vercel.app con credentials:"include"
//     y SameSite=None → cookie viaja → 200
//
// `NEXT_PUBLIC_API_URL` debe apuntar a la URL completa del backend
// (ej: https://ia-agent-quote-marble-operator-production.up.railway.app).
// En dev lo resolvemos a localhost:8000.
function resolveApiBase(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
  }
  return "http://localhost:8000";
}

const API_BASE = resolveApiBase();

/**
 * Antes: cualquier 401 redirigía automáticamente a /login. Problema: si
 * un SOLO fetch secundario (ej: una de las 3 requests que hace /config
 * al montar) devolvía 401 por cualquier motivo transiente (cross-origin
 * cookie issue, redirect chain, expired token en un endpoint pero no en
 * otros), el usuario era pateado a login sin ver el error real.
 *
 * Ahora: NO redirigimos automáticamente. Dejamos que el error burbujee
 * como cualquier otro — el caller muestra toast o inline error. El
 * usuario mantiene su sesión y puede decidir si volver a loguearse
 * manualmente. Si la cookie realmente expiró todas las siguientes
 * requests fallarán con 401, pero al menos ve QUÉ está pasando en vez
 * de un rebote misterioso a /login.
 *
 * El flujo de login/logout explícito sigue funcionando (auth.ts).
 */
function handleAuthError(_res: Response): void {
  // no-op intentional — ver doc arriba
}

/**
 * Inyecta `Authorization: Bearer <token>` si hay token en localStorage.
 * Exportado para usar en flows que no pasan por apiFetch (SSE con fetch
 * directo, principalmente `streamChat`). Si ya viene un header Authorization
 * en `init.headers`, NO lo sobreescribe.
 */
export function withAuthHeader(init?: RequestInit): RequestInit {
  if (typeof window === "undefined") return init || {};
  let token: string | null = null;
  try { token = localStorage.getItem("dangelo:token"); } catch {}
  if (!token) return init || {};

  // Normalizar headers a un objeto mutable sin perder los headers originales.
  const headers = new Headers(init?.headers);
  if (!headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return { ...init, headers };
}

/**
 * Wrap `fetch()` → si tira TypeError "Failed to fetch" (red caída / CORS /
 * backend inalcanzable), el browser muestra un mensaje crudo horrible en
 * los toasts. Lo traducimos a algo accionable.
 *
 * También inyecta el header `Authorization: Bearer <token>` cuando hay un
 * JWT en localStorage — fallback para clientes donde la cookie cross-origin
 * no viaja (iOS Safari con ITP). En desktop el backend prefiere la cookie
 * igual, así que el header es redundancia inofensiva.
 *
 * Uso: `apiFetch(url, init)` en lugar de `fetch(url, init)`.
 */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, withAuthHeader(init));
  } catch (err: any) {
    // TypeError: Failed to fetch (Chrome/Safari) / NetworkError (Firefox)
    if (err instanceof TypeError || err?.name === "NetworkError") {
      throw new Error("No pude conectar con el servidor. Revisá tu conexión e intentalo de nuevo.");
    }
    throw err;
  }
}

export interface ResumenObraRecord {
  pdf_url: string;
  drive_url: string | null;
  drive_file_id?: string | null;
  notes: string;
  generated_at: string;
  quote_ids: string[];
  client_name: string;
  project: string;
}

export interface Quote {
  id: string;
  client_name: string;
  project: string;
  material: string | null;
  total_ars: number | null;
  total_usd: number | null;
  status: "draft" | "pending" | "validated" | "sent";
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
  drive_pdf_url: string | null;
  drive_excel_url: string | null;
  parent_quote_id: string | null;
  quote_kind: "standard" | "building_parent" | "building_child_material" | "variant_option" | null;
  is_building?: boolean | null;
  comparison_group_id: string | null;
  source: string | null;
  is_read: boolean;
  notes: string | null;
  sink_type: { basin_count: "simple" | "doble"; mount_type: "arriba" | "abajo" } | null;
  resumen_obra?: ResumenObraRecord | null;
  condiciones_pdf?: {
    pdf_url: string;
    drive_url?: string | null;
    drive_file_id?: string | null;
    generated_at: string;
    plazo: string;
  } | null;
  created_at: string;
}

export interface SourceFile {
  filename: string;
  type: string;
  size: number;
  url: string;
  uploaded_at: string;
}

export interface MOItem {
  description: string;
  quantity: number;
  unit_price: number;
  base_price?: number;
  total: number;
}

export interface QuoteBreakdown {
  client_name?: string;
  project?: string;
  date?: string;
  delivery_days?: string;
  material_name?: string;
  material_type?: string;
  material_m2?: number;
  material_price_unit?: number;
  material_price_base?: number;
  material_currency?: "USD" | "ARS";
  material_total?: number;
  discount_pct?: number;
  discount_amount?: number;
  merma?: { aplica: boolean; desperdicio: number; sobrante_m2: number; motivo: string };
  piece_details?: { description: string; largo: number; dim2: number; m2: number }[];
  sectors?: { label: string; pieces: string[] }[];
  sinks?: { name: string; quantity: number; unit_price: number }[];
  mo_items?: MOItem[];
  total_ars?: number;
  total_usd?: number;
  /** PR #378 — Presente cuando el operador ya confirmó medidas (Paso 2).
   *  Usado por el frontend como flag para lockear edits inline del
   *  despiece y mostrar el botón "Editar despiece". */
  verified_context?: string;
  /** PR #383 — Presente cuando el operador ya confirmó el contexto
   *  (card `__CONTEXT_ANALYSIS__`). Se usa como flag para mostrar el
   *  botón "Editar contexto" (gemelo de "Editar despiece" pero para
   *  el paso anterior). */
  verified_context_analysis?: { answers?: unknown[] } | null;
}

export interface QuoteDetail extends Quote {
  messages: Message[];
  quote_breakdown: QuoteBreakdown | null;
  source_files: SourceFile[] | null;
  children?: Quote[];  // building_child_material quotes for building_parent
}

export interface Message {
  role: "user" | "assistant";
  content: string | ContentBlock[];
}

export interface ContentBlock {
  type: "text" | "image" | "document" | "tool_use" | "tool_result";
  text?: string;
}

// ── Quotes ────────────────────────────────────────────────────────────────────

export async function fetchQuotes(): Promise<Quote[]> {
  const res = await apiFetch(`${API_BASE}/api/quotes`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar presupuestos");
  return res.json();
}

export interface QuotesCheck {
  count: number;
  last_updated_at: string | null;
}

export async function checkQuotes(): Promise<QuotesCheck> {
  const res = await apiFetch(`${API_BASE}/api/quotes/check`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al verificar presupuestos");
  return res.json();
}

export async function fetchQuote(id: string): Promise<QuoteDetail> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = new Error("Presupuesto no encontrado");
    if (res.status === 404) (err as any).code = "QUOTE_NOT_FOUND";
    throw err;
  }
  return res.json();
}

export async function createQuote(
  options?: { status?: Quote["status"] }
): Promise<{ id: string }> {
  const hasBody = options?.status != null;
  const res = await apiFetch(`${API_BASE}/api/quotes`, {
    method: "POST",
    credentials: "include",
    ...(hasBody && {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: options!.status }),
    }),
  });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al crear presupuesto");
  return res.json();
}

export async function updateQuoteStatus(
  id: string,
  status: Quote["status"]
): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al actualizar estado");
}

export async function deleteQuote(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}`, { method: "DELETE", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al eliminar presupuesto");
}

export async function markQuoteAsRead(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}/read`, { method: "PATCH", credentials: "include" });
  if (!res.ok) throw new Error("Error al marcar como leído");
}

export type QuoteEditablePatch = Partial<{
  client_name: string;
  project: string;
  notes: string;
}>;

export async function updateQuote(id: string, patch: QuoteEditablePatch): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al actualizar presupuesto");
  }
}

// ── Derive Material ─────────────────────────────────────────────────────────

export interface DeriveMaterialPayload {
  material: string;
  thickness_mm?: number;
}

export interface DeriveMaterialResponse {
  ok: boolean;
  quote_id: string;
  material: string;
  total_ars: number;
  total_usd: number;
  derived_from: string;
}

export async function deriveMaterial(quoteId: string, payload: DeriveMaterialPayload): Promise<DeriveMaterialResponse> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${quoteId}/derive-material`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al derivar presupuesto");
  }
  return res.json();
}

// ── Resumen de obra (consolidated multi-quote summary) ───────────────────────

export interface ResumenObraRequest {
  quote_ids: string[];
  notes?: string;
  force_same_client?: boolean;
}

export async function generateResumenObra(
  payload: ResumenObraRequest
): Promise<ResumenObraRecord> {
  const res = await apiFetch(`${API_BASE}/api/quotes/resumen-obra`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al generar resumen de obra");
  }
  return res.json();
}

// ── Client fuzzy match + merge ───────────────────────────────────────────────

export interface ClientMatchCheckResult {
  same: boolean;
  reason: "exact" | "fuzzy" | "ambiguous";
  distinct_names: string[];
}

export async function clientMatchCheck(
  quoteIds: string[]
): Promise<ClientMatchCheckResult> {
  const res = await apiFetch(`${API_BASE}/api/quotes/client-match-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quote_ids: quoteIds }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al verificar el cliente");
  }
  return res.json();
}

export interface MergeClientResult {
  ok: boolean;
  updated_ids: string[];
  client_name: string;
  quote_ids: string[];
}

export async function mergeClient(
  quoteIds: string[],
  canonicalClientName: string
): Promise<MergeClientResult> {
  const res = await apiFetch(`${API_BASE}/api/quotes/merge-client`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quote_ids: quoteIds,
      canonical_client_name: canonicalClientName,
    }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al unificar clientes");
  }
  return res.json();
}

// ── Email draft (AI-generated client email) ──────────────────────────────────

export interface EmailDraft {
  subject: string;
  body: string;
  generated_at: string;
  validated: boolean;
  quote_updated_at_snapshot: string;
  resumen_updated_at_snapshot: string | null;
  sibling_updated_at_snapshots: Record<string, string>;
}

export async function fetchEmailDraft(quoteId: string): Promise<EmailDraft> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${quoteId}/email-draft`, {
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al cargar el email");
  }
  return res.json();
}

export async function regenerateEmailDraft(
  quoteId: string
): Promise<EmailDraft> {
  const res = await apiFetch(
    `${API_BASE}/api/quotes/${quoteId}/email-draft/regenerate`,
    { method: "POST", credentials: "include" }
  );
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al regenerar el email");
  }
  return res.json();
}

// ── Quote Comparison ─────────────────────────────────────────────────────────

export interface QuoteCompareItem {
  id: string;
  material: string | null;
  total_ars: number | null;
  total_usd: number | null;
  status: string;
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
  quote_breakdown: QuoteBreakdown | null;
}

export interface QuoteCompareResponse {
  parent_id: string;
  client_name: string;
  project: string;
  quotes: QuoteCompareItem[];
}

export async function fetchQuoteComparison(id: string): Promise<QuoteCompareResponse | null> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}/compare`, { credentials: "include" });
  if (res.status === 404) return null;
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar comparación");
  return res.json();
}

// ── Generate Documents ───────────────────────────────────────────────────────

export async function generateQuoteDocuments(id: string): Promise<{ ok: boolean; pdf_url?: string; excel_url?: string; drive_url?: string }> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}/generate`, { method: "POST", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al generar documentos");
  }
  return res.json();
}

export async function validateQuote(id: string): Promise<{ ok: boolean; pdf_url?: string; excel_url?: string; drive_url?: string }> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}/validate`, { method: "POST", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al validar presupuesto");
  }
  return res.json();
}

/**
 * PR #378 — Reabre la edición del despiece después de haber confirmado
 * medidas. Limpia el Paso 2 (material + MO + totales + contexto verificado)
 * y deja el quote en estado Paso 1 editable. El operador corrige,
 * reconfirma, y Valentina regenera Paso 2 limpio.
 *
 * Errores:
 *  - 404: quote no existe.
 *  - 409: status es `validated` o `sent` (PDF ya entregado, no se reabre).
 *  - 400: no había confirmación previa (nada que reabrir).
 */
export async function reopenMeasurements(id: string): Promise<void> {
  const res = await apiFetch(
    `${API_BASE}/api/quotes/${id}/reopen-measurements`,
    { method: "POST", credentials: "include" },
  );
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al reabrir edición del despiece");
  }
}

/**
 * PR #383 — Reabre la edición del contexto después de haber confirmado
 * la card de análisis. Limpia Paso 2 + `verified_context_analysis` y
 * corta el historial desde la card `__CONTEXT_ANALYSIS__` (inclusive),
 * regenerándola con los data_known + assumptions + pending_questions
 * que el operador vio en el momento original.
 *
 * Errores:
 *  - 404: quote no existe.
 *  - 409: status es `validated` o `sent` (PDF ya entregado).
 *  - 400: no había confirmación de contexto previa.
 */
export async function reopenContext(id: string): Promise<void> {
  const res = await apiFetch(
    `${API_BASE}/api/quotes/${id}/reopen-context`,
    { method: "POST", credentials: "include" },
  );
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al reabrir edición del contexto");
  }
}

/**
 * Regenera PDF y Excel del presupuesto usando los datos ya guardados en DB.
 * NO re-corre Valentina, NO recalcula precios ni m², NO cambia el status.
 * Solo aplica el template actual sobre el breakdown persistido.
 */
export async function regenerateQuoteDocs(id: string): Promise<{
  ok: boolean;
  pdf_url: string;
  excel_url: string;
  drive_url: string | null;
  regenerated_at: string;
}> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${id}/regenerate`, { method: "POST", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al regenerar archivos");
  }
  return res.json();
}

// ── Usage ────────────────────────────────────────────────────────────────────

export async function fetchUsageDashboard() {
  const res = await apiFetch(`${API_BASE}/api/usage/dashboard`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error cargando uso de API");
  return res.json();
}

export async function fetchUsageDaily() {
  const res = await apiFetch(`${API_BASE}/api/usage/daily`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error cargando detalle diario");
  return res.json();
}

export async function updateUsageBudget(data: { monthly_budget_usd?: number; enable_hard_limit?: boolean }) {
  const res = await apiFetch(`${API_BASE}/api/usage/budget`, {
    method: "PATCH", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error actualizando presupuesto");
  return res.json();
}

// ── Chat SSE ──────────────────────────────────────────────────────────────────

export interface ChatChunk {
  type: "text" | "action" | "done" | "zone_selector" | "dual_read_result" | "context_analysis";
  content: string;
}

// ── Zone Select ──

export async function selectZone(
  quoteId: string,
  bbox: { x1: number; y1: number; x2: number; y2: number },
  pageNum: number = 1,
) {
  // Path absoluto con API_BASE — el rewrite de Next.js proxea a Railway pero
  // no arrastra la cookie (dominio distinto), así que un path relativo devuelve
  // 401. Tiene que ir cross-origin directo, igual que streamChat / fetchQuote.
  const res = await apiFetch(`${API_BASE}/api/quotes/${quoteId}/zone-select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ bbox_normalized: bbox, page_num: pageNum }),
  });
  if (!res.ok) throw new Error(`zone-select failed: ${res.status}`);
  return res.json();
}

// Retry del dual-read invocando a Opus (más caro, más preciso). Usado cuando
// las medidas del primer pass no convencen al operador. MISMA regla que
// selectZone: URL absoluta con API_BASE — el rewrite proxy no pasa la cookie
// en el setup cross-origin (PR #322), así que un path relativo falla 401.
export async function dualReadRetry(quoteId: string): Promise<unknown> {
  const res = await apiFetch(`${API_BASE}/api/quotes/${quoteId}/dual-read-retry`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({} as { detail?: string }));
    throw new Error((err as { detail?: string }).detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function* streamChat(
  quoteId: string,
  message: string,
  files?: File[],
  signal?: AbortSignal
): AsyncGenerator<ChatChunk> {
  const formData = new FormData();
  formData.append("message", message);
  if (files) {
    for (const f of files) {
      formData.append("plan_files", f);
    }
  }

  // Abort if no response within 60s (connection timeout)
  const controller = new AbortController();
  const { CONNECT_TIMEOUT } = await import("@/lib/constants");
  const connectTimeout = setTimeout(() => controller.abort(), CONNECT_TIMEOUT);
  // Forward external abort signal if provided
  if (signal) signal.addEventListener("abort", () => controller.abort(), { once: true });

  let res: Response;
  try {
    // withAuthHeader inyecta Authorization: Bearer <token> si hay sesión en
    // localStorage — imprescindible en iOS Safari (la cookie cross-origin
    // no viaja), inofensivo en desktop (cookie tiene precedencia server-side).
    res = await fetch(`${API_BASE}/api/quotes/${quoteId}/chat`, withAuthHeader({
      method: "POST",
      body: formData,
      credentials: "include",
      signal: controller.signal,
    }));
  } catch (e: any) {
    clearTimeout(connectTimeout);
    if (e.name === "AbortError") {
      throw new Error("El servidor tardó demasiado en responder. Intentá de nuevo.");
    }
    throw new Error("No se pudo conectar con Valentina. Intentá de nuevo.");
  }
  clearTimeout(connectTimeout);

  if (!res.ok) {
    if (res.status === 400) {
      try {
        const err = await res.json();
        throw new Error(err.detail || "Error en los archivos adjuntos.");
      } catch (e) {
        if (e instanceof Error && e.message !== "Error en los archivos adjuntos.") throw e;
        throw new Error("Error en los archivos adjuntos.");
      }
    }
    if (res.status === 404) {
      // Presupuesto borrado: tagear el error para que el caller redirija
      // al dashboard y corte el spam de POSTs inútiles.
      const err = new Error(
        "Este presupuesto ya no existe. Volviendo al listado…"
      );
      (err as any).code = "QUOTE_NOT_FOUND";
      throw err;
    }
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new Error("El servidor está reiniciando. Esperá unos segundos e intentá de nuevo.");
    }
    throw new Error("No se pudo conectar con Valentina. Intentá de nuevo.");
  }
  if (!res.body) throw new Error("El servidor no envió respuesta. Intentá de nuevo.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Stall timeout: abort if no data received during streaming
  const { STALL_TIMEOUT } = await import("@/lib/constants");
  let stallTimer: ReturnType<typeof setTimeout> | null = null;
  const resetStallTimer = () => {
    if (stallTimer) clearTimeout(stallTimer);
    stallTimer = setTimeout(() => {
      reader.cancel();
    }, STALL_TIMEOUT);
  };

  try {
    resetStallTimer();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      resetStallTimer();
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const chunk: ChatChunk = JSON.parse(line.slice(6));
            yield chunk;
          } catch (e) {
            console.warn("SSE parse error:", line, e);
          }
        }
      }
    }
  } finally {
    if (stallTimer) clearTimeout(stallTimer);
  }
}

// ── Catalog ───────────────────────────────────────────────────────────────────

export async function fetchCatalogs() {
  // Trailing slash obligatorio: el endpoint FastAPI está registrado como
  // `@router.get("/")` con prefix `/catalog`, así que la ruta real es
  // `/api/catalog/` (con slash). Sin slash, FastAPI responde 307 con
  // `Location: .../api/catalog/`. El browser sigue el redirect, y si
  // Vercel lo procesa como redirect cross-origin (no proxy), terminamos
  // en origen Railway donde la cookie SameSite=Lax no viaja → 401 →
  // handleAuthError redirige a /login → usuario ve "sesión cerrada".
  //
  // Con el slash vamos directo al handler — zero redirects, zero jumps
  // cross-origin, cookie viaja.
  const res = await apiFetch(`${API_BASE}/api/catalog/`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar catálogos");
  return res.json();
}

export async function fetchCatalog(name: string) {
  const res = await apiFetch(`${API_BASE}/api/catalog/${name}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Catálogo no encontrado");
  return res.json();
}

export async function validateCatalog(name: string, content: unknown) {
  const res = await apiFetch(`${API_BASE}/api/catalog/${name}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al validar catálogo");
  return res.json();
}

export async function updateCatalog(name: string, content: unknown) {
  const res = await apiFetch(`${API_BASE}/api/catalog/${name}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al guardar catálogo");
  return res.json();
}

// ── Catalog Import ──────────────────────────────────────────────────────────

export interface ImportDiffItem {
  sku: string;
  name: string;
  old_price?: number;
  new_price?: number;
  change_pct?: number;
  price?: number;
}

export interface ImportCatalogDiff {
  catalog: string;
  currency: string;
  file_currency: string;
  price_field: string;
  updated: ImportDiffItem[];
  normalized: ImportDiffItem[];
  new: ImportDiffItem[];
  missing: ImportDiffItem[];
  zero_price: ImportDiffItem[];
  unchanged: number;
  warnings: string[];
  total_in_file: number;
  total_in_catalog: number;
}

export interface ImportPreviewResult {
  format: string;
  total_items: number;
  catalogs: Record<string, ImportCatalogDiff>;
  unmatched: { sku: string; name: string; price: number | null }[];
  iva_warning: boolean;
  currency_mismatch: boolean;
  warnings: string[];
}

export interface ImportApplyResult {
  ok: boolean;
  results: Record<string, { ok: boolean; updated?: number; added?: number; skipped_zero?: number; error?: string }>;
  source_file: string;
}

export interface BackupEntry {
  id: number;
  created_at: string | null;
  source_file: string | null;
  stats: { items_before?: number; updated?: number; new?: number; reason?: string } | null;
}

export async function importPreview(file: File): Promise<ImportPreviewResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API_BASE}/api/catalog/import-preview`, {
    method: "POST",
    body: form,
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al analizar archivo");
  }
  return res.json();
}

export async function importApply(file: File, catalogs: string[], includeNew: boolean, sourceFile: string): Promise<ImportApplyResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("catalogs", JSON.stringify(catalogs));
  form.append("include_new", String(includeNew));
  form.append("source_file", sourceFile);
  const res = await apiFetch(`${API_BASE}/api/catalog/import-apply`, {
    method: "POST",
    body: form,
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al importar");
  }
  return res.json();
}

export async function listBackups(catalogName: string): Promise<BackupEntry[]> {
  const res = await apiFetch(`${API_BASE}/api/catalog/backups/${catalogName}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar backups");
  return res.json();
}

export async function restoreBackup(backupId: number): Promise<{ ok: boolean; catalog: string }> {
  const res = await apiFetch(`${API_BASE}/api/catalog/backups/${backupId}/restore`, {
    method: "POST",
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al restaurar backup");
  }
  return res.json();
}

// ── Users ────────────────────────────────────────────────────────────────────

export interface UserInfo {
  id: string;
  username: string;
  created_at: string | null;
}

export async function fetchUsers(): Promise<UserInfo[]> {
  const res = await apiFetch(`${API_BASE}/api/auth/users`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar usuarios");
  return res.json();
}

export async function apiCreateUser(username: string, password: string): Promise<{ ok: boolean; id: string }> {
  const res = await apiFetch(`${API_BASE}/api/auth/create-user`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al crear usuario");
  }
  return res.json();
}

export async function deleteUser(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/auth/users/${id}`, { method: "DELETE", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al eliminar usuario");
  }
}
