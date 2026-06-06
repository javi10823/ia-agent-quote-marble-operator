/**
 * E2E paso-5 estado C · "PDF generado" · Sprint 4 paso-5-c-generado (mockup 20).
 *
 * Triggers (mock):
 * - Sufijo `-GENERATED` en quoteId → SSR seedea estado C directo
 * - Sufijo `-ERROR` → triggerPdfGeneration throw → modal banner error + Reintentar
 * - Sin sufijo → estado A normal (regresión PR #470/#472)
 */
import { expect, test, type Page } from "@playwright/test";

// El mock `_generatedStore` del backend (mocks.ts) persiste in-memory en
// el Next dev server entre requests. Si dos tests del archivo tocan el
// mismo quoteId en workers paralelos, uno deja state que el otro lee como
// estado C inesperado. Forzamos serial mode SOLO en este archivo para
// evitar cross-talk del store · mantenemos paralelismo en el resto de la
// suite.
test.describe.configure({ mode: "serial" });

// Reset del `_generatedStore` mock entre tests para evitar cross-talk con
// otros specs (paso-5-pdf, paso-5-confirm-modal) que usan los mismos IDs
// canon (PRES-2026-018) en workers paralelos. El endpoint solo existe en
// dev/test (404 en prod).
test.afterEach(async ({ request }) => {
  await request.post("/api/_test/reset-pdf-store");
});

async function goPdf(page: Page, id: string) {
  await page.goto(`/quotes/${id}/pdf`);
  // Timeout extendido · el SSR del estado C dispara `getPdfGeneratedInfo`
  // + `Promise.allSettled` con 6 cargas paralelas. Bajo carga de workers
  // paralelos (Next dev recompilando) puede tomar >5s default.
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible({ timeout: 15_000 });
}

test("PRES-018-GENERATED renderea estado C (gen-banner + sidebar generated + chip final)", async ({
  page,
}) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
  await expect(page.locator('[data-testid="version-chip"]')).toContainText("v1 · enviado");
  await expect(page.locator('[data-testid="pdf-gen-banner"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-sidebar-generated"]')).toBeVisible();
  // El sidebar editable del estado A no debe renderearse.
  await expect(page.locator('[data-testid="pdf-sidebar"]')).toHaveCount(0);
});

test("gen-banner muestra timestamp + Marina + trace_id literal", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  const banner = page.locator('[data-testid="pdf-gen-banner"]');
  await expect(banner).toContainText("v1 generado correctamente");
  await expect(banner).toContainText("Marina");
  await expect(banner).toContainText("03.05.2026 18:42");
  await expect(banner).toContainText("logueado en audit log");
  await expect(page.locator('[data-testid="gen-banner-trace"]')).toContainText(
    "op-2026-0847-a3f9c1",
  );
});

test("sidebar generado · 3 file-rows visibles con PDF + Excel + Drive folder", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  await expect(page.locator('[data-testid="file-row-pdf"]')).toContainText("926 KB");
  await expect(page.locator('[data-testid="file-row-xlsx"]')).toContainText("142 KB");
  await expect(page.locator('[data-testid="file-row-drive"]')).toContainText(
    "/Presupuestos/2026/05-mayo/",
  );
  await expect(page.locator('[data-testid="generated-filename"]')).toContainText(
    "Granito Negro Brasil",
  );
});

test("Descargar PDF y Excel · botones funcionales (window.open)", async ({ page, context }) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  // Las URLs son URL-encoded por el browser ("Silestone Blanco Norte" →
  // "Silestone%20Blanco%20Norte"). Decodificamos antes de comparar para no
  // acoplar el test a la representación encoded.
  const [pdfPopup] = await Promise.all([
    context.waitForEvent("page"),
    page.locator('[data-testid="action-download-pdf"]').click(),
  ]);
  expect(decodeURIComponent(pdfPopup.url())).toContain("Silestone Blanco Norte");
  expect(pdfPopup.url()).toMatch(/\.pdf$/);
  await pdfPopup.close();

  const [xlsxPopup] = await Promise.all([
    context.waitForEvent("page"),
    page.locator('[data-testid="action-download-excel"]').click(),
  ]);
  expect(xlsxPopup.url()).toMatch(/\.xlsx$/);
  await xlsxPopup.close();
});

