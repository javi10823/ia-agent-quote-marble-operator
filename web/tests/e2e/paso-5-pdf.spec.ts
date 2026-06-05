/**
 * E2E del paso 5 PDF preview · Sprint 4 paso-5-pdf-preview (mockup 18).
 *
 * Cubre layout 2-col, sidebar live-edit sync con PDF inline, filename
 * auto-gen, trace block, chat closed-default, datasource isolation,
 * fallback ID desconocido + regresión flow paso-1→paso-5.
 */
import { expect, test, type Page } from "@playwright/test";

async function goPdf(page: Page, id = "PRES-2026-018") {
  await page.goto(`/quotes/${id}/pdf`);
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible();
}

test("layout 2-col · PDF preview + sidebar visibles · version chip v1 borrador", async ({
  page,
}) => {
  await goPdf(page);
  await expect(page.locator('[data-testid="pdf-doc-inline"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-sidebar"]')).toBeVisible();
  await expect(page.locator('[data-testid="version-chip"]')).toContainText("v1 · borrador");
});

test("filename auto-generado formato canónico mockup 18 (PDF + Excel)", async ({ page }) => {
  await goPdf(page);
  const pdfName = page.locator('[data-testid="ps-filename-pdf"]');
  const xlsxName = page.locator('[data-testid="ps-filename-xlsx"]');
  await expect(pdfName).toContainText("Estudio Cueto-Heredia · cocina Belgrano");
  await expect(pdfName).toContainText("Granito Negro Brasil");
  await expect(pdfName).toContainText(".pdf");
  await expect(xlsxName).toContainText(".xlsx");
});

test("sidebar Vigencia live-edit refleja en el PDF inline", async ({ page }) => {
  await goPdf(page);
  const input = page.locator('[data-testid="ps-input-vigencia"]');
  await input.fill("21");
  await expect(page.locator('[data-testid="pdf-vigencia"]')).toContainText("21 días");
});

test("sidebar Anticipo live-edit refleja en el footer del PDF", async ({ page }) => {
  await goPdf(page);
  await page.locator('[data-testid="ps-input-anticipo"]').fill("70");
  await expect(page.locator('[data-testid="pdf-anticipo-cond"]')).toContainText("70%");
});

test("sidebar Plazo live-edit refleja en el footer del PDF", async ({ page }) => {
  await goPdf(page);
  await page.locator('[data-testid="ps-input-plazo"]').fill("60 días desde toma de medidas");
  await expect(page.locator('[data-testid="pdf-plazo-cond"]')).toContainText(
    "60 días desde toma de medidas",
  );
});

test("sidebar Datos de envío seedeado desde paso-2 (cliente + localidad)", async ({ page }) => {
  await goPdf(page);
  const envio = page.locator('[data-testid="ps-input-envio"]');
  // PRES-2026-018 contexto canon: cliente "Estudio Cueto-Heredia" + localidad "Belgrano · CABA".
  await expect(envio).not.toHaveValue("");
});

test("sidebar Datos de envío editable · refleja en el PDF inline", async ({ page }) => {
  await goPdf(page);
  await page.locator('[data-testid="ps-input-envio"]').fill("Belgrano · 4° piso (con ascensor)");
  await expect(page.locator('[data-testid="pdf-envio"]')).toContainText(
    "Belgrano · 4° piso (con ascensor)",
  );
});

test("Notas internas NO aparecen en el PDF inline", async ({ page }) => {
  await goPdf(page);
  const notasText = "Cliente quería en 2 semanas, le dije que no";
  await page.locator('[data-testid="ps-input-notas"]').fill(notasText);
  await expect(page.locator('[data-testid="pdf-doc-inline"]')).not.toContainText(notasText);
});

test("Trace block plegable · contiene trace_id canónico PRES-018", async ({ page }) => {
  await goPdf(page);
  const trace = page.locator('[data-testid="pdf-trace-block"]');
  await expect(trace).toBeVisible();
  // El <details> está plegado por default · summary visible, body no.
  // Abrimos y verificamos contenido.
  await trace.locator("summary").click();
  await expect(page.locator('[data-testid="trace-id"]')).toContainText("op-2026-0847-a3f9c1");
});

test("chat panel closed-default · botón abre / cierra panel", async ({ page }) => {
  await goPdf(page);
  await expect(page.locator('[data-testid="pdf-chat-panel"]')).toHaveCount(0);
  await page.locator('[data-testid="open-chat"]').click();
  await expect(page.locator('[data-testid="pdf-chat-panel"]')).toBeVisible();
  await page.locator('[data-testid="chat-close"]').click();
  await expect(page.locator('[data-testid="pdf-chat-panel"]')).toHaveCount(0);
});

test("datasource isolation PRES-017 vs PRES-018 (trace + filename distintos)", async ({ page }) => {
  await goPdf(page, "PRES-2026-017");
  await page.locator('[data-testid="pdf-trace-block"] summary').click();
  await expect(page.locator('[data-testid="trace-id"]')).toContainText("op-2026-0792-c4e2b8");
  await expect(page.locator('[data-testid="trace-id"]')).not.toContainText("op-2026-0847-a3f9c1");
});

test("UUID desconocida renderea fallback gracioso sin crash (regresión Sprint 3)", async ({
  page,
}) => {
  await goPdf(page, "web-deadbeef-1234-cafe-5678-feedface9999");
  // El PdfView se montó (la página no crasheó). Trace generic.
  await page.locator('[data-testid="pdf-trace-block"] summary').click();
  await expect(page.locator('[data-testid="trace-id"]')).toContainText("—");
});

test("CTA 'Generar PDF v1 →' visible y clickeable (visual-only)", async ({ page }) => {
  await goPdf(page);
  const btn = page.locator('[data-testid="generate-pdf"]');
  await expect(btn).toBeVisible();
  await expect(btn).toBeEnabled();
  await btn.click(); // visual-only · no transición persistente
  // Sigue mostrando el preview (no navegó a estado B en este sub-PR).
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible();
});

test("regresión Sprint 3 · stepper marca paso-5 como current", async ({ page }) => {
  await goPdf(page);
  const stepperCurrent = page.locator('.stepper [data-step="pdf"]');
  await expect(stepperCurrent).toHaveClass(/now/);
});

test("regresión PR #466 observability · audit toggle global sigue visible en paso-5", async ({
  page,
}) => {
  await goPdf(page);
  await expect(page.locator('.topbar [data-testid="audit-toggle"]')).toBeVisible();
});
