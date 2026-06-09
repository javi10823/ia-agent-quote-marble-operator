/**
 * Unit tests · Sprint 4 paso-1-real · createDraftQuote real wire.
 *
 * Mocks global `fetch` para verificar la secuencia 2-calls que el wire
 * dispara contra el backend Railway:
 *
 *   1) POST /api/quotes (JSON body vacío) → {id}
 *   2) POST /api/quotes/{id}/chat (multipart) → SSE stream consumido
 *
 * Cobertura:
 *   - happy path text-only (sin photos)
 *   - happy path text + plan + photos (multipart correcto)
 *   - briefText vacío → message placeholder
 *   - 4xx en POST /quotes → ApiError CREATE_QUOTE_FAILED
 *   - 5xx en POST /chat → ApiError BRIEF_PROCESS_FAILED
 *   - SSE chunk `error` + `done.error=true` → ApiError BRIEF_AGENT_ERROR
 *   - SSE stream cierra sin `done` → asume success implícito
 *   - AbortController durante chat → DOMException AbortError propagado
 *
 * Por qué unit y no E2E: el wire HTTP es pura coordinación · más rápido y
 * determinístico testearlo aislado que levantar el backend real Railway en
 * cada run de CI. El E2E gated por `NEXT_PUBLIC_API_URL` complementa con la
 * verificación end-to-end real opcional.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { createDraftQuote } from "@/lib/api/real";
import { ApiError } from "@/lib/api/types";

// Helper: construye una respuesta SSE válida con los chunks dados.
function sseStream(chunks: Array<Record<string, unknown>>): Response {
  const body = chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join("");
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

// Helper: respuesta JSON con `{id}` para POST /quotes.
function createQuoteResponse(id: string = "test-uuid-123"): Response {
  return new Response(JSON.stringify({ id }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

const FAKE_PLAN = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "plano.pdf", {
  type: "application/pdf",
});
const FAKE_PHOTO = new File([new Uint8Array([0xff, 0xd8, 0xff])], "foto.jpg", {
  type: "image/jpeg",
});

describe("createDraftQuote real · secuencia 2-calls", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
    // NEXT_PUBLIC_API_URL debe estar definido para que apiFetch genere URLs absolutas.
    // En unit tests no importa el valor exacto · solo que sea no-vacío.
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://test-backend.local");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  test("happy path text-only · POST /quotes + POST /chat con plan_files sin photos", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("quote-001"))
      .mockResolvedValueOnce(sseStream([{ type: "text", content: "ok" }, { type: "done" }]));

    const result = await createDraftQuote({ planFile: FAKE_PLAN, briefText: "cocina U" });

    expect(result.id).toBe("quote-001");
    expect(result.status).toBe("draft");
    expect(result.createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);

    // 2 calls al backend. La URL exacta depende de `NEXT_PUBLIC_API_URL` que
    // se resuelve en import-time del módulo · acá solo verificamos el path
    // suffix porque vi.stubEnv() ya no llega a tiempo.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [createUrl, createInit] = fetchMock.mock.calls[0];
    expect(createUrl).toMatch(/\/api\/quotes$/);
    expect(createInit.method).toBe("POST");
    expect(createInit.body).toBe("{}");

    const [chatUrl, chatInit] = fetchMock.mock.calls[1];
    expect(chatUrl).toMatch(/\/api\/quotes\/quote-001\/chat$/);
    expect(chatInit.method).toBe("POST");
    expect(chatInit.body).toBeInstanceOf(FormData);
    const form = chatInit.body as FormData;
    expect(form.get("message")).toBe("cocina U");
    const planFiles = form.getAll("plan_files");
    expect(planFiles).toHaveLength(1);
    expect((planFiles[0] as File).name).toBe("plano.pdf");
  });

  test("multimodal · plan + 2 photos enviados como plan_files repetidos", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("quote-002"))
      .mockResolvedValueOnce(sseStream([{ type: "done" }]));

    const photo2 = new File([new Uint8Array([0xff])], "foto2.jpg", { type: "image/jpeg" });
    await createDraftQuote({
      planFile: FAKE_PLAN,
      photos: [FAKE_PHOTO, photo2],
      briefText: "isla central",
    });

    const form = fetchMock.mock.calls[1][1].body as FormData;
    const files = form.getAll("plan_files");
    expect(files).toHaveLength(3);
    expect((files[0] as File).name).toBe("plano.pdf");
    expect((files[1] as File).name).toBe("foto.jpg");
    expect((files[2] as File).name).toBe("foto2.jpg");
  });

  test("briefText vacío · usa message placeholder no-vacío que el backend espera", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("quote-003"))
      .mockResolvedValueOnce(sseStream([{ type: "done" }]));

    await createDraftQuote({ planFile: FAKE_PLAN });

    const form = fetchMock.mock.calls[1][1].body as FormData;
    const message = form.get("message") as string;
    expect(message).toBeTruthy();
    expect(message.length).toBeGreaterThan(0);
    expect(message.toLowerCase()).toContain("presupuesto");
  });

  test("briefText con solo whitespace · trata como vacío", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("quote-003b"))
      .mockResolvedValueOnce(sseStream([{ type: "done" }]));

    await createDraftQuote({ planFile: FAKE_PLAN, briefText: "   \n\t  " });

    const form = fetchMock.mock.calls[1][1].body as FormData;
    expect((form.get("message") as string).length).toBeGreaterThan(0);
  });
});

describe("createDraftQuote real · error paths", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://test-backend.local");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  test("POST /quotes 500 → ApiError CREATE_QUOTE_FAILED", async () => {
    fetchMock.mockResolvedValueOnce(new Response("server down", { status: 500 }));

    await expect(createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" })).rejects.toMatchObject({
      name: "ApiError",
      code: "CREATE_QUOTE_FAILED",
      status: 500,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1); // no llega al chat
  });

  test("POST /quotes devuelve sin id → ApiError CREATE_QUOTE_MALFORMED", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ other: "field" }), { status: 200 }),
    );

    await expect(createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" })).rejects.toMatchObject({
      code: "CREATE_QUOTE_MALFORMED",
    });
  });

  test("POST /chat 503 → ApiError BRIEF_PROCESS_FAILED", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("q-fail"))
      .mockResolvedValueOnce(new Response("LLM offline", { status: 503 }));

    await expect(createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" })).rejects.toMatchObject({
      code: "BRIEF_PROCESS_FAILED",
      status: 503,
    });
  });

  test("SSE chunk error + done.error=true → ApiError BRIEF_AGENT_ERROR con mensaje", async () => {
    fetchMock.mockResolvedValueOnce(createQuoteResponse("q-agent-err")).mockResolvedValueOnce(
      sseStream([
        { type: "text", content: "leyendo plano..." },
        { type: "error", content: "Plano ilegible · resolución insuficiente." },
        { type: "done", error: true },
      ]),
    );

    await expect(createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" })).rejects.toMatchObject({
      code: "BRIEF_AGENT_ERROR",
      message: "Plano ilegible · resolución insuficiente.",
    });
  });

  test("SSE stream cierra sin `done` ni error → asume success implícito", async () => {
    fetchMock.mockResolvedValueOnce(createQuoteResponse("q-noend")).mockResolvedValueOnce(
      new Response("data: " + JSON.stringify({ type: "text", content: "parcial" }) + "\n\n", {
        status: 200,
      }),
    );

    const result = await createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" });
    expect(result.id).toBe("q-noend");
  });

  test("SSE chunks malformados se skipean sin tirar", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("q-malformed"))
      .mockResolvedValueOnce(
        new Response(
          [
            "data: not-json-at-all\n\n",
            "data: " + JSON.stringify({ type: "text", content: "ok" }) + "\n\n",
            "data: " + JSON.stringify({ type: "done" }) + "\n\n",
          ].join(""),
          { status: 200 },
        ),
      );

    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" });
    expect(result.id).toBe("q-malformed");
    expect(consoleWarn).toHaveBeenCalled();
  });

  test("AbortController → propaga AbortError sin envolver en ApiError", async () => {
    const ctrl = new AbortController();
    // fetch real con signal lanza AbortError cuando ctrl.abort() · aquí lo
    // simulamos con un fetchMock que respeta el signal.
    fetchMock.mockImplementationOnce((_url, init: RequestInit | undefined) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    });

    const promise = createDraftQuote(
      { planFile: FAKE_PLAN, briefText: "x" },
      { signal: ctrl.signal },
    );
    ctrl.abort();

    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("createDraftQuote real · auth / SSR", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://test-backend.local");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  test("bearerToken pasado a options se incluye en ambas requests como header Authorization", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("q-auth"))
      .mockResolvedValueOnce(sseStream([{ type: "done" }]));

    await createDraftQuote(
      { planFile: FAKE_PLAN, briefText: "x" },
      { bearerToken: "jwt-token-xyz" },
    );

    for (const call of fetchMock.mock.calls) {
      const headers = call[1].headers as Headers;
      expect(headers.get("authorization")).toBe("Bearer jwt-token-xyz");
    }
  });

  test("sin bearerToken · NO incluye header Authorization (depende de cookie cross-origin)", async () => {
    fetchMock
      .mockResolvedValueOnce(createQuoteResponse("q-noauth"))
      .mockResolvedValueOnce(sseStream([{ type: "done" }]));

    await createDraftQuote({ planFile: FAKE_PLAN, briefText: "x" });

    for (const call of fetchMock.mock.calls) {
      const headers = call[1].headers as Headers;
      expect(headers.get("authorization")).toBeNull();
    }
    // `credentials: "include"` siempre presente (cookie cross-origin)
    for (const call of fetchMock.mock.calls) {
      expect(call[1].credentials).toBe("include");
    }
  });
});
