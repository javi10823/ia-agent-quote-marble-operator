# Master · Diseño completo · Handoff Claude Code

**Status:** AUDIT VISUAL CERRADO · 04.05.2026. Los 8 flows de mockups del Sprint 1.5 pasaron audit independiente con Playwright sobre `originals/X.html` (ver sección 20). Pendiente para definitivo: ítem 4 del Sprint 1.5 (copy-log script `bug-report.js`) que tiene su propio ciclo de audit separado del audit visual.

**Quién lee esto:** cualquier agente o persona que vaya a tocar el código del operator panel D'Angelo. Incluye Claude Code para implementación, Javi para review, equipo backend para integración.

**Qué reemplaza:** consolida y supera todas las páginas de tracking previas. Los errores históricos (canon "Pereyra" del 07 v4 — el case real es **Cueto-Heredia**) están corregidos acá.

**Versión Notion (puede tener cambios más recientes):** https://www.notion.so/356e083d140a8167b49cdeeefb5b5c2f

---

## 1 · Cómo leer este documento

Orden recomendado para alguien que arranca de cero:

1. Sección 2 (visión + producto)
2. Sección 3 (stack + cómo conecta frontend↔backend)
3. Sección 4 (sistema de design + principios)
4. Sección 5 (flujo y mapeo UI↔backend)
5. Sección 6 (los 30 mockups con su case correcto)
6. Sección 7-9 (modelo de cálculo + reglas + componentes)
7. Sección 10-12 (decisiones, bugs, datos canónicos)
8. Sección 13 (limitaciones del mockup que NO se copian a producción)
9. Sección 14 (features backend que NO están en mockup todavía)
10. Sección 15-16 (sprints + archivos para handoff)

Tiempo estimado lectura completa: 30-40 min. Lectura express (solo headers + tablas): 10 min.

---

## 2 · Producto: Operator AI Scoped

**Persona:** Marina, operadora de Marmolería D'Angelo (Rosario, Argentina). Hoy arma presupuestos en planilla + WhatsApp. Cada presupuesto le toma ~45 min. La IA "general" la frustra: contesta cosas obvias, no sabe del taller, le come tiempo en vez de ahorrarlo.

**Hipótesis:** una IA *scoped por sección* (no asistente global) que **propone primero y se calla después** baja el tiempo a ~12 min y le devuelve a Marina la sensación de control.

**Personaje IA:** Valentina, agente de presupuestos de D'Angelo. Tono rioplatense informal, primera persona, itálica serif para destacar su voz. Sus inferencias y sugerencias se marcan con avatar `.vbubble` celeste. Las ediciones de Marina se marcan en púrpura — Valentina nunca las pisa.

---

## 3 · Stack y arquitectura

**Backend (en producción, maduro):**

| Capa | Tech |
|---|---|
| API | FastAPI 0.115 + Python 3.12, async/await |
| ORM | SQLAlchemy 2.0 async (asyncpg) |
| DB | PostgreSQL (Railway) |
| LLM | Anthropic Claude Sonnet 4.5 + Opus 4.6 (lectura visual de planos modo dual) |
| PDF | fpdf2 programático (NO templates HTML) |
| Excel | openpyxl |
| Drive | Google Drive API (Service Account) |
| Streaming | SSE |
| Frontend | Next.js 14 + TypeScript + Tailwind |
| Deploy | API → Railway · Web → Vercel |

**Repo:** `ia-agent-quote-marble-operator`

**Lo que ya existe en backend (NO greenfield):**

- `calculate_quote()` función pura determinística — paso 4 del mockup conecta acá
- `audit_events` tabla Postgres — alimenta el panel `.aud-trail` per-row
- ~30 endpoints REST + SSE streaming chat con Valentina
- Modelo `Quote` rico: `parent_quote_id`, `comparison_group_id`, `quote_kind` (standard / building_parent / building_child_material / variant_option), `change_history`, `email_draft`, `condiciones_pdf`, `resumen_obra`
- Bot externo `/api/v1/quote` separado del operator UI
- Generación PDF programática + upload Drive automático

**Implementación = wire-up del frontend nuevo (mockups) contra estos endpoints.** No es construcción.

---

## 4 · Sistema de design

**6 principios UX:**

1. IA propone, humano decide. Edición no se pisa.
2. Scope acotado por paso. El chat de "Contexto" solo ve los campos del contexto, no el despiece.
3. Click directo = editar. Sin "modo edición". Tab/Enter avanza, Esc cancela.
4. Confirmar y seguir. Sin modal entre pasos (solo en paso 5 que tiene side-effect externo).
5. Loading sin spinner full-screen. Skeletons en celdas + status-bar inferior.
6. Reversibilidad barata. Toda edición se puede deshacer.

**Estados por sección:**

| Estado | Cuándo | Marca visual |
|---|---|---|
| **A · IA propuso** | Primera vez. Datos pre-cargados, nada editado. | Banner celeste neutral |
| **B · Marina editó** | Marina tocó algún campo. | Borde izq púrpura + ✏ + chip "EDITADO" |
| **C · Chat scoped abierto** | Marina abrió panel derecho. | Panel 480px lateral · fila referida con outline celeste |

**Tokens (CSS vars en operator-shared.css):**

