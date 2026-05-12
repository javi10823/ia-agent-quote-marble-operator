# Schema · Brief (Paso 1)

> **Fuente:** `api/app/modules/agent/router.py:2084-2389` (chat handler) + `api/app/modules/quote_engine/schemas.py` (QuoteInput para web bot).
> **Última actualización:** 2026-05-05.

El "Brief" del Paso 1 (Master §6 mockups `00-A/B/C`) es lo que Marina sube al inicio: PDF/imagen del plano + (opcional) fotos + textarea con contexto. **Hay dos paths distintos según el origen:**

1. **Operator Brief** (Marina opera el frontend) → multipart `POST /api/quotes/{id}/chat`
2. **Web Bot Brief** (chatbot externo) → `POST /api/v1/quote` + `POST /api/v1/quote/{id}/files`

Esta doble entrada es deliberada: Master §15 menciona que el bot externo es "separado del operator UI". Ambos terminan creando un row en `quotes` con `source` distinto.

---

## Path 1 · Operator Brief (frontend → chat SSE)

### Frontend collects

```ts
interface OperatorBriefInput {
  /** Texto libre del operador. Multilinea. Master §10:
   * BriefChip[] del data model se materializa concatenado en este string,
   * o el frontend lo manda estructurado. Sin estructura formal hoy. */
  message: string;

  /** Plano técnico (1 página) + fotos del lugar.
   * - Hasta 10 archivos
   * - PDF, JPEG, PNG, WEBP
   * - Max 10MB cada uno
   * - PDFs deben ser de 1 página (multi-página → 400 explícito) */
  plan_files?: File[];
}
```

### Wire — multipart/form-data

```http
POST /api/quotes/{quote_id}/chat HTTP/1.1
Cookie: auth_token=<jwt>
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="message"

Cocina cliente Cueto-Heredia, mide en plano. Silestone Blanco Norte.
Bacha Johnson empotrada. Anafe.

--boundary
Content-Disposition: form-data; name="plan_files"; filename="plano.pdf"
Content-Type: application/pdf

<bytes>

--boundary
Content-Disposition: form-data; name="plan_files"; filename="foto-pared.jpg"
Content-Type: image/jpeg

<bytes>
--boundary--
```

### Lo que pasa server-side

1. Sanitize filenames (strip `../` etc.)
2. Validate MIME type + size + count
3. Save `OUTPUT_DIR/{quote_id}/sources/<filename>`
4. Best-effort upload a Drive ("Archivos Origen" subfolder)
5. Append a `Quote.source_files[]` (con drive_url si OK)
6. Persist en `Quote.quote_breakdown.files_v2.items[]` (Drive-first resolution)
7. Si llegó un plano nuevo: invalida cards previas (`dual_read_result`, `verified_measurements`, etc.)
8. Si NO llegó archivo y existían `source_files`: restaura el plano más reciente desde disco
9. Audit `chat.message_sent` (con `debug_only_payload.message_text` si modo debug ON)
10. Arranca SSE stream → Valentina lee plano + brief, emite `context_analysis` o `dual_read_result` (ver `sse-spec.md`)

### Lo que NO existe (ver `missing-endpoints.md`)

- **No hay `POST /api/quotes/{id}/brief` dedicado.** El brief se manda dentro del primer turno del chat. El frontend del Sprint 2 puede pegar el textarea + chips + files todo junto en un primer `chat` request.
- **No hay schema estructurado de "brief chips"** (Master §10 `BriefChip[]`). El operador escribe libre — Valentina extrae chips del texto durante `context_analysis`. Si el frontend del Sprint 2 quiere enviar chips estructurados, debe **concatenarlos en `message`** con un separador o pedir un endpoint nuevo.

---

## Path 2 · Web Bot Brief (POST /api/v1/quote)

El chatbot externo tiene un schema **MUY diferente** — manda datos estructurados en lugar de texto libre.

### Wire

```http
POST /api/v1/quote HTTP/1.1
X-API-Key: <api-key>
Content-Type: application/json

{ ...QuoteInput }
```

