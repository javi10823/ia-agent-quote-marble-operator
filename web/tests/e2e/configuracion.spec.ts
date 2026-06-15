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
    // Sub-PR 22.2.a.III: ahora hay múltiples `.config-fields-grid` (uno
    // por sección abierta · mesada + operativos default-open). `.first()`
    // evita strict-mode violation.
    const grid = page.locator(".config-fields-grid").first();
    const cols = await grid.evaluate(
      (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length,
    );
    expect(cols).toBe(1);
  });
});

/* ─────────────────────────────────────────────────────────────────────
 * Sub-PR 22.2.a.III · expansion config-ui · descuentos + costing
 * ─────────────────────────────────────────────────────────────────── */

test.describe("Configuración · accordion · secciones nuevas", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("sección Descuentos arranca colapsada (collapsed default)", async ({ page }) => {
    await page.goto("/configuracion");
    const section = page.locator('[data-testid="config-section-descuentos"]');
    await expect(section).toBeVisible();
    await expect(section).toHaveAttribute("data-open", "false");
    // Fields NO visibles hasta expandir
    await expect(
      page.locator('[data-testid="config-row-discount_imported_percentage"]'),
    ).toBeHidden();
  });

  test("expandir Descuentos muestra 5 fields", async ({ page }) => {
    await page.goto("/configuracion");
    await page.locator('[data-testid="config-section-toggle-descuentos"]').click();
    for (const key of [
      "discount_imported_percentage",
      "discount_national_percentage",
      "discount_building_percentage",
      "discount_building_min_m2_threshold",
      "discount_min_m2_threshold",
    ]) {
      await expect(page.locator(`[data-testid="config-row-${key}"]`)).toBeVisible();
    }
  });

  test("validation range descuento importado (0-50) muestra error + bloquea Guardar", async ({
    page,
  }) => {
    await page.goto("/configuracion");
    await page.locator('[data-testid="config-section-toggle-descuentos"]').click();
    const input = page.locator('[data-testid="config-input-discount_imported_percentage"]');
    await input.fill("75");
    await expect(
      page.locator('[data-testid="config-error-discount_imported_percentage"]'),
    ).toBeVisible();
    await expect(page.locator('[data-testid="config-save"]')).toBeDisabled();
    // Volver al rango → desaparece error
    await input.fill("6");
    await expect(
      page.locator('[data-testid="config-error-discount_imported_percentage"]'),
    ).toBeHidden();
    await expect(page.locator('[data-testid="config-save"]')).toBeEnabled();
  });

  test("sección Costing arranca colapsada", async ({ page }) => {
    await page.goto("/configuracion");
    const section = page.locator('[data-testid="config-section-costing"]');
    await expect(section).toBeVisible();
    await expect(section).toHaveAttribute("data-open", "false");
  });

  test("validation range merma (0-10) bloquea Guardar fuera de rango", async ({ page }) => {
    await page.goto("/configuracion");
    await page.locator('[data-testid="config-section-toggle-costing"]').click();
    const input = page.locator('[data-testid="config-input-merma_small_piece_threshold_m2"]');
    await input.fill("15");
    await expect(
      page.locator('[data-testid="config-error-merma_small_piece_threshold_m2"]'),
    ).toBeVisible();
    await expect(page.locator('[data-testid="config-save"]')).toBeDisabled();
  });

  test("accordion mantiene estado al toggle independiente por sección", async ({ page }) => {
    await page.goto("/configuracion");
    const descuentos = page.locator('[data-testid="config-section-descuentos"]');
    const costing = page.locator('[data-testid="config-section-costing"]');
    await page.locator('[data-testid="config-section-toggle-descuentos"]').click();
    await expect(descuentos).toHaveAttribute("data-open", "true");
    await expect(costing).toHaveAttribute("data-open", "false");
    await page.locator('[data-testid="config-section-toggle-costing"]').click();
    await expect(descuentos).toHaveAttribute("data-open", "true");
    await expect(costing).toHaveAttribute("data-open", "true");
    // Cerrar descuentos · costing sigue abierta
    await page.locator('[data-testid="config-section-toggle-descuentos"]').click();
    await expect(descuentos).toHaveAttribute("data-open", "false");
    await expect(costing).toHaveAttribute("data-open", "true");
  });

  test("diff modal muestra solo cambios cross-section", async ({ page }) => {
    await page.goto("/configuracion");
    // Cambio en mesada (siempre visible)
    await page.locator('[data-testid="config-input-default_zocalo_height"]').fill("0.06");
    // Cambio en costing (expandir primero)
    await page.locator('[data-testid="config-section-toggle-costing"]').click();
    await page.locator('[data-testid="config-input-merma_small_piece_threshold_m2"]').fill("2");
    await page.locator('[data-testid="config-save"]').click();
    const modal = page.locator('[data-testid="config-diff-modal"]');
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("Alto de zócalo (m)");
    await expect(modal).toContainText("Umbral merma (m²)");
    // NO debe mostrar fields que no cambiaron
    await expect(modal).not.toContainText("Forma de pago default");
  });

  test("helper text del descuento explica acoplamiento arquitecto+cantidad", async ({ page }) => {
    await page.goto("/configuracion");
    await page.locator('[data-testid="config-section-toggle-descuentos"]').click();
    await expect(
      page.locator('[data-testid="config-helper-discount_imported_percentage"]'),
    ).toContainText(/arquitecto/i);
    await expect(
      page.locator('[data-testid="config-helper-discount_imported_percentage"]'),
    ).toContainText(/cantidad/i);
    await expect(
      page.locator('[data-testid="config-helper-discount_national_percentage"]'),
    ).toContainText(/arquitecto/i);
  });
});
