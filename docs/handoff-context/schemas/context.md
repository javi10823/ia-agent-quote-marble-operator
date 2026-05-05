# Schema · Contexto (Paso 2)

> **Fuente:** `api/app/modules/quote_engine/context_analyzer.py` (build_context_analysis) + `api/app/models/quote.py` (columnas mirror) + `api/app/modules/agent/agent.py` (handlers de `[CONTEXT_CONFIRMED]`).
> **Última actualización:** 2026-05-05.

El "Contexto" del Paso 2 (Master §6 mockups `01-A`, `02-B`, `03-C`) es un híbrido: parte vive como **columnas dedicadas** del `Quote`, parte como **subobjetos en `quote_breakdown`** (cards de IA), parte se **infiere on-the-fly** desde el plano + brief. **No hay un schema único cerrado de "11 campos"** — esa frase del task brief es una abstracción del frontend. Esta página explica qué hay realmente.

> **🤔 Verificar con Javi:** la spec del task `extract-api-contracts` mencionaba "11 campos del paso 2" del mockup. La sección 4 del Master habla de "Estados por sección" pero no enumera los 11 campos. Necesito esa lista para mapear cada campo a su columna/breakdown path. Por ahora documento el universo entero.

---

## Mapa de fuentes

```
                    ┌───────────────────────────────────────┐
                    │        Paso 2 (mockup 01/02/03)       │
                    │     Tabla con 11 campos editables     │
                    └────────────────┬──────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
  Columnas Quote        quote_breakdown JSON              Cards IA
  (PATCH directo)       (estructura calculada)            (auto-generadas)

  client_name           material_name                     context_analysis_pending
  project               material_m2                       └─ data_known
  client_phone          material_currency                 └─ assumptions
  client_email          delivery_days                     └─ tech_detections
  localidad             discount_pct                      └─ pending_questions
  colocacion            sectors                           └─ sector_summary
  pileta                mo_items
  sink_type             merma                             dual_read_result (paso 3)
  anafe                 ...                               verified_context (post-confirm)
  is_building                                             verified_context_analysis
  notes
  pieces (input crudo)
  conversation_id
```

---

## Origin chip · 5 estados (Master §9)

Cada campo del Paso 2 tiene un **origin chip** que indica de dónde salió el valor:

```ts
type OriginChipKind =
  | "DEL BRIEF"       // extraído del texto del operador
  | "DEFAULT"         // valor default del config
  | "INFERIDO"        // Valentina lo dedujo del plano/contexto
  | "FALTA"           // bloqueante — pending question
  | "EDITADO";        // Marina tocó el campo (push púrpura)
```

Esto es UI-only — el backend NO emite el chip directamente. El frontend lo deriva de:

- `data_known[].source` ("brief" | "operator" | "dual_read" | "default")
- `EditedField[]` del data model (Master §10) que el frontend mantiene en client state
- `tech_detections[].status` ("verified" | "needs_confirmation")
- `pending_questions[]` que vacían los `FALTA`

---

## Columnas mirror · `Quote` table

Editables vía `PATCH /api/quotes/{id}` (sin pasar por chat, sin recálculo):

```ts
interface QuoteContextColumns {
  client_name: string;            // VARCHAR(500)
  client_phone: string | null;    // VARCHAR(100) — sanitizado en audit log (PII)
  client_email: string | null;    // VARCHAR(200) — sanitizado en audit log (PII)
  project: string;                // VARCHAR(500)
  material: string | null;        // TEXT — puede ser CSV si multi-material
  localidad: string | null;       // VARCHAR(200)
  colocacion: boolean | null;     // default false
  pileta: PiletaType | null;      // VARCHAR(50)
  sink_type: SinkType | null;     // JSON
  anafe: boolean | null;          // default false
  is_building: boolean | null;    // default false (toggle Particular/Edificio)
  notes: string | null;           // TEXT
  conversation_id: string | null; // VARCHAR(100)
}
```