### `QuoteInput` schema completo

```ts
interface QuoteInput {
  /** Cliente — REQUERIDO. */
  client_name: string;            // 1-200 chars

  /** Proyecto. */
  project?: string;               // max 200 chars, default ""

  /** Material o lista (multi-material). REQUERIDO. */
  material: string | string[];

  /** Piezas con medidas estructuradas. Opcional —
   * si NO viene, el backend intenta parsear `notes` con Claude.
   * Si tampoco hay notes válidas → quote DRAFT vacío. */
  pieces?: PieceInput[] | null;

  /** Localidad para flete. REQUERIDO. */
  localidad: string;              // 1-100 chars

  /** Si incluye colocación. */
  colocacion?: boolean;           // default true

  /** Tipo de pileta — explícito. */
  pileta?: PiletaType;            // "empotrada_cliente" | "empotrada_johnson" | "apoyo"

  /** Tipo de bacha (alternativa estructurada a `pileta`).
   * Si viene `sink_type` y NO viene `pileta`, el backend resuelve:
   *   - mount_type=arriba → "apoyo"
   *   - mount_type=abajo → "empotrada_cliente" */
  sink_type?: SinkType;

  /** SKU específico de pileta Johnson (PR #397).
   * Si viene → resuelve `pileta = empotrada_johnson` y agrega producto físico. */
  pileta_sku?: string;            // max 64 chars

  /** Anafe. */
  anafe?: boolean;                // default false

  /** Frentín. */
  frentin?: boolean;              // default false

  /** Pulido. */
  pulido?: boolean;               // default false

  /** True solo si el cliente retira el trabajo en fábrica. */
  skip_flete?: boolean;           // default false

  /** Plazo de entrega. */
  plazo?: string;                 // 1-100 chars, default desde config.json

  /** Descuento %. */
  discount_pct?: number;          // 0-100, default 0

  /** Fecha. Format: DD/MM/YYYY o DD.MM.YYYY. */
  date?: string;

  /** Chat history del bot — se persiste en Quote.messages.
   * Útil para que el operador vea el contexto de la conversación bot. */
  conversation?: ChatHistoryEntry[];

  /** Notas adicionales del cliente. Si NO hay `pieces`, el backend
   * intenta parsearlas con Claude para extraer piezas. */
  notes?: string;
}

interface PieceInput {
  description: string;            // max 200 chars (ej. "Mesada cocina principal")
  largo: number;                  // > 0, <= 20 (metros)
  prof?: number;                  // > 0, <= 5 — para mesadas
  alto?: number;                  // > 0, <= 5 — para zócalos/alzas
}

interface ChatHistoryEntry {
  role: "user" | "assistant";
  content: string;
}

type PiletaType = "empotrada_cliente" | "empotrada_johnson" | "apoyo";

interface SinkType {
  basin_count: "simple" | "doble";
  mount_type: "arriba" | "abajo";
}
```

### Comportamiento del backend con `QuoteInput`

```
input.pieces presente?
├── SÍ → calculate_quote(...) → quote PENDING con breakdown completo
│        (sin docs — operator valida manualmente)
└── NO
    ├── input.notes presente?
    │   ├── SÍ → text_parser (Claude) intenta extraer pieces
    │   │       ├── parse OK → calculate_quote → quote PENDING
    │   │       └── parse FAIL → quote DRAFT vacío con notes
    │   └── NO → quote DRAFT vacío
    └── (operador completa después vía chat con Valentina)
```

### Subida de planos (segunda llamada)

```http
POST /api/v1/quote/{quote_id}/files HTTP/1.1
X-API-Key: <api-key>
Content-Type: multipart/form-data
```

Mismo formato que Path 1, pero distinto endpoint. Auth via API key. Hasta 5 archivos.

**Comportamiento PR #394:** quotes con `source="web"` que reciben archivo NO disparan auto-estimate. El operador revisa manual desde la UI interna.

