/**
 * E2E del fix NICE-TO-HAVE 1 detectado en audit del PR #455.
 *
 * Bug original: globals.css definía `--serif`, `--sans`, `--mono`
 * como string literal (`"Fraunces", Georgia, serif`). Cuando un
 * componente legacy con `font-family: var(--serif)` se renderea,
 * el browser intenta cargar literalmente "Fraunces" — pero
 * `next/font/google` genera un nombre con suffix dinámico
 * (`__Fraunces_abc123`), entonces caía al fallback Georgia.
 *
 * Fix: globals.css redefine `--serif: var(--font-serif), Georgia, ...`
 * apuntando a las CSS vars que `next/font` define con el suffix
 * correcto. Aplicadas al div root del layout v2.
 *
 * Test: el `.qhead h1` (que usa `font-family: var(--serif)` en
 * operator-shared.css) debe rendear con Fraunces — NO con Georgia.
 */
import { expect, test } from "@playwright/test";

test("componentes legacy usan fonts cargadas por next/font", async ({ page }) => {
  await page.goto("/v2/quotes/PRES-2026-018/contexto");

  // `.qhead h1` declara `font-family: var(--serif)` en operator-shared.css
  const qheadH1 = page.locator(".qhead h1").first();
  await expect(qheadH1).toBeVisible();

  // computed font-family debe contener "Fraunces" (next/font genera suffix)
  const fontFamily = await qheadH1.evaluate((el) => window.getComputedStyle(el).fontFamily);
  expect(fontFamily.toLowerCase()).toContain("fraunces");

  // Anti-regresión: no debe arrancar con Georgia (fallback)
  expect(fontFamily.toLowerCase()).not.toMatch(/^["']?georgia["']?/);
});
