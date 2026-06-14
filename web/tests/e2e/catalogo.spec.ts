/**
 * E2E /catalogo · sub-PR 22.2.b catalogo-and-dux-importer-ui.
 *
 * Lista (search + sort + navegación) + viewer (JSON read-only + backups +
 * restore) + responsive. Modo mock (sin NEXT_PUBLIC_API_URL · mocks.ts).
 */
import { expect, test } from "@playwright/test";

test.describe("Catálogo · lista", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("renderea los 14 catálogos + topbar + CTA import", async ({ page }) => {
    await page.goto("/catalogo");
    await expect(page.locator('[data-testid="catalogo-page"]')).toBeVisible();
    await expect(page.locator(".topbar .crumbs .now")).toContainText("Catálogo");
    await expect(page.locator('[data-testid="catalog-import-cta"]')).toBeVisible();
    const rows = page.locator('[data-testid="catalog-rows"] > li');
    await expect(rows).toHaveCount(14);
  });

  test("search filtra por nombre", async ({ page }) => {
    await page.goto("/catalogo");
    await page.locator('[data-testid="catalog-search"]').fill("silestone");
    const rows = page.locator('[data-testid="catalog-rows"] > li');
    await expect(rows).toHaveCount(1);
    await expect(page.locator('[data-testid="catalog-row-materials-silestone"]')).toBeVisible();
  });

  test("click en fila navega al viewer", async ({ page }) => {
    await page.goto("/catalogo");
    await page.locator('[data-testid="catalog-row-materials-silestone"]').click();
    await page.waitForURL("**/catalogo/materials-silestone");
    await expect(page.locator('[data-testid="catalogo-viewer-page"]')).toBeVisible();
  });
});

test.describe("Catálogo · viewer + backups", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("muestra JSON read-only + lista de backups", async ({ page }) => {
    await page.goto("/catalogo/materials-silestone");
    await expect(page.locator('[data-testid="catalog-json"]')).toBeVisible();
    await expect(page.locator('[data-testid="catalog-json"]')).toContainText("SKU001");
    await expect(page.locator('[data-testid="backup-list"]')).toBeVisible();
    await expect(page.locator('[data-testid="backup-row-101"]')).toBeVisible();
  });

  test("restore pide confirmación y muestra toast de éxito", async ({ page }) => {
    await page.goto("/catalogo/materials-silestone");
    await page.locator('[data-testid="backup-restore-101"]').click();
    await expect(page.locator('[data-testid="restore-confirm"]')).toBeVisible();
    await page.locator('[data-testid="restore-confirm-yes"]').click();
    const toast = page.locator('[data-testid="catalog-toast"]');
    await expect(toast).toBeVisible();
    await expect(toast).toContainText("restaurado");
  });
});

test.describe("Catálogo · responsive mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("viewer grid colapsa a 1 columna en mobile", async ({ page }) => {
    await page.goto("/catalogo/materials-silestone");
    await expect(page.locator('[data-testid="catalog-json"]')).toBeVisible();
    const grid = page.locator(".catalog-viewer-grid");
    const cols = await grid.evaluate(
      (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length,
    );
    expect(cols).toBe(1);
  });
});
