# Known Issues · Sprint 2-5

Este archivo lista bugs conocidos, deuda técnica y gaps detectados en audit que NO bloquean merge pero deben revisitarse en Sprint 5 (QA + perf).

Reglas:
- Cada item documenta: PR de origen, severidad, descripción, plan
- Severidades: BLOCKER (bloquea producción), MAJOR (visible al usuario), MINOR (cosmético/test)
- Cuando un item se resuelve, mover a sección "Resueltos" con commit hash

## Issues abiertos

### sprint-2/paso-1-brief-upload (PR #457) · MINOR · Cobertura E2E parcial de validaciones

**Detectado:** audit independiente PR #457, 06.05.2026, NICE-TO-HAVE 2.

**Descripción:** El mock client `createDraftQuote` implementa 6 validaciones client-side (PDF mime, PDF 20MB, photos count <=5, photo mime, photo 5MB, brief 2000 chars). Los tests E2E cubren 3 de 6 validaciones. Faltan tests para:
- Foto > 5MB rechaza con error
- Brief text > 2000 chars rechaza con error
- Más de 5 fotos rechaza con error

**Impacto:** Las validaciones SÍ funcionan en el código (verificado en audit). Solo no hay tests E2E que prevengan regresiones futuras.

**Plan:** agregar 3 tests E2E faltantes en Sprint 5 (sprint-5/qa-e2e-suite) o como tarea preventiva en cualquier PR posterior que toque el flujo de archivos del paso 1.

### sprint-2/chrome-refactor (PR #456) · MINOR · Inline styles heredados

Detectado en audit independiente PR #457 NICE-TO-HAVE 5. Inline `style={{...}}` en algún componente del chrome shell. Cleanup: Sprint 5.

### sprint-2/paso-2-contexto (PR #458) · MINOR · Mock streamChat incompleto

**Detectado:** audit independiente PR #458, 06.05.2026, NICE-TO-HAVE 1.

**Descripción:** El mock client `streamChat()` en `web/src/lib/v2/api.ts` solo emite 3 event types: `text`, `done`, `error`. El SSE spec real del backend (verificado en `docs/handoff-context/sse-spec.md`) tiene 7 event types totales:

- `text` ✅ implementado
- `done` ✅ implementado
- `error` ✅ implementado
- `action` ⚠️ falta
- `context_analysis` ⚠️ falta
- `dual_read_result` ⚠️ falta
- `zone_selector` ⚠️ falta

**Impacto:** El mock chat de Sprint 2 funciona correctamente para conversación básica. Pero cuando se conecte al backend real en `sprint-3/api-integration`, el `useChatScoped.send()` actual NO maneja los 4 event types adicionales — la respuesta de Valentina puede perder información si el backend emite alguno de esos types.

**Plan:** durante `sprint-3/api-integration`, extender el switch del `useChatScoped.send()` para los 4 event types adicionales según el shape definido en `docs/handoff-context/sse-spec.md`. Es PR de bajo costo (extender un switch existente).

### sprint-2/paso-2-contexto (PR #458) · MINOR · Campos del contexto PRES-018 con valores divergentes

**Detectado:** Claude for Chrome visual check del PR #460, 12.05.2026.

**Descripción:** Algunos campos del contexto del PR #458 muestran valores en distintos elementos respecto del spec del Master §13:

- Regrueso muestra "frontal · 4 cm" en el campo (spec: "4,98 ml")
- Superficie 6,50 m² aparece en header/topbar pero NO como campo del formulario
- Descuento "-5%" aparece en banner Valentina, NO como campo del formulario
- Tomas: banner menciona "TOMAS automático" pero NO hay campo con valor "2"

**Impacto:** cosmético. Los datos están presentes, distribuidos en elementos visuales distintos. No afecta funcionalidad ni cálculo.

**Plan:** revisar y alinear con spec del Master §13 en `sprint-3/paso-3-despiece` (cuando se toque el contexto reabierto) o en `sprint-5/cleanup-deuda`.

