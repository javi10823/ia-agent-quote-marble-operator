/**
 * E2E del Qhead · Sprint 3 qhead-empty-title.
 *
 * MINOR #10 del audit CFC PR #465: título mostraba "— — —" cuando la
 * quote real del backend no tenía nombre populated. Fix: helper de fallback
 * con 4 niveles para el título + 4 combinaciones para el sub.
 */
import { expect, test } from "@playwright/test";

test("Qhead canon PRES-018 · título 'clientFull — client' completo", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-018/calculo");
  await expect(page.locator('[data-testid="qhead-title"]')).toBeVisible();
  await expect(page.locator('[data-testid="qhead-title"]')).toContainText("Estudio Cueto-Heredia");
  await expect(page.locator('[data-testid="qhead-title"]')).toContainText("Cueto-Heredia");
  await expect(page.locator('[data-testid="qhead-sub"]')).toContainText("PRES-2026-018");
  await expect(page.locator('[data-testid="qhead-sub"]')).toContainText("Granito Negro Brasil");
  await expect(page.locator('[data-testid="qhead-sub"]')).toContainText("m²");
});

test("Qhead canon PRES-017 · título Pereyra (distinto datasource)", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-017/calculo");
  await expect(page.locator('[data-testid="qhead-title"]')).toContainText("Pereyra");
});

test("Qhead UUID desconocida · NO renderea '— — —' puro (bug original)", async ({ page }) => {
  await page.goto("/quotes/web-9543be47-cafe-1234-9876-deadbeefcafe/calculo");
  const title = page.locator('[data-testid="qhead-title"]');
  await expect(title).toBeVisible();
  const txt = (await title.textContent()) ?? "";
  // El bug original era exactamente "— — —" (3 em-dashes consecutivos
  // separados solo por espacios). Texto legible puede contener UN em-dash
  // como separador (ej. "Estudio X — Cliente Y") pero nunca el patrón puro.
  expect(txt).not.toMatch(/^—\s*—\s*—$/);
  expect(txt.trim()).not.toBe("—");
  expect(txt.trim().length).toBeGreaterThan(0);
  // Sub debe al menos mostrar el ID (siempre garantizado por el routing).
  await expect(page.locator('[data-testid="qhead-sub"]')).toContainText("web-9543be47");
});

test("Qhead helper se aplica · título no es em-dash literal (regresion MINOR #10)", async ({
  page,
}) => {
  // Test puro del helper en runtime: aunque la data tenga em-dashes, el
  // título resultante NO debe ser solo em-dashes (caso SSR fallback).
  await page.goto("/quotes/PRES-2026-018/calculo");
  const title = page.locator('[data-testid="qhead-title"]');
  await expect(title).toBeVisible();
  // Canon: contiene texto del cliente.
  await expect(title).toContainText("Cueto-Heredia");
});
