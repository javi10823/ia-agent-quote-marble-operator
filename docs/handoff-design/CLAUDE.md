# CLAUDE.md — Marmoleria Operator IA

> Instrucciones persistentes para Claude Code al implementar el handoff de Marmoleria Operator IA en el repo target (Next.js).

## Contexto

Estás implementando un producto interno: **Marmoleria Operator IA**, herramienta IA-asistida para que **Marina** (operadora de marmolería D'Angelo) genere presupuestos a partir de planos PDF/imagen.

El handoff completo está en `design_handoff_marmoleria_operator/`:
- `README.md` — overview, screens, interacciones, data model. **Léelo entero antes de empezar.**
- `design_tokens.ts` — tokens en TS, importable
- `design_files/*.html` — 30 mockups de referencia
- `design_files/operator-shared.css` — CSS canónico, **fuente de verdad para estilos**

## Principios

### 1 · El HTML es referencia, no código a copiar
Los mockups HTML existen como **especificación visual**. Recreá usando los componentes y patrones del codebase Next.js. Si un componente no existe, construilo según los mocks y agregalo al sistema.

**Nunca** copies `chrome.js`, `bug-report.js` ni `frame-label` literalmente. Usá `app/layout.tsx` con sidebar/topbar nativos. Ver `README.md` §13.

### 2 · Tokens primero
Antes de implementar componentes, instanciá los tokens (`design_tokens.ts`) en el sistema del codebase (Tailwind config / CSS vars / theme provider). Todos los colores, fuentes, radios y duraciones de animación salen de ahí.

### 3 · Hifi · pixel-perfect
El diseño es hifi. Respetá:
- Dimensiones exactas (sidebar 240px, chat 480px, topbar 56px, mobile 375px)
- Tipografía exacta (Fraunces serif italic en headings · Inter Tight body · JetBrains Mono en eyebrows/numéricos/SKUs)
- Letter-spacing (`-0.2px` en serif, `0.4–0.6px uppercase` en mono)
- Animaciones (`pulse 1.6s`, `think 2.4s`, `skel 1.4s`, `cursor-blink 1s`)

### 4 · Sin slop visual
Este diseño es sobrio: dark mode pizarra + acento celeste polvo + acento púrpura (humano). **No agregues** gradientes coloridos, emojis (excepto ✓ ✏ ⋯ que ya están), shadows excesivas, ni elementos no especificados. Si dudás, no lo pongas.

### 5 · Spanish rioplatense
Toda la copy va en español rioplatense ("vos", "tenés", "podés"). No traduzcas, no neutralices el dialecto. La voz de Valentina (IA) es serif italic en `<em>` para acentos:
> "Marina, *necesitás un despiece* para seguir."

### 6 · IA ≠ accent · Humano = púrpura
Convención no-negociable:
- Todo lo que origina la IA = `--accent` (celeste polvo `#a9c1d6`)
- Todo lo editado por Marina = `--human` (púrpura `oklch(0.74 0.09 300)`)
- Esta distinción visual es **el corazón del producto** — Marina necesita ver de un vistazo qué tocó ella vs qué propuso la IA.

## Convenciones del codebase

### TypeScript
- `strict: true` siempre
- Tipos del data model en `README.md` §10 → `lib/types.ts`
- Sin `any` salvo en boundaries con APIs externas (y comentado por qué)

### Componentes
Usá la lista del `README.md` §8 como inventario. Naming PascalCase, archivos kebab-case:
```
components/editable-table.tsx       → <EditableTable>
components/chat-panel.tsx           → <ChatPanel>
components/calc-section.tsx         → <CalcSection>
```

Cada componente debe:
1. Aceptar `className` para overrides
2. Exponer todos los estados visuales como props (no estado interno opaco)
3. Tener una historia en Storybook (o Ladle) con cada estado del README

### Estado
Recomendado:
- **Server state**: React Query (Quote, ChatSession, audit log)
- **Client state**: Zustand para UI persistente (chatOpen, ivaTraceable, currentStep)
- **Form state**: React Hook Form + Zod (especialmente las tablas editables)

NO uses `useState` global para cosas como `chatOpen` — múltiples componentes lo necesitan.

### Animaciones
Usá Framer Motion. Reusá las 4 animaciones globales como variants compartidos:
```ts
// lib/motion.ts
export const pulse = { /* 1.6s loop */ }
export const think = { /* 2.4s loop */ }
export const skel = { /* 1.4s loop */ }
export const cursorBlink = { /* 1s step */ }
```

### Routes (App Router)
Sugerido:
```
app/
  layout.tsx                        ← sidebar + topbar
  (dashboard)/
    page.tsx                        ← #25 desktop
  quotes/
    [id]/
      layout.tsx                    ← qhead + stepper
      paso-1/page.tsx               ← upload
      paso-2/page.tsx               ← contexto
      paso-3/page.tsx               ← despiece
      paso-4/page.tsx               ← cómputo
      paso-5/page.tsx               ← cotización
  m/                                ← mobile shell
    quotes/...
```

## Antes de codear

1. **Leer el README entero**, especialmente §10 (data model) y §11 (screens).
2. **Abrir 3–4 HTMLs** del flow que vas a implementar — abrirlos con un live server y abrir DevTools para inspeccionar layouts.
3. **Inspeccionar `operator-shared.css`** — buscar la clase del componente que vas a hacer (ej. `.calc-section`) y leer todas las variantes.
4. **Confirmar** con product/design si vas a desviarte de lo especificado.

## Antes de hacer commit

- ¿La copy está en español rioplatense?
- ¿Los tokens vienen de `design_tokens.ts`, no hardcoded?
- ¿La animación tiene la duración exacta?
- ¿Probaste los estados `edited` (púrpura) y `err` (rojo) en celdas de tabla?
- ¿El sidebar/topbar son layouts nativos de Next, no inyección DOM?
- ¿El chat es sticky a `top: 24px` con `max-height: calc(100vh - 100px)`?
- ¿Los `frame-label` mono uppercase del audit pack NO aparecen en producción?

## Cosas que NO debés hacer

- ❌ Inventar componentes nuevos sin consultar — el inventario en §8 es completo
- ❌ Usar emojis no especificados (✓ ✏ ⋯ × ↳ son OK; 🔵 ⚠️ 🚀 NO)
- ❌ Cambiar la copy "porque suena mejor" — está revisada con Marina
- ❌ Agregar dark/light toggle — el producto es dark-only
- ❌ Reemplazar Fraunces por otra serif "más moderna"
- ❌ Hacer responsive desktop bajando de 1440px (es internal tool, viewport conocido)
- ❌ Generar PDFs como screenshots — debe ser PDF real (jsPDF / react-pdf / server)

## Cosas que SÍ debés hacer

- ✅ Preguntar cuando un mockup tenga un detalle ambiguo
- ✅ Documentar decisiones de implementación que no estén en el README
- ✅ Agregar tests (RTL) para los estados críticos: edición, validación, chat scoped
- ✅ Asumir que la IA real puede tardar 2–30s — siempre tener fallback manual
- ✅ Loguear toda edición humana al audit log (ver §12 transversales)
- ✅ Mantener la convención IA-celeste / Humano-púrpura **religiosamente**

## Si trabás

Volvé al `README.md`. Si la respuesta no está ahí, mirá el HTML correspondiente. Si tampoco, preguntá — no inventes. La consistencia visual de este producto depende de respetar el sistema, no de "mejorarlo" puntualmente.