### sprint-3/extract-calc-contracts (PR #461) · MINOR · Cifras canon Master §13 no reproducibles desde calculator.py

**Detectado:** PR #461 audit de calculator.py 2258 LOC, 2026-05-13.

**Descripción:** USD 2.184 (Cueto-Heredia) y ARS 660.890 (Pereyra) del Master §13 son design references, no reproducibles ejecutando `calculator.py` con catálogo vigente. Confirmado por audit independiente.

**Decisión:** decisión D híbrida — mockups visuales mantienen las cifras, mocks-first y tests usan outputs reales del motor (`calculator-examples.md`). Master §13 actualizado para clarificar.

---

### sprint-3/extract-calc-contracts (PR #461) · MINOR · 2 reglas Master §16 no implementadas en calculator.py

**Detectado:** PR #461 audit, 2026-05-13.

**Descripción:** Master §16 declara 7 reglas; calculator.py implementa 12 reglas reales documentadas en `calculator-rules.md`. 2 reglas declaradas en Master NO están implementadas:

1. Redondeo a múltiplos comerciales (ej: Negro Brasil debe ser entero)
2. Conversión USD↔ARS automática

**Impacto:** ninguno funcional hoy. El motor opera en monedas nativas (USD para material caro como Negro Brasil/Silestone; ARS para servicios locales) sin conversión cruzada.

**Plan:** evaluar si implementar en Sprint 5 o si el approach actual (no conversión) es el correcto. Decidir con Javi al planear demo Marina.

---

### sprint-3/extract-calc-contracts (PR #461) · MINOR · validate_quote no es tool exportado de Valentina

**Detectado:** PR #461 audit, 2026-05-13.

**Descripción:** Master menciona `validate_quote` como tool de Valentina. En realidad:

- Tools exportados de Valentina (`agent.py:1212-1221`): `list_pieces` + `calculate_quote` (entre otros), NO `validate_quote`.
- `validate_quote` es función interna del módulo `validation_tool.py` (`validate_despiece`), no expuesta como Anthropic tool.

**Impacto:** ninguno hoy. El doc `tools/validate_quote.md` aclara este punto explícitamente.

**Plan:** si en el futuro se quiere exponer validación como tool a Valentina, registrar como feature nueva.

---

### sprint-3/extract-calc-contracts (PR #461) · MINOR · Motor calculator.py es 2258 LOC, no 360

**Detectado:** PR #461 audit, 2026-05-13.

**Descripción:** El spec del task mencionaba "calculator.py ~360 líneas". El motor real es 2258 líneas + spans multiple files del módulo `quote_engine/`. Cosmético, ya documentado en `calculator.md`.

**Plan:** ninguno — solo registro para futuras estimaciones de scope.

---

### sprint-3/api-integration (PR #464) · ARCHITECTURE · 6+1 funciones siguen en mock (B3 incremental)

**Detectado:** FASE 1 PR #463 + confirmado en FASE 1 PR #464, 2026-05-14.

**Descripción:** el backend es agent/chat-centric, no REST-CRUD. Solo 3 funciones mapean limpio a endpoints REST y se wirearon contra real: `streamChat` (`POST /api/quotes/{id}/chat`), `listQuotes` (`GET /api/quotes`), `getQuoteMetadata` (`GET /api/quotes/{id}`). Las siguientes **NO tienen endpoint REST equivalente** y quedan en mock con el feature flag activo:

- `getContextForQuote` / `updateContextForQuote` — el contexto vive en `quote_breakdown` + el SSE `context_analysis`, no hay GET/PATCH dedicado.
- `listPiecesForQuote` / `updatePieceForQuote` / `addPieceForQuote` / `deletePieceForQuote` — piezas embebidas en `quote_breakdown.dual_read_result`, side-effect del agent. (Editables vía `PATCH /api/quotes/{id}` con `pieces[]`, pero sin GET/POST/DELETE dedicados.)
- `regenerateDespiece` — `POST /api/quotes/{id}/regenerate` existe pero regenera **PDF/Excel**, no piezas.
- `getDashboardKpis` — no existe (los KPIs dependen de m²/actividad que el listado real no expone).
- `getValentinaBriefSummary` — no existe.