test("Copiar link · badge ✓ aparece y desaparece", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await goPdf(page, "PRES-2026-018-GENERATED");
  const badge = page.locator('[data-testid="copied-badge"]');
  await expect(badge).not.toHaveClass(/show/);
  await page.locator('[data-testid="share-copy-link"]').click();
  await expect(badge).toHaveClass(/show/);
  // Después de ~1.8s desaparece.
  await page.waitForTimeout(2000);
  await expect(badge).not.toHaveClass(/show/);
});

test("trace block extendido · contiene generado timestamp + drive_id", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  await page.locator('[data-testid="trace-block-generated"] summary').click();
  await expect(page.locator('[data-testid="trace-generated-at"]')).toContainText(
    "03.05.2026 18:42",
  );
  await expect(page.locator('[data-testid="trace-drive-id"]')).toContainText("1aB2cD");
});

test("v2 link visible · onClick visual-only (TODO mockup 21)", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  const link = page.locator('[data-testid="v2-link"]');
  await expect(link).toBeVisible();
  await expect(link).toContainText("Crear revisión v2");
  await expect(link).toContainText("para corregir errores");
  // El click no transiciona en este PR.
  await link.click();
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
});

test("modal flow success · click Generar v1 → spinner → transición a estado C", async ({
  page,
}) => {
  // ID dedicado fuera de los canónicos (PRES-2026-018/017) para no contaminar
  // otros specs paralelos que cargan los mismos PRES IDs sin sufijo. El page
  // hace `Promise.allSettled` y degrada graceful con datos genéricos · igual
  // valida la transición de estado.
  await goPdf(page, "PRES-2026-018-MODAL-FLOW-OK");
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "A");
  await page.locator('[data-testid="generate-pdf"]').click();
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toBeVisible();
  await page.locator('[data-testid="modal-confirm"]').click();
  // Spinner durante la request mock (~800-1500ms).
  await expect(page.locator('[data-testid="modal-spinner"]')).toBeVisible();
  // Success → modal cierra + estado transiciona a C.
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
  await expect(page.locator('[data-testid="pdf-gen-banner"]')).toBeVisible();
});

test("modal flow error · sufijo -ERROR · banner rojo + Reintentar", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-ERROR");
  await page.locator('[data-testid="generate-pdf"]').click();
  await page.locator('[data-testid="modal-confirm"]').click();
  // Tras el throw mostramos error banner.
  await expect(page.locator('[data-testid="modal-error-banner"]')).toBeVisible();
  await expect(page.locator('[data-testid="modal-error-banner"]')).toContainText(
    "No se pudo generar",
  );
  // Botón ahora dice "Reintentar".
  await expect(page.locator('[data-testid="modal-confirm"]')).toContainText("Reintentar");
  // El estado sigue siendo A (no transicionó).
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "A");
});

test("Datasource isolation · PRES-017-GENERATED muestra Pereyra + traceId distinto", async ({
  page,
}) => {
  await goPdf(page, "PRES-2026-017-GENERATED");
  await expect(page.locator('[data-testid="generated-filename"]')).toContainText("Pereyra");
  await expect(page.locator('[data-testid="gen-banner-trace"]')).toContainText(
    "op-2026-0792-c4e2b8",
  );
});

test("Audit ON en estado C · AuditTray sigue visible (regresión PR #466)", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator('[data-testid="audit-tray"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
});

test("Regresión PR #470 · PRES-018 sin sufijo sigue siendo estado A editable", async ({ page }) => {
  await goPdf(page, "PRES-2026-018");
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "A");
  await expect(page.locator('[data-testid="version-chip"]')).toContainText("v1 · borrador");
  await expect(page.locator('[data-testid="pdf-sidebar"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-sidebar-generated"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="pdf-gen-banner"]')).toHaveCount(0);
});

test("UUID desconocido + GENERATED · fallback gracioso sin crash", async ({ page }) => {
  await goPdf(page, "web-deadbeef-cafe-GENERATED");
  // Página renderea (no crash) · status sent porque endsWith -GENERATED.
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible();
});
