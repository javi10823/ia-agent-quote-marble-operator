/**
 * E2E error-states · Sprint 3 ÚLTIMO sub-PR (mockups 15 + 17).
 *
 * Cubre:
 * - Estado rejected (mockup 15): banner error + tabla discarded + RecoveryBlock
 *   con 3 caminos visual-only + composer feedback + trace-row + empty-chat side.
 *   Trigger: sufijo `-REJECTED` en quoteId.
 * - Estado flagged (mockup 17): SessionInfoBanner + tabla con row-chat-ref +
 *   chat scoped con FlaggedMessage + FeedbackBanner + composer prefill warn.
 *   Trigger: sufijo `-FLAGGED` en quoteId.
 * - Datasource isolation, fallback gracioso, regresión despiece normal.
 */
import { expect, test, type Page } from "@playwright/test";

async function go(page: Page, route: string) {
  await page.goto(route);
  await expect(page.locator(".topbar")).toBeVisible();
}

/* ─── Mockup 15 · rejected ─────────────────────────────────────────── */

test("rejected · banner + tabla discarded + recovery block visibles", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-REJECTED/despiece");
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute(
    "data-state",
    "rejected",
  );
  await expect(page.locator('[data-testid="rejected-banner"]')).toBeVisible();
  await expect(page.locator('[data-testid="rejected-banner"]')).toContainText("esto no me sirve");
  await expect(page.locator('[data-testid="despiece-table"]')).toHaveAttribute(
    "data-discarded",
    "true",
  );
  await expect(page.locator('[data-testid="discarded-tag"]')).toContainText("descartado");
  await expect(page.locator('[data-testid="recovery-block"]')).toBeVisible();
  await expect(page.locator('[data-testid="rpath-detalle"]')).toBeVisible();
  await expect(page.locator('[data-testid="rpath-pieza"]')).toBeVisible();
  await expect(page.locator('[data-testid="rpath-mano"]')).toBeVisible();
});

test("rejected · trace-row con traceId q_8f2a + status rejected", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-REJECTED/despiece");
  await expect(page.locator('[data-testid="trace-row"]')).toContainText("q_8f2a");
  await expect(page.locator('[data-testid="trace-status"]')).toContainText("rejected");
});

test("rejected · composer feedback captura texto y bloquea send vacío", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-REJECTED/despiece");
  const input = page.locator('[data-testid="recovery-input"]');
  const send = page.locator('[data-testid="recovery-send"]');
  await expect(send).toBeDisabled();
  await input.fill("Faltó la isla y los voladizos están al revés");
  await expect(send).toBeEnabled();
  await send.click();
  await expect(send).toContainText("Enviado");
});

test("rejected · empty-chat side panel con CTA abre chat", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-REJECTED/despiece");
  const emptyChat = page.locator('[data-testid="despiece-empty-chat"]');
  await expect(emptyChat).toBeVisible();
  await page.locator('[data-testid="empty-chat-open"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
});

/* ─── Mockup 17 · flagged ──────────────────────────────────────────── */

test("flagged · session-info banner + row-chat-ref + chat auto-open con stream preset", async ({
  page,
}) => {
  await go(page, "/quotes/PRES-2026-018-FLAGGED/despiece");
  await expect(page.locator('[data-testid="session-info-banner"]')).toContainText(
    "CHAT ABIERTO SOBRE R5",
  );
  await expect(page.locator('[data-testid="row-chat-ref-R5"]')).toContainText(
    "chat referido a esta pieza",
  );
  // Chat se abrió solo con el preset.
  await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
  await expect(page.locator('[data-testid="chat-session-info"]')).toContainText(
    "4 mensajes · primer turno hace 8 min",
  );
});

test("flagged · último mensaje Valentina marcado + btn-feedback disabled (post-click)", async ({
  page,
}) => {
  await go(page, "/quotes/PRES-2026-018-FLAGGED/despiece");
  const flagged = page.locator('[data-testid="flagged-message"]');
  await expect(flagged).toBeVisible();
  await expect(flagged).toContainText("regrueso es una técnica");
  // alreadyFlagged arranca en true (mockup post-click)
  await expect(page.locator('[data-testid="btn-feedback"]')).toBeDisabled();
  await expect(page.locator('[data-testid="feedback-banner"]')).toBeVisible();
});

test("flagged · composer pre-cargado con última pregunta + hint warn", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-FLAGGED/despiece");
  const input = page.locator('[data-testid="chat-input"]');
  await expect(input).toHaveValue(/regrueso del zócalo/);
  await expect(page.locator('[data-testid="chat-hint"]')).toContainText("pre-cargada");
});

test("flagged · click 'Reformular' resetea feedback + re-prefilllea composer", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-FLAGGED/despiece");
  await page.locator('[data-testid="feedback-reformulate"]').click();
  // Tras reformular, el banner desaparece y btn-feedback vuelve a estar enabled.
  await expect(page.locator('[data-testid="feedback-banner"]')).not.toBeVisible();
  await expect(page.locator('[data-testid="btn-feedback"]')).toBeEnabled();
  // Composer queda con el prefill listo para editar.
  await expect(page.locator('[data-testid="chat-input"]')).toHaveValue(/regrueso del zócalo/);
});

test("flagged · click 'Cerrar chat' cierra el panel", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-FLAGGED/despiece");
  await page.locator('[data-testid="feedback-close"]').click();
  await expect(page.locator('[data-testid="chat-panel"]')).not.toBeVisible();
});

/* ─── Datasource isolation + regresión ─────────────────────────────── */

test("audit-tray con trace · rejected sufijo aplicado", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018-REJECTED/despiece");
  await page.locator('[data-testid="audit-toggle"]').click();
  // Audit tray del PR #466 hereda el snapshot de PRES-018 + sufijo "· rejected".
  await expect(page.locator('[data-testid="audit-tray"]')).toContainText("q_8f2a · rejected");
});

test("regresión despiece normal sin sufijo · no muestra rejected ni flagged UI", async ({
  page,
}) => {
  await go(page, "/quotes/PRES-2026-018/despiece");
  await expect(page.locator('[data-testid="despiece-view"]')).toHaveAttribute("data-state", "idle");
  await expect(page.locator('[data-testid="rejected-banner"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="session-info-banner"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="despiece-table"]')).toHaveAttribute(
    "data-discarded",
    "false",
  );
});
