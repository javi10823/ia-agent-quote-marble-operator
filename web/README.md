# Marble Operator · Frontend v2

Next.js 14 (App Router) · TypeScript. Panel del operador para el agente
Valentina (presupuestos de marmolería D'Angelo).

## Cómo correr local

### Modo mock (default · sin backend)

```bash
npm install
npm run dev          # http://localhost:3000
```

Sin `NEXT_PUBLIC_API_URL`, el client (`src/lib/api`) sirve **mocks**
determinísticos (`src/lib/api/mocks.ts`). Es el modo de los tests E2E y de
desarrollo sin backend.

### Modo real (contra backend Railway)

```bash
NEXT_PUBLIC_API_URL=https://ia-agent-quote-marble-operator-production.up.railway.app \
NEXT_PUBLIC_REQUIRE_AUTH=true \
npm run dev
```

→ redirige a `/login`. Logueás con un user real de la DB (ej. `marmoleria`).
En modo real, **3 funciones** pegan al backend (`streamChat`, `listQuotes`,
`getQuoteMetadata`); el resto sigue en mock (B3 incremental · ver
`docs/known-issues.md`).

## Variables de entorno

| Var | Default | Efecto |
|-----|---------|--------|
| `NEXT_PUBLIC_API_URL` | (mock) | Definida → client real contra esa URL. Sin definir → mocks. |
| `NEXT_PUBLIC_REQUIRE_AUTH` | `false` | `"true"` → `AuthGuard` exige login (redirige a `/login` sin sesión). |

Las dos son **ortogonales**: una controla mock/real, la otra auth on/off
(ver `docs/known-issues.md` § "Decisiones de arquitectura").

## Tests

```bash
npm run lint          # eslint
npm run typecheck     # tsc --noEmit
npm run test:unit     # vitest (lógica pura + SSE event types)
npm run test:e2e      # playwright (modo mock por default)
npm run build         # next build
```

Los E2E corren en **modo mock** (el `playwright.config.ts` NO setea
`NEXT_PUBLIC_API_URL`). Para correrlos contra el backend real, exportá la var
manualmente antes de `npm run test:e2e`.
