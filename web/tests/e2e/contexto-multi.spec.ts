/**
 * E2E del fix BLOCKER detectado por Visual Check del PR #460:
 * `getContextForQuote` indexa correctamente por quoteId. Antes devolvía
 * siempre CANONICAL_CONTEXT (Cueto-Heredia) para cualquier ID.
 *
 * Estos tests son el guardrail anti-regresión.
 */
import { expect, test } from "@playwright/test";

test("PRES-2026-017 carga datos Pereyra, NO Cueto-Heredia", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-017/contexto");
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();
  await expect(page.locator('[data-testid="context-value-cliente"]')).toContainText("Pereyra");
  await expect(page.locator('[data-testid="context-value-cliente"]')).not.toContainText(
    "Cueto-Heredia",
  );
  await expect(page.locator('[data-testid="context-value-material"]')).toContainText("Silestone");
});

test("PRES-2026-018 sigue cargando Cueto-Heredia (regression check)", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();
  await expect(page.locator('[data-testid="context-value-cliente"]')).toContainText(
    "Cueto-Heredia",
  );
  await expect(page.locator('[data-testid="context-value-cliente"]')).not.toContainText("Pereyra");
});
