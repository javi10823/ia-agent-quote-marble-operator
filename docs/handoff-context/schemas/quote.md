# Schema · Quote

> **Fuente:** `api/app/models/quote.py` (modelo SQLAlchemy) + `api/app/modules/agent/schemas.py` (response schemas) + `api/app/modules/quote_engine/calculator.py` (shape de `quote_breakdown`).
> **Última actualización:** 2026-05-05.

El modelo `Quote` es el agregado central del sistema. Cada presupuesto creado por Marina o por el bot web vive como un row en la tabla `quotes` con un `quote_breakdown` JSON que contiene todo el cálculo determinístico.

---

## Tabla `quotes` — columnas

```ts
interface QuoteRow {
  // Primary key
  id: string;                         // UUID o "web-<uuid>" para source=web

  // Client + project
  client_name: string;                // VARCHAR(500)
  project: string;                    // VARCHAR(500)
  client_phone: string | null;        // VARCHAR(100)
  client_email: string | null;        // VARCHAR(200)

  // Quote essentials
  material: string | null;            // TEXT
  total_ars: number | null;           // FLOAT (monto en pesos)
  total_usd: number | null;           // FLOAT (monto USD si material importado)
  status: QuoteStatus;                // ENUM: draft | pending | validated | sent

  // Lineage / variantes
  parent_quote_id: string | null;     // VARCHAR — apunta al root para children
  quote_kind: QuoteKind | null;       // VARCHAR(30) default "standard"
  comparison_group_id: string | null; // VARCHAR(200) — para variant_option

  // Origen
  source: "operator" | "web" | null;  // VARCHAR(20) default "operator"
  is_read: boolean;                   // default true (false solo para nuevos web quotes)

  // File URLs (locales relativos al server, sirven via /files/{path})
  pdf_url: string | null;             // VARCHAR(500) ej "/files/{id}/<filename>.pdf"
  excel_url: string | null;
  drive_url: string | null;           // legacy — uno solo (PDF u Excel, último uploaded)
  drive_file_id: string | null;       // VARCHAR(200) — para delete
  drive_pdf_url: string | null;       // PR #38 — separados PDF
  drive_excel_url: string | null;     // PR #38 — separados Excel

  // Quote details
  localidad: string | null;           // VARCHAR(200) — ciudad para flete
  colocacion: boolean | null;         // default false
  pileta: PiletaType | null;          // VARCHAR(50)
  anafe: boolean | null;              // default false
  sink_type: SinkType | null;         // JSON — basin_count + mount_type
  is_building: boolean | null;        // default false
  pieces: PieceInput[] | null;        // JSON — input crudo de medidas

  // JSON blobs grandes
  quote_breakdown: QuoteBreakdown | null;  // JSON — TODO el cálculo (ver abajo)
  source_files: SourceFile[] | null;       // JSON — planos/imágenes uploaded
  messages: ChatMessage[];                  // JSON — chat history (default [])
  change_history: ChangeHistoryEntry[] | null;  // JSON default []

  // Cards generadas (Sprint 2-4)
  resumen_obra: ResumenObra | null;        // JSON — consolidado N quotes
  email_draft: EmailDraft | null;          // JSON — borrador comercial
  condiciones_pdf: CondicionesPdf | null;  // JSON — solo edificios

  // PR #400 — auditoría web
  web_input: object | null;           // JSON — body raw del POST /v1/quote
  conversation_id: string | null;     // VARCHAR(100) — link a sesión chatbot

  // Notas
  notes: string | null;               // TEXT — del cliente para el operador

  // Timestamps
  created_at: string;                 // TIMESTAMPTZ con default NOW()
  updated_at: string;                 // TIMESTAMPTZ con onupdate NOW()

  // Concurrency control
  version: number;                    // INTEGER default 1 — increment on each update
}
```

### Enums

```ts
type QuoteStatus = "draft" | "pending" | "validated" | "sent";

type QuoteKind =
  | "standard"                  // quote único, no familia
  | "building_parent"           // edificio multi-material — padre
  | "building_child_material"   // edificio — material del padre
  | "variant_option";           // variante (mismo despiece, otro material)

type PiletaType = "empotrada_cliente" | "empotrada_johnson" | "apoyo";

interface SinkType {
  basin_count: "simple" | "doble";
  mount_type: "arriba" | "abajo";
}
```

### Transiciones de status

| Desde | Hacia válidos |
|---|---|
| `draft` | `validated`, `pending` |
| `pending` | `validated`, `draft` |
| `validated` | `sent`, `draft` |
| `sent` | `validated` |

