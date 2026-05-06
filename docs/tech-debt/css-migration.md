# Deuda Técnica · Migración completa de CSS a Tailwind

## Status

🟡 Diferida a Sprint 5 (QA + cleanup).

## Contexto

En Sprint 2 (PR `sprint-2/design-system-migration`, 2026-05-06) decidimos estrategia híbrida:

- ✅ **Tokens migrados** a `web/tailwind.config.ts` (colors, fonts, radii custom)
- ✅ **CSS variables** sincronizadas en `web/src/app/v2/globals.css` (`:root`) para que `operator-shared.css` y Tailwind compartan fuente de verdad
- 🟡 **CSS de componentes** (`operator-shared.css`, ~4710 líneas) importado as-is. NO migrado a Tailwind utilities.

## Por qué no se migró completo

- El `operator-shared.css` ya pasó audit visual Sprint 1.5 (8 flows, 30 mockups, 9 iteraciones de fix). Refactorearlo a Tailwind es trabajo de migración con riesgo de romper detalles visuales finos sin agregar valor a Marina.
- Los tokens migrados son lo que realmente da superpoder: cuando se armen componentes nuevos en Sprint 2-4, pueden usar `className="bg-accent text-ink-soft"` y el resultado matchea automáticamente el design system.
- El cleanup completo es propio de Sprint 5 (QA + perf), donde se puede aislar como tarea con su propio audit visual.

## Trade-off conocido

Durante Sprint 2-4 conviven dos sistemas de estilos para componentes v2:

1. **Clases CSS legacy de operator-shared.css**: `.etable`, `.vbubble`, `.chat`, `.stepper`, `.btn.primary`, `.aud-trail`, `.calc-section`, `.ia-banner`, `.qhead`, `.confirm-bar`, `.mob`, etc.
2. **Tailwind utilities**: `bg-accent`, `text-human`, `font-serif`, `rounded-r-md`, `p-4`, `flex`, `border-line`, etc. — para componentes nuevos.

### Regla de uso durante Sprint 2-4

- Si el mockup usa una clase del CSS legacy (ej. `.vbubble`, `.etable`), **reusala**. NO la reescribas en Tailwind.
- Para layout, spacing, color de elementos NUEVOS que no estén en `operator-shared.css`, usá Tailwind.
- Si un componente legacy necesita un override puntual, hacelo con Tailwind via `className="..."`. NO toques `operator-shared.css`.
- Para acceder a los radii del handoff (6/10/14 px) sin pisar los `rounded-md/lg` defaults de Tailwind que el legacy ya usa: `rounded-r-sm`, `rounded-r-md`, `rounded-r-lg` (custom tokens definidos en `tailwind.config.ts`).

### Bridging que ya hicimos

- `globals.css` del v2 redefine `--serif`, `--sans`, `--mono` para que apunten a `var(--font-serif)`, `var(--font-sans)`, `var(--font-mono)` — los fonts cargados por `next/font/google`. Sin esto, las strings literales `"Fraunces"` que usa `operator-shared.css` no matchearían las fuentes (next/font genera nombres con suffix `__Fraunces_xyz`).
- Tailwind `theme.extend.colors` agrega los nombres del v2 (`accent`, `human`, `ok`, etc.) **sin pisar** los nombres del legacy (`acc`, `t1`, `s1`, etc.). Ambos paths conviven.

## Plan de cleanup en Sprint 5

1. **Componentes-by-component:** tomar cada clase `.xyz` del CSS legacy, identificar dónde se usa en componentes v2, refactorear el componente a Tailwind utilities, borrar la clase del CSS.
2. **Audit visual con Playwright** para asegurar que cero regresión.
3. **Estimación:** 3-5 días de trabajo dedicado en Sprint 5.

## Riesgo conocido · CSS bleed entre v2 y legacy

`operator-shared.css` se importa en `web/src/app/v2/layout.tsx`. Next.js App Router carga el CSS chunk **solo cuando se renderea una ruta de `/v2/*`** — esto es lo que evita el bleed teórico.

Pero hay edge cases:

1. **Navegación client-side:** si el usuario va `/quotes` (legacy) → `/v2` → `/quotes`, el chunk de v2 ya está cargado en memoria del browser. Como CSS es global, los selectores `:root`, `html`, `body`, `*` del `operator-shared.css` SÍ pueden afectar al legacy en esa visita posterior.
2. **Selectores top-level afectados:** `operator-shared.css` declara `html, body { background: var(--bg); ... font-size: 14px; ... }` y `body { min-width: 1440px }`. Si bleed ocurre, el legacy podría:
   - Cambiar `font-size: 15px → 14px`
   - Tener `min-width: 1440px` en mobile (legacy responsive se rompería)

**Mitigación inmediata:** sub-PRs siguientes verifican preview Vercel del legacy en cada PR. Si aparece regresión visual, abrir PR de scope manual (envolver `operator-shared.css` con un wrapper `.v2-root { ... }` — requiere modificar el archivo, lo cual sale del scope del task que prohibió tocarlo).

**Mitigación definitiva:** Sprint 5 cleanup migra los selectores top-level a Tailwind base layer scoped al v2. La capa Tailwind con `@layer base { html.v2-root { ... } }` permite scoping sin tocar `operator-shared.css`.

## Archivos relevantes

- `web/src/app/v2/operator-shared.css` — CSS canónico legacy (NO MODIFICAR durante Sprint 2-4)
- `web/src/app/v2/globals.css` — CSS vars compartidas (espejo de design_tokens.ts)
- `web/tailwind.config.ts` — tokens migrados (sección "V2 tokens · Sprint 2")
- `docs/handoff-design/design_tokens.ts` — fuente original
- `docs/handoff-design/design_files/operator-shared.css` — fuente legacy (no se borra del handoff)

## Cuándo revisitar

Sprint 5 (QA + perf + demo Marina). Crear PR `sprint-5/css-migration` cuando se arranque.

---

**Última actualización:** 2026-05-06 — PR `sprint-2/design-system-migration` mergeado a `sprint-2/main`.