```
--accent       celeste IA (propuesta de Valentina)
--human        púrpura oklch(0.74 0.09 300) — editado por Marina
--ok --warn --info --error    semánticos
--ink --ink-soft --ink-mute    texto
--bg --bg-muted --surface --surface-2    superficies
--serif (Fraunces)  --sans (Inter Tight)  --mono (JetBrains Mono)
--r-sm 6  --r-md 10  --r-lg 14    radii
```

**Paleta dark, fondo `#0f1318`. Por qué púrpura para edición humana:**

- No coincide con ningún semántico existente (verde=ok, ámbar=warn, rojo=error, celeste=IA)
- Misma luminosidad que celeste IA → no compite jerárquicamente, indica autoría
- Accesible sobre fondo `#0f1318` (contraste 4.6:1)
- Sin carga cultural en taller (no es "rojo=malo" ni "verde=bien")

---

## 5 · Flujo y mapeo UI ↔ backend

El frontend muestra **5 pasos visuales**. El agente Valentina ejecuta **3 pasos backend**.

```
UI (5 pasos)               Backend (3 pasos Valentina)        Tools
────────────────────────  ────────────────────────────────  ─────────────────────
Paso 1 · Brief upload   ┐
Paso 2 · Contexto       ┴→ pre-Paso 1 (validation)         (no LLM tools)
Paso 3 · Despiece       →  Paso 1 Valentina               list_pieces
Paso 4 · Cálculo        →  Paso 2 Valentina               calculate_quote
Paso 5 · PDF            →  Paso 3 Valentina               generate_documents
```

**Reglas hard del agente que el frontend debe respetar:**

- Cliente Y proyecto bloqueantes (sin los dos, Valentina NO arranca)
- PROHIBIDO en Paso 1 llamar `catalog_lookup`, `catalog_batch_lookup`, `calculate_quote`. Solo `list_pieces`
- `list_pieces` rendera Paso 1 con texto exacto — frontend NO recalcula m² manualmente
- Frases prohibidas: "mientras", "voy a buscar", "dejame verificar", "voy a recortar", "¿Es edificio?"
- Excepción edificio: si recibe JSON pre-calculado del sistema de edificio, NO llamar list_pieces

---

## 6 · Los 30 mockups con su case correcto

**Importante:** el case canon del **flow desktop** es **Cueto-Heredia**, no Pereyra. Pereyra solo aparece en el mobile flow y en el dashboard detalle 24.

### Paso 1 · Brief (3)

| Mockup | Case | Notas |
|---|---|---|
| `00-paso1-A-vacio` | sin quote | hero Valentina + dropzone PDF + chips opcionales |
| `00-paso1-B-subido` | Cueto-Heredia · borrador sin ID | PDF cargado + 2 fotos + textarea brief |
| `00-paso1-C-procesando` | Cueto-Heredia · borrador sin ID | status-bar slow + skeleton + cancelar |

### Paso 2 · Contexto (3) · case Cueto-Heredia · Negro Brasil

| Mockup | Estado |
|---|---|
| `01-contexto-A-ia-propuso` | A · 11 campos extraídos + agrupados |
| `02-contexto-B-marina-edito` | B · 3 campos editados en púrpura |
| `03-contexto-C-chat-abierto` | C · chat 480px scoped |

### Paso 3 · Despiece (5) · sin cliente visible (solo piezas)

| Mockup | Estado |
|---|---|
| `04-despiece-A-ia-propuso` | A · 5 piezas + skel R6/R7 + 4 pasadas timeline |
| `04-despiece-A-completar-a-mano` | fallback manual |
| `04-paralelismo` | B3 fix "era 240cm" |
| `05-despiece-B-marina-edito` | B · cantidades editadas |
| `06-despiece-C-chat-abierto` | C · consulta sobre R2 (bacha) |

### Paso 4 · Cálculo (4) · case Cueto-Heredia

| Mockup | Material | Notas |
|---|---|---|
| `07-paso4-A-ia-propuso` (v3 LEGACY) | Silestone Blanco Norte | Modelo viejo con margen — solo referencia histórica |
| `07-paso4-A-v4` ✅ CANONICAL | Silestone Blanco Norte | Modelo nuevo (Material/Merma/MO/Piletas/Flete/Total) |
| `08-paso4-B-error-validacion` | Negro Brasil (post-cambio) | Escenario A5: Marina cambió material sin recalcular, merma fantasma |
| `09-paso4-C-chat-abierto` | Silestone Blanco Norte | Chat scoped sobre paso 4 |

### Paso 5 · Preview/PDF (5) · case Cueto-Heredia · Silestone

| Mockup | Estado |
|---|---|
| `18-paso5-A-preview` | PDF preview + sidebar live-edit |
| `19-paso5-B-confirmar` | modal confirmación + bullet "guardado local + Drive" |
| `20-paso5-C-generado` | sidebar 5 bloques (PDF + Excel + share) |
| `21-paso5-D-revision-v2` | diff drawer side-by-side v1↔v2 |
| `22-paso5-E-vencido` | banner rojo + renovar/perdido + tracking visitas |

### Mobile flow (3) · case **Familia Pereyra** · Negro Brasil

| Mockup | Notas |
|---|---|
| `10-mobile-contexto-A` | paso 2 en 375px |
| `11-mobile-despiece-A` | paso 3 en 375px |
| `12-mobile-paso4-A` | paso 4 en 375px |

### Bloque E · Dashboard (3)