Validado en `PATCH /api/quotes/{id}/status` (Flow 2 endpoints-spec).

---

## `quote_breakdown` — JSON con todo el cálculo

Calculado por `calculate_quote()` en `api/app/modules/quote_engine/calculator.py:1880`. Persistido en `Quote.quote_breakdown` después del Paso 2 backend Valentina.

```ts
interface QuoteBreakdown {
  ok: true;

  // Identificación
  client_name: string;
  project: string;
  date: string;                   // formato "DD.MM.YYYY"
  delivery_days: string;          // ej. "30 dias desde la toma de medidas"

  // Material
  material_name: string;          // ej. "SILESTONE BLANCO NORTE"
  material_type: string;          // ej. "silestone", "granito", "marmol"
  thickness_mm: number;           // default 20
  material_m2: number;            // total m² (round 2 dec)
  material_price_unit: number;    // precio por m² c/IVA (USD: floor, ARS: round)
  material_price_base: number;    // precio base s/IVA
  material_currency: "USD" | "ARS";
  material_total: number;         // material_m2 * price_unit - discount

  // Descuentos
  discount_pct: number;           // 0-100 — solo aplica al material
  discount_amount: number;        // monto descuento en moneda del material
  mo_discount_pct: number;        // descuento opcional sobre MO (excluye flete)
  mo_discount_amount: number;

  // Merma (solo sintéticos)
  merma: {
    aplica: boolean;
    desperdicio: number;          // m² desperdiciados
    sobrante_m2: number;          // m² ofrecidos al cliente (mitad de precio)
    motivo: string;               // "Sintético, desperdicio ≥ 1m²" / "Negro Brasil — nunca aplica" / etc.
  };
  sobrante_m2: number;            // duplicado al top-level (legacy)
  sobrante_total: number;

  // Despiece
  piece_details: PieceDetail[];   // piezas con sus m² calculados
  sectors: Sector[];              // agrupación por proyecto/sector con labels finales

  // Mano de obra
  mo_items: MOItem[];
  total_mo_ars: number;           // subtotal MO (sin material, sin sinks)

  // Piletas físicas (cuando D'Angelo las vende)
  sinks: SinkLine[];

  // Totales (GRAND TOTAL)
  total_ars: number;              // MO + piletas + flete (+ material si ARS)
  total_usd: number;              // material si USD; 0 si material es ARS

  // Metadata para regenerate sin recalcular
  has_m2_override: boolean;       // true si alguna pieza usó m2_override del operador

  // Persist input params para patch mode
  localidad: string;
  colocacion: boolean;
  is_edificio: boolean;
  pileta: PiletaType | null;
  pileta_qty: number;
  anafe: boolean;
  frentin: boolean;
  frentin_ml: number;
  regrueso: boolean;
  regrueso_ml: number;
  inglete: boolean;
  pulido: boolean;
  skip_flete: boolean;

  // Warnings (opcional)
  warnings?: string[];

  // Fuzzy match metadata (si Valentina corrigió el material)
  fuzzy_corrected_from?: string;  // ej. "silestone blanca norte" (typo del operador)
  fuzzy_score?: number;           // 0-100 confidence
  fuzzy_catalog?: string;         // ej. "materials-silestone"
  fuzzy_family?: string;

  // Edificio validation checklist (solo is_edificio=true)
  edificio_checklist?: {
    sin_colocacion: boolean;
    flete_qty: number;
    flete_calculo: string;        // ej. "5 fletes"
    mo_dividido_1_05: boolean;
    descuento_18: boolean;
  };

  // Cards y estado del flow Sprint 2 (persistido por chat handlers)
  dual_read_result?: DualReadResult;        // ver sse-spec.md
  dual_read_plan_hash?: string;
  dual_read_planilla_m2?: number;
  dual_read_crop_label?: string;
  context_analysis_pending?: ContextAnalysis;  // ver sse-spec.md
  verified_context_analysis?: object;          // post-confirmación
  verified_context?: object;
  verified_measurements?: object;
  brief_analysis?: object;
  page_data?: Record<string, PageData>;        // para visual-pages flow (edificios)
  zone_default?: string;
  zone_default_bbox?: number[];
  selected_zone?: object;
  building_step?: string;
  files_v2?: { items: FileV2Item[] };          // metadata Drive-first

  // ... otros campos transitorios (se ignoran si no aplica el caso)
}

interface PieceDetail {
  description: string;       // ej. "Mesada cocina"
  largo: number;             // metros
  dim2: number;              // prof o alto según el contexto
  m2: number;                // m² calculado de esta pieza
  override?: boolean;        // true si vino de Planilla de Cómputo (m2_override)
  quantity?: number;         // default 1
  // ... otros campos de la piece original
}

interface Sector {
  label: string;             // ej. "Cocina", "Baño"
  pieces: string[];          // labels formateados (ej. "2.10 × 0.60 Mesada", "ZOCALO 2.00 × 0.05")
}

interface MOItem {
  description: string;       // ej. "COLOCACION", "PEGADOPILETA"
  quantity: number;          // m² para colocación, count para resto
  unit_price: number;        // c/IVA (round)
  base_price?: number;       // s/IVA (para traceability — IVA toggle)
  total: number;             // quantity × unit_price
}

interface SinkLine {
  name: string;              // ej. "JOHNSON LUXOR171"
  quantity: number;
  unit_price: number;        // ARS
}
```

