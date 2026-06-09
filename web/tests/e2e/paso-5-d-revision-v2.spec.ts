/**
 * E2E paso-5 estado D · "Revisión v2 (diff drawer)" · mockup 21.
 *
 * Triggers (mock):
 * - Sufijo `-REVISING` → SSR seedea estado D directo (drawer abierto · v1
 *   sigue oficial en el preview · 3-col layout).
 * - Flow desde C → click "Crear revisión v2 →" del sidebar generated → fetch
 *   on-demand del diff → estado D.
 * - "Generar v2 →" del drawer → modal v2 → confirma → estado C con v2 generada.
 */
import { expect, test, type Page } from "@playwright/test";

// Mismo cross-talk del `_generatedStore` que paso-5-c: este flujo también
// puebla el store via `triggerPdfV2Generation`. Serial para evitar drift.
test.describe.configure({ mode: "serial" });

test.afterEach(async ({ request }) => {
  await request.post("/api/_test/reset-pdf-store");
});

async function goPdf(page: Page, id: string) {
  await page.goto(`/quotes/${id}/pdf`);
  await expect(page.locator('[data-testid="pdf-view"]')).toBeVisible({ timeout: 15_000 });
}

test("PRES-018-REVISING renderea estado D · drawer + 2 chips + banner amber", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "D");
  // Ambos chips simultáneos (v1 oficial + v2 borrador).
  await expect(page.locator('[data-testid="version-chip-v1"]')).toContainText("v1 · oficial");
  await expect(page.locator('[data-testid="version-chip-v2"]')).toContainText("v2 · borrador");
  // Banner amber con icono ✎.
  const banner = page.locator('[data-testid="pdf-gen-banner"][data-variant="amber-revision"]');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Revisión v2 en curso");
  await expect(banner).toContainText("v1 trace · op-2026-0847-a3f9c1");
  // Drawer visible.
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toBeVisible();
});

test("drawer · 6 rows con 4 con cambio · diff-count literal", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await expect(page.locator('[data-testid="dd-diff-count"]')).toContainText(
    "4 con cambio · 2 sin cambio",
  );
  await expect(page.locator('[data-testid="dd-row-vigencia"]')).toHaveAttribute(
    "data-diff",
    "true",
  );
  await expect(page.locator('[data-testid="dd-row-vigencia"]')).toContainText("7 días");
  await expect(page.locator('[data-testid="dd-row-vigencia"]')).toContainText("15 días");
  await expect(page.locator('[data-testid="dd-row-anticipo"]')).toHaveAttribute(
    "data-diff",
    "false",
  );
  await expect(page.locator('[data-testid="dd-row-plazo-entrega"]')).toHaveAttribute(
    "data-diff",
    "false",
  );
  await expect(page.locator('[data-testid="dd-row-datos-de-envío"]')).toContainText(
    "ascensor de servicio",
  );
  await expect(page.locator('[data-testid="dd-row-notas-internas"]')).toContainText("anti-mancha");
  await expect(page.locator('[data-testid="dd-row-subtotal-mo"]')).toContainText("$498.450");
  await expect(page.locator('[data-testid="dd-row-subtotal-mo"]')).toContainText("+$4.260");
});

test("drawer · sección Resumen con 4 chips · trace literal de subtotal", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await expect(page.locator('[data-testid="dd-chip-count"]')).toContainText("4 cambios");
  const summary = page.locator(".dd-summary");
  await expect(summary).toContainText("Vigencia");
  await expect(summary).toContainText("15 días");
  await expect(summary).toContainText("ampliados con ascensor de servicio");
  await expect(summary).toContainText("anti-mancha");
  await expect(summary).toContainText("+$4.260");
});

test("drawer close (×) cierra drawer pero v1 sigue oficial · vuelve a estado C", async ({
  page,
}) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await page.locator('[data-testid="dd-close"]').click();
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toHaveCount(0);
  // Vuelve a estado C (v1 sigue siendo la oficial).
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
  await expect(page.locator('[data-testid="version-chip"]')).toContainText("v1 · enviado");
});

test("drawer Cancelar revisión cierra drawer", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await page.locator('[data-testid="dd-cancel"]').click();
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
});

test("Generar v2 → abre modal · ESC cierra · backdrop NO cierra", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await page.locator('[data-testid="dd-generate-v2"]').click();
  const modal = page.locator('[data-testid="pdf-confirm-v2-modal"]');
  await expect(modal).toBeVisible();
  await expect(modal).toContainText("Vas a generar");
  await expect(modal).toContainText("v2");
  // Filenames con suffix v2.
  const blob = page.locator('[data-testid="modal-v2-filenames"]');
  await expect(blob).toContainText("v2.pdf");
  await expect(blob).toContainText("v2.xlsx");
  // audit-note.purple con cambios resumidos.
  const summary = page.locator('[data-testid="modal-v2-summary"]');
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("Vigencia");
  await expect(summary).toContainText("+$4.260");
  // Click backdrop NO cierra (paso destructivo).
  await page.locator('[data-testid="pdf-confirm-v2-backdrop"]').click({ position: { x: 5, y: 5 } });
  await expect(modal).toBeVisible();
  // ESC cierra.
  await page.keyboard.press("Escape");
  await expect(modal).toHaveCount(0);
});

test("Modal v2 · Cancelar cierra modal · drawer queda abierto", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await page.locator('[data-testid="dd-generate-v2"]').click();
  await page.locator('[data-testid="modal-v2-cancel"]').click();
  await expect(page.locator('[data-testid="pdf-confirm-v2-modal"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toBeVisible();
});

test("Generar v2 → confirma → transición a estado C con filenames v2", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  await page.locator('[data-testid="dd-generate-v2"]').click();
  await page.locator('[data-testid="modal-v2-confirm"]').click();
  // Post-success: drawer + modal cerrados · estado C visible.
  await expect(page.locator('[data-testid="pdf-confirm-v2-modal"]')).toHaveCount(0, {
    timeout: 5_000,
  });
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
});

test("Flow C → click `Crear revisión v2 →` → estado D · drawer monta on-demand", async ({
  page,
}) => {
  await goPdf(page, "PRES-2026-018-GENERATED");
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "C");
  // El link "Crear revisión v2 →" del sidebar generated.
  await page.locator(".v2-link").first().click();
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toBeVisible({ timeout: 5_000 });
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "D");
});

test("PRES-2026-018 sin sufijo NO renderea drawer (regresión estado A)", async ({ page }) => {
  await goPdf(page, "PRES-2026-018");
  await expect(page.locator('[data-testid="pdf-view"]')).toHaveAttribute("data-state", "A");
  await expect(page.locator('[data-testid="pdf-diff-drawer"]')).toHaveCount(0);
});

test("PRES-018-REVISING · banner amber sigue ahí mientras drawer abierto", async ({ page }) => {
  await goPdf(page, "PRES-2026-018-REVISING");
  const banner = page.locator('[data-testid="pdf-gen-banner"][data-variant="amber-revision"]');
  await expect(banner).toBeVisible();
  // Cerrar drawer · banner verde NO aparece porque revising=false hace que el
  // banner amber se oculte y rendereemos el green (v1 sigue generada).
  await page.locator('[data-testid="dd-close"]').click();
  await expect(banner).toHaveCount(0);
  await expect(page.locator('[data-testid="pdf-gen-banner"][data-variant="green"]')).toBeVisible();
});