| Mockup | Case |
|---|---|
| `23-paso-dashboard-A-mobile` | sin quote (lista) |
| `24-paso-dashboard-B-mobile-detalle` | **Pereyra · PRES-2026-017** · Silestone (este SÍ es Pereyra) |
| `25-paso-dashboard-C-desktop` | sin quote (lista) |

### Extras (4)

| Mockup | Notas |
|---|---|
| `13-audit-banner-on` | debug ON con trace_id, tokens, prompt_v |
| `15-ia-error` | IA "no me sirve" + rehacer + cargar a mano |
| `16-empty-despiece-lateral` | estado vacío paso 3 |
| `17-chat-error-ia` | chat con error de IA |

**Total: 30 mockups standalone bundleados.**

---

## 7 · Modelo de cálculo cerrado (paso 4)

**No existen** en el modelo:

- ~~Margen taller 22%~~
- ~~Costo subyacente~~
- ~~Subtotal antes de margen~~
- ~~Slider de margen~~
- ~~Forzar margen negativo~~ (modal A3 reusa nombre, ahora es "forzar omitir COLOCACION")

**Estructura real:**

```
1. MATERIAL          m² × precio c/IVA + descuentos
                     Solo 1 descuento por presupuesto
                     · arquitecta 5% importado / 8% nacional
                     · edificio 18% si m²>15
                     · si aplican 2, usar el mayor

2. MERMA / SOBRANTE  condicional por material
                     · Sintéticos (silestone, dekton, neolith, puraprima, purastone, laminatto):
                       desperdicio <1m² → no aplica
                       desperdicio ≥1m² → aplica sobrante a mitad de precio (opcional)
                     · Granito Negro Brasil → NUNCA lleva merma (regla absoluta)
                     · Piedra natural (granito/mármol) → sin merma
                     · Cuarto estado: stock confirmado en taller (toggle editable)

3. MANO DE OBRA      tabla SKUs · cant × base s/IVA × 1,21 = total c/IVA
                     SKUs: PEGADOPILETA, AGUJEROAPOYO, COLOCACION, COLOCACIONDEKTON,
                     ANAFE, REGRUESO, FALDON, FALDONDEKTON, CORTE45, CORTE45DEKTON,
                     TOMAS, PUL, PUL2, MDF
                     · Si material es sintético → SKUs DEKTON automáticamente
                     · Edificios → MO ÷1.05

4. PILETAS           1 línea por pileta
                     · Si cliente la trae → solo PEGADOPILETA en MO
                     · Si Johnson → línea con modelo + precio
                     · Edificios → ÷1.05

5. FLETE             1 línea (ENVIOROS u otra zona)
                     · Edificios → ceil(piezas/6) viajes

6. GRAND TOTAL       bicurrency, dos cifras grandes
                     ARS = MO + piletas + flete (+ material si nacional)
                     USD = material (si importado)
```

**Reglas de redondeo (centralizadas en `calculator.py`):**

| Valor | Regla |
|---|---|
| m² por pieza | sin redondear |
| m² total | round 2 dec |
| Precio USD unitario | floor (truncar) |
| Total material USD | round entero |
| Precio ARS MO | round entero |
| Colocación qty | = m² total con max(_, 1.0) |

**IVA:** flag `price_includes_vat` por item del catálogo. Si `true`, precio JSON ya incluye IVA. Si `false`, multiplicar por 1.21.

---

## 8 · Reglas Valentina vs Sistema

**Valentina** (vbubble + serif italic):

- Inferencias (cocina→empotrada, isla→PEGADOPILETA, alzada→TOMAS)
- Detecciones de símbolos del plano (INGLETE, DESAGUE, anafe)
- Match parcial de arquitecta
- Sugerencias de descuento
- Advertencias contextuales
- Resolución de ambigüedades

**Sistema** (sin vbubble, mono):

- `catalog_batch_lookup` (precios)
- `calculate_quote` (m², merma, totales — determinístico)
- IVA ×1,21 (regla absoluta)
- Reglas duras (Negro Brasil sin merma, descuento solo material, edificio sin colocación)
- Audit log (trace_id, timestamp, usuario)

---

## 9 · Componentes reusables

**Resumen del inventario en operator-shared.css:**

```
Layout      .page · .body · .sidebar · .topbar · .qhead · .stepper
IA banner   .ia-banner (+ .vbubble avatar)
Tabla       .etable · .colh · .group · .row.row-edited · .cell.edited · .cell.err · .input · .add-row
Origin chip .k (DEL BRIEF, DEFAULT, INFERIDO, FALTA, EDITADO)
Loading     .skel · .status-bar · .vbubble (animado)
Footer      .confirm-bar
Buttons     .btn · .btn.primary · .btn.ghost · .btn.sm · .btn.icon
Chat        .chat · .head · .scope · .stream · .sugs · .composer · .msg.user · .msg.v · .sug
Mobile      .mob · .mhead · .mstep · .mfield · .litem · .pcard · .mfoot · .mfilter-chip · .mob-bottom-info
Dashboard   .status-chip (.draft .sent .expired .lost) · .kpi-card · .kpi-card.urgent · .kpi-card.warn
Audit       .aud-i (trigger ⓘ) · .aud-trail (panel inline) · .audit-toggle (pill)
Copy log    .btn-copy-log (idle / copied / error)  ← Sprint 1.5 ítem 4
```

