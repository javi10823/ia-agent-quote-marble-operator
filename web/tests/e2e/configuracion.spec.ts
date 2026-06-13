/**
 * E2E /configuracion · Sprint 4 sub-PR 22.2.a config-ui-page.
 *
 * Cubre 6 defaults editables + diff modal + responsive + bug fix
 * zócalo prod. Fixtures con shape REAL del config.json (lección #60).
 */
import { expect, test } from "@playwright/test";

test.describe("Configuración · render base", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("topbar 'Configuración' + form con 6 fields renderizados", async ({ page }) => {
    await page.goto("/configuracion");
    await expect(page.locator('[data-testid="configuracion-page"]')).toBeVisible();
    await expect(page.locator(".topbar .crumbs .now")).toContainText("Configuración");
    await expect(page.locator('[data-testid="config-form"]')).toBeVisible();
    for (const key of [
      "default_zocalo_height",
      "default_alzada_height",
      "default_depth",
      "delivery_zone_sku",
      "forma_pago",
      "colocacion_particulares",
    ]) {
      await expect(page.locator(`[data-testid="config-row-${key}"]`)).toBeVisible();
    }
  });

  test("zócalo arranca en 0.05 (BUG PROD FIX 7→5cm · master Regla 10)", async ({ page }) => {
    await page.goto("/configuracion");
    const input = page.locator('[data-testid="config-input-default_zocalo_height"]');
    await expect(input).toHaveValue("0.05");
    await expect(page.locator('[data-testid="config-helper-default_zocalo_height"]')).toContainText(
      "5cm",
    );
  });

  test("helper de alzada muestra '60cm'", async ({ page }) => {
    await page.goto("/configuracion");
    await expect(page.locator('[data-testid="config-helper-default_alzada_height"]')).toContainText(
      "60cm",
    );
  });
});

test.describe("Configuración · edición y diff modal", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("sin cambios · botón Guardar disabled", async ({ page }) => {
    await page.goto("/configuracion");
    await expect(page.locator('[data-testid="config-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="config-save"]')).toBeDisabled();
  });

  test("cambio en zócalo habilita Guardar y abre diff modal con antes/después", async ({
    page,
  }) => {
    await page.goto("/configuracion");
    const input = page.locator('[data-testid="config-input-default_zocalo_height"]');
    await input.fill("0.06");
    const save = page.locator('[data-testid="config-save"]');
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.locator('[data-testid="config-diff-modal"]')).toBeVisible();
    const row = page.locator('[data-testid="diff-row-Alto de zócalo (m)"]');
    await expect(row).toContainText("0.05 m");
    await expect(row).toContainText("0.06 m");
  });

  test("confirmar persiste + badge 'Guardado' visible + modal cierra", async ({ page }) => {
    await page.goto("/configuracion");
    await page.locator('[data-testid="config-input-forma_pago"]').fill("Contado / Transferencia");
    await page.locator('[data-testid="config-save"]').click();
    await page.locator('[data-testid="config-modal-confirm"]').click();
    await expect(page.locator('[data-testid="config-diff-modal"]')).toBeHidden();
    const badge = page.locator('[data-testid="config-saved-badge"]');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText("Guardado");
    await expect(badge).toContainText("puede tardar unos segundos en producción");
  });

  test("Descartar restaura valores originales", async ({ page }) => {
    await page.goto("/configuracion");
    const zocalo = page.locator('[data-testid="config-input-default_zocalo_height"]');
    await zocalo.fill("0.08");
    await page.locator('[data-testid="config-reset"]').click();
    await expect(zocalo).toHaveValue("0.05");
    await expect(page.locator('[data-testid="config-save"]')).toBeDisabled();
  });
});

test.describe("Configuración · responsive mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("grid 1 col en mobile + form visible", async ({ page }) => {
    await page.goto("/configuracion");
    await expect(page.locator('[data-testid="config-form"]')).toBeVisible();
    const grid = page.locator(".config-fields-grid");
    const cols = await grid.evaluate(
      (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length,
    );
    expect(cols).toBe(1);
  });
});