**Plan Sprint 4/5:** A) refactor frontend a chat-centric (derivar context+pieces del SSE + `quote_breakdown`); B) backend agrega endpoints REST (viola "no tocar backend"); C) híbrido.

---

### sprint-3/api-integration (PR #464) · MAJOR · createDraftQuote queda en mock SIN hide — paso-1 rompe en modo real

**Detectado:** FASE 1 PR #464, 2026-05-14.

**Descripción:** el real `POST /api/quotes` crea un **draft vacío** (`{id}` only, sin brief/archivos) — el procesamiento del brief ES el chat stream (multipart), no la creación. El mock `createDraftQuote({planFile, photos, briefText})` no mapea. Queda en mock. **Consecuencia con flag real activo:** el paso-1 (`/quotes/new` → BriefView) crea quotes mock cuyo `id` (PRES-2026-018) NO existe en el `listQuotes` real → navegar a `/quotes/PRES-2026-018/contexto` mostrará un 404 o quote distinto. Javi aceptó romper parcial (sistema no se usa todavía).

**Plan Sprint 4:** `sprint-4/paso-1-real` — rebuild BriefView para el flow real 2-fases (`POST /quotes` shell + `POST /chat` multipart con `dual_read_result`).

---

### sprint-3/api-integration (PR #464) · MINOR · Schema gaps degradados con em dash

**Detectado:** FASE 1 PR #464, 2026-05-14.

**Descripción:** el listado/detalle real no expone `m2`, `lastActivityDays`, `daysToExpire`. El adapter en `real.ts` los degrada a `"—"` (em dash, no 0) — `toLocaleString` sobre un string devuelve el string, así que la tabla muestra "— m²" sin romper. `clientFull`←`client_name`, `currency/amount`← `total_usd>0 ? USD : ARS`. `getQuoteMetadata` intenta derivar `m2` de `quote_breakdown.dual_read_result.sectores[].m2_total`, fallback "—".

**Plan Sprint 4:** `sprint-4/derive-fields` (mejorar adapters) + `sprint-4/dashboard-kpis` (calcular KPIs client-side derivando del listado real).

---

## Decisiones de arquitectura

### sprint-3/auth · auth gate via `NEXT_PUBLIC_REQUIRE_AUTH` (no `NEXT_PUBLIC_API_URL`)

**Fecha:** 2026-05-13.