```ts
interface UploadFilesResponse {
  ok: true;
  saved: number;
  errors: string[];
  files: SourceFile[];
  // PR #394 — solo si gate aplicó:
  estimate_skipped?: true;
  estimate_skip_reason?: "web_upload_manual_review";
  message?: string;  // copy para mostrar al cliente del bot
}
```

---

## Persistencia — qué se guarda dónde

| Campo del brief | Termina en |
|---|---|
| `message` (operator) | NO se persiste como campo aparte. El primer turno del chat lo guarda en `Quote.messages[0].content`. Valentina lo procesa y emite `context_analysis` que persiste en `quote_breakdown.context_analysis_pending`. |
| `client_name`, `project`, `material`, `localidad`, etc. (web bot) | Columnas dedicadas de `quotes` (mirror también a `quote_breakdown`) |
| `pieces` (web bot) | `Quote.pieces` (input crudo) + `quote_breakdown.piece_details` (post-cálculo) |
| `notes` | `Quote.notes` |
| `conversation` (web bot) | `Quote.messages` |
| `pileta_sku` (web bot) | NO persiste como columna — usado solo en `calculate_quote` para resolver pileta + agregar producto físico |
| `web_input` (raw body) | `Quote.web_input` JSON — para auditoría del bot vs backend (PR #400) |
| Archivos uploaded | Disco `OUTPUT_DIR/{quote_id}/sources/<filename>` + Drive (best-effort) + metadata en `Quote.source_files[]` y `quote_breakdown.files_v2` |

---

## Validación cliente-side (Sprint 2)

Antes de mandar el chat o el QuoteInput, replicar lo que el backend valida con Pydantic:

```ts
const VALIDATION = {
  message: { required: false },             // puede ser vacío si hay archivos
  plan_files: {
    max_count: 10,                          // operator
    max_size_bytes: 10 * 1024 * 1024,       // 10MB
    allowed_mime: [
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/webp",
    ],
    pdf_max_pages: 1,                       // backend rebota multi-page con SSE message
  },
  // Para web bot (Sprint 2 mockea contra esta shape):
  client_name: { min: 1, max: 200 },
  project: { max: 200 },
  localidad: { min: 1, max: 100 },
  plazo: { min: 1, max: 100 },
  pileta_sku: { max: 64 },
  discount_pct: { min: 0, max: 100 },
  pieces_item: {
    description: { max: 200 },
    largo: { gt: 0, le: 20 },
    prof: { gt: 0, le: 5 },
    alto: { gt: 0, le: 5 },
  },
};
```

---

## Mockups del Paso 1 vs schema real

| Mockup | Realidad backend |
|---|---|
| `00-paso1-A-vacio` — dropzone + chips IA + custom | El frontend muestra UI pero NO hay endpoint para crear chips antes de subir. Marina arrastra plano + escribe textarea + (opcional) elige chips IA — todo viaja en el primer chat request. |
| `00-paso1-B-subido` — filecard + brief chips | Igual — todo en memoria del frontend hasta que Marina clickea "Continuar a contexto". |
| `00-paso1-C-procesando` — skeletons + status bar | Cuando Marina clickea "Continuar", arranca el `POST /chat` con SSE. El frontend muestra `action` events como status bar; el `text` que llega es la respuesta de Valentina. |

**Side note (decisión de implementación Sprint 2):** los `BriefChip[]` del Master §10 data model son una abstracción del frontend. El backend no los conoce — recibe el texto concatenado. Si Marina los edita después, el frontend reconstruye el string y manda nuevo turn al chat.

---

## Archivos backend leídos para derivar este schema

- `api/app/modules/agent/router.py` (líneas 2084-2389 — handler completo de `POST /chat`)
- `api/app/modules/quote_engine/router.py` (líneas 29-261 — `POST /v1/quote`)
- `api/app/modules/quote_engine/router.py` (líneas 264-386 — `POST /v1/quote/{id}/files`)
- `api/app/modules/quote_engine/schemas.py` (`QuoteInput`, `PieceInput`, `PiletaType`, `SinkType`)
- `api/app/modules/quote_engine/text_parser.py` (parser de `notes` con Claude)
