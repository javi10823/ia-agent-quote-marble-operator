/**
 * E2E del dashboard · Sprint 4 dashboard-redesign (sub-PR 22.1.b).
 *
 * Cubre el nuevo diseño · 5 decisiones Javi lockeadas:
 *   1. Filter chips multi-select
 *   2. Buscador responsive (mobile + desktop)
 *   3. Header 2 filas (saludo+search+CTA · meta count)
 *   4. SIN KpiCard band (cleanup en este sub-PR · regression guard)
 *   5. QuoteTable 6 columnas (mantenidas)
 *
 * Single layout responsive · NO dual render `.dashboard-desktop/.dashboard-mobile`.
 */
import { expect, test } from "@playwright/test";

test.describe("Header · 2 filas", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("muestra 'Hola Marina' h1 + eyebrow 'Presupuestos'", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="dashboard-head"]')).toBeVisible();
    await expect(page.locator("h1").first()).toContainText("Hola Marina");
    await expect(page.locator(".eyebrow").first()).toContainText("Presupuestos");
  });

  test("fila 2 con meta count + 'ordenados por última actividad ↓'", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="dashboard-meta"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-meta"]')).toContainText(
      /Tenés \d+ presupuestos? · ordenados por última actividad/,
    );
  });

  test("buscador EN el header (no en aside lateral · regresión scope)", async ({ page }) => {
    await page.goto("/");
    const search = page.locator('[data-testid="search-input"]');
    await expect(search).toBeVisible();
    // El buscador debe estar dentro de `.dashboard-head` (no en aside)
    const insideHeader = await search.evaluate((el) => !!el.closest(".dashboard-head"));
    expect(insideHeader).toBe(true);
  });

  test("CTA '+ Nuevo presupuesto' en header · navega a /quotes/new", async ({ page }) => {
    await page.goto("/");
    const cta = page.locator('[data-testid="cta-new-quote"]');
    await expect(cta).toBeVisible();
    await cta.click();
    await page.waitForURL("**/quotes/new");
    await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
  });
});

test.describe("Filtro chips · multi-select", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("renderea 4 chips de status sin pseudo 'Todos'", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="filter-chip-draft"]')).toBeVisible();
    await expect(page.locator('[data-testid="filter-chip-sent"]')).toBeVisible();
    await expect(page.locator('[data-testid="filter-chip-expired"]')).toBeVisible();
    await expect(page.locator('[data-testid="filter-chip-lost"]')).toBeVisible();
    await expect(page.locator('[data-testid="filter-chip-all"]')).toHaveCount(0);
  });

  test("click chip toggle activo + filtra tabla", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="filter-chip-draft"]').click();
    await page.waitForTimeout(700);
    await expect(page.locator('[data-testid="filter-chip-draft"]')).toHaveAttribute(
      "data-active",
      "true",
    );
    const rows = page.locator('[data-testid="quote-table"] tbody tr');
    await expect(rows.first()).toBeVisible();
    const statuses = await rows.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-status")),
    );
    expect(statuses.every((s) => s === "draft")).toBe(true);
  });

  test("MULTI-SELECT · click 2 chips · ambos activos · tabla muestra union", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="filter-chip-draft"]').click();
    await page.locator('[data-testid="filter-chip-sent"]').click();
    await page.waitForTimeout(700);
    await expect(page.locator('[data-testid="filter-chip-draft"]')).toHaveAttribute(
      "data-active",
      "true",
    );
    await expect(page.locator('[data-testid="filter-chip-sent"]')).toHaveAttribute(
      "data-active",
      "true",
    );
    const rows = page.locator('[data-testid="quote-table"] tbody tr');
    const statuses = await rows.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-status")),
    );
    // Todos draft o sent · ninguno expired/lost
    expect(statuses.every((s) => s === "draft" || s === "sent")).toBe(true);
    // Y debe haber AL MENOS 1 de cada (no es solo single-select disfrazado)
    expect(statuses.some((s) => s === "draft")).toBe(true);
    expect(statuses.some((s) => s === "sent")).toBe(true);
  });
});

test.describe("'Limpiar' condicional + search", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("'Limpiar' OCULTO al cargar (no hay filtros activos)", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(500);
    await expect(page.locator('[data-testid="clear-filters"]')).toHaveCount(0);
  });

  test("'Limpiar' APARECE tras activar un chip", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="filter-chip-draft"]').click();
    await expect(page.locator('[data-testid="clear-filters"]')).toBeVisible();
  });

  test("'Limpiar' APARECE tras tipear en search", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="search-input"]').fill("Cueto");
    await expect(page.locator('[data-testid="clear-filters"]')).toBeVisible();
  });

  test("click 'Limpiar' resetea search + chips", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="search-input"]').fill("Cueto");
    await page.locator('[data-testid="filter-chip-draft"]').click();
    await page.locator('[data-testid="clear-filters"]').click();
    await expect(page.locator('[data-testid="search-input"]')).toHaveValue("");
    await expect(page.locator('[data-testid="filter-chip-draft"]')).toHaveAttribute(
      "data-active",
      "false",
    );
    await expect(page.locator('[data-testid="clear-filters"]')).toHaveCount(0);
  });

  test("search filtra tabla + results-count se actualiza", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="search-input"]').fill("Cueto");
    await page.waitForTimeout(700);
    const rows = page.locator('[data-testid="quote-table"] tbody tr');
    await expect(rows).toHaveCount(1);
    await expect(page.locator('[data-testid="results-count"]')).toContainText("1 resultado");
  });
});

