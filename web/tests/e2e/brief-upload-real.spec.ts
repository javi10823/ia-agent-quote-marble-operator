/**
 * E2E paso-1-real · brief upload wireado al backend Railway.
 *
 * Gated: solo corre cuando `NEXT_PUBLIC_API_URL` está seteado · default CI
 * arranca sin esa env var, así que estos tests se SKIPEAN y los 9 tests
 * mock (`brief-upload.spec.ts`) siguen siendo el cover por defecto.
 *
 * Estrategia: aún con env var seteada, NO dependemos del backend Railway
 * vivo · interceptamos los 2 endpoints (POST /quotes + POST /quotes/{id}/chat)
 * con `page.route()` y simulamos respuestas. Esto verifica:
 *   - El gate `USE_REAL_API` del index.ts efectivamente swap-eó al wire real
 *   - La secuencia 2-calls + drain del SSE
 *   - Error paths (4xx, agent error, network)
 *
 * Para correr contra Railway REAL: configurar `NEXT_PUBLIC_API_URL=https://api...`
 * y quitar los `page.route()` interceptors del test que querramos validar end-to-end.
 */
import { expect, test, type Page, type Route } from "@playwright/test";
import path from "node:path";

const FIXTURE_PDF = path.join(__dirname, "..", "fixtures", "sample.pdf");
const HAS_API_URL = !!process.env.NEXT_PUBLIC_API_URL;

// Skip toda la suite si no hay env var · 9 tests mock siguen siendo el cover default.
test.skip(
  !HAS_API_URL,
  "brief-upload-real requiere NEXT_PUBLIC_API_URL · default CI corre mocks (brief-upload.spec.ts)",
);

// Cross-talk de stores no aplica acá (cero state mock) pero el flow real
// crea Quote en backend mock-eado · serial evita interceptors race entre tests.
test.describe.configure({ mode: "serial" });

const BACKEND_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function quotesRoute(id: string) {
  return `${BACKEND_BASE}/api/quotes/${id}/chat`;
}

async function mockBackendOk(page: Page, quoteId: string, chunks: Array<Record<string, unknown>>) {
  await page.route(`${BACKEND_BASE}/api/quotes`, async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: quoteId }),
    });
  });
  await page.route(quotesRoute(quoteId), async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const sse = chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join("");
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse,
    });
  });
}

async function uploadPdf(page: Page) {
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles(FIXTURE_PDF);
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
}

test("happy path · text + plan → POST /quotes + POST /chat (SSE done) → redirect /contexto", async ({
  page,
}) => {
  await mockBackendOk(page, "real-001", [
    { type: "text", content: "leyendo plano" },
    { type: "done" },
  ]);

  // Capturamos los requests para verificar la secuencia.
  const calls: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/quotes")) calls.push(`${req.method()} ${req.url()}`);
  });

  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("cocina U + isla en Belgrano");
  await page.locator('[data-testid="brief-submit"]').click();

  // Espera el redirect a /contexto (backend mock devuelve done rápido).
  await page.waitForURL(/\/quotes\/real-001\/contexto/, { timeout: 30_000 });

  expect(calls.some((c) => c.endsWith("/api/quotes"))).toBe(true);
  expect(calls.some((c) => c.endsWith("/api/quotes/real-001/chat"))).toBe(true);
});

test("multimodal · text + plan + foto · ambos archivos viajan como plan_files", async ({
  page,
}) => {
  await mockBackendOk(page, "real-002", [{ type: "done" }]);

  let chatRequest: ReturnType<Page["waitForRequest"]> | null = null;
  chatRequest = page.waitForRequest(quotesRoute("real-002"));

  await page.goto("/quotes/new");
  await uploadPdf(page);
  // Adjuntar foto via PhotoUploader (FileInput hidden).
  await page.locator('[data-testid="photo-uploader-input"]').setInputFiles({
    name: "foto.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0]),
  });
  await page.locator('[data-testid="brief-text"]').fill("isla central");
  await page.locator('[data-testid="brief-submit"]').click();

  const req = await chatRequest;
  // multipart parsing inline: contamos las apariciones del field plan_files.
  const body = req.postData() ?? "";
  const planMatches = body.match(/name="plan_files"/g) ?? [];
  expect(planMatches.length).toBeGreaterThanOrEqual(2);

  await page.waitForURL(/\/quotes\/real-002\/contexto/, { timeout: 30_000 });
});

