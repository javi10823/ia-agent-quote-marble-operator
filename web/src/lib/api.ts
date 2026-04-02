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
  status: "draft" | "validated" | "sent";
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
  parent_quote_id: string | null;
  source: string | null;
  is_read: boolean;
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

export async function fetchQuote(id: string): Promise<QuoteDetail> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}`, { credentials: "include" });
  handleAuthError(res);
  if (!res.ok) throw new Error("Presupuesto no encontrado");
  return res.json();
}

export async function createQuote(): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/api/quotes`, { method: "POST", credentials: "include" });
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

// ── Quote Comparison ─────────────────────────────────────────────────────────

export interface QuoteCompareItem {
  id: string;
  material: string | null;
  total_ars: number | null;
  total_usd: number | null;
  status: string;
  pdf_url: string | null;
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

// ── Chat SSE ──────────────────────────────────────────────────────────────────

export interface ChatChunk {
  type: "text" | "action" | "done";
  content: string;
}

export async function* streamChat(
  quoteId: string,
  message: string,
  files?: File[]
): AsyncGenerator<ChatChunk> {
  const formData = new FormData();
  formData.append("message", message);
  if (files) {
    for (const f of files) {
      formData.append("plan_files", f);
    }
  }

  const res = await fetch(`${API_BASE}/api/quotes/${quoteId}/chat`, {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!res.ok) {
    if (res.status === 400) {
      // Backend validation error — show the detail message
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

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const chunk: ChatChunk = JSON.parse(line.slice(6));
          yield chunk;
        } catch {}
      }
    }
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
