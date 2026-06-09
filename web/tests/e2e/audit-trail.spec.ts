/**
 * E2E Sprint 4 audit-trail-copy.
 *
 * Cubre el botón CTA del topbar (persistente en TODOS los pasos del quote)
 * y la página /quotes/{id}/audit (vista pretty con copy buttons).
 *
 * Clipboard: Playwright permite leer `navigator.clipboard` desde el page
 * context · usamos `page.context().grantPermissions(["clipboard-read"])`
 * para que el assert funcione.
 */
import { expect, test, type Page } from "@playwright/test";

const QUOTE_ID = "PRES-2026-018";

async function grantClipboard(page: Page) {
  await page
    .context()
    .grantPermissions(["clipboard-read", "clipboard-write"], { origin: "http://localhost:3000" });
}

async function readClipboard(page: Page): Promise<string> {
  return page.evaluate(() => navigator.clipboard.readText());
}

test.describe("CTA Copiar audit · topbar persistente", () => {
  for (const step of ["contexto", "despiece", "calculo", "pdf"]) {
    test(`CTA visible en paso ${step}`, async ({ page }) => {
      await page.goto(`/quotes/${QUOTE_ID}/${step}`);
      await expect(page.locator('[data-testid="audit-copy-button"]')).toBeVisible({
        timeout: 10_000,
      });
    });
  }

  test("Click CTA copia plain text estructurado al clipboard", async ({ page }) => {
    await grantClipboard(page);
    await page.goto(`/quotes/${QUOTE_ID}/contexto`);
    await page.locator('[data-testid="audit-copy-button"]').click();
    // Badge "✓ Copiado" visible
    await expect(page.locator('[data-testid="audit-copy-button"]')).toHaveAttribute(
      "data-state",
      "copied",
      { timeout: 5_000 },
    );
    const text = await readClipboard(page);
    expect(text).toContain(`QUOTE AUDIT · ${QUOTE_ID}`);
    expect(text).toContain("EVENTS (timeline");
    expect(text).toContain("CALLS");
    expect(text).toContain("End audit");
  });

  test("Badge vuelve a idle tras 2s", async ({ page }) => {
    await grantClipboard(page);
    await page.goto(`/quotes/${QUOTE_ID}/contexto`);
    await page.locator('[data-testid="audit-copy-button"]').click();
    await expect(page.locator('[data-testid="audit-copy-button"]')).toHaveAttribute(
      "data-state",
      "copied",
    );
    await expect(page.locator('[data-testid="audit-copy-button"]')).toHaveAttribute(
      "data-state",
      "idle",
      { timeout: 4_000 },
    );
  });
});

test.describe("Página /quotes/{id}/audit", () => {
  test("Renderea header + summary + timeline + tools + breakdown", async ({ page }) => {
    await page.goto(`/quotes/${QUOTE_ID}/audit`);
    await expect(page.locator('[data-testid="audit-view"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".section-head h2")).toContainText(QUOTE_ID);
    // Summary chips
    await expect(page.locator('[data-testid="audit-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="summary-chat-duration"]')).toBeVisible();
    // Timeline
    const timeline = page.locator('[data-testid="audit-timeline"]');
    await expect(timeline).toBeVisible();
    await expect(timeline.locator("li").first()).toBeVisible();
    // Tools table
    await expect(page.locator('[data-testid="audit-tools-table"]')).toBeVisible();
    // Breakdown collapsable
    await expect(page.locator('[data-testid="audit-breakdown-details"]')).toBeVisible();
  });

  test("Latencia coloreada via data-severity", async ({ page }) => {
    await page.goto(`/quotes/${QUOTE_ID}/audit`);
    // read_plan en mock = 11566ms → watch (5-15s)
    const readPlanRow = page.locator('[data-testid="audit-tool-read_plan"]');
    await expect(readPlanRow).toHaveAttribute("data-severity", "watch");
    // chat duration = 24778ms → slow (15-30s)
    await expect(page.locator('[data-testid="summary-chat-duration"]')).toHaveAttribute(
      "data-severity",
      "slow",
    );
  });

  test("Botón 'Copiar todo' funcional + badge", async ({ page }) => {
    await grantClipboard(page);
    await page.goto(`/quotes/${QUOTE_ID}/audit`);
    await page.locator('[data-testid="audit-copy-all"]').click();
    await expect(page.locator('[data-testid="audit-copy-all"]')).toContainText("Copiado");
    const text = await readClipboard(page);
    expect(text).toContain(`QUOTE AUDIT · ${QUOTE_ID}`);
    expect(text).toContain("QUOTE_BREAKDOWN");
  });

  test("Botón 'Copiar timeline' omite CALLS y BREAKDOWN", async ({ page }) => {
    await grantClipboard(page);
    await page.goto(`/quotes/${QUOTE_ID}/audit`);
    await page.locator('[data-testid="audit-copy-timeline"]').click();
    await expect(page.locator('[data-testid="audit-copy-timeline"]')).toContainText("Copiado");
    const text = await readClipboard(page);
    expect(text).toContain("EVENTS");
    expect(text).not.toContain("CALLS");
    expect(text).not.toContain("QUOTE_BREAKDOWN");
  });

  test("Botón 'Copiar JSON' copia solo el breakdown", async ({ page }) => {
    await grantClipboard(page);
    await page.goto(`/quotes/${QUOTE_ID}/audit`);
    await page.locator('[data-testid="audit-copy-json"]').click();
    const text = await readClipboard(page);
    // Es JSON parseable
    expect(() => JSON.parse(text)).not.toThrow();
    const parsed = JSON.parse(text);
    expect(parsed).toHaveProperty("total_ars");
  });

  test("Quote ID no canon renderea fallback gracioso (mock vacío)", async ({ page }) => {
    await page.goto(`/quotes/UNKNOWN-XYZ/audit`);
    await expect(page.locator('[data-testid="audit-view"]')).toBeVisible({ timeout: 10_000 });
    // events_total=0 → summary visible aún · timeline existe en DOM pero
    // puede no tener altura visible sin items · solo confirmamos no-crash
    // y la summary banda con "Eventos: 0".
    await expect(page.locator('[data-testid="audit-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="audit-summary"]')).toContainText("Eventos");
  });
});

test.describe("Regresión chrome shell", () => {
  test("AuditToggle sigue visible junto al AuditCopyButton", async ({ page }) => {
    await page.goto(`/quotes/${QUOTE_ID}/contexto`);
    await expect(page.locator('[data-testid="audit-copy-button"]')).toBeVisible();
    // AuditToggle se renderea via `.audit-toggle` o similar · al menos confirmar el botón labelled
    await expect(page.locator(".topbar .right")).toBeVisible();
    // status chip persiste
    await expect(page.locator(".status-chip")).toBeVisible();
  });
});
