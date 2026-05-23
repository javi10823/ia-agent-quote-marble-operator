/**
 * E2E del paso 3 — despiece + chat scoped.
 *
 * Cubre los estados visuales (mockups 04-A / 04-manual / 05 / 06 / 16),
 * edit mode inline (Tab/Enter/Esc), add/delete, chat scoped sobre el paso
 * y sobre una pieza (R2 = bacha), persistencia borra-al-cerrar (Master §10
 * #1), regenerate, empty state, routing al paso 4 y — crítico — que los
 * datasources indexan por quoteId (lección Sprint 2.5 fix-up #2 del PR #460).
 */
import { expect, test, type Page } from "@playwright/test";

const URL_018 = "/quotes/PRES-2026-018/despiece";
const URL_017 = "/quotes/PRES-2026-017/despiece";

/** Navega y espera a que termine la carga (5 piezas canon visibles). */
async function gotoLoaded(page: Page, url = URL_018) {
  await page.goto(url);
  await expect(page.locator('[data-testid="piece-row-R1"]')).toBeVisible({ timeout: 8000 });
}

test("estado loading — skeleton + timeline corriendo", async ({ page }) => {
  await page.goto(URL_018);
  // El skeleton + la pasada 4 corriendo se renderean durante la carga inicial
  // (DespieceView arranca en state=loading, incluso en el SSR).
  await expect(page.locator('[data-testid="despiece-loading"]')).toBeVisible();
  await expect(page.locator('[data-testid="timeline-step-4"]')).toHaveAttribute(
    "data-state",
    "running",
  );
});

test("estado A — 5 piezas canon visibles + timeline done", async ({ page }) => {
  await gotoLoaded(page);
  await expect(page.locator('[data-testid^="piece-row-"]')).toHaveCount(5);
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute("data-state", "idle");
  await expect(page.locator('[data-testid="timeline-step-4"]')).toHaveAttribute(
    "data-state",
    "done",
  );
  await expect(page.locator('[data-testid="despiece-banner"]')).toContainText("Valentina");
});

test("cifras canon — R1..R5 con dimensiones del mockup 04-A", async ({ page }) => {
  await gotoLoaded(page);
  // R1 285×62 = 1.77
  await expect(page.locator('[data-testid="piece-largo-R1-value"]')).toHaveText("285");
  await expect(page.locator('[data-testid="piece-ancho-R1-value"]')).toHaveText("62");
  await expect(page.locator('[data-testid="piece-m2unit-R1"]')).toHaveText("1.77");
  // R5 220×100 = 2.20 (isla)
  await expect(page.locator('[data-testid="piece-largo-R5-value"]')).toHaveText("220");
  await expect(page.locator('[data-testid="piece-ancho-R5-value"]')).toHaveText("100");
  await expect(page.locator('[data-testid="piece-m2unit-R5"]')).toHaveText("2.20");
  // total canon 6.81 m²
  await expect(page.locator('[data-testid="despiece-summary"]')).toContainText("5 piezas");
  await expect(page.locator('[data-testid="despiece-summary"]')).toContainText("6.81");
});

test("edit mode — click → input → Tab guarda → row púrpura + chip EDITADO", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="piece-largo-R2-value"]').click();
  const input = page.locator('[data-testid="piece-largo-R2-input"]');
  await expect(input).toBeVisible();
  await expect(input).toBeFocused();
  await input.fill("250");
  await page.keyboard.press("Tab");
  await expect(page.locator('[data-testid="piece-row-R2"]')).toHaveAttribute(
    "data-edited",
    "true",
    {
      timeout: 3000,
    },
  );
  await expect(page.locator('[data-testid="piece-edited-chip-R2"]')).toBeVisible();
  // m² recalculado: 250×62 = 1.55
  await expect(page.locator('[data-testid="piece-m2unit-R2"]')).toHaveText("1.55");
  // El form pasa a dirty
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute("data-dirty", "true");
});

