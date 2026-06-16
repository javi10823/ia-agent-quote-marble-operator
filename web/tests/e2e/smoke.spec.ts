/**
 * Smoke E2E del root.
 *
 * Cubre:
 *   1. `/` home con saludo Valentina + CTA primario "+ Nuevo presupuesto"
 *   2. Chrome shell renderea en `/quotes/[id]/[step]` (sidebar +
 *      topbar + qhead + stepper + body)
 *   3. Stepper se actualiza al navegar entre rutas (paso 1 → 2 → 4)
 *
 * Features reales se testean en sub-PRs específicos.
 */
import { expect, test } from "@playwright/test";

test("/ home muestra dashboard con saludo Marina + CTA Nuevo presupuesto", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
  await expect(page.locator("h1").first()).toContainText("Hola Marina");
  await expect(page.locator('[data-testid="cta-new-quote"]')).toBeVisible();
});

test("/quotes/[id]/brief redirige a /contexto", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-018/brief");
  await page.waitForURL(/\/quotes\/PRES-2026-018\/contexto/, { timeout: 5000 });
});

test("stepper se actualiza al navegar entre rutas", async ({ page }) => {
  // Paso 2
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "contexto");
  await expect(page.locator('.stepper .step[data-step="contexto"]')).toHaveClass(/now/);
  await expect(page.locator('.stepper .step[data-step="brief"]')).toHaveClass(/done/);

  // Paso 4
  await page.goto("/quotes/PRES-2026-018/calculo");
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "calculo");
  await expect(page.locator('.stepper .step[data-step="calculo"]')).toHaveClass(/now/);
  await expect(page.locator('.stepper .step[data-step="despiece"]')).toHaveClass(/done/);
  await expect(page.locator('.stepper .step[data-step="pdf"]')).not.toHaveClass(/done|now/);
});

/* ─── Sprint 4 fix-up sidebar-new-quote-cta ───────────────────────── */

test("Sidebar CTA '+ Nuevo presupuesto' navega a /quotes/new desde dentro de un quote", async ({
  page,
}) => {
  // Bug reportado por Javi via screenshot: dentro de /quotes/{id}/contexto
  // el CTA del sidebar no andaba (era `<div>` placeholder sin handler).
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator('[data-testid="sidebar-new-quote-cta"]')).toBeVisible();
  await page.locator('[data-testid="sidebar-new-quote-cta"]').click();
  await page.waitForURL("**/quotes/new", { timeout: 5000 });
  await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
});