---

## Cifras canónicas — caso Cueto-Heredia (Master §13)

`PRES-2026-018` · Silestone Blanco Norte · 6,50 m². Después del descuento 5% arquitecta:

```ts
const cuetoHerediaQuoteBreakdown: QuoteBreakdown = {
  ok: true,
  client_name: "Cueto-Heredia",
  project: "Cocina + baño",
  date: "05.05.2026",
  delivery_days: "30 dias desde la toma de medidas",

  material_name: "SILESTONE BLANCO NORTE",
  material_type: "silestone",
  thickness_mm: 20,
  material_m2: 6.50,
  material_price_unit: 249,           // USD c/IVA — referencial del mockup, ver bug P2
  material_price_base: 206,           // USD s/IVA
  material_currency: "USD",
  material_total: 1538,               // post descuento 5%

  discount_pct: 5,
  discount_amount: 81,
  mo_discount_pct: 0,
  mo_discount_amount: 0,

  merma: { aplica: false, desperdicio: 0, sobrante_m2: 0, motivo: "Cabe en placa" },
  sobrante_m2: 0,
  sobrante_total: 0,

  piece_details: [
    { description: "Mesada cocina", largo: 2.50, dim2: 0.65, m2: 1.625 },
    { description: "Mesada cocina (extensión)", largo: 1.80, dim2: 0.65, m2: 1.170 },
    { description: "Tope baño", largo: 1.20, dim2: 0.55, m2: 0.660 },
    { description: "Mesada cocina + zócalo", largo: 4.30, dim2: 0.05, m2: 0.215 },
    // ... el detalle real depende del plano
  ],

  sectors: [
    { label: "Cocina + baño", pieces: ["2.50 × 0.65 Mesada", "1.80 × 0.65 Mesada", "1.20 × 0.55 Tope", "ZOCALO 4.30 × 0.05"] },
  ],

  mo_items: [
    { description: "COLOCACION",   quantity: 6.50, unit_price: 60135, base_price: 49698, total: 390877 },
    { description: "PEGADOPILETA", quantity: 1,    unit_price: 65147, base_price: 53840, total:  65147 },
    { description: "ANAFE",        quantity: 1,    unit_price: 43097, base_price: 35617, total:  43097 },
    { description: "REGRUESO",     quantity: 4.98, unit_price: 16710, base_price: 13810, total:  83217 },
    { description: "TOMAS",        quantity: 2,    unit_price:  7818, base_price:  6461, total:  15636 },
    { description: "Flete + toma medidas Rosario", quantity: 1, unit_price: 62920, base_price: 52000, total: 62920 },
  ],
  total_mo_ars: 660893,                // ≈ $660.890 (ARS canon)

  sinks: [],                           // cliente no compró pileta en D'Angelo
  total_ars: 660890,                   // canon
  total_usd: 1538,                     // canon (material)

  has_m2_override: false,
  localidad: "rosario",
  colocacion: true,
  is_edificio: false,
  pileta: "empotrada_cliente",
  pileta_qty: 1,
  anafe: true,
  frentin: false,
  frentin_ml: 0,
  regrueso: true,
  regrueso_ml: 4.98,
  inglete: false,
  pulido: false,
  skip_flete: false,
};
```

**Nota sobre Bug P2 Silestone (Master §12):** el mockup 07-v4 muestra USD 249/m² c/IVA, pero el catálogo real dice USD 519 c/IVA. Las cifras de arriba reflejan el mockup. En producción, `calculate_quote()` toma el catálogo real → totales pueden diferir hasta que se reconcilie el dataset.

---

## Cifras canon — caso Pereyra mobile (Master §13)

`PRES-2026-017` · Pereyra · Silestone · 6,50 m² (aparece en mockup `24-paso-dashboard-B-mobile-detalle`):