**Side effect del PATCH:** los campos espejados (client_name, project, localidad, colocacion, pileta, anafe, material) también se actualizan dentro de `quote_breakdown` via `_BREAKDOWN_MIRROR_FIELDS` (PR #438) — para que el frontend del detail view (que lee del breakdown) y el PDF regenerado vean el valor nuevo.

---

## `context_analysis_pending` (en `quote_breakdown`)

Card emitida por Valentina vía SSE event `context_analysis`. Persistida en `quote_breakdown.context_analysis_pending`. Permite reconstruir la card al reabrir el quote.

```ts
interface ContextAnalysisPending {
  data_known: KnownItem[];
  assumptions: AssumptionItem[];
  tech_detections: TechDetection[];
  pending_questions: PendingQuestion[];
  sector_summary: string | null;       // ej. "2 mesada(s) en cocina + isla"
  brief_analysis: {
    extraction_method: "haiku" | "fallback";
    work_types: string[];              // ej. ["cocina", "baño"]
  };
  _brief_analysis_raw: object;         // dump crudo — frontend ignora
}

interface KnownItem {
  field: string;        // ej. "client_name", "material", "localidad", "pileta"
  value: string;
  source: "brief" | "operator" | "dual_read" | "default";
}

interface AssumptionItem {
  field: string;        // ej. "colocacion", "discount_pct"
  value: string;
  reason: string;       // por qué Valentina asumió eso
  confidence: number;   // 0-1
}

interface TechDetection {
  field: string;        // ej. "tomas_count", "anafe_count", "isla_presence"
  detected: boolean;
  status: "verified" | "needs_confirmation";
  confidence: number;
  detail?: string;
  options?: string[];   // si needs_confirmation: opciones para radio buttons inline
}

interface PendingQuestion {
  id: string;           // ej. "anafe_count", "pileta_simple_doble"
  question: string;     // texto humano
  options?: string[];
}
```

Ver `sse-spec.md` evento `context_analysis` para más detalle.

---

## `verified_context` y `verified_context_analysis` (post-confirmación)

Cuando el operador escribe `[CONTEXT_CONFIRMED]` en el chat (con respuestas inline a las pending_questions), el agent handler:

1. Promueve `context_analysis_pending` → `verified_context_analysis`
2. Materializa los valores confirmados en `verified_context` (versión "limpia" sin tech_detections, lista para usar en `calculate_quote`)
3. Persiste el `[CONTEXT_CONFIRMED]` con respuestas en `Quote.messages`

```ts
interface VerifiedContext {
  client_name: string;
  project: string;
  material: string;
  localidad: string;
  colocacion: boolean;
  pileta: PiletaType | null;
  anafe: boolean;
  pileta_qty: number;
  anafe_qty: number;
  // ... otros campos materializados según las respuestas
  // (shape exacto depende de las pending_questions y precedence:
  //  operator_answer > brief > dual_read > default)
}

// `verified_context_analysis` es básicamente una snapshot del
// `context_analysis_pending` en el momento de la confirmación —
// sirve para `/reopen-context` que regenera la card original.
```

---

## Reopen flow

Cuando el operador clickea "Editar contexto" después de confirmado:

```
POST /api/quotes/{id}/reopen-context
        │
        ▼
1. Valida status NOT IN (validated, sent) — sino 409
2. Limpia: verified_context_analysis, verified_context, verified_measurements
3. PRESERVA: dual_read_result, context_analysis_pending, brief_analysis
4. Limpia tramos `_derived: true` del dual_read_result
5. total_ars / total_usd → null
6. Trunca Quote.messages desde el último __CONTEXT_ANALYSIS__ (inclusive)
7. Re-inserta el card __CONTEXT_ANALYSIS__<json> con context_analysis_pending
8. Audit `quote.reopened` con kind="context"
        │
        ▼
Frontend re-fetcha el quote → renderea card de contexto editable
```

Ver `endpoints-spec.md` Flow 4 / 7 para detalle del endpoint.

---

## "Modo PATCH default" (Master §10 decisión 6)

> Surgical edit, recalcular todo = excepción explícita.

El operador edita cells del Paso 2 y el frontend hace `PATCH /api/quotes/{id}` con SOLO los campos cambiados. NO triggea recálculo automático. Si el operador quiere recalcular después de un cambio que afecta el cómputo (ej. cambió material), debe **pasar explícitamente al chat** y pedir "recalculá" o usar `POST /api/quotes/{id}/derive-material`.

**Implicancia para Sprint 2:** el frontend tiene que distinguir entre:

- **Edit cosmético** (client_phone, project, notes) → solo PATCH
- **Edit que afecta cálculo** (material, pieces, localidad, colocacion, anafe, pileta) → PATCH + sugerir al operador que recalcule via chat

---

## Cifras canónicas — caso Cueto-Heredia (Master §13)

Estado del contexto post-confirmación para `PRES-2026-018`:

```ts
const cuetoHerediaContextColumns: QuoteContextColumns = {
  client_name: "Cueto-Heredia",
  client_phone: null,            // no provisto en mockup
  client_email: null,
  project: "Cocina + baño",
  material: "Silestone Blanco Norte",
  localidad: "rosario",
  colocacion: true,
  pileta: "empotrada_cliente",   // cliente trae la pileta
  sink_type: { basin_count: "simple", mount_type: "abajo" },
  anafe: true,
  is_building: false,            // particular
  notes: null,
  conversation_id: null,
};

const cuetoHerediaContextAnalysis: ContextAnalysisPending = {
  data_known: [
    { field: "client_name", value: "Cueto-Heredia", source: "operator" },
    { field: "project", value: "Cocina + baño", source: "brief" },
    { field: "material", value: "Silestone Blanco Norte", source: "brief" },
    { field: "localidad", value: "Rosario", source: "default" },
  ],
  assumptions: [
    { field: "colocacion", value: "true", reason: "Particular cocina default con colocación", confidence: 0.9 },
    { field: "discount_pct", value: "5", reason: "Cliente arquitecta detectada (CUETO-HEREDIA ARQUITECTAS)", confidence: 0.95 },
  ],
  tech_detections: [
    { field: "anafe_count", detected: true, status: "verified", confidence: 0.85, detail: "Detecté 1 anafe en el plano (símbolo en isla)" },
  ],
  pending_questions: [
    { id: "pileta_simple_doble", question: "¿Pileta simple o doble?", options: ["simple", "doble"] },
  ],
  sector_summary: "1 mesada en cocina",
  brief_analysis: {
    extraction_method: "haiku",
    work_types: ["cocina", "baño"],
  },
  _brief_analysis_raw: {},
};
```

Después del `[CONTEXT_CONFIRMED]` (operador respondió `pileta_simple_doble = simple`):

```ts
const cuetoHerediaVerifiedContext: VerifiedContext = {
  client_name: "Cueto-Heredia",
  project: "Cocina + baño",
  material: "Silestone Blanco Norte",
  localidad: "rosario",
  colocacion: true,
  pileta: "empotrada_cliente",
  anafe: true,
  pileta_qty: 1,
  anafe_qty: 1,
};
```

---

## Validación cliente-side

Replicar las validaciones del backend Pydantic (ver `quote.md`):

```ts
const CONTEXT_LIMITS = {
  client_name: { min: 1, max: 500 },
  client_phone: { max: 100 },
  client_email: { max: 200 },
  project: { max: 500 },
  localidad: { max: 200 },
  pileta: {
    enum: ["empotrada_cliente", "empotrada_johnson", "apoyo"] as const,
  },
  sink_type: {
    basin_count: { enum: ["simple", "doble"] as const },
    mount_type: { enum: ["arriba", "abajo"] as const },
  },
  notes: { max: undefined },  // TEXT — sin límite practico, pero >2KB se sanitiza en audit
};
```

---

## Mockup ↔ origen real

| Campo del mockup `01-A` | Columna o breakdown path | Origin chip esperado |
|---|---|---|
| Cliente | `client_name` | DEL BRIEF / EDITADO |
| Dirección | `client_phone` o `notes` (no hay columna address) | INFERIDO o FALTA |
| Tipo cliente | `is_building` (toggle) | INFERIDO o EDITADO |
| Contacto | `client_phone` / `client_email` | DEL BRIEF / FALTA |
| Material | `material` | DEL BRIEF (Valentina extrajo del texto) |
| Demora | `quote_breakdown.delivery_days` | DEFAULT (de config.json) o EDITADO |
| Localidad | `localidad` | DEL BRIEF / DEFAULT (rosario) |
| Colocación | `colocacion` | DEFAULT (true) o EDITADO |
| Pileta | `pileta` + `sink_type` | INFERIDO (Valentina detecta del plano) o FALTA |
| Anafe | `anafe` | INFERIDO (Valentina detecta símbolo) |
| Notas | `notes` | DEL BRIEF |

> **🤔 Verificar con Javi:** confirmar la lista exacta de los 11 campos del mockup `01-A` para fijar el mapeo definitivo. Lo de arriba es mi mejor inferencia desde el handoff-design.

---

## Archivos backend leídos para derivar este schema

- `api/app/modules/quote_engine/context_analyzer.py` (782 líneas — `build_context_analysis()` y helpers)
- `api/app/models/quote.py` (columnas espejo del contexto)
- `api/app/modules/agent/agent.py` (handlers de `[CONTEXT_CONFIRMED]` y persistencia de `verified_context`)
- `api/app/modules/agent/router.py` (líneas 629-743 — `POST /reopen-context`)
- `api/app/modules/quote_engine/brief_analyzer.py` (extracción inicial del brief con Haiku)
