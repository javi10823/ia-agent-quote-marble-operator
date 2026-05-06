# Frontend v2 · Sprint 2-5

> Refactor del operator panel D'Angelo según los 30 mockups del Sprint 1.5.
> Path coexistence con el legacy (Master §21.7 decisión c1) — `/quotes` legacy y `/v2/quotes` conviven en el mismo Next.js.

---

## Estructura

```
web/
├── src/
│   ├── app/v2/                    ← rutas Sprint 2 (este scaffold + sub-PRs)
│   │   ├── layout.tsx             ← layout placeholder (chrome shell pendiente)
│   │   ├── page.tsx               ← /v2 placeholder
│   │   └── quotes/page.tsx        ← /v2/quotes placeholder
│   ├── components/v2/
│   │   └── chrome/                ← Sidebar/Topbar/Stepper (sub-PR chrome-refactor)
│   └── lib/v2/
│       ├── api.ts                 ← HTTP client placeholder
│       ├── types.ts               ← types compartidos del v2
│       └── mocks/                 ← fixtures (sub-PR paso-1-brief-upload)
└── tests/
    ├── e2e/                       ← Playwright
    │   └── smoke.spec.ts
    └── unit/                      ← Vitest
        └── smoke.test.ts
```

## Convenciones

Vienen de `docs/handoff-design/CLAUDE.md`:

- TypeScript strict (sin `any` salvo en boundaries con APIs externas)
- Naming: PascalCase componentes, kebab-case filenames
- Dark-only, sin toggle light
- Copy en español rioplatense ("vos", "tenés", "podés")
- IA = `--accent` (celeste polvo) · Humano = `--human` (púrpura)
- Animaciones: `pulse 1.6s` · `think 2.4s` · `skel 1.4s` · `cursor-blink 1s`
- Mockups son referencia visual hifi — recrear con componentes React, NO copiar HTML

## Comandos de dev local

```bash
cd web

# Lint (solo v2 — el legacy usa `npm run lint`)
npm run lint:v2

# Typecheck (todo el repo)
npm run typecheck

# Unit tests (Vitest, jsdom)
npm run test:unit

# Unit tests watch
npm run test:unit:watch

# E2E tests (Playwright, headless)
npm run test:e2e

# E2E tests modo interactivo
npm run test:e2e:ui

# Build de producción
npm run build

# Format con Prettier
npm run format
```

Antes de abrir un PR, todos verdes localmente.

## Path aliases

```ts
import { something } from "@/v2/quotes/page";          // → src/app/v2/quotes/page
import { Sidebar } from "@/v2-components/chrome/Sidebar"; // → src/components/v2/chrome/Sidebar
import { V2_API_BASE } from "@/v2-lib/api";            // → src/lib/v2/api
```

## Sub-PRs siguientes

Orden secuencial dentro de Sprint 2 (Master §21.2):

1. **`sprint-2/scaffold`** ← este PR
2. `sprint-2/design-system-migration` — tokens CSS de `design_handoff` → `tailwind.config.ts`
3. `sprint-2/chrome-refactor` — Sidebar + Topbar + QuoteHeader + Stepper
4. `sprint-2/paso-1-brief-upload` — mockups `00-A/B/C`
5. `sprint-2/paso-2-contexto` — mockups `01-A/02-B/03-C`

## Backend

Ver `docs/handoff-context/`:

- `endpoints-spec.md` — contratos REST
- `sse-spec.md` — protocolo SSE chat Valentina
- `schemas/*.md` — Quote, brief, context, audit_events
- `catalog/` — JSONs sanitizados con cifras canon Cueto-Heredia (Master §13)

Wire-up real: `useApiClient()` switch en Sprint 3 inicial. Sprint 2 mockea contra `useMockClient()`.
