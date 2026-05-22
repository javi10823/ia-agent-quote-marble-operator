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

test("PRES-2026-017: topbar + h1 + banner reflejan Pereyra (fix-up #2)", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-017/contexto");
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();

  // Topbar breadcrumb
  const crumb = page.locator(".topbar .crumbs .now");
  await expect(crumb).toContainText("PRES-2026-017");
  await expect(crumb).toContainText("Pereyra");
  await expect(crumb).not.toContainText("PRES-2026-018");
  await expect(crumb).not.toContainText("Cueto-Heredia");

  // Qhead h1 + subheader
  await expect(page.locator(".qhead h1")).toContainText("Pereyra");
  await expect(page.locator(".qhead h1")).not.toContainText("Cueto-Heredia");
  await expect(page.locator(".qhead .sub")).toContainText("PRES-2026-017");
  await expect(page.locator(".qhead .sub")).toContainText("Silestone");

  // Banner Valentina pristine — espera al fetch async del summary
  const banner = page.locator('[data-testid="context-banner"]');
  await expect(banner).toContainText("Pereyra", { timeout: 3000 });
  await expect(banner).not.toContainText("Cueto-Heredia");
});

test("PRES-2026-018: topbar + h1 + banner reflejan Cueto-Heredia (regression)", async ({
  page,
}) => {
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();
  const crumb = page.locator(".topbar .crumbs .now");
  await expect(crumb).toContainText("PRES-2026-018");
  await expect(crumb).toContainText("Cueto-Heredia");
  await expect(page.locator(".qhead h1")).toContainText("Cueto-Heredia");
  await expect(page.locator('[data-testid="context-banner"]')).toContainText("Cueto-Heredia", {
    timeout: 3000,
  });
});
