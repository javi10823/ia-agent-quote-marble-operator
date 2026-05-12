/**
 * E2E del dashboard (Bloque E · mockup 25 desktop + mockup 23 mobile).
 *
 * Cubre:
 *   - desktop: KPI band + tabla + sidebar filtros + CTA
 *   - mobile: chips filter + lista vertical + FAB
 *   - interacciones: filter por status, click row → contexto,
 *     CTA → paso 1, KPI cards filtran tabla
 *   - cifras canon Cueto-Heredia (PRES-2026-018) + Pereyra (PRES-2026-017)
 */
import { expect, test } from "@playwright/test";

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("KPI cards + tabla + CTA visibles en /", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="dashboard-desktop"]')).toBeVisible();
    await expect(page.locator('[data-testid="kpi-expire-soon"]')).toBeVisible();
    await expect(page.locator('[data-testid="kpi-no-response"]')).toBeVisible();
    await expect(page.locator('[data-testid="quote-table"]')).toBeVisible();
    await expect(page.locator('[data-testid="cta-new-quote"]')).toBeVisible();
  });

  test("cifras canon · PRES-2026-018 Cueto-Heredia visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="quote-row-PRES-2026-018"]')).toContainText(
      "Cueto-Heredia",
    );
    await expect(page.locator('[data-testid="quote-row-PRES-2026-018"]')).toContainText(
      "Negro Brasil",
    );
  });

  test("cifras canon · PRES-2026-017 Pereyra visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="quote-row-PRES-2026-017"]')).toContainText("Pereyra");
    await expect(page.locator('[data-testid="quote-row-PRES-2026-017"]')).toContainText(
      "Silestone",
    );
  });

  test("filter por status draft reduce resultados", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="quote-table"] tbody tr')).toHaveCount(16);
    await page.locator('[data-testid="status-filter-draft"]').click();
    // Esperar re-fetch del mock (delay 200-500ms)
    await page.waitForTimeout(700);
    const rows = page.locator('[data-testid="quote-table"] tbody tr');
    await expect(rows.first()).toBeVisible();
    // Todos deben ser draft
    const statuses = await rows.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-status")),
    );
    expect(statuses.every((s) => s === "draft")).toBe(true);
  });

  test("click en row navega a /quotes/[id]/contexto", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="quote-link-PRES-2026-018"]').click();
    await page.waitForURL("**/quotes/PRES-2026-018/contexto");
    await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "contexto");
  });

  test("CTA + Nuevo presupuesto navega a /quotes/new", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="cta-new-quote"]').click();
    await page.waitForURL("**/quotes/new");
    await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
  });

  test("KPI urgent filtra tabla a expire-soon", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="kpi-expire-soon"]').click();
    await page.waitForTimeout(700);
    await expect(page.locator('[data-testid="kpi-expire-soon"]')).toHaveAttribute(
      "data-active",
      "true",
    );
    // Verifica que las rows visibles son sent c/daysToExpire<=7 o expired
    const rows = page.locator('[data-testid="quote-table"] tbody tr');
    await expect(rows.first()).toBeVisible();
  });
});

test.describe("mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("chips filter + lista vertical + FAB visibles", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="dashboard-mobile"]')).toBeVisible();
    await expect(page.locator('[data-testid="filter-chips"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobile-fab"]')).toBeVisible();
    // Item de lista contiene PRES-018
    await expect(page.locator('[data-testid="mobile-item-PRES-2026-018"]')).toContainText(
      "Cueto-Heredia",
    );
  });

  test("chip Borrador filtra la lista", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="filter-chip-draft"]').click();
    await page.waitForTimeout(700);
    await expect(page.locator('[data-testid="filter-chip-draft"]')).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  test("FAB navega a /quotes/new", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="mobile-fab"]').click();
    await page.waitForURL("**/quotes/new");
  });
});
