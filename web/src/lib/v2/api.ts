/**
 * HTTP client placeholder para v2.
 *
 * Sprint 2 scaffold: stub vacío. La implementación real (mock-first
 * según Master §21.7 decisión 4) se construye en
 * `sprint-2/paso-1-brief-upload` cuando arrancan los primeros hooks
 * que consumen endpoints reales.
 *
 * Cuando se implemente:
 *   - `useMockClient()` en Sprint 2 → fixtures locales basadas en
 *     `docs/handoff-context/catalog/*.json` y cifras canon Cueto-Heredia
 *     (Master §13).
 *   - `useApiClient()` en Sprint 3 inicial → swap a HTTP real contra
 *     los endpoints documentados en
 *     `docs/handoff-context/endpoints-spec.md`.
 *
 * NO importar este archivo desde producción todavía — los tipos no
 * están finalizados. Ver sub-PRs para spec definitiva.
 */

export const V2_API_BASE = "/api";

// Sentinel para detectar uso accidental durante el scaffold.
export const V2_SCAFFOLD_PLACEHOLDER = true as const;
