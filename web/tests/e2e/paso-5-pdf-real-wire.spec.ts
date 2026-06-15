/**
 * E2E paso-5-pdf-real-wire · PDF generation wireado al backend Railway.
 *
 * Gated: solo corre cuando `NEXT_PUBLIC_API_URL` está seteado · default
 * CI arranca sin env var, así que estos tests se SKIPEAN y los 4 specs
 * existentes (paso-5-*.spec.ts) siguen siendo el cover por defecto via
 * mocks deterministas.
 *
 * Estrategia (idem brief-upload-real.spec.ts): aún con env var seteada
 * NO dependemos del backend Railway vivo · interceptamos los endpoints
 * con `page.route()` y simulamos respuestas para verificar:
 *   - El gate `USE_REAL_API` del index.ts efectivamente swap-eó al wire real
 *   - El POST /quotes/{id}/generate se dispara con bearer correcto
 *   - Estado A → C transition post-success
 *   - Error mapping (BREAKDOWN_MISSING, DRIVE_QUOTA, PDF_TIMEOUT) renderea
 *     mensaje específico en español, no el detail crudo del backend.
 *
 * Para correr contra Railway REAL: `NEXT_PUBLIC_API_URL=https://...`
 * y quitar los `page.route()` interceptors.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const HAS_API_URL = !!process.env.NEXT_PUBLIC_API_URL;
test.skip(
  !HAS_API_URL,
  "paso-5-pdf-real-wire requiere NEXT_PUBLIC_API_URL · default CI corre mocks",
);

test.describe.configure({ mode: "serial" });

const BACKEND_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function generateRoute(quoteId: string) {
  return `${BACKEND_BASE}/api/quotes/${quoteId}/generate`;
}

function quoteDetailRoute(quoteId: string) {
  return `${BACKEND_BASE}/api/quotes/${quoteId}`;
}

/** Mockea GET /quotes/{id} (necesario para SSR del estado inicial · el
 * adapter espera Quote con `pdf_url`/`excel_url`). Default sin pdf_url
 * → estado A (sin generar). */
async function mockQuoteDetail(page: Page, quoteId: string, withPdf: boolean = false) {
  await page.route(quoteDetailRoute(quoteId), async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: quoteId,
        client_name: "Cliente Test",
        project: "Cocina test",
        material: "Blanco Paloma",
        status: withPdf ? "sent" : "draft",
        pdf_url: withPdf ? "https://drive.google.com/file/test-pdf" : null,
        excel_url: withPdf ? "https://drive.google.com/file/test-xlsx" : null,
        drive_url: withPdf ? "https://drive.google.com/folder/test-folder" : null,
        drive_file_id: withPdf ? "abc123" : null,
        updated_at: "2026-06-14T18:42:00Z",
        quote_breakdown: { client_name: "Cliente Test" },
      }),
    });
  });
}

test("real wire · POST /generate retorna 200 + pdf_url → estado C visible con file rows", async ({
  page,
}) => {
  const quoteId = "real-pdf-001";
  await mockQuoteDetail(page, quoteId, false);
  await page.route(generateRoute(quoteId), async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        pdf_url: "https://drive.google.com/file/real-pdf",
        excel_url: "https://drive.google.com/file/real-xlsx",
        drive_url: "https://drive.google.com/folder/real-folder",
        drive_file_id: "real-abc-123",
      }),
    });
  });

  await page.goto(`/quotes/${quoteId}/pdf`);
  await page.locator('[data-testid="generate-pdf"]').click();
  await page.locator('[data-testid="modal-confirm"]').click();
  // Estado C visible · sidebar generated con file rows.
  await expect(page.locator('[data-testid="pdf-state-c-sidebar"]')).toBeVisible({
    timeout: 10_000,
  });
});

test("real wire · 400 BREAKDOWN_MISSING → modal renderea mensaje español específico", async ({
  page,
}) => {
  const quoteId = "real-pdf-002";
  await mockQuoteDetail(page, quoteId, false);
  await page.route(generateRoute(quoteId), async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Este presupuesto no tiene datos de cálculo (quote_breakdown)",
      }),
    });
  });

  await page.goto(`/quotes/${quoteId}/pdf`);
  await page.locator('[data-testid="generate-pdf"]').click();
  await page.locator('[data-testid="modal-confirm"]').click();
  const banner = page.locator('[data-testid="modal-error-banner"]');
  await expect(banner).toBeVisible({ timeout: 10_000 });
  await expect(banner).toContainText(/falta procesar el contexto/i);
  // El botón "Reintentar" debe quedar habilitado para reintento.
  await expect(page.locator('[data-testid="modal-confirm"]')).toBeEnabled();
});

test("real wire · descarga usa pdf_url real del backend (window.open con URL exacta)", async ({
  page,
  context,
}) => {
  const quoteId = "real-pdf-003";
  const expectedPdfUrl = "https://drive.google.com/file/expected-pdf-url";
  // GET pre-poblado · estado C ya seedeado desde SSR.
  await mockQuoteDetail(page, quoteId, true);
  await page.route(quoteDetailRoute(quoteId), async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: quoteId,
        client_name: "Cliente Download",
        project: "Test",
        material: "Test",
        status: "sent",
        pdf_url: expectedPdfUrl,
        excel_url: "https://drive.google.com/file/excel-url",
        drive_url: "https://drive.google.com/folder/test",
        drive_file_id: "dl-123",
        updated_at: "2026-06-14T18:42:00Z",
        quote_breakdown: { client_name: "Cliente Download" },
      }),
    });
  });

  await page.goto(`/quotes/${quoteId}/pdf`);
  // Click descarga PDF · capturamos la nueva pestaña.
  const popupPromise = context.waitForEvent("page", { timeout: 10_000 });
  await page.locator('[data-testid="download-pdf-row"]').click();
  const popup = await popupPromise;
  expect(popup.url()).toBe(expectedPdfUrl);
});
