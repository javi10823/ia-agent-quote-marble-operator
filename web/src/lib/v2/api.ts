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

/** Los 11 campos del contexto (Master §6 mockup 01-A). */
export interface ContextData {
  cliente: string; // arquitecta / razón social
  contacto: string; // teléfono / email
  localidad: string; // obra · ciudad
  plazo: string; // desde confirmación de medidas
  tipologia: string; // cocina, baño, mesa
  tipo_obra: "particular" | "edificio";
  material: string; // piedra o engineered
  pileta: string; // tipo + origen
  zocalo: string; // contra pared · si/no + alto
  regrueso: string; // borde frontal grueso
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
 * GET context para un quote. Mock retorna CANONICAL_CONTEXT (Master §13)
 * la primera vez, luego cualquier estado guardado en la sesión.
 */
export async function getContextForQuote(
  quoteId: string,
  options?: { signal?: AbortSignal },
): Promise<ContextResponse> {
  await delay(150 + Math.random() * 200, options?.signal);
  const existing = _contextStore.get(quoteId);
  if (existing) return existing;
  // Lazy import para evitar circular en build (canonicalQuote re-importa types).
  const { CANONICAL_CONTEXT } = await import("./mocks/canonicalQuote");
  const seeded = JSON.parse(JSON.stringify(CANONICAL_CONTEXT)) as ContextResponse;
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

/** Frases canónicas rioplatenses para mock — varían según scope. */
function pickResponse(scope: ChatScope, message: string): string {
  const lower = message.toLowerCase();
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
  options?: { signal?: AbortSignal },
): ReadableStream<ChatStreamChunk> {
  const text = pickResponse(scope, message);
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