**Animaciones:** `pulse` (audit banner), `think` (avatar Valentina), `skel` (shimmer loader).

**Detalle completo de componentes:** ver `docs/handoff-design/README.md` §8.

---

## 10 · Decisiones cerradas

| # | Decisión | Resolución |
|---|---|---|
| 1 | Persistencia chat | Borra al cerrar (deliberado) |
| 2 | Multi-material | Postergar implementación a Sprint 4 (modelo backend ya soporta) |
| 3 | Particular/Edificio | Toggle visible paso 2 + inferencia rica Valentina |
| 4 | Banner paso 4 híbrido | Línea 1 cálculo sistema, línea 2 ajustes Valentina vbubble |
| 5 | Negro Brasil moneda | USD (importado) — NUNCA lleva merma |
| 6 | Modo PATCH default | Surgical edit, recalcular todo = excepción explícita |
| 7 | Margen | NO existe en el modelo |
| 8 | Audit per-row | `.aud-i` ⓘ + `.aud-trail` panel inline (visible cuando data-audit=on) |
| 9 | Densidad | Media (14px base, 14-16px padding) |
| 10 | Ediciones IA | NO se pisan al re-generar (preserva púrpura) |
| 11 | Audit visibility | Off default, on por config |
| 12 | Tono Valentina | Rioplatense informal, primera persona, serif itálica |
| 13 | Mobile read-only | Mobile NO crea quotes, solo consulta (Bloque E) |
| 14 | PDF replica formato real D'Angelo | sí, programático con fpdf2 |
| 15 | Sidebar paso 5 sin scroll interno | sí |
| 16 | Forma de pago | NUNCA preguntar, siempre "Contado" |
| 17 | Footer obligatorio | "No se suben mesadas que no entren en ascensor" — en producción se inyecta desde settings |
| 18 | Naming PDF | `Cliente - Material - DD.MM.YYYY.pdf` auto |
| 19 | Excel + Drive | Generación atómica con PDF (`generate_documents`) |
| 20 | Compartir con cliente | Solo PDF (Excel es interno del taller) |
| 21 | Diff drawer | 400px lateral, side-by-side v1↔v2, púrpura |
| 22 | Eliminar pending-review | Marina opera sola, no review system. Bustos+Roca → draft |
| 23 | Audit per-row sistema | Tooltip nativo (.aud-i title="") + panel inline (.aud-trail) |
| 24 | chrome.js sin hardcode | refactor para data-attrs por mockup |

---

## 11 · Decisiones abiertas críticas

| Decisión | Estado | Impacto |
|---|---|---|
| Datos fijos sistema en PDF (footer, Contado, naming) | ✅ resuelto: settings backend inyecta · mockup hardcodea para fidelidad visual | bajo |
| Multi-material | ✅ Sprint 4 implementación · backend ya soporta | medio |
| Edificio vs Particular | ✅ toggle paso 2 + inferencia Valentina | medio |
| Handoff Agos | ✅ NO hay sistema de review · Marina opera sola | resuelto |
| Anticipo % default real D'Angelo | ⚠️ pendiente confirmar · sospecha 70% particulares | bajo · cosmético |
| Diff v1↔v2 drawer pattern | ✅ confirmado: drawer derecho 400px side-by-side | resuelto |
| Spec "Aplicar simulación al breakdown" en mockup 09 | ⚠️ pendiente definir comportamiento exacto | bajo |

---

## 12 · Bugs conocidos

### P2 cosmético · Precio Silestone Blanco Norte

Mockup 07 v4 muestra USD 249/m² c/IVA. Catálogo dice USD 429 s/IVA = USD 519 c/IVA. Diff −52% en cifra material visible al cliente.

**No afecta producción** — `calculate_quote()` toma precios del catálogo real, los mockups son referenciales. **Sí afecta demo Marina**. Decisión Javi pendiente: actualizar dataset/mockups o actualizar catálogo.

### P3 info · 4 materiales fantasma en dataset

4 materiales del dataset compartido (23/25) NO existen en catálogo:
- Calacatta Borghini · Travertino Romano · Calacatta Statuario · Silestone Eternal Calacatta

**Implicancia Sprint 4:** si Claude Code valida materials.sku contra catálogo cuando levante el dashboard real, va a fallar para esos 4 quotes ficticios. Workaround: filtrar el dataset mock antes de poblar DB de testing, o agregar los 4 como SKUs de prueba.

### P2 · Subtotal MO 07 v4 diff $1

Suma de filas c/IVA = $597.971, subtotal claimed = $597.970. Cierre automático en Sprint 3 cuando paso 4 se conecte a `calculate_quote` real (deja de ser hardcoded).

---

## 13 · Datos canónicos de referencia

### Canon Cueto-Heredia · Silestone Blanco Norte (mockup 07 v4)

```
Material:
  Silestone Blanco Norte 20mm · 6,50 m² · USD 249/m² c/IVA = USD 1.619
                                          (precio del mockup - ver bug P2)
  Descuento arquitecta 5% (Cueto-Heredia) → USD 1.538

Mano de obra (5 ítems):
  COLOCACION    6,50 m² × $49.698  = $323.037 base
  PEGADOPILETA  1 × $53.840         = $53.840 base
  ANAFE         1 × $35.617         = $35.617 base
  REGRUESO      4,98 ml × $13.810   = $68.774 base
  TOMAS         2 × $6.461          = $12.922 base
  ----------------------------------------------
  Subtotal MO base s/IVA              $494.190
  IVA (×0,21)                          $103.780
  Subtotal MO c/IVA                   $597.970

Flete Rosario:                        $62.920
----------------------------------------------
TOTAL ARS:                          $660.890
Material USD (separado):              USD 1.538
```

