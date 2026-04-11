// Use relative URLs to go through Next.js rewrite proxy (avoids CORS)
const API_BASE = "";

function handleAuthError(res: Response): void {
  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
  }
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
  comparison_group_id: string | null;
  source: string | null;
  is_read: boolean;
  notes: string | null;
  sink_type: { basin_count: "simple" | "doble"; mount_type: "arriba" | "abajo" } | null;
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
  const res = await fetch(`${API_BASE}/api/quotes`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar presupuestos");
  return res.json();
}

export interface QuotesCheck {
  count: number;
  last_updated_at: string | null;
}

export async function checkQuotes(): Promise<QuotesCheck> {
  const res = await fetch(`${API_BASE}/api/quotes/check`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al verificar presupuestos");
  return res.json();
}

export async function fetchQuote(id: string): Promise<QuoteDetail> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Presupuesto no encontrado");
  return res.json();
}

export async function createQuote(
  options?: { status?: Quote["status"] }
): Promise<{ id: string }> {
  const hasBody = options?.status != null;
  const res = await fetch(`${API_BASE}/api/quotes`, {
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
  const res = await fetch(`${API_BASE}/api/quotes/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
    credentials: "include",
  });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al actualizar estado");
}

export async function deleteQuote(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}`, { method: "DELETE", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al eliminar presupuesto");
}

export async function markQuoteAsRead(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}/read`, { method: "PATCH", credentials: "include" });
  if (!res.ok) throw new Error("Error al marcar como leído");
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
  const res = await fetch(`${API_BASE}/api/quotes/${quoteId}/derive-material`, {
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
  const res = await fetch(`${API_BASE}/api/quotes/${id}/compare`, { credentials: "include" });
  if (res.status === 404) return null;
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar comparación");
  return res.json();
}

// ── Generate Documents ───────────────────────────────────────────────────────

export async function generateQuoteDocuments(id: string): Promise<{ ok: boolean; pdf_url?: string; excel_url?: string; drive_url?: string }> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}/generate`, { method: "POST", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al generar documentos");
  }
  return res.json();
}

export async function validateQuote(id: string): Promise<{ ok: boolean; pdf_url?: string; excel_url?: string; drive_url?: string }> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}/validate`, { method: "POST", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al validar presupuesto");
  }
  return res.json();
}

// ── Usage ────────────────────────────────────────────────────────────────────

export async function fetchUsageDashboard() {
  const res = await fetch(`${API_BASE}/api/usage/dashboard`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error cargando uso de API");
  return res.json();
}

export async function fetchUsageDaily() {
  const res = await fetch(`${API_BASE}/api/usage/daily`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error cargando detalle diario");
  return res.json();
}

export async function updateUsageBudget(data: { monthly_budget_usd?: number; enable_hard_limit?: boolean }) {
  const res = await fetch(`${API_BASE}/api/usage/budget`, {
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
  type: "text" | "action" | "done";
  content: string;
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
    res = await fetch(`${API_BASE}/api/quotes/${quoteId}/chat`, {
      method: "POST",
      body: formData,
      credentials: "include",
      signal: controller.signal,
    });
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
  const res = await fetch(`${API_BASE}/api/catalog`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar catálogos");
  return res.json();
}

export async function fetchCatalog(name: string) {
  const res = await fetch(`${API_BASE}/api/catalog/${name}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Catálogo no encontrado");
  return res.json();
}

export async function validateCatalog(name: string, content: unknown) {
  const res = await fetch(`${API_BASE}/api/catalog/${name}/validate`, {
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
  const res = await fetch(`${API_BASE}/api/catalog/${name}`, {
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
  price_field: string;
  updated: ImportDiffItem[];
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
  const res = await fetch(`${API_BASE}/api/catalog/import-preview`, {
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
  const res = await fetch(`${API_BASE}/api/catalog/import-apply`, {
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
  const res = await fetch(`${API_BASE}/api/catalog/backups/${catalogName}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar backups");
  return res.json();
}

export async function restoreBackup(backupId: number): Promise<{ ok: boolean; catalog: string }> {
  const res = await fetch(`${API_BASE}/api/catalog/backups/${backupId}/restore`, {
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
  const res = await fetch(`${API_BASE}/api/auth/users`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Error al cargar usuarios");
  return res.json();
}

export async function apiCreateUser(username: string, password: string): Promise<{ ok: boolean; id: string }> {
  const res = await fetch(`${API_BASE}/api/auth/create-user`, {
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
  const res = await fetch(`${API_BASE}/api/auth/users/${id}`, { method: "DELETE", credentials: "include" });
  handleAuthError(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Error al eliminar usuario");
  }
}
