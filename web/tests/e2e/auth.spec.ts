/**
 * E2E del sub-PR auth (Opción 1 · client-side gate).
 *
 * Default (CI, sin NEXT_PUBLIC_REQUIRE_AUTH): el AuthGuard es no-op →
 * los flujos siguen accesibles sin login. Estos 2 tests corren siempre.
 *
 * Modo auth (NEXT_PUBLIC_REQUIRE_AUTH==='true' + credentials): login real
 * contra Railway. Skip por default hasta tener credentials de prod
 * confirmadas (admin/admin da 401 en prod — users viven en DB).
 */
import { expect, test } from "@playwright/test";

const REQUIRE_AUTH = process.env.NEXT_PUBLIC_REQUIRE_AUTH === "true";

test("modo mock: no requiere login, acceso directo a /", async ({ page }) => {
  // Sprint 4 dashboard-redesign: KpiCard removido · validamos acceso al
  // dashboard via el head testid (agnóstico al rediseño interno).
  await page.goto("/");
  await expect(page.locator('[data-testid="dashboard-head"]')).toBeVisible();
});

test("modo mock: /quotes/[id]/contexto sin login carga el canon", async ({ page }) => {
  await page.goto("/quotes/PRES-2026-018/contexto");
  await expect(page.locator('[data-testid="context-value-cliente"]')).toContainText(
    "Cueto-Heredia",
  );
});

test.describe("modo real (requiere NEXT_PUBLIC_REQUIRE_AUTH + credentials)", () => {
  test.skip(!REQUIRE_AUTH, "NEXT_PUBLIC_REQUIRE_AUTH no configurada");

  test("login con credenciales correctas redirect a /", async ({ page }) => {
    test.skip(
      !process.env.TEST_USERNAME || !process.env.TEST_PASSWORD,
      "TEST_USERNAME/TEST_PASSWORD no configuradas",
    );
    await page.goto("/login");
    await page.fill('[name="username"]', process.env.TEST_USERNAME!);
    await page.fill('[name="password"]', process.env.TEST_PASSWORD!);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/");
  });

  test("login con credenciales incorrectas muestra error", async ({ page }) => {
    await page.goto("/login");
    await page.fill('[name="username"]', "wrong-user-xyz");
    await page.fill('[name="password"]', "wrong-password-xyz");
    await page.click('button[type="submit"]');
    await expect(page.locator('[data-testid="login-error"]')).toContainText(
      /credenciales inválidas/i,
    );
  });

  test("ruta protegida sin sesión redirect a /login", async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/login"); // asegura origin cargado antes de tocar localStorage
    await page.evaluate(() => localStorage.clear());
    await page.goto("/quotes/PRES-2026-018/contexto");
    await expect(page).toHaveURL(/\/login/);
  });
});
