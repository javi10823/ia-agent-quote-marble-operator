/**
 * Vitest config.
 *
 * Sprint 2.5 switch-to-main: promovido desde `vitest.config.v2.ts`.
 * El legacy config fue eliminado. jsdom + include scoped a `tests/unit/**`.
 *
 * Uso:
 *   - Local:  `npm run test:unit`
 *   - Watch:  `npm run test:unit:watch`
 *   - CI:     job `unit-tests` del workflow `web-ci.yml`
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