**Contexto:** el `auth_token` del backend es una cookie httpOnly scoped a `railway.app`. El frontend vive en `vercel.app` (cross-origin, PR #322). Ni el JS del cliente ni el middleware edge de Vercel pueden leer esa cookie → un middleware edge que gatee por `auth_token` produce loop infinito (documentado en `web/src/middleware.ts`).

**Decisión route-protection:** client-side gate (`AuthGuard`) — la sesión se trackea en `localStorage`; el enforcement real lo hace el backend con 401. (Recomendado por PR #322.)

**Decisión sobre el flag de activación:** se usa un flag **dedicado** `NEXT_PUBLIC_REQUIRE_AUTH`, NO `NEXT_PUBLIC_API_URL`. Razón: `NEXT_PUBLIC_API_URL` ya estaba seteada a `http://localhost:8000` (dummy) en `playwright.config.ts:42` desde Sprint 2 — reusarla para gatear auth rompía los 48 E2E previos (todos redirigían a `/login`).

Dos flags ortogonales:

| Var | Controla |
|-----|----------|
| `NEXT_PUBLIC_API_URL` | mock vs real backend (gestionado por `sprint-3/api-integration`) |
| `NEXT_PUBLIC_REQUIRE_AUTH` | auth on/off (este PR) |

Para activar auth en prod: setear `NEXT_PUBLIC_REQUIRE_AUTH=true` en las env vars del proyecto Vercel.

### v2 NO compila Tailwind utilities · decisión + deuda

**Detectado:** visual check PR #463, 2026-05-13.

**Estado actual:** el proyecto tiene `web/tailwind.config.ts` pero **NO tiene directivas `@tailwind` en ningún archivo CSS**. Resultado: las utility classes (`flex`, `min-h-screen`, `items-center`, `font-serif`, `italic`, `rounded-md`, `bg-accent`, `text-ink`, `px-3`, etc.) **NO se generan en el CSS bundle — son dead no-ops**.

**Patrón v2 que SÍ funciona** (verificado en `DashboardView`, `ContextView`, `Sidebar`):

1. Clases legacy de `operator-shared.css` (`.btn primary`, `.input`, `.eyebrow`, `.nav-i`, `.kpi-card`, `.etable`, etc.)
2. Inline `style={{}}` para layout (`display: flex`, `minHeight`, etc.)
3. CSS vars del design system (`var(--bg)`, `var(--ink)`, `var(--accent)`, `var(--serif)`, `var(--mono)`, `var(--r-md)`, etc.)

**Componentes que YA usan utility classes muertas** (deuda latente — no rompen hoy por respaldo inline o herencia de operator-shared.css):

- `DashboardView` (algunas classes Tailwind ignoradas)
- Root layout `<body className="bg-bg text-ink">` (no aplica — el bg real lo da operator-shared.css)
- (otros TBD si se hace pasada de cleanup)

**Opciones para Sprint 5:**

- **A) Pasada de cleanup:** eliminar todas las utility classes muertas del v2, estandarizar inline styles + clases legacy.
- **B) Agregar directivas `@tailwind` al pipeline:** activaría TODAS las utilities de golpe → requiere QA visual completo (clases hoy no-ops empezarían a aplicar, potencialmente rompiendo el diseño actual).
- **C) Híbrido:** configurar Tailwind con cherry-pick de utilities específicas vía `corePlugins`.

**Decisión pendiente:** Sprint 5 cleanup, o cuando se haga refactor del design system.

**REGLA OPERATIVA para PRs en curso (Sprint 3+):**

- ❌ NO usar Tailwind utility classes en componentes nuevos del v2.
- ✅ USAR clases legacy de `operator-shared.css` + inline `style={{}}` con CSS vars.
- ✅ Visual check vía Claude for Chrome **OBLIGATORIO** para todo PR con UI nueva (el audit de código + tests E2E NO detectan layout roto por utilities muertas).

### sprint-3/auth (PR #463) · MINOR · `body { min-width: 1440px }` global descentra páginas standalone

**Detectado:** screenshot verificado por Claude Code durante el refactor visual del PR #463, 2026-05-13.

**Descripción:** `operator-shared.css` tiene `body { min-width: 1440px }` global. En viewports <1440 cualquier página standalone se renderiza **descentrada** — el body es 1440px wide aunque el viewport sea menor, el contenido se centra dentro del body y aparece off-center respecto al viewport real.

**Impacto:** `/login` standalone lo sufría antes del fix. Otras páginas standalone potencialmente igual. El dashboard y rutas con chrome shell completo no lo notan porque el chrome ≥1440 ya define su layout.

**Fix aplicado en /login (commit 64a8e04):** `.login-root` con `position: fixed; inset: 0` → fija al viewport real, no al body con min-width global. Sin tocar operator-shared.css.

> Nota: este hallazgo **solo lo detecta un visual check / screenshot** — los E2E y el audit de código pasan igual con la card descentrada. Refuerza la regla operativa del ADR de Tailwind (visual check obligatorio para UI nueva).

**Plan Sprint 5:** decidir entre:

1. Eliminar el `min-width` global de operator-shared.css (requiere QA visual del chrome).
2. Mover el `min-width` a un contenedor específico del chrome shell.
3. Documentar como "operator es desktop-only intencional, mobile es excepción".

## Resueltos

_(vacío al inicio)_
