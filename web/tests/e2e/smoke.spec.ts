/**
 * Smoke E2E del v2.
 *
 * Cubre:
 *   1. /v2 placeholder del scaffold sigue activo
 *   2. Chrome shell renderea en `/v2/quotes/[id]/[step]` (sidebar +
 *      topbar + qhead + stepper + body)
 *   3. Stepper se actualiza al navegar entre rutas (paso 1 → 2 → 4)
 *
 * Features reales se testean en sub-PRs específicos.
 */
import { expect, test } from "@playwright/test";

test("/v2 carga el placeholder con design system aplicado", async ({ page }) => {
  await page.goto("/v2");
  await expect(page.locator("h1")).toContainText("Design system migrated");
});

test("chrome shell renderea en /v2/quotes/[id]/brief", async ({ page }) => {
  await page.goto("/v2/quotes/PRES-2026-018/brief");

  // Sidebar visible con brand
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator(".sidebar .brand")).toContainText("D'Angelo Operator");

  // Topbar visible con breadcrumb del quote
  await expect(page.locator(".topbar")).toBeVisible();
  await expect(page.locator(".topbar .crumbs .now")).toContainText("PRES-2026-018");
  await expect(page.locator(".topbar .crumbs .now")).toContainText("Cueto-Heredia");

  // Status chip draft
  await expect(page.locator(".status-chip.draft")).toBeVisible();

  // Qhead muestra cliente canon
  await expect(page.locator(".qhead h1")).toContainText("Cueto-Heredia");
  await expect(page.locator(".qhead .sub")).toContainText("Silestone Blanco Norte");

  // Stepper presente con 5 pasos y paso 1 activo
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "brief");
  await expect(page.locator('.stepper .step[data-step="brief"]')).toHaveClass(/now/);
});

test("stepper se actualiza al navegar entre rutas", async ({ page }) => {
  // Paso 2
  await page.goto("/v2/quotes/PRES-2026-018/contexto");
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "contexto");
  await expect(page.locator('.stepper .step[data-step="contexto"]')).toHaveClass(/now/);
  await expect(page.locator('.stepper .step[data-step="brief"]')).toHaveClass(/done/);

  // Paso 4
  await page.goto("/v2/quotes/PRES-2026-018/calculo");
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "calculo");
  await expect(page.locator('.stepper .step[data-step="calculo"]')).toHaveClass(/now/);
  await expect(page.locator('.stepper .step[data-step="despiece"]')).toHaveClass(/done/);
  await expect(page.locator('.stepper .step[data-step="pdf"]')).not.toHaveClass(/done|now/);
});
