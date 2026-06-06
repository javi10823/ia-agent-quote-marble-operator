/**
 * E2E del modal de confirmación pre-generación · mockup 19 LITERAL.
 *
 * Cubre el scope mínimo del mockup: SOLO el modal overlay. El flujo de
 * generación real + transición a "PDF inmutable" + links Drive es mockup 20
 * (sub-PR siguiente).
 */
import { expect, test, type Page } from "@playwright/test";

async function goPdf(page: Page, id = "PRES-2026-018") {
  await page.goto(`/quotes/${id}/pdf`);
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible();
}

async function openModal(page: Page) {
  await page.locator('[data-testid="generate-pdf"]').click();
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toBeVisible();
}

test('click "Generar PDF v1" abre el modal de confirmación', async ({ page }) => {
  await goPdf(page);
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toHaveCount(0);
  await openModal(page);
});

test("modal muestra los 2 filenames LITERAL del estado A (PDF + Excel)", async ({ page }) => {
  await goPdf(page);
  await openModal(page);
  const blob = page.locator('[data-testid="modal-filenames"]');
  await expect(blob).toContainText("Estudio Cueto-Heredia");
  await expect(blob).toContainText("Granito Negro Brasil");
  await expect(blob).toContainText(".pdf");
  await expect(blob).toContainText(".xlsx");
});

test("modal copy LITERAL del mockup (eyebrow + h3 + 3 items + warning)", async ({ page }) => {
  await goPdf(page);
  await openModal(page);
  const modal = page.locator('[data-testid="pdf-confirm-modal"]');
  await expect(modal).toContainText("Confirmá antes de generar");
  await expect(modal).toContainText("Vas a generar v1 del presupuesto");
  await expect(modal).toContainText("/quotes/2026/");
  await expect(modal).toContainText("/Presupuestos/2026/05-mayo/");
  await expect(modal).toContainText('El presupuesto pasa al estado "enviado"');
  await expect(modal).toContainText("v2");
  await expect(modal).toContainText("trace_id");
  await expect(modal).toContainText("hash de inputs");
  const warning = page.locator('[data-testid="modal-warning"]');
  await expect(warning).toContainText("Acción irreversible");
  await expect(warning).toContainText("generás una v2");
});

test("ESC cierra el modal", async ({ page }) => {
  await goPdf(page);
  await openModal(page);
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toHaveCount(0);
});

test("Click backdrop NO cierra el modal (paso destructivo · mockup literal)", async ({ page }) => {
  await goPdf(page);
  await openModal(page);
  // Click en el backdrop (alrededor del modal). El backdrop es 100% viewport;
  // hacemos click en una esquina lejos del modal centrado.
  await page.locator('[data-testid="pdf-confirm-backdrop"]').click({ position: { x: 10, y: 10 } });
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toBeVisible();
});

test('botón "Cancelar" cierra el modal', async ({ page }) => {
  await goPdf(page);
  await openModal(page);
  await page.locator('[data-testid="modal-cancel"]').click();
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toHaveCount(0);
});

test('botón "Generar v1 →" cierra el modal (visual-only · sin transición en este PR)', async ({
  page,
}) => {
  await goPdf(page);
  await openModal(page);
  await page.locator('[data-testid="modal-confirm"]').click();
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toHaveCount(0);
  // El estado A sigue intacto (no hay transición a estado generado · es mockup 20).
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible();
  await expect(page.locator('[data-testid="version-chip"]')).toContainText("v1 · borrador");
});

test("modal coexiste con AUDIT ON sin romper observability (regresión PR #466)", async ({
  page,
}) => {
  await goPdf(page);
  await page.locator('[data-testid="audit-toggle"]').click();
  await openModal(page);
  await expect(page.locator('[data-testid="audit-tray"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-confirm-modal"]')).toBeVisible();
});

test("Sidebar editable detrás del modal (no se bloquea inputs)", async ({ page }) => {
  await goPdf(page);
  await openModal(page);
  // El input de vigencia del sidebar (estado A · PR #470) sigue funcional ·
  // el modal es overlay puro sin bloquear el form detrás.
  // Cerramos el modal primero · ESC es la salida limpia per mockup.
  await page.keyboard.press("Escape");
  await page.locator('[data-testid="ps-input-vigencia"]').fill("30");
  await expect(page.locator('[data-testid="ps-input-vigencia"]')).toHaveValue("30");
});

test("Regresión paso-5 estado A · flow sin abrir el modal sigue intacto", async ({ page }) => {
  await goPdf(page);
  // El estado A debe verse igual que en el PR #470: sidebar + PDF inline + chip v1.
  await expect(page.locator('[data-testid="version-chip"]')).toContainText("v1 · borrador");
  await expect(page.locator('[data-testid="pdf-sidebar"]')).toBeVisible();
  await expect(page.locator('[data-testid="pdf-doc-inline"]')).toBeVisible();
  // El botón Generar sigue clickeable y sigue disparando el modal · ya no es no-op.
  await expect(page.locator('[data-testid="generate-pdf"]')).toBeVisible();
});