**Verificación cruzada con catálogo real:** todos los SKUs MO (5/5) matchean exacto. Solo el precio Silestone Blanco Norte tiene diff −52% (bug P2 conocido, no bloqueante).

### Dataset compartido (23 ↔ 25 byte-identical)

```
Total: 47 quotes
  - draft:   6  (Sosa, Hauer, Bustos, Roca, +2 históricos)
  - sent:    12
  - expired: 3
  - lost:    26
  - total:   47 ✓

Visibles renderizados: 16 rows
PRES-2026-017 = Pereyra · Silestone · 6,50 m² · ARS $660.890 + USD 1.538
             ↑ caso del MOBILE DETAIL 24 (NO del flow desktop)
PRES-2026-018 = Cueto-Heredia · Negro Brasil · 8,40 m² · USD 2.184
             ↑ caso del FLOW DESKTOP completo (00 a 22)
```

---

## 14 · Limitaciones del mockup (NO copiar a producción)

Comportamientos del shell estático que **no son regresión** pero hay que refactorear al implementar:

1. **chrome.js** - en producción los valores `data-quote-id`, `data-quote-client`, `data-quote-project` vienen del state real del quote, no hardcoded en cada page.
2. **CSS comments legacy** ("A3 — Modal de forzar margen negativo") siguen en operator-shared.css. El modal A3 fue repurposed a "forzar omitir COLOCACION cuando enunciado la mencionaba". Comments → cleanup post-Sprint 5.
3. **Inline styles aceptables** - skeleton widths variables (`style="width: 70%"`) en mobile/paralelismo. Son data-shape, no estilo. Mantenidos a propósito.
4. **`<iframe srcdoc>` con HTML inlineado** (mockup 24) — copia literal del template, NO se sincroniza con archivos source separados. En producción el PDF se genera con `fpdf2`, no embebed HTML.
5. **Footer hardcoded en template Pereyra** (mockup 24) - en producción se inyecta desde settings backend. Mockup hardcodea para fidelidad visual.

---

## 15 · Backend features NO en mockup

Lo que el backend ya soporta pero los mockups todavía no muestran:

- **Multi-material** - `parent_quote_id` + `quote_kind=building_parent`/`building_child_material`. Sprint 4 lo implementa contra el modelo existente.
- **Bot externo `/api/v1/quote`** - separado del operator UI. El operador valida los quotes que entran por el bot.
- **`derive-material`** - genera variant_option con mismo despiece, otro material. UI pendiente.
- **`reopen-measurements` / `reopen-context`** - vuelve a Paso 1 / inicio preservando contexto. UI pendiente.
- **`zone-select`** - selecciona zona del plano para crop manual. UI pendiente.
- **`email-draft`** - borrador comercial generado por IA. UI pendiente.
- **`resumen-obra`** - consolida N quotes en PDF de obra. UI pendiente.
- **`client-match-check` / `merge-client`** - detecta y unifica duplicados. UI pendiente.
- **`condiciones_pdf`** - PDF de Condiciones de Contratación (solo edificios). UI pendiente.

**Decisión:** estas features se implementan **en orden de prioridad de Marina**, no todas en Sprint 2-5. Algunas pueden quedar para v1.1.

---

## 16 · Sprints planeados

| Sprint | Foco | Status |
|---|---|---|
| **1.5** | Cierre design (7 ítems) | 🟡 6/7 cerrados · ítem 4 (copy-log) en progreso |
| **2** | Wire-up frontend con design system + paso 1 + paso 2 | ⏳ |
| **3** | Paso 3 + paso 4 + observability per-row | ⏳ |
| **4** | Paso 5 + Bloque E + multi-material + email-draft | ⏳ |
| **5** | QA + performance + demo Marina | ⏳ |

**Estimación:** ~1 mes desde fin Sprint 1.5 a demo Marina.

---

## 17 · Archivos para handoff a Claude Code

Todo está en este branch `sprint-1.5/master-handoff`:

```
docs/
  master.md                          ← este archivo (resumen ejecutivo)
  handoff-design/                    ← spec técnica completa del design
    README.md                        ⭐ 819 líneas (spec UX + componentes + data model + interactions)
    CLAUDE.md                        ⭐ 140 líneas (instrucciones específicas Claude Code)
    design_tokens.ts                 ⭐ tokens en TypeScript const, importable
    design_tokens.json               tokens en JSON
    design_files/
      operator-shared.css            CSS canónico ~4707 líneas (post-audit visual)
      *.html                         30 mockups bundleados (referencia visual)
      chrome.js, bug-report.js       NO reproducir literal (ver §13 README handoff)
      dashboard-dataset.js           47 quotes mock para tests/Storybook
      assets/logo-dangelo.png
  handoff-context/                   ← specs técnicas backend
    README.md                        índice + nota PR `extract-api-contracts`
    (resto se llena con PR previo a Sprint 2)
.github/
  pull_request_template.md
  CODEOWNERS
```

