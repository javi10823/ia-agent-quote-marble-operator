/**
 * E2E del paso 1 — brief upload.
 *
 * Cubre los 3 estados visuales (mockups 00 A/B/C), validaciones,
 * cancel y success path.
 *
 * El "backend" es el mock client en lib/v2/api.ts con latencia
 * 2-5s + AbortController. NO toca backend real.
 */
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const FIXTURE_PDF = path.join(__dirname, "..", "fixtures", "sample.pdf");

async function uploadPdf(page: Page, file: string = FIXTURE_PDF) {
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles(file);
}

test("estado A — dropzone vacío al cargar /v2/quotes/new", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).not.toBeVisible();
  await expect(page.locator('[data-testid="brief-status-bar"]')).not.toBeVisible();
  await expect(page.locator(".brief-hero h2")).toContainText("Subí lo que tengas");
});

test("estado A → B — al subir un PDF aparece el form con el filename", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  await uploadPdf(page);
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-name"]')).toHaveText("sample.pdf");
  await expect(page.locator(".brief-hero h2")).toContainText("Tengo todo lo que necesito");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeEnabled();
});

test("validación — PDF tipo inválido (txt) rechazado en estado A", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles({
    name: "wrong.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("no soy un PDF"),
  });
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toContainText("PDF");
  // Sigue en estado A (no avanzó)
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).not.toBeVisible();
});

test("validación — PDF > 20MB rechazado en estado A", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  // Buffer de 21MB en memoria — react-dropzone rechaza por size sin
  // necesidad de un PDF real
  const big = Buffer.alloc(21 * 1024 * 1024, 0);
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles({
    name: "huge.pdf",
    mimeType: "application/pdf",
    buffer: big,
  });
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toContainText("20");
});

test("validación — foto tipo inválido rechazada", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="photo-input"]').setInputFiles({
    name: "wrong.gif",
    mimeType: "image/gif",
    buffer: Buffer.from("fake"),
  });
  await expect(page.locator('[data-testid="brief-helper"]')).toContainText(/JPG|PNG/);
});

test("estado B → C — click Procesar muestra skeleton + status-bar", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  await expect(page.locator('[data-testid="brief-status-bar"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-processing"]')).toBeVisible();
  await expect(page.locator(".skel").first()).toBeVisible();
});

test("cancel — estado C → vuelve a B con planFile preservado", async ({ page }) => {
  await page.goto("/v2/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  await expect(page.locator('[data-testid="brief-status-bar"]')).toBeVisible();
  await page.locator('[data-testid="brief-cancel"]').click();
  // Vuelve a estado B con el form intacto
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-name"]')).toHaveText("sample.pdf");
  await expect(page.locator('[data-testid="brief-status-bar"]')).not.toBeVisible();
});

test("success path — completar el flujo navega a /v2/quotes/PRES-2026-018/contexto", async ({
  page,
}) => {
  await page.goto("/v2/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("Cocina U + isla, 3,20m");
  await page.locator('[data-testid="brief-submit"]').click();
  // Mock simula latencia 2-5s — esperar redirect (timeout 10s safety)
  await page.waitForURL("**/quotes/PRES-2026-018/contexto", { timeout: 10000 });
  // Confirmar que el chrome del [id] layout está activo
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "contexto");
});

test("CTA en /v2 navega a /v2/quotes/new", async ({ page }) => {
  await page.goto("/v2");
  await page.locator('[data-testid="cta-new-quote"]').click();
  await page.waitForURL("**/v2/quotes/new");
  await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
});
