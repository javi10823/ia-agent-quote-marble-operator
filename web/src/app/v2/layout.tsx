/**
 * Layout root del v2.
 *
 * Path coexistence (Master §21.7 decisión c1): /v2/* convive con el
 * frontend legacy bajo el mismo Next.js. El root <html>/<body> vive
 * en `src/app/layout.tsx` (legacy). Acá solo wrappeamos el v2 con
 * un container limpio — sin AppShell legacy.
 *
 * Sprint 2: este layout queda como placeholder. El chrome shell real
 * (sidebar + topbar + qhead + stepper) va en sub-PR
 * `sprint-2/chrome-refactor`.
 */
export default function V2Layout({ children }: { children: React.ReactNode }) {
  return <div data-v2-root>{children}</div>;
}
