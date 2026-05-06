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
