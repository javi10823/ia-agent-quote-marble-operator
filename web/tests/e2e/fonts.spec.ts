/**
 * E2E del fix NICE-TO-HAVE 1 detectado en audit del PR #455 +
 * fix-up del audit del PR #456.
 *
 * Bug original (PR #455): globals.css definía `--serif`, `--sans`,
 * `--mono` como string literal. Los componentes legacy con
 * `font-family: var(--serif)` caían al fallback Georgia porque
 * next/font/google genera nombres con suffix dinámico.
 *
 * Bug del PR #456 (audit fix-up): el bridge de globals.css estaba bien,
 * PERO operator-shared.css declara su propio :root con string literals
 * que pisaba el bridge por orden de cascade. El test original solo
 * inspeccionaba el computed style string — no detectaba que el browser
 * caía al fallback. Fix: invertir orden de imports en layout v2 +
 * mejorar este test.
 *
 * Estrategia (Opción B · canvas measurement):
 *   1. document.fonts.check('16px Fraunces') confirma que el browser
 *      cargó la fuente real.
 *   2. ctx.measureText() compara el ancho de un string entre el font
 *      computed y Georgia. Si renderean igual ⇒ está cayendo al
 *      fallback. Si renderean distinto (≥ 2px) ⇒ está usando Fraunces.
 *
 * Documentación de decisión: elegida Opción B sobre A porque atrapa
 * regresiones donde document.fonts.check() pasa pero el cascade pisa
 * el bind y termina aplicando otra fuente al elemento.
 */
import { expect, test } from "@playwright/test";

test("componentes legacy renderean con Fraunces real (no fallback Georgia)", async ({ page }) => {
  await page.goto("/v2/quotes/PRES-2026-018/contexto");

  // `.qhead h1` declara `font-family: var(--serif)` en operator-shared.css
  await expect(page.locator(".qhead h1").first()).toBeVisible();

  // Esperar a que las fonts terminen de cargar (next/font + cualquier swap)
  await page.evaluate(() => document.fonts.ready);

  const result = await page.evaluate(() => {
    const el = document.querySelector(".qhead h1") as HTMLElement;
    const computed = window.getComputedStyle(el).fontFamily;
    const measure = (font: string) => {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d")!;
      ctx.font = `26px ${font}`; // 26px = tamaño real del .qhead h1
      return ctx.measureText("Cueto-Heredia — Proyecto Residencial").width;
    };
    return {
      computed,
      computedWidth: measure(computed),
      georgiaWidth: measure("Georgia"),
      // document.fonts.check requiere font name resoluble. Pasamos el
      // primer family del computed (next/font genera "__Fraunces_xxx").
      fraunces_loaded: document.fonts.check(`26px ${computed.split(",")[0]}`),
    };
  });

  // 1. La fuente del computed style efectivamente está cargada en el browser
  expect(result.fraunces_loaded).toBe(true);

  // 2. El ancho renderizado difiere de Georgia ⇒ no está cayendo al fallback
  expect(Math.abs(result.computedWidth - result.georgiaWidth)).toBeGreaterThan(2);

  // 3. Anti-regresión defensiva: el computed family contiene "fraunces"
  expect(result.computed.toLowerCase()).toContain("fraunces");
});
