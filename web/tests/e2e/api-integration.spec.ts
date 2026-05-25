/**
 * E2E · Sprint 3 api-integration.
 *
 * Modo mock (default · sin NEXT_PUBLIC_API_URL). Verifica que:
 *  1. El feature flag default sigue sirviendo mocks (dashboard carga canon).
 *  2. El mock streamChat extendido (con card events action/context_analysis/
 *     dual_read_result/zone_selector intercalados) NO rompe el streaming de
 *     texto del chat — Valentina sigue respondiendo end-to-end.
 *  3. zone_selector dispara el console.warn del hook (único event con efecto
 *     observable hoy; las cards restantes son state sin UI · Sprint 4).
 *
 * La cobertura unitaria de los 4 event types está en tests/unit/sse-events.test.ts.
 */
import { expect, test } from "@playwright/test";

test("modo mock default · dashboard carga datos canon (sin NEXT_PUBLIC_API_URL)", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator('[data-testid="quote-row-PRES-2026-018"]')).toContainText(
    "Cueto-Heredia",
  );
});

test("chat sigue streameando texto con card events intercalados en el stream", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();
  await page.locator('[data-testid="open-chat"]').click();
  // Mensaje que dispara dual_read_result + action en el mock
  await page.locator('[data-testid="chat-input"]').fill("leé el plano y las medidas");
  await page.locator('[data-testid="chat-send"]').click();
  // El texto de Valentina llega igual (las cards no rompen el stream)
  const valentina = page.locator('[data-testid="chat-msg-valentina"]').first();
  await expect(valentina).toBeVisible();
  await expect(page.locator('[data-testid="chat-panel"]')).toHaveAttribute(
    "data-panel-state",
    "open",
    { timeout: 10000 },
  );
  await expect(valentina).not.toHaveText("");
});

test("zone_selector dispara console.warn del hook (efecto observable)", async ({ page }) => {
  const warnings: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "warning") warnings.push(msg.text());
  });
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator('[data-testid="context-form"]')).toBeVisible();
  await page.locator('[data-testid="open-chat"]').click();
  await page.locator('[data-testid="chat-input"]').fill("¿en qué zona está la bacha?");
  await page.locator('[data-testid="chat-send"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).toHaveAttribute(
    "data-panel-state",
    "open",
    { timeout: 10000 },
  );
  expect(warnings.some((w) => w.includes("zone_selector"))).toBe(true);
});
