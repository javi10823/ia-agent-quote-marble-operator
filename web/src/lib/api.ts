const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  created_at: string;
}

export interface QuoteDetail extends Quote {
  messages: Message[];
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
  const res = await fetch(`${API_BASE}/api/quotes`);
  if (!res.ok) throw new Error("Error al cargar presupuestos");
  return res.json();
}

export async function fetchQuote(id: string): Promise<QuoteDetail> {
  const res = await fetch(`${API_BASE}/api/quotes/${id}`);
  if (!res.ok) throw new Error("Presupuesto no encontrado");
  return res.json();
}

export async function createQuote(): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/api/quotes`, { method: "POST" });
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
  });
  if (!res.ok) throw new Error("Error al actualizar estado");
}

// ── Chat SSE ──────────────────────────────────────────────────────────────────

export interface ChatChunk {
  type: "text" | "action" | "done";
  content: string;
}

export async function* streamChat(
  quoteId: string,
  message: string,
  planFile?: File
): AsyncGenerator<ChatChunk> {
  const formData = new FormData();
  formData.append("message", message);
  if (planFile) {
    formData.append("plan_file", planFile);
  }

  const res = await fetch(`${API_BASE}/api/quotes/${quoteId}/chat`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) throw new Error("Error en el chat");
  if (!res.body) throw new Error("Sin respuesta del servidor");

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
  const res = await fetch(`${API_BASE}/api/catalog`);
  if (!res.ok) throw new Error("Error al cargar catálogos");
  return res.json();
}

export async function fetchCatalog(name: string) {
  const res = await fetch(`${API_BASE}/api/catalog/${name}`);
  if (!res.ok) throw new Error("Catálogo no encontrado");
  return res.json();
}

export async function validateCatalog(name: string, content: unknown) {
  const res = await fetch(`${API_BASE}/api/catalog/${name}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Error al validar catálogo");
  return res.json();
}

export async function updateCatalog(name: string, content: unknown) {
  const res = await fetch(`${API_BASE}/api/catalog/${name}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Error al guardar catálogo");
  return res.json();
}