test("Esc cancela edición — revierte y no guarda", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="piece-ancho-R3-value"]').click();
  await page.locator('[data-testid="piece-ancho-R3-input"]').fill("99");
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-testid="piece-ancho-R3-value"]')).toHaveText("62");
  await expect(page.locator('[data-testid="piece-row-R3"]')).toHaveAttribute(
    "data-edited",
    "false",
  );
});

test("add pieza — fila nueva con origin AGREGADO_MANUAL", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="despiece-add-row"]').click();
  await expect(page.locator('[data-testid="piece-row-R6"]')).toBeVisible({ timeout: 3000 });
  await expect(page.locator('[data-testid="piece-row-R6"]')).toHaveAttribute(
    "data-origin",
    "AGREGADO_MANUAL",
  );
  await expect(page.locator('[data-testid^="piece-row-"]')).toHaveCount(6);
});

test("delete pieza — kebab → confirmación → pieza eliminada", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="piece-menu-R5"]').click();
  await page.locator('[data-testid="piece-delete-R5"]').click();
  await page.locator('[data-testid="piece-delete-confirm-R5"]').click();
  await expect(page.locator('[data-testid="piece-row-R5"]')).toHaveCount(0, { timeout: 3000 });
  await expect(page.locator('[data-testid^="piece-row-"]')).toHaveCount(4);
});

test("chat scoped paso — abrir, enviar, streaming", async ({ page }) => {
  await gotoLoaded(page);
  await expect(page.locator('[data-testid="chat-panel"]')).not.toBeVisible();
  await page.locator('[data-testid="despiece-open-chat"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
  await expect(page.locator('[data-testid="chat-panel"]')).toHaveAttribute("data-scope", "step");

  await page.locator('[data-testid="chat-input"]').fill("¿Por qué partiste la mesada en 3?");
  await page.locator('[data-testid="chat-send"]').click();
  await expect(page.locator('[data-testid="chat-msg-user"]').first()).toContainText("mesada");
  await expect(page.locator('[data-testid="chat-panel"]')).toHaveAttribute(
    "data-panel-state",
    "open",
    { timeout: 10000 },
  );
  await expect(page.locator('[data-testid="chat-msg-valentina"]').first()).toContainText(
    /despiece|pieza|medida|corte|plano/i,
  );
});

test("chat scoped R2 — enfocado en la bacha", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="piece-menu-R2"]').click();
  await page.locator('[data-testid="piece-chat-R2"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
  await expect(page.locator('[data-testid="chat-panel"]')).toHaveAttribute("data-scope", "piece");
  await expect(page.locator('[data-testid="chat-scope-focus"]')).toContainText("R2");

  await page.locator('[data-testid="chat-input"]').fill("¿La bacha entra en 65cm de ancho?");
  await page.locator('[data-testid="chat-send"]').click();
  await expect(page.locator('[data-testid="chat-msg-valentina"]').first()).toContainText(
    /bacha|undermount|ancho/i,
    { timeout: 10000 },
  );
});

test("persistencia chat — cerrar borra mensajes (Master §10 #1)", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="despiece-open-chat"]').click();
  await page.locator('[data-testid="chat-input"]').fill("hola Valentina");
  await page.locator('[data-testid="chat-send"]').click();
  await expect(page.locator('[data-testid="chat-msg-user"]').first()).toBeVisible();
  await page.locator('[data-testid="chat-close"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).not.toBeVisible();
  // Reabrir → stream vacío
  await page.locator('[data-testid="despiece-open-chat"]').click();
  await expect(page.locator('[data-testid="chat-empty"]')).toBeVisible();
  await expect(page.locator('[data-testid="chat-msg-user"]')).toHaveCount(0);
});