**Acceso al repo:**
- GitHub: `javi10823/ia-agent-quote-marble-operator`
- Branch handoff: `sprint-1.5/master-handoff`
- Sub-branches Sprint 2 saldrán de `sprint-2/main` (a abrir después del PR `extract-api-contracts`)

---

## 18 · Lecciones de proceso

**Audit independiente es no-negociable.** Cada PR de Claude Code se audita antes de mergear, mismo workflow que validamos en Sprint 1.5 visual con Playwright sobre mockups.

**Errores históricos pueden propagarse durante audits.** El "canon Pereyra del 07 v4" arrastró por varios audits hasta que se detectó cruzando contenido de mockup vs spec. Lección: cuando haya canon de cifras, validar contra el contenido literal del mockup, no contra memoria de audits anteriores.

**Mockups son referenciales para producción.** Los precios pueden estar desactualizados (bug P2 Silestone). Producción usa `calculate_quote()` contra catálogo real. Mockups sirven para spec visual + flow + componentes, no para datos.

---

## 19 · Cierre Audit Visual Sprint 1.5

**Fecha cierre:** 04.05.2026 · **Método:** Playwright render-test independiente sobre `originals/X.html`, screenshots + medición DOM, regression check cross-flow.

### Estado por flow

| Flow | Mockups | Status | Iters fix |
|---|---|---|---|
| 01 · Upload | 00 A/B/C | ✅ OK | 1 |
| 02 · Contexto | 01, 02, 03 | ✅ OK | 1 |
| 03 · Despiece | 04, 04-pl, 05, 06, 16 | ✅ OK | 1 |
| 04 · Cálculo | 07 v4, 08, 09 | ✅ OK | 1 |
| 05 · Cotización | 18, 19, 20, 21, 22 | ✅ OK | 2 |
| 06 · Dashboard Marina | 23, 24, 25 | ✅ OK | 2 |
| 07 · Mobile pasos | 10, 11, 12 | ✅ OK | 1 |
| 08 · Estados especiales | 13, 15, 17 | ✅ OK | 1 |

**Total: 30/30 mockups bundleados, 8/8 flows verificados, 9 iteraciones de fix totales.** Cero regresiones acumuladas entre flows.

### Fixes sistémicos cerrados (operator-shared.css)

```
1. Layout viewport-fixed (desktop)
   .page  { height: 100vh; overflow: hidden }
   .main  { display: grid; grid-template-rows: auto auto auto 1fr; min-height: 0 }
   .body  { overflow-y: auto; min-height: 0 }
   → Marina nunca ve page-scroll, solo scroll interno del .body.

2. Fix B · buttons sin bg propio
   .chat .head .x-btn, .chat .sugs .sug, .pdf-sidebar .ps-input/.ps-textarea
   con bg explícito para evitar UA default gris/blanco.

3. Scrollbars finitas
   scrollbar-width: thin en .body, .chat .stream, .pdf-sidebar.

4. Tabla despiece (etable)
   .cell.label-cell con word-break: normal + overflow-wrap: break-word + min-width: 0
   → columna PIEZA no colapsa a vertical en chat scoped (700px disponibles).

5. Re-calcular CTA nowrap
   .recalc-btn con white-space: nowrap.

6. Sticky CTAs flow-05 (drawer + sidebar)
   .body.pdf-layout                 { grid-template-rows: 100% }   en ambos modos
   .pdf-sidebar, .diff-drawer       { display:flex; flex-direction:column;
                                      height:100%; max-height:100% }
   .dd-section                      { display:flex; flex-direction:column; flex-shrink:0 }
   .diff-drawer > .dd-section:has(> .dd-table)
                                    { flex:1; min-height:0; overflow:hidden }
   .dd-cta, .ps-cta                 { flex-shrink: 0; border-top: 1px solid var(--line) }
   → CTAs anclados al fondo del drawer/sidebar, contenido scrollea internamente.

7. [hidden] global con !important
   [hidden] { display: none !important; }
   → El atributo HTML hidden se respeta aunque la clase tenga display: flex/grid/block.
```

### Canon de formato · línea PRESUPUESTO TOTAL

Formato literal único válido en TODOS los outputs (PDF cliente, PDF taller, preview operator, PDF embebido en mobile detalle):

```
PRESUPUESTO TOTAL: $660.890 mano de obra + USD 1.538 material
```

