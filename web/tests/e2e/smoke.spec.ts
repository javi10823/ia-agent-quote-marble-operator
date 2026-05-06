/**
 * Smoke E2E del scaffold v2.
 *
 * Único objetivo: confirmar que `/v2` rendea el placeholder y que el
 * routing v2 está vivo en el mismo Next.js que el legacy. NO testea
 * features (eso va en sub-PRs específicos).
 */
import { expect, test } from "@playwright/test";

test("/v2 carga el placeholder del scaffold", async ({ page }) => {
  await page.goto("/v2");
  await expect(page.locator("h1")).toHaveText("Sprint 2 scaffold OK");
});