test.describe("Regression · scope eliminado (KPIs + aside)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("NO hay KpiCard band visible (cleanup sub-PR 22.1.b)", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="kpi-expire-soon"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="kpi-no-response"]')).toHaveCount(0);
    await expect(page.locator(".kpi-band")).toHaveCount(0);
  });

  test("NO hay aside.dash-filters lateral (search está en header)", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("aside.dash-filters")).toHaveCount(0);
  });

  test("NO usa toggle dual-render .dashboard-desktop/.dashboard-mobile · single layout", async ({
    page,
  }) => {
    await page.goto("/");
    // El single layout usa .dashboard-v2 · NO los dos toggles legacy
    await expect(page.locator(".dashboard-v2")).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-desktop"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="dashboard-mobile"]')).toHaveCount(0);
  });

  test("QuoteTable 6 columnas mantenidas · regression (decisión Javi #5)", async ({ page }) => {
    await page.goto("/");
    const ths = page.locator('[data-testid="quote-table"] thead th');
    await expect(ths).toHaveCount(6);
    const labels = await ths.evaluateAll((els) => els.map((el) => el.textContent?.trim()));
    expect(labels).toEqual(["Cliente", "Material", "m²", "Monto", "Estado", "Última actividad"]);
  });

  test("click row navega a /quotes/[id]/contexto · regression", async ({ page }) => {
    await page.goto("/");
    await page.locator('[data-testid="quote-link-PRES-2026-018"]').click();
    await page.waitForURL("**/quotes/PRES-2026-018/contexto");
  });

  test("cifras canon · PRES-2026-018 + PRES-2026-017 visibles · regression", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="quote-row-PRES-2026-018"]')).toContainText(
      "Cueto-Heredia",
    );
    await expect(page.locator('[data-testid="quote-row-PRES-2026-017"]')).toContainText("Pereyra");
  });
});

test.describe("SourceTag · canal web/operador + id oculto", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("el id crudo ya NO se muestra en la fila de la lista", async ({ page }) => {
    await page.goto("/");
    const row = page.locator('[data-testid="quote-row-PRES-2026-018"]');
    await expect(row).toContainText("Cueto-Heredia");
    // El id (UUID `web-…` en prod, PRES-* en mock) ya no se renderiza como texto.
    await expect(row).not.toContainText("PRES-2026-018");
  });

  test("tag 'Web' en quote source=web · tag 'Operador' en source=operator", async ({ page }) => {
    await page.goto("/");
    // PRES-2026-017 (Pereyra) tiene source: "web" en el dataset.
    await expect(
      page
        .locator('[data-testid="quote-row-PRES-2026-017"]')
        .locator('[data-testid="source-tag-web"]'),
    ).toBeVisible();
    // PRES-2026-018 (Cueto-Heredia) tiene source: "operator".
    await expect(
      page
        .locator('[data-testid="quote-row-PRES-2026-018"]')
        .locator('[data-testid="source-tag-operator"]'),
    ).toContainText("Operador");
  });
});

test.describe("Mobile · responsive single layout", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("buscador VISIBLE en mobile (regresión vs estado pre-fix · antes no había)", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="search-input"]')).toBeVisible();
  });

  test("filter chips funcionan en mobile · multi-select", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="filter-chips"]')).toBeVisible();
    await page.locator('[data-testid="filter-chip-draft"]').click();
    await page.locator('[data-testid="filter-chip-sent"]').click();
    await expect(page.locator('[data-testid="filter-chip-draft"]')).toHaveAttribute(
      "data-active",
      "true",
    );
    await expect(page.locator('[data-testid="filter-chip-sent"]')).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  test("CTA inline en header (NO FAB fixed) · decisión Javi (a)", async ({ page }) => {
    await page.goto("/");
    const cta = page.locator('[data-testid="cta-new-quote"]');
    await expect(cta).toBeVisible();
    // CTA NO debe tener position: fixed (regression del FAB legacy)
    const position = await cta.evaluate((el) => getComputedStyle(el).position);
    expect(position).not.toBe("fixed");
    // FAB legacy removido
    await expect(page.locator('[data-testid="mobile-fab"]')).toHaveCount(0);
  });

  test("mobile lista de cards · QuoteListItem visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="dashboard-list-mobile"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobile-item-PRES-2026-018"]')).toContainText(
      "Cueto-Heredia",
    );
  });
});
