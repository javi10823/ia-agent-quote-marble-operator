/**
 * E2E /catalogo/import · sub-PR 22.2.b · importador Dux 3 estados.
 *
 * upload → preview (diff + counts + selección) → apply success. Modo mock:
 * mocks.importPreview/importApply son deterministas; el nombre del archivo
 * dispara el banner GLOBAL iva_warning (decisión 22.2.b).
 */
import { expect, test } from "@playwright/test";

const CSV = {
  name: "dux_materials.csv",
  mimeType: "text/csv",
  buffer: Buffer.from("codigo,descripcion,precio de venta\nSIL-001,Silestone,135\n"),
};

const CSV_IVA = {
  name: "dux_con_iva.csv",
  mimeType: "text/csv",
  buffer: Buffer.from("codigo,descripcion,precio con iva\nSIL-001,Silestone,163\n"),
};

test.describe("Import Dux · upload → preview → apply", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("upload muestra preview con counts por catálogo", async ({ page }) => {
    await page.goto("/catalogo/import");
    await expect(page.locator('[data-testid="catalogo-import-page"]')).toBeVisible();
    await page.locator('[data-testid="import-file-input"]').setInputFiles(CSV);
    await page.locator('[data-testid="import-analyze-btn"]').click();
    await expect(page.locator('[data-testid="import-preview"]')).toBeVisible();
    // 2 catálogos afectados (silestone + dekton)
    await expect(page.locator('[data-testid="catalog-tab-materials-silestone"]')).toBeVisible();
    await expect(page.locator('[data-testid="catalog-tab-materials-dekton"]')).toBeVisible();
    // counts del diff de silestone
    await expect(page.locator('[data-testid="diff-table-materials-silestone"]')).toContainText(
      "2 actualizados",
    );
    await expect(page.locator('[data-testid="diff-table-materials-silestone"]')).toContainText(
      "1 nuevos",
    );
  });

  test("deseleccionar un catálogo baja el contador del botón aplicar", async ({ page }) => {
    await page.goto("/catalogo/import");
    await page.locator('[data-testid="import-file-input"]').setInputFiles(CSV);
    await page.locator('[data-testid="import-analyze-btn"]').click();
    await expect(page.locator('[data-testid="import-apply-btn"]')).toContainText("2 catálogos");
    await page.locator('[data-testid="catalog-select-materials-dekton"]').uncheck();
    await expect(page.locator('[data-testid="import-apply-btn"]')).toContainText("1 catálogo");
  });

  test("apply → confirm → success con resultados y link al viewer", async ({ page }) => {
    await page.goto("/catalogo/import");
    await page.locator('[data-testid="import-file-input"]').setInputFiles(CSV);
    await page.locator('[data-testid="import-analyze-btn"]').click();
    await page.locator('[data-testid="import-apply-btn"]').click();
    await expect(page.locator('[data-testid="apply-confirm"]')).toBeVisible();
    await page.locator('[data-testid="apply-confirm-yes"]').click();
    await expect(page.locator('[data-testid="import-success"]')).toBeVisible();
    await expect(page.locator('[data-testid="import-result-materials-silestone"]')).toContainText(
      "actualizados",
    );
    await expect(page.locator('[data-testid="import-another"]')).toBeVisible();
  });
});

test.describe("Import Dux · iva_warning banner global", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("archivo con columna CON IVA → banner global + apply bloqueado", async ({ page }) => {
    await page.goto("/catalogo/import");
    await page.locator('[data-testid="import-file-input"]').setInputFiles(CSV_IVA);
    await page.locator('[data-testid="import-analyze-btn"]').click();
    await expect(page.locator('[data-testid="import-iva-warning"]')).toBeVisible();
    await expect(page.locator('[data-testid="import-apply-btn"]')).toBeDisabled();
  });
});

test.describe("Import Dux · validación client", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("extensión no soportada → error de validación, sin analizar", async ({ page }) => {
    await page.goto("/catalogo/import");
    await page.locator('[data-testid="import-file-input"]').setInputFiles({
      name: "datos.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4"),
    });
    await expect(page.locator('[data-testid="import-validation-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="import-analyze-btn"]')).toBeDisabled();
  });
});