test("regenerate — confirmación → regenerating → idle con 5 piezas", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="despiece-regen"]').click();
  await page.locator('[data-testid="despiece-regen-confirm"]').click();
  // El estado se setea sincrónico al confirmar (antes del await del mock).
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute(
    "data-state",
    "regenerating",
  );
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute(
    "data-state",
    "idle",
    {
      timeout: 6000,
    },
  );
  await expect(page.locator('[data-testid^="piece-row-"]')).toHaveCount(5);
});

test("empty state — status failed → empty-hero + CTA completar a mano", async ({ page }) => {
  await page.goto("/quotes/PRES-2099-000/despiece");
  await expect(page.locator('[data-testid="despiece-empty"]')).toBeVisible({ timeout: 5000 });
  const manual = page.locator('[data-testid="empty-complete-manual"]');
  await expect(manual).toBeVisible();
  await expect(manual).toContainText("Completar a mano");
  // Click → modo manual con tabla vacía editable
  await manual.click();
  await expect(page.locator('[data-testid="despiece-table"]')).toBeVisible();
  await expect(page.locator('[data-testid="despiece-status-manual"]')).toBeVisible();
});

test("routing post-confirm — navega a /calculo", async ({ page }) => {
  await gotoLoaded(page);
  await page.locator('[data-testid="confirm-despiece"]').click();
  await page.waitForURL("**/quotes/PRES-2026-018/calculo");
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "calculo");
});

test("datasources por quoteId — PRES-017 muestra piezas de Pereyra, no de 018", async ({
  page,
}) => {
  await gotoLoaded(page, URL_017);
  // Pereyra = 3 piezas con dims distintas (R1 300cm), NO las de 018 (R1 285cm).
  await expect(page.locator('[data-testid^="piece-row-"]')).toHaveCount(3);
  await expect(page.locator('[data-testid="piece-largo-R1-value"]')).toHaveText("300");
  await expect(page.locator('[data-testid="piece-largo-R1-value"]')).not.toHaveText("285");
});

test("regenerate keep-edits — preserva la edición de R1, re-genera el resto (Master §10 #10)", async ({
  page,
}) => {
  await gotoLoaded(page);
  // Estado inicial: R3 es propuesta IA sin tocar (largo 180, no editada).
  await expect(page.locator('[data-testid="piece-largo-R3-value"]')).toHaveText("180");
  await expect(page.locator('[data-testid="piece-row-R3"]')).toHaveAttribute(
    "data-edited",
    "false",
  );

  // Marina edita R1 (285 → 250 cm).
  await page.locator('[data-testid="piece-largo-R1-value"]').click();
  await page.locator('[data-testid="piece-largo-R1-input"]').fill("250");
  await page.keyboard.press("Tab");
  await expect(page.locator('[data-testid="piece-row-R1"]')).toHaveAttribute(
    "data-edited",
    "true",
    {
      timeout: 3000,
    },
  );
  // Estado dirty → aparece el split-button "Re-generar no-editadas".
  const keepBtn = page.locator('[data-testid="despiece-regen-keep"]');
  await expect(keepBtn).toBeVisible();

  // Re-generar preservando ediciones (mode keep-edits, sin confirmación).
  await keepBtn.click();
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute(
    "data-state",
    "regenerating",
  );
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute(
    "data-state",
    "idle",
    {
      timeout: 6000,
    },
  );

  // La edición de R1 SOBREVIVE (Master §10 #10: las ediciones no se pisan).
  await expect(page.locator('[data-testid="piece-largo-R1-value"]')).toHaveText("250");
  await expect(page.locator('[data-testid="piece-row-R1"]')).toHaveAttribute("data-edited", "true");
  // R3 (no editada) se re-generó desde el canon: sigue siendo IA, sin púrpura.
  await expect(page.locator('[data-testid="piece-row-R3"]')).toHaveAttribute(
    "data-edited",
    "false",
  );
  await expect(page.locator('[data-testid="piece-largo-R3-value"]')).toHaveText("180");
  // Sigue habiendo 5 piezas.
  await expect(page.locator('[data-testid^="piece-row-"]')).toHaveCount(5);
});
