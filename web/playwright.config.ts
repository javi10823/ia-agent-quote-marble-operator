/**
 * Playwright config · Sprint 2 v2.
 *
 * Scope: tests E2E de las rutas `/v2/*`. Levanta `next dev` con
 * `NEXT_PUBLIC_API_URL=http://localhost:8000` (mock-first del Sprint 2
 * NO necesita backend vivo — los smoke tests del scaffold solo
 * verifican rendering de placeholders).
 *
 * Local: `npm run test:e2e` (modo headless) o `npm run test:e2e:ui`
 * (modo interactivo).
 *
 * CI: `.github/workflows/web-v2-ci.yml` job `e2e-tests`.
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // Reutiliza el dev server del legacy (mismo Next.js — el routing v2
    // convive). En CI no hay backend real, NEXT_PUBLIC_API_URL apunta
    // a placeholder para que `next.config.mjs` no rompa.
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
    },
  },
});
