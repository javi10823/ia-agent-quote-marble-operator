/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "node:path";

/**
 * PR #357 — Vitest setup mínimo para tests de lógica pura.
 *
 * Scope intencionalmente chico: sin jsdom, sin React Testing Library.
 * Los tests apuntan a helpers puros (ej: `applyCandidate`) que no
 * necesitan DOM. Si en el futuro se quieren tests de componente,
 * agregar `test.environment: "jsdom"` + `@testing-library/react`.
 */
export default defineConfig({
  test: {
    // Por default vitest usa `node` environment → sin DOM, más rápido.
    include: ["src/**/*.test.ts"],
  },
  resolve: {
    alias: {
      // Mismo alias que tsconfig.json para que `@/lib/...` funcione
      // dentro de los tests.
      "@": path.resolve(__dirname, "src"),
    },
  },
});
