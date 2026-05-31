/**
 * E2E del paso 4 · Cálculo · Sprint 3 paso-4-calculo.
 *
 * Cubre los 4 estados visuales (loading / A / B / C), toggles (audit/iva/
 * tipo cliente), checkboxes sobrante+stock, form datos-pdf editable sin
 * persist, chat scoped, datasource por params.id, fallback gracioso para
 * ID desconocido (lección Sprint 3 día 3), routing post-confirm a /pdf,
 * estado B con botón "Ver diff" disabled (decisión Javi #5).
 */
import { expect, test, type Page } from "@playwright/test";

async function goCalc(page: Page, id = "PRES-2026-018") {
  await page.goto(`/quotes/${id}/calculo`);
  await expect(page.locator('[data-testid="calculo-view"]')).toBeVisible();
}

test("estado A · banner + 5 secciones + totales bi-currency Cueto-Heredia", async ({ page }) => {
  await goCalc(page);
  await expect(page.locator('[data-testid="calculo-view"]')).toHaveAttribute("data-state", "A");
  await expect(page.locator('[data-testid="calc-banner"]')).toContainText("$660.890");
  await expect(page.locator('[data-testid="calc-banner"]')).toContainText("USD 1.538");
  for (const s of ["material", "merma", "labor", "piletas", "flete"]) {
    await expect(page.locator(`[data-testid="calc-section-${s}"]`)).toBeVisible();
  }
  await expect(page.locator('[data-testid="grand-total-ars"]')).toContainText("$660.890");
  await expect(page.locator('[data-testid="grand-total-usd"]')).toContainText("USD 1.538");
});

test("IVA toggle muestra/oculta cols Base + ×1,21 en la tabla MO", async ({ page }) => {
  await goCalc(page);
  const table = page.locator('[data-testid="labor-table"]');
  await expect(table).toContainText("Base s/IVA");
  await page.locator('[data-testid="iva-toggle"] input').click();
  await expect(table).not.toContainText("Base s/IVA");
  await page.locator('[data-testid="iva-toggle"] input').click();
  await expect(table).toContainText("Base s/IVA");
});

test("AUDIT toggle activa aud-trail + chips per-row", async ({ page }) => {
  await goCalc(page);
  await expect(page.locator('[data-testid="aud-trail"]').first()).not.toBeVisible();
  await page.locator('[data-testid="audit-toggle"]').click();
  await expect(page.locator('[data-testid="audit-toggle"]')).toHaveAttribute("data-on", "true");
  await expect(page.locator('[data-testid="aud-trail"]').first()).toBeVisible();
});

test("tipo cliente Particular/Edificio toggle (visual-only)", async ({ page }) => {
  await goCalc(page);
  await expect(page.locator('[data-testid="tipo-toggle"]')).toHaveAttribute(
    "data-tipo",
    "particular",
  );
  await page.locator('[data-testid="tipo-edificio"]').click();
  await expect(page.locator('[data-testid="tipo-toggle"]')).toHaveAttribute(
    "data-tipo",
    "edificio",
  );
});

test("sobrante + stock checkboxes en sección merma (visual-only)", async ({ page }) => {
  await goCalc(page);
  const sobrante = page.locator('[data-testid="sobrante-toggle"]');
  const stock = page.locator('[data-testid="stock-toggle"]');
  await expect(sobrante).not.toBeChecked();
  await expect(stock).toBeChecked();
  await sobrante.click();
  await expect(sobrante).toBeChecked();
});

test("datos-pdf form editable sin persist (decisión Javi #4)", async ({ page }) => {
  await goCalc(page);
  await page.locator('[data-testid="datos-pdf"] summary').click();
  const plazo = page.locator('[data-testid="dp-plazo"]');
  await expect(plazo).toHaveValue(/3 semanas/);
  await plazo.fill("5 semanas");
  await expect(plazo).toHaveValue("5 semanas");
});

test("chat scoped (estado C) · abrir/enviar/cerrar", async ({ page }) => {
  await goCalc(page);
  await page.locator('[data-testid="open-chat"]').click();
  await expect(page.locator('[data-testid="calculo-view"]')).toHaveAttribute("data-state", "C");
  await expect(page.locator('[data-testid="calc-chat-panel"]')).toBeVisible();
  await page.locator('[data-testid="chat-input"]').fill("Explicame el descuento arquitecta");
  await page.locator('[data-testid="chat-send"]').click();
  await expect(page.locator('[data-testid="chat-msg-user"]').first()).toContainText("descuento");
  await page.locator('[data-testid="chat-close"]').click();
  await expect(page.locator('[data-testid="calc-chat-panel"]')).not.toBeVisible();
});

test("datasource por params.id · PRES-017 vs PRES-018", async ({ page }) => {
  await goCalc(page, "PRES-2026-017");
  await expect(page.locator('[data-testid="calc-banner"]')).toContainText("Pereyra");
  await goCalc(page, "PRES-2026-018");
  await expect(page.locator('[data-testid="calc-banner"]')).toContainText("arquitecta");
});

test("ID desconocido (UUID) renderea CANONICAL_GENERIC sin crash", async ({ page }) => {
  await page.goto("/quotes/web-9543be47-deadbeef/calculo");
  await expect(page.locator('[data-testid="calculo-view"]')).toBeVisible();
  await expect(page.locator('[data-testid="calc-banner"]')).toContainText("pendiente");
});

test("confirm navega a /quotes/[id]/pdf", async ({ page }) => {
  await goCalc(page);
  await page.locator('[data-testid="confirm-calculo"]').click();
  await page.waitForURL("**/quotes/PRES-2026-018/pdf");
});

test("recalcular ↻ dispara loading + recarga datos", async ({ page }) => {
  await goCalc(page);
  await page.locator('[data-testid="recalculate"]').click();
  // El loading state aparece brevemente; verificamos que vuelve a estado A
  await expect(page.locator('[data-testid="calculo-view"]')).toHaveAttribute("data-state", "A", {
    timeout: 5000,
  });
  await expect(page.locator('[data-testid="calc-banner"]')).toContainText("$660.890");
});

test("estado B · patch-banner + auto-fix + diff button disabled (decisión Javi #5)", async ({
  page,
}) => {
  await page.goto("/quotes/PRES-2026-018-ERROR/calculo");
  await expect(page.locator('[data-testid="calculo-view"]')).toHaveAttribute("data-state", "B");
  await expect(page.locator('[data-testid="patch-banner"]')).toBeVisible();
  await expect(page.locator('[data-testid="patch-banner"]')).toContainText("merma fantasma");
  // confirm bloqueado en estado B
  await expect(page.locator('[data-testid="confirm-calculo"]')).toBeDisabled();
  // botón "Ver diff con v1" disabled (decisión Javi: TODO Sprint 4)
  await expect(page.locator('[data-testid="patch-diff-disabled"]')).toBeDisabled();
  // Auto-fix vuelve a estado A
  await page.locator('[data-testid="patch-fix"]').click();
  await expect(page.locator('[data-testid="calculo-view"]')).toHaveAttribute("data-state", "A", {
    timeout: 5000,
  });
  await expect(page.locator('[data-testid="confirm-calculo"]')).toBeEnabled();
});
