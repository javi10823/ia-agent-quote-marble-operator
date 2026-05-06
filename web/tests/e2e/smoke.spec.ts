/**
 * Smoke E2E del v2.
 *
 * Confirma que `/v2` rendea el placeholder con el design system
 * aplicado y que el routing v2 está vivo en el mismo Next.js que
 * el legacy. NO testea features (eso va en sub-PRs específicos).
 */
import { expect, test } from "@playwright/test";

test("/v2 carga el placeholder con design system aplicado", async ({ page }) => {
  await page.goto("/v2");
  // El h1 incluye el marker "Design system migrated" que confirma
  // que este sub-PR (sprint-2/design-system-migration) está activo.
  await expect(page.locator("h1")).toContainText("Design system migrated");
});
