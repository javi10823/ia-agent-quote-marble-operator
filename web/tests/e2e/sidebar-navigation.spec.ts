/**
 * E2E Sprint 4 sidebar-and-navigation-fix.
 *
 * Cierra 4 bugs heredados Sprint 2/2.5:
 * 1. Sidebar NO aparecía en `/` (dashboard sin chrome)
 * 2. Items del Sidebar eran `<div>` sin onClick · clicks no navegaban
 * 3. Rutas `/catalogo` `/configuracion` `/clientes` daban 404
 * 4. Crumb en `/quotes/new` apuntaba a `/v2` legacy (también 404)
 *
 * Anti-regresión: lockea comportamiento post-fix · buscador del dashboard
 * + CTA "+ Nuevo presupuesto" siguen intactos · active state dinámico.
 */
import { expect, test } from "@playwright/test";

test.describe("Sidebar presente en chrome global", () => {
  test("sidebar visible en / (dashboard) · regresión Sprint 2.5", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".sidebar")).toBeVisible();
    await expect(page.locator(".brand")).toContainText("D'Angelo Operator");
  });

  test("sidebar visible en /quotes/[id]/contexto · regresión Sprint 2", async ({ page }) => {
    await page.goto("/quotes/PRES-2026-018/contexto");
    await expect(page.locator(".sidebar")).toBeVisible();
  });

  test("sidebar visible en /quotes/new · regresión", async ({ page }) => {
    await page.goto("/quotes/new");
    await expect(page.locator(".sidebar")).toBeVisible();
  });
});

test.describe("Items del Sidebar navegan (Next Link nativo)", () => {
  test("click Catálogo navega a /catalogo · renderea lista real", async ({ page }) => {
    // Sub-PR 22.2.b catalogo-and-dux-importer-ui reemplazó el placeholder
    // por la lista real (`catalogo-page`). Antes: catalogo-placeholder.
    await page.goto("/");
    await page.locator('[data-testid="sidebar-nav-catalogo"]').click();
    await page.waitForURL("**/catalogo");
    await expect(page.locator('[data-testid="catalogo-page"]')).toBeVisible();
    await expect(page.locator(".crumbs .now")).toContainText("Catálogo");
  });

  test("click Configuración navega a /configuracion · renderea form real", async ({ page }) => {
    // Sub-PR 22.2.a config-ui-page reemplazó el placeholder por el form
    // real (`configuracion-page` + `config-form`). Antes: configuracion-placeholder.
    await page.goto("/");
    await page.locator('[data-testid="sidebar-nav-configuracion"]').click();
    await page.waitForURL("**/configuracion");
    await expect(page.locator('[data-testid="configuracion-page"]')).toBeVisible();
  });

  test("click Clientes navega a /clientes · renderea placeholder", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="sidebar-nav-clientes"]').click();
    await page.waitForURL("**/clientes");
    await expect(page.locator('[data-testid="clientes-placeholder"]')).toBeVisible();
  });

  test("click '+ Nuevo presupuesto' del sidebar navega a /quotes/new", async ({ page }) => {
    await page.goto("/catalogo");
    await page.locator('[data-testid="sidebar-new-quote-cta"]').click();
    await page.waitForURL("**/quotes/new");
    await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
  });
});

test.describe("Anti-regresión chrome global", () => {
  test("dashboard header 'Hola Marina' + search input intactos post-chrome", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1").first()).toContainText("Hola Marina");
    // Search input es feature contextual del dashboard · NO se mueve al chrome global
    await expect(page.locator('[data-testid="search-input"]')).toBeVisible();
  });

  test("active state .on matchea pathname (dinámico, no hardcoded)", async ({ page }) => {
    await page.goto("/catalogo");
    // Catálogo .on, Presupuestos no
    await expect(page.locator('[data-testid="sidebar-nav-catalogo"]')).toHaveClass(/\bon\b/);
    await expect(page.locator('[data-testid="sidebar-nav-home"]')).not.toHaveClass(/\bon\b/);
    // aria-current='page' en el activo (a11y)
    await expect(page.locator('[data-testid="sidebar-nav-catalogo"]')).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("Presupuestos activo en / Y dentro de /quotes/[id]/* (contexto operador)", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="sidebar-nav-home"]')).toHaveClass(/\bon\b/);
    await page.goto("/quotes/PRES-2026-018/contexto");
    await expect(page.locator('[data-testid="sidebar-nav-home"]')).toHaveClass(/\bon\b/);
  });

  test("crumb /quotes/new linkea a / (no /v2 legacy 404)", async ({ page }) => {
    await page.goto("/quotes/new");
    const crumbLink = page.locator(".crumbs a", { hasText: "Presupuestos" });
    await expect(crumbLink).toHaveAttribute("href", "/");
    await crumbLink.click();
    await page.waitForURL((url) => url.pathname === "/");
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
  });
});
