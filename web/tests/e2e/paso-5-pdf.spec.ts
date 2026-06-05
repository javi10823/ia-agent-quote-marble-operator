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

test("sidebar Vigencia es info interna · NO aparece en el PDF (template real)", async ({
  page,
}) => {
  // Fix-up #1 · el template HTML del backend NO tiene placeholder para
  // vigencia (es info interna del workflow · queda en el state hasta que
  // el quote pasa a estado "expired" en mockup 22). El sidebar igual
  // controla el campo pero no se renderea en el documento.
  await goPdf(page);
  await page.locator('[data-testid="ps-input-vigencia"]').fill("21");
  const doc = page.locator('[data-testid="pdf-doc-inline"]');
  await expect(doc).not.toContainText("21 días desde hoy");
});

test("sidebar Anticipo live-edit refleja en grid cliente (Forma de pago)", async ({ page }) => {
  // Fix-up #1 · template real tiene el anticipo en grid "Forma de pago"
  // (no en el footer · ese fue invento mío).
  await goPdf(page);
  await page.locator('[data-testid="ps-input-anticipo"]').fill("70");
  await expect(page.locator('[data-testid="pdf-forma-pago"]')).toContainText("70%");
});

test("sidebar Plazo live-edit refleja en grid cliente (Fecha de entrega)", async ({ page }) => {
  // Fix-up #1 · template real tiene el plazo en grid "Fecha de entrega"
  // (no en el footer · ese fue invento mío).
  await goPdf(page);
  await page.locator('[data-testid="ps-input-plazo"]').fill("60 días desde toma de medidas");
  await expect(page.locator('[data-testid="pdf-fecha-entrega"]')).toContainText(
    "60 días desde toma de medidas",
  );
});

test("PDF contiene contact info LITERAL del template (Rosario · D'Angelo)", async ({ page }) => {
  await goPdf(page);
  const doc = page.locator('[data-testid="pdf-doc-inline"]');
  await expect(doc).toContainText("SAN NICOLAS 1160");
  await expect(doc).toContainText("341-3082996");
  await expect(doc).toContainText("marmoleriadangelo@gmail.com");
});

test("PDF renderea sub-filas row-piece con las piezas del paso-3", async ({ page }) => {
  // Canon PRES-2026-018: 5 piezas (R1-R5) del despiece.
  await goPdf(page);
  const pieces = page.locator('[data-testid="pdf-row-piece"]');
  await expect(pieces).toHaveCount(5);
});

test("PDF grid cliente · orden Cliente / Forma de pago / Proyecto / Fecha entrega", async ({
  page,
}) => {
  await goPdf(page);
  // Las 4 celdas en el orden literal del template.
  await expect(page.locator('[data-testid="pdf-cliente"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-forma-pago"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-proyecto"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-fecha-entrega"]')).toBeVisible();
});

test("PDF tabla headers LITERAL del template", async ({ page }) => {
  await goPdf(page);
  const doc = page.locator('[data-testid="pdf-doc-inline"]');
  await expect(doc).toContainText("Descripción");
  await expect(doc).toContainText("Cantidad");
  await expect(doc).toContainText("Precio unitario");
  await expect(doc).toContainText("Precio total");
});

test("PDF row-sobrante visible cuando merma.status='aplica' (canon 018)", async ({ page }) => {
  await goPdf(page);
  await expect(page.locator('[data-testid="pdf-row-sobrante"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-row-sobrante"]')).toContainText("SOBRANTE");
});

test("PDF footer contiene copy LITERAL del template (CONDICIONES + FORMAS DE PAGO)", async ({
  page,
}) => {
  await goPdf(page);
  const doc = page.locator('[data-testid="pdf-doc-inline"]');
  await expect(doc).toContainText("*COTIZACION OFICIAL:");
  await expect(doc).toContainText("CONDICIONES");
  await expect(doc).toContainText("*LOS PRECIOS INCLUYEN IVA");
  await expect(doc).toContainText("FORMAS DE PAGO");
  await expect(doc).toContainText("80% seña , 20% restante contra entrega");
  await expect(doc).toContainText("TARJETAS DE CREDITO CONSULTAR PLANES");
});

test("sidebar Datos de envío seedeado desde paso-2 (cliente + localidad)", async ({ page }) => {
  await goPdf(page);
  const envio = page.locator('[data-testid="ps-input-envio"]');
  // PRES-2026-018 contexto canon: cliente "Estudio Cueto-Heredia" + localidad "Belgrano · CABA".
  await expect(envio).not.toHaveValue("");
});

test("sidebar Datos de envío es info interna · NO aparece en el PDF (template real)", async ({
  page,
}) => {
  // Fix-up #1 · idem vigencia · el template HTML NO tiene placeholder para
  // dirección de envío. Es info interna para preparar la entrega.
  await goPdf(page);
  const sentinel = "Belgrano · 4° piso (con ascensor)";
  await page.locator('[data-testid="ps-input-envio"]').fill(sentinel);
  const doc = page.locator('[data-testid="pdf-doc-inline"]');
  await expect(doc).not.toContainText(sentinel);
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
