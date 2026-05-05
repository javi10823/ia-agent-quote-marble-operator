# Handoff · Marmoleria Operator IA

> **Sprint 1.5 — Operador IA-asistido para presupuestos D'Angelo**
> Generado el 5 mayo 2026

---

## 1 · Overview

**Marmoleria Operator IA** es la herramienta interna que usa **Marina** (operadora administrativa de la marmolería D'Angelo) para producir presupuestos a partir de planos PDF/imagen del arquitecto. La IA (`Valentina`, asistente embebida) propone un primer borrador a partir del plano + contexto histórico del cliente, y Marina **edita, valida y confirma** cada paso. Es un flujo **IA-first pero humano-en-el-loop**: la IA siempre propone, Marina siempre aprueba.

El flujo completo tiene **5 pasos** + **dashboard de seguimiento**:

| # | Paso | Qué hace Marina aquí |
|---|---|---|
| 1 | **Upload** | Sube el plano del arquitecto, agrega brief de contexto |
| 2 | **Contexto** | Confirma cliente / obra / piezas detectadas |
| 3 | **Despiece** | Valida la lista de piezas con dimensiones |
| 4 | **Cómputo** | Revisa cálculo (material + merma + MO + flete) |
| 5 | **Cotización** | Genera PDF, manda a cliente, gestiona revisiones |
| — | **Dashboard** | Ve todos los presupuestos en curso (mobile + desktop) |

A través de los 5 pasos hay un **mini chat lateral** persistente (Valentina, scoped al paso actual) que permite a Marina pedir aclaraciones o cambios en lenguaje natural sin salir del flujo.

---

## 2 · About the Design Files

Los archivos en `design_files/` son **referencias de diseño en HTML** — prototipos de cómo se ve y se comporta el producto, no código de producción. La tarea es **recrear estos diseños en el codebase target (Next.js)** usando los componentes y patrones ya existentes ahí, no copiar el HTML directamente.

Si el repo target todavía no tiene un design system instanciado, los design tokens de este handoff (`design_tokens.json` / `design_tokens.ts`) son la fuente canónica para inicializarlo.

---

## 3 · Fidelity

**Hifi** — Pixel-perfect en colores, tipografía, espaciado, estados, animaciones. Recrear con fidelidad usando los componentes del codebase Next.js. Si un componente equivalente no existe en el codebase, **construirlo según estos mocks** y agregarlo al sistema.

Los HTMLs son interactivos en lo cosmético (chat se abre, botones tienen hover, modal se muestra) pero NO tienen lógica de negocio real — Marina no puede subir un plano y obtener un despiece real. La lógica de IA, persistencia, autenticación, etc., son responsabilidad del implementador.

---

## 4 · Stack target

- **Next.js** (App Router asumido — confirmar con repo)
- **TypeScript estricto**
- **Tailwind o CSS Modules** — adaptar tokens en `design_tokens.ts` al sistema existente
- **Framer Motion** o equivalente para las animaciones (`pulse`, `think`, `skel`, `cursor-blink`)
- **State**: cliente (Zustand / Jotai / React Query) — el flujo es muy stateful
- Toda la copy está **en español rioplatense** — mantener tal cual

---

## 5 · Estructura de archivos

```
design_handoff_marmoleria_operator/
├── README.md                  ← este archivo
├── CLAUDE.md                  ← guidelines para Claude Code en el repo target
├── design_tokens.json         ← tokens en JSON
├── design_tokens.ts           ← tokens en TypeScript const
└── design_files/
    ├── operator-shared.css    ← CSS canónico (≈4700 líneas, fuente de verdad)
    ├── chrome.js              ← injection helpers para sidebar/header (NO reproducir literal — ver §13)
    ├── bug-report.js          ← widget de feedback
    ├── dashboard-dataset.js   ← mock de datos del dashboard (estructura de datos canónica)
    ├── assets/
    │   └── logo-dangelo.png
    └── *.html                 ← 30 mockups (lista en §7)
```

---

## 6 · Page chrome global

Todos los mockups desktop comparten un **page chrome** (3 zonas):

| Zona | Tamaño | Contenido |
|---|---|---|
| **Sidebar** (izq) | `240px` ancho fijo | Brand "D'Angelo" + dot accent · Nav: Inicio, Presupuestos (badge contador), Clientes, Stocks, Histórico · Footer: Marina (avatar + rol) |
| **Topbar** (sup) | `56px` alto | Crumbs (`Operator AI · Sprint 1.5`) · botones íconos derecha (search, notif, settings) |
| **Main** (resto) | `1fr` | qhead → stepper → body |

**Importante (Sprint 1.5 layout fix):** En desktop (`≥1024px`) NO se scrollea la página entera. `.page` es `height: 100vh; overflow: hidden;`. Solo `.body` (zona inferior) tiene `overflow-y: auto`. Topbar + qhead + stepper quedan **siempre visibles**. Esta regla NO aplica en mobile ni en print.

**`min-width: 1440px`** en `body` → nunca achicar bajo eso en desktop. Mobile usa contenedor `.mob` de `375px`.

### Quote header (`.qhead`)
- Eyebrow mono uppercase (`OBRA EN CURSO · #DG-2024-0157`)
- H1 serif italic 26px (`Casa Mendoza — cocina + baño`)
- Sub mono 12.5px con metadata (cliente, fecha, etc.)
- Acciones derecha (volver, guardar borrador, ⋯)

### Stepper (5 pasos)
Estados: `done` (✓ verde), `now` (azul, underline accent), `pending` (mute, dashed circle, append " · pendiente").

---

## 7 · Mockups por flow

Mapeo screen → archivo. Cada mockup tiene un caption en `frame-label` con número y estado.

### Flow 01 · Paso 1 · Upload
| # | Archivo | Estado |
|---|---|---|
| 00-A | `00-paso1-A-vacio.html` | Dropzone vacío, sin archivo |
| 00-B | `00-paso1-B-subido.html` | Archivo cargado, brief chips IA + custom |
| 00-C | `00-paso1-C-procesando.html` | IA procesando (skeletons + status bar) |

### Flow 02 · Paso 2 · Contexto
| # | Archivo | Estado |
|---|---|---|
| 01-A | `01-contexto-A-ia-propuso.html` | IA propuso cliente/obra/piezas |
| 02-B | `02-contexto-B-marina-edito.html` | Marina editó (filas púrpura) |
| 03-C | `03-contexto-C-chat-abierto.html` | Chat abierto, scoped al paso 2 |

### Flow 03 · Paso 3 · Despiece
| # | Archivo | Estado |
|---|---|---|
| 04-A1 | `04-despiece-A-ia-propuso.html` | IA propuso despiece completo |
| 04-A2 | `04-despiece-A-completar-a-mano.html` | Fallback manual (IA no pudo) |
| 04-P | `04-paralelismo.html` | Vista lado-a-lado IA vs manual (educativa) |
| 05-B | `05-despiece-B-marina-edito.html` | Marina editó dimensiones |
| 06-C | `06-despiece-C-chat-abierto.html` | Chat abierto |

### Flow 04 · Paso 4 · Cómputo
| # | Archivo | Estado |
|---|---|---|
| 07-A | `07-paso4-A-ia-propuso.html` | Cálculo bicurrency (USD + ARS), banner híbrido sistema+Valentina |
| 07-A2 | `07-paso4-A-v4.html` | Variante v4 (rev posterior) |
| 08-B | `08-paso4-B-error-validacion.html` | Margen negativo → modal de forzar |
| 09-C | `09-paso4-C-chat-abierto.html` | Chat abierto |

### Flow 05 · Paso 5 · Cotización
| # | Archivo | Estado |
|---|---|---|
| 18-A | `18-paso5-A-preview.html` | Preview PDF + sidebar acciones |
| 19-B | `19-paso5-B-confirmar.html` | Confirmación previa al envío |
| 20-C | `20-paso5-C-generado.html` | PDF generado, opciones envío |
| 21-D | `21-paso5-D-revision-v2.html` | Revisión v2 (diff drawer con cambios) |
| 22-E | `22-paso5-E-vencido.html` | Presupuesto vencido |

### Flow 06 · Dashboard
| # | Archivo | Estado |
|---|---|---|
| 23 | `23-paso-dashboard-A-mobile.html` | Lista mobile |
| 24 | `24-paso-dashboard-B-mobile-detalle.html` | Detalle mobile |
| 25 | `25-paso-dashboard-C-desktop.html` | Vista desktop completa |

### Flow 07 · Mobile
| # | Archivo | Estado |
|---|---|---|
| 10 | `10-mobile-contexto-A.html` | Paso 2 en mobile |
| 11 | `11-mobile-despiece-A.html` | Paso 3 en mobile |
| 12 | `12-mobile-paso4-A.html` | Paso 4 en mobile |

### Flow 08 · Estados especiales
| # | Archivo | Estado |
|---|---|---|
| 13 | `13-audit-banner-on.html` | Banner audit-mode (debug, top de pantalla) |
| 15 | `15-ia-error.html` | IA falló, fallback completar a mano |
| 16 | `16-empty-despiece-lateral.html` | Empty state despiece (chat empty + paths) |
| 17 | `17-chat-error-ia.html` | Chat con error de IA en última respuesta |

> Hay un screenshot por mockup en `screenshots/` cuando esté disponible. Si no, abrir el HTML directamente con `open design_files/<archivo>.html`.

---

## 8 · Componentes (lista canónica)

Inventario derivado del CSS. Cada uno mapea a un componente React en el repo target.

### Layout / chrome
- `<PageShell>` (`.page` grid 240/1fr · sidebar + main)
- `<Sidebar>` (`.sidebar` con `.brand`, `.nav-h` headers, `.nav-i` items con badges)
- `<Topbar>` (`.topbar` con crumbs + ico-btn cluster derecha)
- `<AuditBanner>` (`.audit` rojo, dot pulse, copy mono, link "ver auditoría")
- `<QuoteHeader>` (`.qhead`)
- `<Stepper>` (`.stepper` con steps `done|now|pending`)
- `<FrameLabel>` (`.frame-label` caption fuera del mockup, solo para el audit pack — en producción NO renderizar)

### Tabular / data
- `<EditableTable>` (`.etable`, varias config de columnas: `cols-220-1fr-140-60`, `cols-despiece`, `cols-breakdown`, `cols-mo`)
  - Variantes de celda: `.cell.label-cell`, `.cell.num`, `.cell.action`, `.cell.edited` (púrpura + ✏ icon), `.cell.err` (rojo + tooltip), `.cell.typing` (cursor blink)
  - `.row.row-edited` highlight
  - `.row.row-empty` placeholder italics
  - `.row.row-chat-ref` outline accent (cuando chat se refiere a esa fila)
  - `.add-row` para agregar fila

### IA / chat
- `<IABanner>` (`.ia-banner` con `.vbubble` gradient + texto + actions; variantes `.warn`, `.muted`, `.system`)
- `<StatusBar>` (`.status-bar` loading IA; variantes `.slow` warning >8s, `.manual` post-fallback)
- `<ChatPanel>` (`.chat`, sidebar 480px sticky)
  - `.chat .head` con vbubble + título serif + close
  - `.chat .scope` (mono uppercase + pill chips)
  - `.chat .stream` (mensajes `.msg.user` / `.msg.v`)
  - `.chat .composer` (input + send)
  - `.chat .sugs` (sugerencias chips)
  - Variante `.chat.empty` con `.empty-body`
- `<FeedbackBanner>` (`.feedback-banner` warn, post "no útil")

### Cómputo (paso 4)
- `<CalcBanner>` (`.calc-banner` 2 líneas: sistema mono + Valentina sans)
- `<CalcSection>` (`.calc-section` con `.sh` header + `.sb` body con `.row-line` y `.subtotal`)
- `<MOTable>` (`.etable.cols-mo` 7 columnas con SKU + IVA toggle)
- `<IVAToggle>` (`.iva-toggle` chip pill)
- `<TipoToggle>` (`.tipo-toggle` Particular/Edificio segmented)
- `<GrandTotal>` (`.grand-total` bicurrency USD + ARS, divider central)
- `<MermaStock>` toggle ad-hoc

### Botones / forms
- `<Button>` variants: default, `ghost`, `primary`, `sm`, `icon`, `danger`
- `<RegenSplit>` (`.regen-split` botón principal + kebab dropdown con `.regen-menu`)
- `<Modal>` (`.modal` + `.modal-backdrop`, con `.m-head`/`.m-body`/`.m-foot`)
- `<EmptyHero>` + `<EmptyPaths>` (estado vacío con CTAs primary/secondary)

### Mobile
- `<MobShell>` (`.mob` 375px container)
- `<MobHeader>` (`.mhead`)
- `<MobBody>` (`.mbody`)
- `<MobFooterSticky>` (`.mfoot.sticky`, respeta `env(safe-area-inset-bottom)`)
- `<MobBannerRed>` (estados de error mobile)

### Misc
- `<BriefChip>` (con variante `.from-ia` con marca "IA")
- `<TraceFlag>` (warn pill cross-mockup)
- `<Skeleton>` (`.skel` con `sk-w-*` modifiers)
- `<Kbd>` (`.k` keyboard shortcut hint)

---

## 9 · Design tokens

Ver `design_tokens.json` y `design_tokens.ts`. Resumen:

### Colores
| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#0f1318` | Fondo base |
| `--bg-muted` | `#161b22` | Sidebar, table headers |
| `--surface` | `#1c2129` | Cards, modales, chat |
| `--surface-2` | `#232932` | Hover state |
| `--line` | `rgba(232,237,229,0.08)` | Divisores |
| `--line-strong` | `rgba(232,237,229,0.14)` | Bordes prominentes |
| `--ink` | `#e8ede5` | Texto primario |
| `--ink-soft` | `#b9c0c8` | Texto secundario |
| `--ink-mute` | `#6d7682` | Disabled / metadata |
| `--accent` | `#a9c1d6` | **IA / primary · celeste polvo** |
| `--ok` | `oklch(0.78 0.13 150)` | Verde éxito |
| `--warn` | `oklch(0.84 0.13 75)` | Ámbar warning |
| `--info` | `oklch(0.82 0.09 255)` | Azul info |
| `--human` | `oklch(0.74 0.09 300)` | **Púrpura · editado por humano** |
| `--error` | `oklch(0.72 0.16 25)` | Rojo error |

### Tipografía
| Family | Uso |
|---|---|
| **Fraunces** (serif italic 500) | Display headings, eyebrows IA, labels destacados (`<em>` dentro de banners IA) |
| **Inter Tight** (sans 400/500/600) | Body, UI, labels |
| **JetBrains Mono** (monospace 400/500) | Numéricos, eyebrows uppercase, metadata, SKUs, status |

Cargar las 3 desde Google Fonts. Letter-spacing: `-0.2px` para serif italic en headings; `0.4–0.6px uppercase` para mono eyebrows.

### Radius
- `--r-sm: 6px` chips, small btn
- `--r-md: 10px` cards, modals, banners
- `--r-lg: 14px` modal grande
- `999px` pills

### Spacing
Múltiplos de 4 (4, 6, 8, 10, 12, 14, 16, 18, 22, 24, 28, 32). Padding `.body`: `28px 24px 80px`. Gap entre col main y chat: `24px`.

### Animaciones
| Nombre | Duración | Loop | Uso |
|---|---|---|---|
| `pulse` | 1.6s ease | sí | Audit banner dot |
| `think` | 2.4s ease | sí | vbubble "Valentina pensando" |
| `skel` | 1.4s ease | sí | Skeleton loading |
| `cursor-blink` | 1s step-end | sí | Cursor en celda editándose |

---

## 10 · Data model

Modelo TypeScript canónico inferido de `dashboard-dataset.js` + mockups. Todas las estructuras visibles en los mockups deben ser serializables a esto.

```ts
// — Cliente / Obra ————————————————————————————————————

type ClientType = 'particular' | 'edificio' | 'estudio'

interface Client {
  id: string
  name: string                    // "Casa Mendoza"
  type: ClientType
  address?: string
  contactPhone?: string
  contactEmail?: string
  notes?: string                  // comentarios persistentes (visible en mockup 02)
  createdAt: string               // ISO
}

interface Quote {
  id: string                      // "DG-2024-0157"
  clientId: string
  status: QuoteStatus
  step: 1 | 2 | 3 | 4 | 5
  title: string                   // "cocina + baño"
  briefChips: BriefChip[]         // tags de contexto · ver §11
  plan: PlanFile                  // PDF/imagen subido
  context: ContextData            // paso 2
  pieces: Piece[]                 // paso 3 (despiece)
  computation: Computation        // paso 4
  pdf?: GeneratedPDF              // paso 5 (cuando existe)
  versions: QuoteVersion[]        // historial de revisiones
  createdAt: string
  updatedAt: string
  expiresAt?: string              // "vencido" si pasa
}

type QuoteStatus =
  | 'draft'
  | 'in_progress'
  | 'sent_to_client'
  | 'revising'                    // v2, v3...
  | 'approved'
  | 'rejected'
  | 'expired'

// — Brief chips (paso 1) ————————————————————————————

interface BriefChip {
  id: string
  label: string                   // "Cocina"
  origin: 'ia' | 'user'           // distinción visual: IA = celeste mark
  category?: 'space' | 'piece' | 'finish' | 'urgency' | 'budget' | 'custom'
  value?: string
}

interface PlanFile {
  filename: string
  mime: 'application/pdf' | 'image/jpeg' | 'image/png'
  url: string
  pages: number
  uploadedAt: string
}

// — Contexto (paso 2) ——————————————————————————————

interface ContextData {
  detectedClient: Client | null   // IA propuso match con BD existente
  detectedPieces: PieceSummary[]  // pre-listing
  detectedFinishes: string[]
  ediciones: EditedField[]        // qué tocó Marina
}

interface EditedField {
  field: string                   // "cliente.address"
  previousValue: any              // lo que propuso IA
  newValue: any                   // lo que dejó Marina
  editedAt: string
}

// — Despiece (paso 3) ——————————————————————————————

type PieceCategory =
  | 'mesada' | 'pileta' | 'isla' | 'zocalo' | 'bacha' | 'frente' | 'tope_lavatorio' | 'otro'

interface Piece {
  id: string
  sku?: string                    // "MES-001"
  category: PieceCategory
  label: string                   // "Mesada cocina principal"
  ambient?: string                // "Cocina"
  dimensions: {
    largo_cm: number
    ancho_cm: number
    espesor_mm: number
  }
  qty: number
  material?: MaterialRef
  finish?: string                 // "pulido", "mate"
  edges?: EdgeFinish              // "biselado", "recto"...
  notes?: string
  edited: boolean                 // marca púrpura
  origin: 'ia' | 'user'
}

interface PieceSummary { category: PieceCategory; count: number }

// — Cómputo (paso 4) ——————————————————————————————

interface Computation {
  material: MaterialBlock
  merma: MermaBlock
  manoObra: MOBlock
  flete: FleteBlock
  piletas?: PiletasBlock          // opcional, "cliente la trae"
  iva: { traceable: boolean }     // toggle on = mostrar Base + ×1.21 separados
  tipoCliente: ClientType         // afecta cálculo (Edificio = sin recargo)
  margen: { pct: number; forced: boolean; reason?: string }
  totalUSD: number
  totalARS: number
  exchangeRate: number            // USD → ARS
}

interface MaterialBlock {
  ref: MaterialRef
  m2Total: number
  precioUSDxM2: number
  subtotalUSD: number
}

interface MaterialRef {
  id: string
  name: string                    // "Granito Verde Ubatuba"
  origin: string                  // "Brasil"
  pricingUSDxM2: number
  stockM2?: number
}

interface MermaBlock {
  applies: boolean                // false → renderizar `.merma-na`
  pct: number                     // % aplicado
  m2: number
  fromStock: boolean              // toggle "viene de stock"
  subtotalUSD: number
  reason?: string                 // si NA: "cliente trae material"
}

interface MOBlock {
  rows: MOLine[]
  subtotalUSD: number
}

interface MOLine {
  sku: string                     // "MO-CORTE-01"
  desc: string                    // "Corte recto a medida"
  qty: number
  baseUSD: number                 // sin IVA (visible si traceable)
  iva: number                     // 21% factor (visible si traceable)
  totalUSD: number
}

interface FleteBlock { km: number; tarifaUSDxKm: number; subtotalUSD: number }

interface PiletasBlock {
  inline: boolean                 // "cliente la trae" → solo header
  items?: PiletaItem[]
}

interface PiletaItem { id: string; model: string; precioUSD: number }

// — Cotización (paso 5) ————————————————————————————

interface GeneratedPDF {
  url: string
  generatedAt: string
  version: number                 // v1, v2...
  sentTo?: { email: string; sentAt: string }[]
  diff?: DiffEntry[]              // versus versión anterior (mockup 21)
}

interface DiffEntry {
  field: string                   // "pieces[2].dimensions.largo_cm"
  prev: any
  next: any
  reason?: string                 // texto humano del cambio
}

interface QuoteVersion {
  version: number
  snapshot: Quote                 // sin recursión: subset
  createdAt: string
  reason?: string
}

// — Chat IA ———————————————————————————————————————

type ChatScope = {
  step: 1 | 2 | 3 | 4 | 5
  refRows?: string[]              // IDs de filas a las que se refiere (highlight)
}

interface ChatMessage {
  id: string
  role: 'user' | 'valentina'
  body: string                    // markdown-ish con <em> para acentos
  ts: string                      // ISO
  flagged?: boolean               // "no útil" persistente en audit
  feedback?: 'good' | 'bad'
  error?: boolean                 // mockup 17 — falla del modelo
}

interface ChatSession {
  quoteId: string
  scope: ChatScope
  messages: ChatMessage[]
  startedAt: string
}
```

`dashboard-dataset.js` contiene **datos reales de mock** que el dev puede usar como seed para tests / Storybook.

---

## 11 · Interacciones · screen-by-screen

> Documentación exhaustiva de hover/active/loading/error por screen. Algunos states se solapan (ej. todas las tablas tienen los mismos estados de celda) — se documentan una vez en `<EditableTable>` y se referencia.

### Convenciones globales
- **Hover**: surfaces suben un escalón (`bg → bg-muted`, `surface → surface-2`)
- **Focus**: outline `2px solid var(--accent)` offset `-1px`
- **Active**: ligero `transform: translateY(1px)` en `.card`
- **Disabled**: `opacity: 0.4; cursor: not-allowed`
- **Transitions**: 0.15s ease default; las animaciones loop están listadas en §9

### `<EditableTable>` (estados de celda)
Aplican a todas las tablas (`cols-220-1fr-140-60`, `cols-despiece`, `cols-mo`, `cols-breakdown`):

| Estado | Visual | Trigger |
|---|---|---|
| Default | text mono `--ink`, transparent bg | inicial |
| Focus input | input gana underline `--accent` | tab/click |
| `.cell.edited` | bg `--human-bg`, border-left 2px `--human`, ✏ icon top-right | cuando `value !== originalIA` |
| `.cell.typing` | input outline `--human`, glow box-shadow, cursor blink en `::before` | mientras user tipea (debounce 300ms al value commit) |
| `.cell.err` | bg rosa, border-left 2px `--error`, tooltip `.err-msg` abajo | validación falla |
| `.row.row-edited` | gradient horizontal `human-bg → transparent` | si cualquier cell de la row está edited |
| `.row.row-chat-ref` | outline accent + first cell accent bold | cuando ChatPanel se refiere a esa row (highlight bidireccional) |

### Por screen

#### `00-paso1-A-vacio.html` — Dropzone vacío
- **Dropzone** ocupa main; estilo dashed ink-mute
- **Hover dropzone**: border solid `--accent`, bg `oklch(... / 0.06)`
- **Drag-over**: bg accent más sólido, shadow inset
- Botón "Subir plano" primary; alt "Pegar URL"
- Brief: chips vacíos placeholder italic

#### `00-paso1-B-subido.html` — Archivo subido
- Dropzone reemplazado por **filecard** (filename + size + page count + thumbnail mini)
- `.dz-actions` con `Reemplazar` (ghost) y `Eliminar` (`.dz-sep` separator + danger ghost)
- Brief chips: 4–5 IA-marked (`.brief-chip.from-ia`) + slot "+ agregar" abierto
- Botón `Continuar a contexto` primary (sticky bottom)

#### `00-paso1-C-procesando.html` — IA procesando
- Filecard se mantiene
- Brief chips reemplazados por `<Skeleton>` rows (`.skel.sk-w-*`)
- `.status-bar` con vbubble think + texto "Valentina analizando el plano…"
- A 8s: `.status-bar.slow` (variant ámbar) + `.elapsed` "12s" + `.fallback-btn` "Completar a mano"
- CTA primary disabled

#### `01-contexto-A-ia-propuso.html` — Paso 2 IA propuso
- Stepper: `done done now pending pending`
- `.ia-banner` "Valentina propuso este contexto a partir del plano y del histórico"
- 2 tablas (`cols-220-1fr-140-60`):
  - **Cliente**: nombre / dirección / tipo / contacto
  - **Obra**: piezas detectadas summary (no detalle, eso va en paso 3)
- `.confirm-bar` abajo: summary mono + botones `Editar contexto` (ghost) + `Confirmar y seguir` (primary)

#### `02-contexto-B-marina-edito.html` — Marina editó
- Misma estructura que A
- Filas con `.cell.edited` → púrpura + ✏
- `.row.row-edited` highlight en la row entera
- `.k.k-edited` chip "EDITADO" en eyebrow
- Sub `.sub.sub-edited` con valor anterior tachado: "↳ era 'Av. Cabildo 1234'"
- `.ia-banner.muted` (vbubble opacity 0.55) reemplaza al banner IA original — Valentina "se queda quieta" cuando Marina toma control

#### `03-contexto-C-chat-abierto.html` — Chat abierto
- `.body` cambia a 2 cols (`1fr 480px`)
- Tabla del lado izq se contrae (algunos cells se truncan)
- `<ChatPanel>` derecha sticky:
  - Head: vbubble think + "Valentina" + "Paso 2 · Contexto" sub mono + close
  - Scope: pill "Paso 2 · Contexto"
  - Stream: msg user "¿podés revisar el contacto?", msg.v con `.body` + `<em>` accent
  - Sugs: chips `Cambiar dirección` / `Agregar contacto secundario` / `Editar tipo cliente`
  - Composer: input + send accent
- Cuando msg.v menciona una row → `.row.row-chat-ref` highlight en la tabla

#### `04-despiece-A-ia-propuso.html` — Despiece IA
- `.ia-banner` "Valentina detectó 7 piezas en el plano"
- `<EditableTable cols-despiece>` 8 columnas:
  - SKU · Etiqueta · Largo · Ancho · Esp · Cant · Material · ⋯
- Group dividers `.group` separan ambientes ("Cocina", "Baño")
- `.add-row` al final de cada group
- Confirm-bar abajo

#### `04-despiece-A-completar-a-mano.html` — Manual fallback
- `.ia-banner.warn` "Valentina no pudo extraer el despiece" + actions: "Completar a mano" / "Reintentar"
- Tabla con `.row.row-empty` en blanco, placeholder italic dim
- `.row.row-empty.cursor` primera row con cursor blink en label cell
- `.status-bar.manual` púrpura "Modo manual · Valentina pausada"

#### `04-paralelismo.html` — IA vs manual side-by-side
- 2 columnas idénticas, una con `.ia-banner` y otra con `.ia-banner.warn`
- Educacional / referencia · NO es estado real del flujo, es para diseño/audit

#### `05-despiece-B-marina-edito.html` — Despiece editado
- Filas púrpura + sub-was-value `↳ era 240cm`
- Si dimensión absurda (> 400cm) → `.cell.err` + `.err-msg`
- Confirm-bar: summary "7 piezas · 6 confirmadas · 1 con error"

#### `06-despiece-C-chat-abierto.html` — Chat
- Como el 03 pero scope "Paso 3 · Despiece"
- Sugs: `Recalcular merma` / `Cambiar material` / `Sumar bacha`

#### `07-paso4-A-ia-propuso.html` — Cómputo
- Top: `<CalcBanner>`
  - L1 sistema mono: "✓ cálculo completado · 7 piezas · 12.4m² · USD/ARS@1430"
  - L2 Valentina: vmini + "Valentina ajustó: <em>+8% merma</em> · <em>flete largo</em> · <em>recargo edificio</em>"
- `<TipoToggle>` top-right segmented Particular/Edificio
- 4 `<CalcSection>` consecutivas:
  1. **MATERIAL**: row-line(s) m² · USD/m² · subtotal · `.subtotal`
  2. **MERMA**: rowline + `.merma-stock` toggle (o `.merma-na` si NA)
  3. **MO**: `<EditableTable cols-mo>` con SKU · Desc · Cant · Base · ×1.21 · Total · ⋯ + `.iva-toggle` chip en `.section-head` (`body[data-iva="off"]` colapsa cols)
  4. **FLETE**: simple row-line + km input
- Opcional: **PILETAS** inline (`piletas-inline`, solo `.sh`) si "cliente la trae"
- `.sobrante-opt`: dashed border, checkbox + label clickeable
- `<GrandTotal>` bicurrency (USD izq · ARS der, divider central serif italic 30px)

#### `07-paso4-A-v4.html` — variante v4
- Iteración de diseño posterior. Diff con v1: layout más denso, copy más corta. Implementar v4.

#### `08-paso4-B-error-validacion.html` — margen negativo
- Tras editar precio, margen baja a -3% → row "Margen" en `.row.err`
- Al confirmar: `<Modal>` (backdrop blur)
  - Eyebrow rojo: "ATENCIÓN"
  - H3 serif italic: "Estás forzando un margen negativo"
  - Body: explicación + `.impact` block mono "Margen actual: -3% · pérdida estimada USD 1,240"
  - Textarea required "¿Por qué? (queda en audit log)"
  - Audit-note mono "se registra con tu usuario y timestamp"
  - Foot: `Cancelar` ghost + `Forzar y seguir` `.btn.danger`

#### `09-paso4-C-chat-abierto.html` — chat paso 4
- Scope "Paso 4 · Cómputo"
- Sugs: `Aplicar 10% descuento` / `Cambiar material` / `Recalcular flete`

#### `13-audit-banner-on.html` — debug banner
- `.audit` rojo en top de pantalla (entre topbar y qhead)
- Pulse dot + texto mono "AUDIT MODE · 3 ediciones humanas en este flujo · ver auditoría"
- Link subraya
- En producción: solo internal users / dev mode

#### `15-ia-error.html` — error IA en paso 3
- `.ia-banner` rojo (variante warn más fuerte)
- "Valentina falló · reintentar / completar a mano"
- Tabla en blanco con `.row.row-empty`

#### `16-empty-despiece-lateral.html` — empty hero
- Page chrome normal pero `.body` sin tabla
- `<EmptyHero>`:
  - Glyph dashed 44×44
  - H3 serif italic "<em>Necesitás un despiece</em> para seguir"
  - Lead: "Marina, podés <em>subir un plano nuevo</em>… o <em>completar a mano</em>"
  - `<EmptyPaths>` 2 cards:
    - Primary: "Subir plano" (icon + ttl + desc + meta `recomendado`)
    - Secondary: "Completar a mano"
- Aside: `<ChatPanel.empty>` (vbubble dim, scope dashed pill, msg empty serif italic, composer disabled)
- Stepper: pasos posteriores `pending` con dashed circle + "· pendiente"
- `body[data-empty-prev="true"]` reduce padding-bottom

#### `17-chat-error-ia.html` — chat respuesta falló
- ChatPanel normal pero última `.msg.v` con `.error`
- Body: "No pude procesar eso. <em>Reintentar</em> o <em>reformular</em>"
- Feedback row con botones "Reintentar" + "Reportar"

#### `18-paso5-A-preview.html` — preview PDF
- `.body` 2 cols: PDF preview (mock, paper-bg) izq + `.pdf-sidebar` der
- Sidebar: acciones (Generar PDF / Vista previa / Editar / Compartir) — sticky bottom CTAs
- Top: summary numbers (#piezas, total, vencimiento)

#### `19-paso5-B-confirmar.html` — confirm
- Modal-like (no modal real, in-page) con resumen final
- Toggle "enviar por email" + input + send

#### `20-paso5-C-generado.html` — PDF generado
- `.pdf-sidebar` muestra estado "Generado · v1 · hace 2 min"
- Acciones: descargar / copiar link / enviar por WhatsApp / por email

#### `21-paso5-D-revision-v2.html` — revisión v2
- `.diff-drawer` arriba (sticky), lista de cambios v1→v2:
  - Cada DiffEntry: field path mono + prev (line-through) + arrow + next (accent)
- PDF preview muestra v2

#### `22-paso5-E-vencido.html` — vencido
- Frame label `.state.warn` "VENCIDO"
- Banner rojo en top "Este presupuesto venció el 28/04/2026"
- CTA primary: "Renovar (genera v2)"
- PDF preview con marca de agua "VENCIDO"

#### `23-paso-dashboard-A-mobile.html` — dashboard mobile lista
- `.mob` 375px
- Header con avatar Marina + título "Mis presupuestos"
- Lista de cards: cliente · status pill · paso actual · fecha · monto
- Filtros chip-row (Todos / En curso / Enviados / Vencidos)
- FAB bottom-right "+ Nuevo"

#### `24-paso-dashboard-B-mobile-detalle.html` — detalle mobile
- Tap en card → vista detalle
- Header con back + título quote
- Stepper compacto (5 dots)
- Bloques info: cliente, piezas, total
- `.mfoot.sticky` con CTAs "Ver PDF" + "Continuar"

#### `25-paso-dashboard-C-desktop.html` — desktop completo
- `<PageShell>` + `<Sidebar>` + `<Topbar>` normal
- Body: tabla de quotes (sortable) con filtros sticky top
- Side metrics row: 4 cards (Total mes, En curso, Aprobados, Vencidos)
- Click en row → drawer / nav a quote

#### `10/11/12-mobile-*` — pasos 2, 3, 4 mobile
- Cada paso reproducido en `.mob` 375px
- IA banner se compacta a una línea con vbubble pequeño
- Tabla → cards stacked verticales (no scroll horizontal)
- Stepper compacto (5 dots con número en `now`)
- Chat: pantalla full bottom-sheet (no sidebar 480)
- `.mfoot.sticky` siempre con CTA primary del paso

---

## 12 · Comportamientos transversales

### Edición humana (`edited` púrpura)
1. Estado inicial: cell muestra valor IA (`origin: 'ia'`)
2. User tipea → `.cell.typing` (cursor blink, glow)
3. On blur con `value !== originalIA` → `.cell.edited` (push a `EditedField[]`)
4. Si user vuelve al valor original → `.cell.edited` se quita
5. La row hereda `.row-edited` si CUALQUIER cell está edited

### Chat scoped
- Scope se pasa en query params o context: `{ step, refRows? }`
- Chat side-effect: cuando IA responde mencionando una row, post-message `{ refRows: [id] }` → tabla aplica `.row-chat-ref` por 4s, luego fade
- Close chat = state `chatOpen: false` por step (no cierra global)

### Loading IA (`<StatusBar>`)
- Default: 0–8s, `.status-bar` think animation
- 8s+: agregar `.slow` modifier, mostrar `.elapsed` + `.fallback-btn`
- User click `.fallback-btn` → `.status-bar.manual`, mode swap one-way (no vuelve auto)

### Validaciones (cell.err)
- Reglas por categoría:
  - Dimensiones: 1 ≤ valor ≤ 400 cm
  - Cantidad: ≥ 1
  - Precios: > 0
  - Margen: warn si < 5%, error+modal si < 0
- `.err-msg` tooltip queda visible mientras la row tiene foco

### IVA toggle
- `body[data-iva="off"]` (toggle off) → CSS colapsa cols Base + ×1.21 en MO table
- `<IVAToggle>` controla este atributo body-level (o context)

### Bicurrency
- Source of truth: `Computation.totalUSD`
- Display: `totalUSD` y `totalARS = totalUSD × exchangeRate`
- `<GrandTotal>` muestra ambos en serif italic 30px, divider central
- Header chip top-right del paso 4: `USD/ARS @ 1430` (clickeable → modal cambiar)

### Audit log
- Toda edición humana, todo forzado de margen negativo, todo "no útil" en chat → push a `audit_log`
- `.audit` banner se enciende cuando hay 1+ entries en quote actual
- Click banner → drawer con todas las entries

### Versioning
- Cada vez que Marina envía PDF y luego edita → snapshot v(n+1)
- DiffDrawer en mockup 21 visualiza el diff
- `QuoteVersion[]` mantiene el historial

---

## 13 · ⚠️ NO reproducir literal

### `chrome.js`
Es un **inyector DOM** que reproduce el sidebar/topbar en cada mockup HTML standalone para evitar duplicar markup. **En el codebase target NO reproducir esto** — usar layouts de Next.js (`app/layout.tsx` con sidebar fijo + outlet). El JS está incluido para que el dev pueda leer la estructura HTML que genera y replicarla en JSX.

### `bug-report.js`
Widget de feedback flotante. **Reemplazar** con el sistema interno (Linear / Sentry user feedback / lo que use D'Angelo). El diseño visual del widget (botoncito esquina + drawer) sí es referencia.

### `dashboard-dataset.js`
Mock data. **Usar como seed** para tests / Storybook fixtures. Estructura es canónica (matches `Quote` interface en §10).

### `frame-label`
El caption mono que aparece arriba/debajo de cada mockup ("01 · Paso 1 · Upload — A · vacío") es **solo del audit pack**. NO renderizar en producción.

---

## 14 · Assets

| Archivo | Uso | Notas |
|---|---|---|
| `assets/logo-dangelo.png` | Brand sidebar + PDF cotización | Confirmar versión final con D'Angelo (puede que tengan SVG vectorial mejor) |
| Fraunces / Inter Tight / JetBrains Mono | Tipografías | Cargar de Google Fonts (free) |
| Iconos | Inline en HTMLs como SVG o ✓/✏/⋯/× chars | Reemplazar con icon set del codebase (Lucide / Heroicons / etc.) — la convención visual es trazo fino, monocromo `--ink-soft` |

---

## 15 · Fases sugeridas de implementación

1. **Tokens + chrome** — sidebar, topbar, qhead, stepper. Storybook con los 3.
2. **EditableTable** — el componente más crítico, reutilizado en pasos 2/3/4. Estados completos.
3. **ChatPanel** — sticky, scoped, con todos los msg states.
4. **Paso 1 → 5 happy path** — un paso por sprint.
5. **States especiales** — error IA, vacío, vencido, audit banner.
6. **Mobile** — adapter de cada paso a 375px.
7. **Dashboard** — last, depende de todo lo anterior.

---

## 16 · Preguntas abiertas (para confirmar con product)

- ¿La IA real ya está conectada? (assume no, mocks por ahora)
- ¿El PDF se genera client-side (jsPDF/react-pdf) o server-side?
- ¿Auth — quién accede al audit log además de Marina?
- ¿Multi-tenant? (D'Angelo es un cliente — habrá más marmolerías?)
- ¿i18n? — todo está en español rioplatense ahora; confirmar si hay que abstraer copy.

---

**Fin del README.** Para guidelines específicas para Claude Code en el repo target, ver `CLAUDE.md`.
