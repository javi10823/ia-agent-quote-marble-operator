/**
 * Vitest config · Sprint 2 v2.
 *
 * Separado del `vitest.config.ts` del legacy a propósito (regla
 * "NO romper legacy"): el legacy tiene `include: ["src/**\/*.test.ts"]`
 * sin jsdom. Acá agregamos jsdom para tests de componentes React del
 * v2, y limitamos el include a `tests/unit/**` para no pisar el legacy.
 *
 * Uso:
 *   - Local:  `npm run test:unit`           (= `vitest run --config vitest.config.v2.ts`)
 *   - Watch:  `npm run test:unit:watch`
 *   - CI:     job `unit-tests` del workflow `web-v2-ci.yml`
 */
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    include: ["tests/unit/**/*.test.ts", "tests/unit/**/*.test.tsx"],
    environment: "jsdom",
    globals: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