Reglas no opinables:
- `"mano de obra"` agrupa TODO lo cobrado en pesos (MO base + IVA + flete). Etiqueta comercial D'Angelo, no descripción técnica.
- Sin espacio entre `$` y la cifra (`$660` no `$ 660`).
- Una sola línea, `white-space: nowrap`.
- `"USD 1.538 material"` con espacio entre USD y cifra (excepción al patrón anterior, así está en el PDF real D'Angelo).

Aplicado en mockups 18, 19, 20, 21, 22 + PDF embebido del mockup 24.

### Principios de interacción validados

**Auditabilidad sobre todo.** Cada turno IA queda en audit log con `trace_id` + hash de inputs. Nada se borra, ni respuestas marcadas "no útil". Tabla `audit_events` viva mientras el quote esté abierto.

**Feedback no-destructivo.** Marina puede rechazar respuestas IA con "esto no me sirve" sin perder historial. Valentina reconoce el error y ofrece reformular o cerrar. El mensaje rechazado queda visible con badge `MARCADO COMO NO ÚTIL · QUEDA EN HISTORIAL`.

**Empty states coordinados.** Si Marina entra a un paso sin contexto previo, paneles principal+sidebar muestran empty coordinado, no uno funcional y el otro vacío.

### Known issues post-handoff (no bloquean implementación)

Resuelven naturalmente al traducir mockups a componentes React reales en Claude Code. Iterar sobre HTMLs estáticos que van a ser refactoreados es desperdicio.

| # | Issue | Severidad |
|---|---|---|
| 1 | Drawer 21 · columna V2 wrappea celdas largas ("Datos de envío") | cosmético |
| 2 | Tabla 25 desktop · columnas estrechas + ~700px vacíos a la derecha | cosmético |
| 3 | Locale inconsistente · USD con coma (USD 2,184) vs ARS con punto (660.890) | data layer |
| 4 | UI native 24 · `"$ 660.890"` con espacio post-$ vs PDF canon sin espacio | decisión diseño |
| 5 | Filter chip strip 23 mobile · "Vencido (3)" cortado, scroll horizontal funciona | mejora opcional |
| 6 | Stepper mobile 10/11 · "BREAKDOWN" cortado en último step | mejora opcional |
| 7 | Math margen 12 · diff de $239 vs cálculo directo · validar contra modelo FastAPI real | validación modelo |

El #7 NO es bug visual — es validación contra el modelo de cálculo. Se resuelve cuando el frontend conecte a `calculate_quote()` real en Sprint 3.

---

## 20 · Estrategia de branching para Sprint 2-5

**Decisión:** Claude Code NUNCA trabaja sobre `main` directo. Todo Sprint 2-5 va en branches con PRs auditables.

### Estructura de branches

```
main
│
├── sprint-1.5/master-handoff       ← este branch · referencia local para Claude Code
│
├── sprint-1.5/extract-api-contracts ← PR previo a Sprint 2 (ver sección 21)
│
├── sprint-2/main                   ← branch integrador Sprint 2
│   ├── sprint-2/design-system-migration   ← tokens CSS → Tailwind config
│   ├── sprint-2/chrome-refactor           ← layout shell + viewport-fixed
│   ├── sprint-2/paso-1-brief-upload
│   └── sprint-2/paso-2-contexto
│
├── sprint-3/main
├── sprint-4/main
└── sprint-5/main
```

**Flow de PRs:**
- Sub-branches → PR contra `sprint-N/main` · audit independiente · merge cuando OK
- `sprint-N/main` → PR contra `main` · audit final del sprint · merge solo cuando todos los sub-PRs están adentro

### Reglas de engagement para Claude Code

```
1. NUNCA commit directo a main. Siempre branch.

2. Convención de nombres:
   - sprint-N/main          → branch integrador del sprint
   - sprint-N/<feature>     → sub-branches de trabajo

3. PRs:
   - Sub-branches → sprint-N/main (Javi review + audit)
   - sprint-N/main → main (audit final del sprint)

4. Antes de abrir PR de sub-branch:
   - Tests unitarios verdes
   - Build sin warnings
   - Lint pass
   - Si toca UI: screenshots de los mockups equivalentes en el PR description
   - Diff con el mockup original como referencia visual

5. main es deployable siempre. Nunca mergear algo que rompa main.

6. Si encontrás algo fuera del scope del PR, NO lo arregles.
   Anotalo en docs/known-issues.md y abrí issue separado.

7. Commits descriptivos en español. Convención conventional commits:
   feat(paso-2): wire chat scoped a SSE
   fix(despiece): regresión de label-cell wrap vertical
   chore(design-system): migrar tokens CSS a tailwind config
   test(paso-1): cobertura E2E para upload PDF
   docs(handoff): import master de Notion

8. NO arregles known issues post-handoff (sección 19 del Master)
   sin que Javi lo apruebe explícitamente.

9. Cifras canon Cueto-Heredia (sección 13) van en fixtures/tests,
   NO hardcodeadas en componentes. En producción viene de calculate_quote().

10. Si el audit independiente reporta bug bloqueante, abrí branch
    sprint-N/<feature>-fix sobre el sub-branch original (no nuevo desde main).
```

### Decisiones pre-Sprint 2 · RESUELTAS 05.05.2026

| # | Decisión | Resolución |
|---|---|---|
| 1 | Frontend Next.js previo en main | **c1) Path coexistence bajo `/v2`**. El frontend actual es producción viva (Vercel) con auth cross-origin, SSE chat, audit log, observability. Sprint 2 va bajo rutas `/v2/quotes/*` compartiendo `lib/api.ts` + middleware auth. Cuando Sprint 5 cierre, redirect `/quotes → /v2/quotes`. |
| 2 | CI/CD readiness | ✅ listo. GitHub Actions corre pytest backend + npm build/lint frontend. Vercel hace previews automáticos por branch. Branch protection main lockeada — admin bypass eliminado. |
| 3 | Auditor independiente | Instancia separada de Claude. Mismo workflow que Sprint 1.5 visual. |
| 4 | Mocks-first vs backend-first | **Mocks-first**. Sprint 2 cablea componentes contra mock data + fixtures basados en cifras canon Cueto-Heredia. Switch a backend real es 1 PR de Sprint 3 inicial. |
| 5 | Quién escribe specs API | **d4) Claude Code extrae contratos del backend en PR previo a Sprint 2** (`sprint-1.5/extract-api-contracts`). Javi NO es backend dev. Claude Code lee routers + schemas + tools del repo y genera specs Markdown. |

