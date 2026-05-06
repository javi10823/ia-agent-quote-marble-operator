/**
 * E2E del paso 2 — contexto + chat scoped.
 *
 * Cubre los 3 estados visuales (mockups 01 A / 02 B / 03 C),
 * edit mode (Tab/Enter/Esc), chat streaming, persistencia
 * borra-al-cerrar (Master §10 #1) y routing al paso 3.
 */
import { expect, test, type Page } from "@playwright/test";

const QUOTE_URL = "/v2/quotes/PRES-2026-018/contexto";

async function gotoContexto(page: Page) {
  await page.goto(QUOTE_URL);
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();
}

test("estado A — 11 campos canon visibles, banner pristine", async ({ page }) => {
  await gotoContexto(page);
  await expect(page.locator('[data-testid="context-form"]')).toHaveAttribute("data-state", "A");
  // 11 rows de contexto
  const rows = page.locator('[data-testid^="context-row-"]');
  await expect(rows).toHaveCount(11);
  // Cifras canon Cueto-Heredia
  await expect(page.locator('[data-testid="context-value-cliente"]')).toContainText(
    "Cueto-Heredia",
  );
  await expect(page.locator('[data-testid="context-value-material"]')).toContainText("Silestone");
  await expect(page.locator('[data-testid="context-value-tipologia"]')).toContainText("cocina");
  // Banner pristine menciona "Valentina extrajo"
  await expect(page.locator('[data-testid="context-banner"]')).toContainText("Valentina");
});

test("edit mode — click → input con foco, Esc cancela", async ({ page }) => {
  await gotoContexto(page);
  await page.locator('[data-testid="context-value-localidad"]').click();
  const input = page.locator('[data-testid="context-input-localidad"]');
  await expect(input).toBeVisible();
  await expect(input).toBeFocused();
  await input.fill("Palermo · CABA");
  await page.keyboard.press("Escape");
  // Vuelve al value original (Esc revierte)
  await expect(page.locator('[data-testid="context-value-localidad"]')).toContainText("Belgrano");
  // Row sigue sin clase edited
  await expect(page.locator('[data-testid="context-row-localidad"]')).toHaveAttribute(
    "data-edited",
    "false",
  );
});

test("estado A → B — editar 1 campo aplica row-edited + chip EDITADO", async ({ page }) => {
  await gotoContexto(page);
  await page.locator('[data-testid="context-value-localidad"]').click();
  await page.locator('[data-testid="context-input-localidad"]').fill("Palermo · CABA");
  await page.keyboard.press("Enter");
  // Espera al save mock (~150ms + delay)
  await expect(page.locator('[data-testid="context-row-localidad"]')).toHaveAttribute(
    "data-edited",
    "true",
    { timeout: 3000 },
  );
  await expect(page.locator('[data-testid="origin-chip-localidad"]')).toContainText("EDITADO");
  await expect(page.locator('[data-testid="edit-icon-localidad"]')).toBeVisible();
  // Form cambia a estado B
  await expect(page.locator('[data-testid="context-form"]')).toHaveAttribute("data-state", "B");
  // Banner se vuelve muted con copy distinto
  await expect(page.locator('[data-testid="context-banner"]')).toContainText("Marina");
});

test("chat panel — abrir, enviar, recibir streaming, cerrar borra mensajes", async ({ page }) => {
  await gotoContexto(page);
  // Panel cerrado al inicio
  await expect(page.locator('[data-testid="chat-panel"]')).not.toBeVisible();
  // Abrir
  await page.locator('[data-testid="open-chat"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
  await expect(page.locator('[data-testid="chat-empty"]')).toBeVisible();

  // Enviar mensaje
  await page.locator('[data-testid="chat-input"]').fill("¿Por qué pusiste anafe?");
  await page.locator('[data-testid="chat-send"]').click();

  // User message visible
  await expect(page.locator('[data-testid="chat-msg-user"]').first()).toContainText("anafe");
  // Valentina responde — esperar al menos un chunk de texto
  const valentina = page.locator('[data-testid="chat-msg-valentina"]').first();
  await expect(valentina).toBeVisible();
  // Esperar a que termine el stream (panel-state vuelve a "open")
  await expect(page.locator('[data-testid="chat-panel"]')).toHaveAttribute(
    "data-panel-state",
    "open",
    { timeout: 10000 },
  );
  await expect(valentina).toContainText(/plano|símbolo|mesada/);

  // Cerrar panel
  await page.locator('[data-testid="chat-close"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).not.toBeVisible();

  // Reabrir → mensajes vacíos (Master §10 #1)
  await page.locator('[data-testid="open-chat"]').click();
  await expect(page.locator('[data-testid="chat-empty"]')).toBeVisible();
  await expect(page.locator('[data-testid="chat-msg-user"]')).toHaveCount(0);
});

test("chat — sugerencia rápida envía pregunta", async ({ page }) => {
  await gotoContexto(page);
  await page.locator('[data-testid="open-chat"]').click();
  await page.locator('[data-testid="chat-suggestion"]').first().click();
  await expect(page.locator('[data-testid="chat-msg-user"]').first()).toContainText("anafe");
});

test("confirm — click navega a /v2/quotes/PRES-2026-018/despiece", async ({ page }) => {
  await gotoContexto(page);
  await page.locator('[data-testid="confirm-context"]').click();
  await page.waitForURL("**/quotes/PRES-2026-018/despiece");
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "despiece");
});