```ts
const pereyraTotals = {
  total_ars: 660890,
  total_usd: 1538,
  material_m2: 6.50,
  material: "Silestone (variante Pereyra del mockup mobile)",
};
```

---

## ChatMessage shape (en `Quote.messages`)

```ts
interface ChatMessage {
  role: "user" | "assistant";
  content: string | ContentBlock[];
}

// `content` puede ser string simple o array (multimodal Anthropic)
type ContentBlock =
  | { type: "text"; text: string }
  | { type: "image"; source: { type: "base64"; media_type: string; data: string } };

// Markers especiales que pueden aparecer en `content` (string completo):
//   "__DUAL_READ__<json>"             → card despiece persistida
//   "__CONTEXT_ANALYSIS__<json>"      → card contexto persistida
//   "[DUAL_READ_CONFIRMED]"           → confirmación del operador
//   "[CONTEXT_CONFIRMED]"             → confirmación del operador
//   "[SYSTEM_TRIGGER:<event>]"        → trigger interno
//   "(contexto confirmado)"           → legacy fake turn (ignorar)
//   "_SHOWN_"                         → legacy placeholder (ignorar — pre-PR #379)
```

Frontend al reabrir un quote: `GET /api/quotes/{id}` trae `messages[]`. Renderear filtrando los markers de sistema.

---

## ChangeHistoryEntry shape

```ts
interface ChangeHistoryEntry {
  timestamp: string;          // ISO datetime
  action: "regenerate_docs" | "generate_docs" | "patch_quote" | "update_quote" | string;
  // Campos según `action`:
  pdf_url_before?: string | null;
  pdf_url_after?: string | null;
  excel_url_before?: string | null;
  excel_url_after?: string | null;
  fields?: string[];          // para patch_quote
  // ... otros campos según el contexto
}
```

Append-only. Usado para computar `pdf_outdated` en `GET /api/quotes/{id}` (PR #442).

---

## SourceFile shape

```ts
interface SourceFile {
  filename: string;           // ej. "plano.pdf"
  type: string;               // MIME, ej. "application/pdf"
  size: number;               // bytes
  url: string;                // path local, ej. "/files/{quote_id}/sources/plano.pdf"
  uploaded_at: string;        // ISO datetime
  // Drive metadata (opcional, best effort):
  drive_file_id?: string;
  drive_url?: string;
  drive_download_url?: string;
}
```

---

## ResumenObra, EmailDraft, CondicionesPdf shapes

Generados por endpoints específicos. Se persisten dentro del quote para mostrar como cards en el detalle.

```ts
interface ResumenObra {
  pdf_url: string;
  drive_url: string | null;
  drive_file_id?: string | null;
  notes: string;
  generated_at: string;       // ISO
  quote_ids: string[];        // los N quotes consolidados
  client_name: string;
  project: string;
}

interface EmailDraft {
  subject: string;
  body: string;
  generated_at: string;
  validated: boolean;
  quote_updated_at_snapshot: string;
  resumen_updated_at_snapshot: string | null;
  sibling_updated_at_snapshots: Record<string, string>;  // quote_id → ISO
}

interface CondicionesPdf {
  pdf_url: string;
  drive_url: string | null;
  drive_file_id?: string | null;
  generated_at: string;
  plazo: string;
}
```

---

## Validación cliente-side

Para PATCH y POST de quotes, replicar las validaciones del backend (Pydantic V2):

```ts
const QUOTE_LIMITS = {
  client_name: { min: 1, max: 500 },
  project: { max: 500 },
  client_phone: { max: 100 },
  client_email: { max: 200 },
  localidad: { max: 200 },
  pileta: { max: 50 },
  conversation_id: { max: 100 },
  parent_quote_id: { max: 200 },
  delivery_days: { max: 200 },
};

const PIECE_LIMITS = {
  description: { max: 200 },
  largo: { gt: 0, le: 20 },     // metros
  prof: { gt: 0, le: 5 },       // metros
  alto: { gt: 0, le: 5 },       // metros
};
```

---

## Archivos backend leídos para derivar este schema

- `api/app/models/quote.py` (modelo SQLAlchemy completo)
- `api/app/modules/agent/schemas.py` (`QuoteListResponse`, `QuoteDetailResponse`, `QuotePatchRequest`)
- `api/app/modules/quote_engine/schemas.py` (`PieceInput`, `PiletaType`, `SinkTypeInput`, `QuoteInput`)
- `api/app/modules/quote_engine/calculator.py` (líneas 1880-1950 — return shape de `calculate_quote()`)
- `api/CONTEXT.md` (referencia de SKUs y cifras canon — system prompt Valentina)
