/**
 * E2E del observability mode global · Sprint 3 observability-per-row.
 *
 * Cubre mockup 13 LITERAL:
 * - Toggle AUDIT en TopBar global (refactor decisión Javi C).
 * - AuditTray banner top: 3 columnas con metadata IA + traza + eventos.
 * - body[data-audit="on"] cuando toggle ON, "off" cuando OFF.
 * - useAuditMode persiste en localStorage entre nav.
 * - IaAuditBanner visible en paso-3/paso-4 cuando audit on.
 * - ChatAuditNote visible dentro del chat scoped cuando audit on.
 * - Tree view del trace_id disabled con TODO Sprint 4 (decisión Javi G).
 * - Datasource isolation PRES-018 vs PRES-017.
 * - Fallback gracioso para ID desconocido (UUID/web-XXX).
 * - Audit per-row del paso-4 (aud-trail) sigue funcionando con el nuevo
 *   toggle global (regression check post-refactor).
 */
import { expect, test, type Page } from "@playwright/test";

async function go(page: Page, route: string) {
  await page.goto(route);
  await expect(page.locator(".topbar")).toBeVisible();
}

test("toggle AUDIT global en TopBar sincroniza body[data-audit]", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await expect(page.locator('[data-testid="audit-toggle"]')).toBeVisible();
  await expect(page.locator('[data-testid="audit-toggle"]')).toHaveAttribute("data-on", "false");
  // Fix-up #1 H3: en OFF el atributo data-audit NO existe (delete en useAuditMode).
  // Functionally equivalente para CSS [data-audit="on"] pero coherente con spec.
  await expect(page.locator("body")).not.toHaveAttribute("data-audit", /.+/);
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator('[data-testid="audit-toggle"]')).toHaveAttribute("data-on", "true");
  await expect(page.locator("body")).toHaveAttribute("data-audit", "on");
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator("body")).not.toHaveAttribute("data-audit", /.+/);
});

test("AuditTray banner muestra 3 columnas con datos canon PRES-018", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await expect(page.locator('[data-testid="audit-tray"]')).not.toBeVisible();
  await page.locator('[data-testid="audit-toggle"]').click();
  const tray = page.locator('[data-testid="audit-tray"]');
  await expect(tray).toBeVisible();
  await expect(tray).toContainText("Última llamada IA");
  await expect(tray).toContainText("claude-sonnet-4");
  await expect(tray).toContainText("in 1.842");
  await expect(tray).toContainText("4.2s");
  await expect(tray).toContainText("Trazabilidad");
  await expect(tray).toContainText("q_8f2a");
  await expect(tray).toContainText("despiece.v3.2");
  await expect(tray).toContainText("84%");
  await expect(tray).toContainText("Eventos en sesión");
  await expect(tray).toContainText("contexto.confirm");
  await expect(tray).toContainText("despiece.draft.partial");
});

test("AuditTray datasource correcto PRES-017 vs PRES-018", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-017/calculo");
  await page.locator('[data-testid="audit-toggle"]').click();
  const tray = page.locator('[data-testid="audit-tray"]');
  await expect(tray).toContainText("q_4c1e");
  await expect(tray).toContainText("calculo.v2.4");
  await expect(tray).not.toContainText("q_8f2a");
});

test("AuditTray + banner + note SE OCULTAN cuando snapshot es empty (quote desconocida)", async ({
  page,
}) => {
  // Fix-up #2: para quotes con fallback genérico (isEmpty=true), tray/banner/note
  // NO deben renderearse · solo el chip TopBar queda visible (UX limpia).
  await go(page, "/quotes/web-deadbeef-cafe/contexto");
  await page.locator('[data-testid="audit-toggle"]').click();
  // El chip del TopBar SÍ sigue visible y ON.
  await expect(page.locator("body")).toHaveAttribute("data-audit", "on");
  await expect(page.locator('[data-testid="audit-toggle"]')).toHaveAttribute("data-on", "true");
  // Pero tray + banner explicativo NO renderean.
  await expect(page.locator('[data-testid="audit-tray"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="ia-audit-banner"]')).toHaveCount(0);
});

test("AuditTray SÍ renderea cuando snapshot tiene datos canon (no empty)", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await page.locator('[data-testid="audit-toggle"]').click();
  // Esperar a que el snapshot canónico cargue antes de asertar.
  await expect(page.locator('[data-testid="audit-tray"]')).toBeVisible();
  await expect(page.locator('[data-testid="ia-audit-banner"]')).toBeVisible();
});

test("tree view del trace_id está disabled con TODO Sprint 4", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await page.locator('[data-testid="audit-toggle"]').click();
  const treeLink = page.locator('[data-testid="trace-tree-disabled"]');
  await expect(treeLink).toBeVisible();
  await expect(treeLink).toHaveAttribute("aria-disabled", "true");
  await expect(treeLink).toHaveAttribute("title", /Sprint 4/);
});

test("IaAuditBanner visible en paso-3 despiece cuando audit on", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/despiece");
  await expect(page.locator('[data-testid="ia-audit-banner"]')).not.toBeVisible();
  await page.locator('[data-testid="audit-toggle"]').click();
  const banner = page.locator('[data-testid="ia-audit-banner"]');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Audit ON");
  await expect(banner).toContainText("trace_id");
});

test("IaAuditBanner visible en paso-4 calculo cuando audit on", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator('[data-testid="ia-audit-banner"]')).toBeVisible();
});

test("ChatAuditNote visible dentro del chat scoped del paso-4 cuando audit on", async ({
  page,
}) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await page.locator('[data-testid="audit-toggle"]').click();
  await page.locator('[data-testid="open-chat"]').click();
  const note = page.locator('[data-testid="chat-audit-note"]');
  await expect(note).toBeVisible();
  await expect(note).toContainText("trace_id");
});

test("audit mode persiste en localStorage al navegar entre rutas", async ({ page }) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator("body")).toHaveAttribute("data-audit", "on");
  await go(page, "/quotes/PRES-2026-018/despiece");
  await expect(page.locator("body")).toHaveAttribute("data-audit", "on");
  await expect(page.locator('[data-testid="audit-tray"]')).toBeVisible();
});

test("paso-4 audit per-row aud-trail sigue funcionando con toggle global (regression)", async ({
  page,
}) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  await expect(page.locator('[data-testid="aud-trail"]').first()).not.toBeVisible();
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator('[data-testid="aud-trail"]').first()).toBeVisible();
});

test("CalcToolbar ya no tiene AUDIT toggle local (solo Tipo + IVA + Recalcular)", async ({
  page,
}) => {
  await go(page, "/quotes/PRES-2026-018/calculo");
  // El AUDIT toggle ahora está en TopBar (1 sola instancia · refactor decisión Javi C).
  await expect(page.locator('[data-testid="audit-toggle"]')).toHaveCount(1);
  await expect(page.locator('.topbar [data-testid="audit-toggle"]')).toBeVisible();
});