---

## 21 · PR previo a Sprint 2 · `extract-api-contracts`

**Antes de abrir `sprint-2/main`,** Claude Code ejecuta un PR de extracción de contratos API. Alcance acotado: NO escribe código de producción.

**Branch:** `sprint-1.5/extract-api-contracts` (sale de `sprint-1.5/master-handoff`)

**Output esperado en `docs/handoff-context/`:**

```
endpoints-spec.md           ← cada endpoint REST que el frontend usa:
                              método HTTP, path, request body shape (TypeScript-flavored),
                              response shape, error codes, ejemplos.
                              Agrupado por flow (auth, quotes, brief, context, despiece,
                              calculo, pdf, dashboard).

sse-spec.md                 ← protocolo SSE del chat Valentina:
                              event types (token, tool_use, tool_result, message_done, error),
                              payload shape de cada uno, reconexión, scope de mensajes.

schemas/
  quote.md                  ← modelo Quote completo en MD: campos, tipos, defaults,
                              relaciones, quote_kind enum, status enum.
  audit_events.md           ← schema audit_events: trace_id, hash, fields, valor pre/post.
  brief.md                  ← modelo Brief: PDF + fotos + textarea.
  context.md                ← 11 campos paso 2 con tipos + defaults.

catalog/                    ← 9 catálogos JSON copiados directo del backend
  materials.json
  labor.json
  sinks.json
  architects.json
  config.json
  delivery-zones.json
  stock.json
  finishes.json (si existe)
  edges.json (si existe)
```

**Reglas estrictas para Claude Code en este PR:**

1. NO escribir código de producción (.ts, .tsx, .py). Solo Markdown + JSON copiado.
2. NO inventar endpoints que no existen. Si un mockup sugiere un endpoint que no está implementado, anotar en `docs/handoff-context/missing-endpoints.md` para discusión.
3. Specs en formato TypeScript-flavored para que el frontend pueda copiar las types.
4. SSE spec con event types reales del backend, no inventados.
5. Catalog JSONs van **sanitizados** — sin precios reales si son sensibles, sin nombres de clientes reales.
6. NO incluir `.env`, credenciales, Service Account JSON, ni info personal de clientes.

**Estimación:** medio día Claude Code + 1 hora audit. Output: ~30 archivos, ~80-120KB.

**Audit del PR:**
1. Spec coherente con mockups — cada flow del Master §6 tiene sus endpoints documentados.
2. Cifras canónicas Cueto-Heredia presentes en los ejemplos.
3. SSE spec con todos los event types que aparecen en mockup 03/06/09 (chat scoped).
4. NO hay código de producción committeado.
5. NO hay credenciales en ningún archivo.

---

## 22 · Roles y orquestación Sprint 2-5

Hay 4 roles distintos coordinando Sprint 2-5:

| Rol | Quién | Qué hace | Qué NO hace |
|---|---|---|---|
| **Master/Audit** | Instancia Claude (chat con Javi) | Planifica, escribe en Notion, prepara prompts para Claude Code, audita PRs | NO ejecuta código. NO mergea. NO accede directo a GitHub. |
| **Claude Code** | Instancia con acceso al repo | Ejecuta sub-PRs, escribe código, lee repo, deriva specs, abre PRs ready-for-review | NO mergea a main. NO arregla cosas fuera de scope. NO inventa endpoints. |
| **Backend backend** | Instancia separada (solo Sprint 3+ si requiere cambios FastAPI) | Toca `agent.py`, `calculator.py`, schemas Postgres en repo backend | NO toca frontend. NO mergea a main del repo operator. |
| **Javi** | Único humano | Coordina, decide alcance, audita visualmente Vercel previews, mergea a main, pasa contexto entre instancias Claude | NO escribe código. NO escribe specs técnicas. NO autoriza bypass admin. |

**Flow típico de un sub-PR:**

1. **Master** prepara el prompt con alcance, criterio de aceptación, archivos a leer del handoff.
2. **Javi** copia el prompt y lo pega en **Claude Code** en su terminal.
3. **Claude Code** ejecuta: lee handoff, escribe código, abre PR contra `sprint-N/main`.
4. **Javi** abre el preview Vercel, ve si visualmente matchea el mockup.
5. **Master** audita el PR (estructura del código, regression check, screenshots Playwright).
6. **Javi** tiene 2 reportes (visual + técnico). Si OK, mergea. Si bugs, pasa instrucciones a Claude Code vía Javi.
7. Iterar hasta merge limpio.

**Lo que NO hacemos.** Javi no escribe Python, TypeScript, queries SQL, ni specs API. Toda decisión técnica fina sale de Master o de Claude Code. Javi juzga alcance + UX + producto.

---

*Última actualización: 05.05.2026 · Audit visual Sprint 1.5 cerrado + 5 decisiones pre-Sprint 2 resueltas + estructura real del branch handoff + roles definidos.*

*Esta página queda definitiva cuando se mergea el PR `sprint-1.5/extract-api-contracts` a `sprint-1.5/master-handoff` y arranca el primer sub-PR de Sprint 2.*