test("error backend · POST /quotes 500 → estado error visible + reintentar", async ({ page }) => {
  await page.route(`${BACKEND_BASE}/api/quotes`, async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({ status: 500, body: "internal" });
  });

  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("brief x");
  await page.locator('[data-testid="brief-submit"]').click();

  // Vuelve a estado B con banner error · `error.message` contiene el código.
  await expect(page.locator('[data-testid="brief-error"]')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-testid="brief-error"]')).toContainText(/POST \/api\/quotes/);
});

test("error agent SSE · done.error=true → ApiError surface en banner", async ({ page }) => {
  await mockBackendOk(page, "real-err", [
    { type: "text", content: "intentando" },
    { type: "error", content: "Plano ilegible · resolución insuficiente." },
    { type: "done", error: true },
  ]);

  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("brief y");
  await page.locator('[data-testid="brief-submit"]').click();

  await expect(page.locator('[data-testid="brief-error"]')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-testid="brief-error"]')).toContainText(/ilegible/i);
});

test("error chat 503 → ApiError BRIEF_PROCESS_FAILED surface", async ({ page }) => {
  await page.route(`${BACKEND_BASE}/api/quotes`, async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "real-503" }),
    });
  });
  await page.route(quotesRoute("real-503"), async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({ status: 503, body: "LLM down" });
  });

  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("brief z");
  await page.locator('[data-testid="brief-submit"]').click();

  await expect(page.locator('[data-testid="brief-error"]')).toBeVisible({ timeout: 15_000 });
});

test("cancel mid-processing · vuelve a estado B preservando form", async ({ page }) => {
  // Simulamos un backend que tarda · cancelamos antes de que responda.
  await page.route(`${BACKEND_BASE}/api/quotes`, async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "real-cancel" }),
    });
  });
  await page.route(quotesRoute("real-cancel"), async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    // Hang la respuesta para forzar el cancel.
    await new Promise((r) => setTimeout(r, 10_000));
    return route.fulfill({ status: 200, body: 'data: {"type":"done"}\n\n' });
  });

  await page.goto("/quotes/new");
  await uploadPdf(page);
  const text = "brief preservado · cancel test";
  await page.locator('[data-testid="brief-text"]').fill(text);
  await page.locator('[data-testid="brief-submit"]').click();

  // Estado C (processing) visible.
  await expect(page.locator('[data-testid="brief-status-bar"]')).toBeVisible({ timeout: 5_000 });

  // Cancelar.
  await page.locator('[data-testid="brief-cancel"]').click();

  // Vuelve a estado B · form preservado.
  await expect(page.locator('[data-testid="brief-status-bar"]')).not.toBeVisible({
    timeout: 5_000,
  });
  await expect(page.locator('[data-testid="brief-text"]')).toHaveValue(text);
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
});

test("happy path text-only sin photos · plan_files trae solo el plan", async ({ page }) => {
  await mockBackendOk(page, "real-text-only", [{ type: "done" }]);

  const chatReq = page.waitForRequest(quotesRoute("real-text-only"));

  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("brief minimal");
  await page.locator('[data-testid="brief-submit"]').click();

  const req = await chatReq;
  const body = req.postData() ?? "";
  const planMatches = body.match(/name="plan_files"/g) ?? [];
  expect(planMatches.length).toBe(1);

  await page.waitForURL(/\/quotes\/real-text-only\/contexto/, { timeout: 30_000 });
});
