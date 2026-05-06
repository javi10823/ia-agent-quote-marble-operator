# Endpoints Spec · Marble Operator Backend

> **Fuente:** código backend real (`api/app/modules/*/router.py`).
> **Derivado de:** auditoría manual de los routers de FastAPI commit `1915317` (branch `sprint-1.5/master-handoff`).
> **Última actualización:** 2026-05-05 (PR `sprint-1.5/extract-api-contracts`).
>
> **Audiencia:** frontend Sprint 2-5. Mockear contra estos contratos. Cuando el switch a backend real ocurra (Sprint 3 inicial), los hooks `useApiClient()` consumen estos paths sin cambios al frontend.
>
> **Convención de tipos:** TypeScript-flavored. Copiables directo a `web/src/lib/types.ts`.

---

## Conventions globales

### Auth

Tres mecanismos según endpoint:

| Mecanismo | Cómo se manda | Cuándo aplica |
|---|---|---|
| **Cookie** `auth_token` | `httpOnly`, `Secure` (prod), `SameSite=None` (cross-origin Vercel→Railway) | Default de operator panel — todos los `/api/*` salvo excepciones |
| **Bearer header** | `Authorization: Bearer <jwt>` | Fallback cuando la cookie cross-origin no viaja (ej. iOS Safari con ITP). Cookie tiene precedencia si ambas presentes. |
| **API Key** | Header `X-API-Key: <key>` | Solo `/api/v1/quote*` y `/api/v1/business-rules` (bot externo). Si `QUOTE_API_KEY` env vacío en dev → check skipeado. |
| **Sin auth** | — | `/health` y `/api/auth/login` |

**Sliding refresh:** cuando al token le quedan <24h, las requests autenticadas devuelven un nuevo JWT en `X-Refreshed-Token` header (además de un nuevo `Set-Cookie`). El cliente debe sincronizar `localStorage.setItem("dangelo:token", refreshed)` para mantener vivo el fallback Bearer.

### Rate limits

| Path | Límite | Por qué |
|---|---|---|
| `POST /api/auth/login` | 10 req/min por IP | Brute force |
| `POST /api/quotes/{id}/chat` | 20 req/min por IP | Costo por turno de Valentina |

Excedido → `429` con `{"detail": "Demasiados intentos..."}`.

### Errors comunes

Todos los endpoints autenticados pueden devolver:

- `401 {"detail": "No autenticado"}` — sin token
- `401 {"detail": "Sesión expirada"}` — token inválido/expirado
- `429 {"detail": "Demasiados intentos. Esperá un minuto."}` — rate limit
- `500 {"detail": "..."}` — bug interno (ver audit log)

### Status enum

`QuoteStatus` valores:

```ts
type QuoteStatus = "draft" | "pending" | "validated" | "sent";
```

Transiciones válidas:

| Desde | Hacia |
|---|---|
| `draft` | `validated`, `pending` |
| `pending` | `validated`, `draft` |
| `validated` | `sent`, `draft` |
| `sent` | `validated` |

Cualquier otra transición → `400 {"detail": "Transición inválida: X → Y"}`.

### Cifras canónicas en ejemplos

Los ejemplos de response usan el case **Cueto-Heredia** (Master §13):

- Quote: `PRES-2026-018` · Silestone Blanco Norte · 6,50 m² · USD 1.538 + ARS 660.890
- Arquitecta: `CUETO-HEREDIA ARQUITECTAS` (5% descuento sobre material importado)
- MO SKUs: `COLOCACION` ($49.698 base), `PEGADOPILETA` ($53.840), `ANAFE` ($35.617), `REGRUESO` ($13.810), `TOMAS` ($6.461)
- Flete: `Rosario` → `ENVIOROS` ($62.920 c/IVA)

---

## Flow 1 · Auth

### `POST /api/auth/login` — público

Login con username/password. Setea cookie + devuelve JWT en body.

**Auth:** ninguna · **Rate limit:** 10/min/IP

**Request body:**

```ts
interface LoginRequest {
  username: string;  // se trimean leading/trailing spaces server-side
  password: string;
}
```

**Response 200:**

```ts
interface LoginResponse {
  ok: true;
  username: string;
  token: string;  // JWT — guardar en localStorage como fallback Bearer
}
```

**Side effects:**
- `Set-Cookie: auth_token=<jwt>; HttpOnly; Secure; SameSite=None; Max-Age=259200` (72h)

**Errores:**
- `401 {"detail": "Usuario o contraseña incorrectos"}` — credenciales inválidas
- `429` — rate limit

---

### `POST /api/auth/logout`

Limpia la cookie. No invalida el token server-side (los JWTs son stateless).

**Auth:** Cookie

**Response 200:**

```ts
interface LogoutResponse { ok: true; }
```

---

### `POST /api/auth/create-user`

Crea usuario. Sin auth si no hay usuarios todavía (setup inicial). Después requiere JWT válido.

**Auth:** condicional (sin auth solo para el primer usuario)

**Request body:**

```ts
interface CreateUserRequest {
  username: string;
  password: string;  // min 6 chars
}
```

**Response 200:**

```ts
interface CreateUserResponse {
  ok: true;
  id: string;       // UUID
  username: string;
}
```

**Errores:**
- `400 {"detail": "El usuario 'X' ya existe"}` — username repetido
- `400 {"detail": "La contraseña debe tener al menos 6 caracteres"}`
- `401 {"detail": "No autenticado"}` — post-setup sin token

---

### `GET /api/auth/users`

Lista todos los usuarios (sin passwords).

**Auth:** Cookie

**Response 200:**

```ts
type UsersResponse = Array<{
  id: string;
  username: string;
  created_at: string | null;  // ISO datetime
}>;
```

---

### `DELETE /api/auth/users/{user_id}`

Elimina un usuario. Bloqueado si es el único.

**Auth:** Cookie

**Response 200:** `{ ok: true }`

**Errores:**
- `400 {"detail": "No se puede eliminar el ultimo usuario"}`
- `404 {"detail": "Usuario no encontrado"}`

---

## Flow 2 · Quotes — lifecycle

Cubre creación, listado, detalle, edición, eliminación, polling.

### `POST /api/quotes`

Crea un quote vacío en `status=draft` (default). El operador después agrega cliente/proyecto/material vía PATCH o vía chat con Valentina.

**Auth:** Cookie

**Request body** (opcional):

```ts
interface CreateQuoteRequest {
  status?: "draft" | "pending";  // default "draft"
}
```

**Response 200:**

```ts
interface CreateQuoteResponse {
  id: string;  // UUID
}
```

**Side effects:**
- Trigger `cleanup_empty_drafts()` async (limpia drafts > 1h sin client_name)
- Audit event `quote.created`

---

### `GET /api/quotes`

Lista quotes con paginación. Excluye drafts vacíos (sin `client_name`) y excluye `building_child_material` (viven dentro del padre).

**Auth:** Cookie

**Query params:**

```ts
interface ListQuotesQuery {
  limit?: number;   // 1-200, default 100
  offset?: number;  // >= 0, default 0
}
```

**Response 200:**

```ts
type ListQuotesResponse = QuoteListItem[];

interface QuoteListItem {
  id: string;
  client_name: string;
  project: string;
  material: string | null;
  total_ars: number | null;
  total_usd: number | null;
  status: QuoteStatus;
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
  drive_pdf_url: string | null;
  drive_excel_url: string | null;
  parent_quote_id: string | null;
  quote_kind: "standard" | "building_parent" | "building_child_material" | "variant_option" | null;
  is_building: boolean;
  comparison_group_id: string | null;
  source: "operator" | "web" | null;
  is_read: boolean;
  client_phone: string | null;
  client_email: string | null;
  localidad: string | null;
  colocacion: boolean | null;
  pileta: PiletaType | null;
  sink_type: SinkType | null;
  anafe: boolean | null;
  pieces: PieceInput[] | null;
  conversation_id: string | null;
  notes: string | null;
  created_at: string;  // ISO datetime
}

type PiletaType = "empotrada_cliente" | "empotrada_johnson" | "apoyo";

interface SinkType {
  basin_count: "simple" | "doble";
  mount_type: "arriba" | "abajo";
}

interface PieceInput {
  description: string;        // max 200 chars
  largo: number;              // > 0, <= 20 (m)
  prof?: number | null;       // > 0, <= 5 (m) — para mesadas
  alto?: number | null;       // > 0, <= 5 (m) — para zócalos/alzas
}
```

Sort: `created_at DESC`.

---

### `GET /api/quotes/check`

Polling liviano. Devuelve count + último `updated_at` para que el cliente sepa si hay cambios sin cargar la lista completa.

**Auth:** Cookie

**Response 200:**

```ts
interface CheckQuotesResponse {
  count: number;
  last_updated_at: string | null;  // ISO datetime
}
```

**Uso típico:** `setInterval(checkQuotes, 15_000)` + comparar contra estado anterior. Si cambió, re-fetch `GET /quotes`.

---

### `GET /api/quotes/{quote_id}`

Detalle del quote. Incluye `quote_breakdown` (JSON con todo el cálculo), `messages` (chat history), `source_files`, y campos derivados (`pdf_outdated`).

**Auth:** Cookie

**Response 200:**

```ts
interface QuoteDetailResponse extends QuoteListItem {
  messages: ChatMessage[];
  quote_breakdown: QuoteBreakdown | null;
  source_files: SourceFile[] | null;
  resumen_obra: ResumenObra | null;
  email_draft: EmailDraft | null;
  condiciones_pdf: CondicionesPdf | null;  // solo edificios
  web_input: object | null;  // raw body POST /v1/quote (solo source="web")
  pdf_outdated: boolean | null;  // true si edits posteriores al último regenerate
  pdf_generated_at: string | null;  // ISO datetime del último PDF generado
  // Si quote_kind === "building_parent":
  children?: QuoteListItem[];
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string | ContentBlock[];  // string para texto simple, array para multimodal
}

interface SourceFile {
  filename: string;
  type: string;          // MIME type
  size: number;          // bytes
  url: string;           // /files/{quote_id}/sources/{filename}
  uploaded_at: string;   // ISO datetime
  drive_file_id?: string;
  drive_url?: string;
  drive_download_url?: string;
}

// Ver schemas/quote.md para QuoteBreakdown completo
```

**Errores:**
- `404 {"detail": "Presupuesto no encontrado"}`

---

### `PATCH /api/quotes/{quote_id}`

Editar campos del quote. Todos opcionales — solo se actualizan los que vienen con valor no-null. Side effect: si tocás campos espejados en `quote_breakdown` (client_name, project, localidad, colocacion, pileta, anafe, material), también se sincronizan ahí.

**Auth:** Cookie

**Request body:**

```ts
interface QuotePatchRequest {
  status?: QuoteStatus;
  client_name?: string;       // max 500
  client_phone?: string;      // max 100
  client_email?: string;      // max 200
  project?: string;           // max 500
  material?: string | string[];
  pieces?: PatchPieceInput[];
  localidad?: string;         // max 200
  colocacion?: boolean;
  pileta?: string;            // max 50
  sink_type?: SinkType;
  anafe?: boolean;
  conversation_id?: string;   // max 100
  origin?: "web" | "operator";  // se renombra a `source` server-side
  notes?: string;
  parent_quote_id?: string;   // max 200
  delivery_days?: string;     // max 200 — vive en quote_breakdown.delivery_days, NO columna
}

interface PatchPieceInput {
  description: string;  // max 200
  largo: number;        // > 0, <= 20
  prof?: number;        // > 0, <= 5
  alto?: number;        // > 0, <= 5
}
```

**Response 200:**

```ts
interface PatchQuoteResponse {
  ok: true;
  updated: string[];  // lista de field names que se actualizaron
}
```

**Side effects:**
- Audit event `quote.patched` con `payload.fields = [updated keys]` (sanitizer redacta phone/email).

**Errores:**
- `400 {"detail": "No valid fields to update"}` — body vacío
- `404 {"detail": "Quote not found"}`

---

### `PATCH /api/quotes/{quote_id}/status`

Cambia status validando transiciones.

**Auth:** Cookie

**Request body:**

```ts
interface StatusUpdateRequest {
  status: QuoteStatus;
}
```

**Response 200:** `{ ok: true }`

**Side effects:**
- Audit event `quote.status_changed`

**Errores:**
- `400 {"detail": "Transición inválida: draft → sent"}` — ver tabla de transiciones
- `404`

---

### `PATCH /api/quotes/{quote_id}/read`

Marca el quote como leído (`is_read = true`).

**Auth:** Cookie

**Response 200:** `{ ok: true }`

---

### `DELETE /api/quotes/{quote_id}`

**Cascade delete** de la familia entera (root + children). Mejor effort en Drive (no bloquea si falla).

**Auth:** Cookie

**Response 200:**

```ts
interface DeleteQuoteResponse {
  ok: true;
  deleted: string[];  // IDs eliminados (incluye children del building parent)
}
```

**Side effects:**
- Resuelve `root_id` desde `parent_quote_id || quote_id`
- Borra todos los quotes con `id == root_id` o `parent_quote_id == root_id`
- Best-effort: borra Drive files (`drive_file_id`) y `OUTPUT_DIR/{quote_id}/`

**Errores:**
- `404 {"detail": "Presupuesto no encontrado"}`

---

## Flow 3 · Brief upload (Paso 1 — Master §6)

**No hay endpoint dedicado para "subir brief".** El brief (PDF + fotos + textarea) se manda **dentro del primer turno del chat** vía `POST /quotes/{id}/chat` con multipart. Ver Flow 5.

Flujo típico para Paso 1 del mockup:

1. `POST /api/quotes` → obtener `quote_id`
2. `POST /api/quotes/{id}/chat` con `message=<brief textarea>` + `plan_files=[plano.pdf, foto1.jpg, foto2.jpg]` (multipart)
3. SSE response stream del agente — ver Flow 5

Ver `missing-endpoints.md` para discusión sobre si conviene crear `POST /api/quotes/{id}/brief` dedicado.

---

## Flow 4 · Contexto (Paso 2 — Master §6)

**No hay endpoint dedicado** ni schema dedicado para los "11 campos del contexto". El contexto vive **dentro de `quote_breakdown` JSON** del quote. Los campos se setean:

1. **Por Valentina** durante el chat — emite `dual_read_result` (despiece) y `context_analysis` (cards) que persisten en `quote_breakdown`
2. **Por el operador** vía `PATCH /api/quotes/{id}` — setea client_name, project, localidad, colocacion, pileta, sink_type, anafe directo en columnas (con mirror al breakdown)
3. **Por el chat** cuando el operador escribe `[CONTEXT_CONFIRMED]` o `[DUAL_READ_CONFIRMED]` (markers de confirmación)

Ver `schemas/context.md` para el detalle del shape esperado en `quote_breakdown`.

### `POST /api/quotes/{quote_id}/reopen-context`

Vuelve al estado pre-confirmación de contexto (Master §15: feature backend implementada). Limpia Paso 2 + corta `messages` desde la card `__CONTEXT_ANALYSIS__`. Bloqueado en `validated`/`sent`.

**Auth:** Cookie

**Response 200:** `QuoteDetailResponse` (ver Flow 2)

**Side effects:**
- Limpia `verified_context_analysis`, `verified_context`, `verified_measurements` del breakdown
- Preserva `dual_read_result`, `context_analysis_pending`, `brief_analysis`
- Quita tramos `_derived: true` del `dual_read_result`
- `total_ars`, `total_usd` → null
- Audit event `quote.reopened` con `payload.kind = "context"`

**Errores:**
- `400 {"detail": "No hay confirmación de contexto que reabrir..."}` — idempotencia
- `404`
- `409 {"detail": "El presupuesto está en estado 'X'. No se puede reabrir..."}` — status validated/sent

---

## Flow 5 · Despiece + Cálculo (Pasos 3-4 — Master §6)

El despiece y cálculo viven dentro del **chat con Valentina** (SSE). Las tools del agente que se invocan son:

- `list_pieces` — Paso 1 backend Valentina (pre-cálculo)
- `calculate_quote` — Paso 2 backend Valentina (determinístico)

Estas NO se exponen como REST. El frontend dispara el chat y consume eventos SSE — ver `sse-spec.md`.

### `POST /api/quotes/{quote_id}/chat` — SSE streaming

Punto único de interacción con Valentina. El operador manda mensaje + (opcionalmente) archivos. El backend stream eventos vía Server-Sent Events.

**Auth:** Cookie · **Rate limit:** 20/min/IP · **Content-Type:** `multipart/form-data`

**Form fields:**

| Field | Tipo | Required | Descripción |
|---|---|---|---|
| `message` | string | Sí | Texto del operador (puede contener markers como `[DUAL_READ_CONFIRMED]`, `[CONTEXT_CONFIRMED]`, `[SYSTEM_TRIGGER:*]`) |
| `plan_files` | file[] | No | Hasta **10** archivos. PDF, JPEG, PNG, WEBP. Max **10MB** c/u. PDFs deben ser **1 página** (multi-page → 400 explícito). |

**Response:** `text/event-stream` (SSE).

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
Connection: keep-alive

data: {"type": "text", "content": "Voy a ver el plano…"}

data: {"type": "action", "content": "⚙️ Ejecutando: catalog_batch_lookup..."}

data: {"type": "dual_read_result", "content": "...", "data": {...}}

data: {"type": "done", "content": ""}
```

Ver **`sse-spec.md`** para la spec completa de event types + payload shapes + reconexión.

**Pre-flight checks** (server hace antes de iniciar el stream):

1. **Budget gate:** si el gasto mensual de Anthropic supera `monthly_budget_usd` del config y `enable_hard_limit=true` → `429`
2. **File validation:** size, mime, count
3. **Multi-page PDF:** `_pdf.pages > 1` → respuesta corta SSE con mensaje "solo planos de 1 página por ahora"
4. **Quote exists:** `404` si no

**Errores HTTP (antes de empezar el stream):**
- `400 "Máximo 10 archivos por mensaje"`
- `400 "<filename> — tipo no soportado..."`
- `400 "<filename> — excede 10MB..."`
- `404 "Presupuesto no encontrado"`
- `429 "Límite mensual de API alcanzado..."`
- `429` rate limit

**Side effects:**
- Audit `chat.message_sent` (con `debug_only_payload.message_text` si modo debug global activo)
- Archivos guardados en `OUTPUT_DIR/{quote_id}/sources/<filename>` + uploaded a Drive (best-effort, "Archivos Origen" subfolder)
- Si llega un plano nuevo: invalida `dual_read_result`, `verified_measurements`, `verified_context` etc del breakdown
- Si **no** llega archivo y existen `source_files` previos: el plano se **restaura** desde disco para que Valentina siempre tenga acceso

---

## Flow 6 · Validación + PDF/Excel (Paso 5 — Master §6)

Tres endpoints relacionados:

### `POST /api/quotes/{quote_id}/validate`

Genera PDF + Excel + sube a Drive + cambia `status` a `validated`. Requiere `quote_breakdown` previo.

**Auth:** Cookie

**Response 200:**

```ts
interface ValidateQuoteResponse {
  ok: true;
  pdf_url: string | null;     // /files/{quote_id}/<filename>.pdf
  excel_url: string | null;
  drive_url: string | null;
}
```

**Side effects:**
- Si existía `drive_file_id` previo: lo borra antes de subir el nuevo
- Si Drive upload falla, preserva `drive_url` previo (no sobrescribe con `null`)

**Errores:**
- `400 {"detail": "El presupuesto no tiene desglose calculado"}` — sin breakdown
- `404`

---

### `POST /api/quotes/{quote_id}/regenerate`

Re-emite PDF + Excel **sin recalcular**. No toca `status`, `client_name`, `project`, `totales`, `quote_breakdown`. Solo actualiza file URLs y appendea a `change_history`.

**Auth:** Cookie

**Response 200:**

```ts
interface RegenerateResponse {
  ok: true;
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
  regenerated_at: string;  // ISO datetime
}
```

**Side effects:**
- Re-toma campos editables del Quote columns (client_name, project, notes) por si fueron PATCH-eados sin regenerar
- Borra archivos Drive viejos (mejor effort)
- Sube PDF + Excel **separados** a Drive (cada uno con su `drive_url`)
- Append a `change_history` con `{action: "regenerate_docs", timestamp, ...}`
- Audit `docs.regenerated` (con `success=false` si Drive partial-fail)

**Errores:**
- `400 {"detail": "El presupuesto no tiene desglose calculado..."}`
- `404`
- `500 {"detail": "Falló la generación de documentos: <error>"}`

**Caso de uso:** corregiste un bug en el template Excel (formato, SKU mal). Querés regenerar archivos sin tocar nada del negocio.

---

### `POST /api/quotes/{quote_id}/generate`

Genera PDF + Excel + sube a Drive **para quotes web sin documentos**. Setea `status = validated`.

**Auth:** Cookie

**Response 200:**

```ts
interface GenerateResponse {
  ok: true;
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
}
```

**Diferencia con `/validate`:** este endpoint es para quotes que llegaron de `/api/v1/quote` (web bot) y nunca tuvieron docs. Pensar en él como "validate para web flow" — semánticamente equivalente pero el frontend lo llama desde el preview del quote web.

**Errores:**
- `400 {"detail": "Este presupuesto no tiene datos de cálculo (quote_breakdown)"}`
- `404`
- `500 {"detail": "<doc gen error>"}`

---

## Flow 7 · Reopen + Rehydrate

Endpoints para volver a un step previo o reparar quotes legacy.

### `POST /api/quotes/{quote_id}/reopen-measurements`

Vuelve a Paso 1 editable (PR #378). Limpia Paso 2 + MO + totales. Bloqueado en `validated`/`sent`.

**Auth:** Cookie

**Response 200:** `QuoteDetailResponse`

**Side effects:**
- Promueve `verified_measurements` → `dual_read_result` (preserva edits del operador)
- Trunca `messages` desde el último `__DUAL_READ__` y regenera la card con el despiece actualizado
- `total_ars`, `total_usd` → null
- Audit `quote.reopened` con `payload.kind = "measurements"`

**Errores:**
- `400 {"detail": "No hay confirmación de medidas que reabrir..."}`
- `404`
- `409 {"detail": "El presupuesto está en estado '<x>'. No se puede reabrir edición..."}`

---

### `POST /api/quotes/{quote_id}/rehydrate-history`

Repara quotes viejos cuyo `messages` tiene placeholders `_SHOWN_` vacíos, bloques internos del system prompt mezclados, o fake turns. **Idempotente** — si está limpio, `changed=false` y no UPDATE.

**Auth:** Cookie

**Response 200:**

```ts
interface RehydrateResponse {
  changed: boolean;
  before_count: number;
  after_count: number;
  // + más campos diagnósticos
}
```

**Uso típico:** operador abre quote pre-PR #380 y ve markers crudos. Llama este endpoint manualmente o vía un botón de admin.

---

## Flow 8 · Comparación (variantes)

### `GET /api/quotes/{quote_id}/compare`

Devuelve quote raíz + todos sus children/variants para comparación side-by-side. Mínimo 2 quotes para comparar.

**Auth:** Cookie

**Response 200:**

```ts
interface CompareQuotesResponse {
  parent_id: string;
  client_name: string;
  project: string;
  quotes: QuoteCompareItem[];
}

interface QuoteCompareItem {
  id: string;
  material: string | null;
  total_ars: number | null;
  total_usd: number | null;
  status: QuoteStatus;
  pdf_url: string | null;
  excel_url: string | null;
  drive_url: string | null;
  quote_breakdown: QuoteBreakdown | null;
}
```

**Errores:**
- `404 {"detail": "Presupuesto no encontrado"}`
- `404 {"detail": "Presupuesto padre no encontrado"}`
- `404 {"detail": "No hay variantes para comparar"}` — solo 1 quote en la familia

---

### `GET /api/quotes/{quote_id}/compare/pdf`

Genera y descarga un PDF comparativo side-by-side de todas las variantes.

**Auth:** Cookie

**Response 200:**
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="Comparativo - <client_name>.pdf"`
- Body: bytes del PDF

**Errores:**
- `404` (mismo que `/compare`)

---

### `POST /api/quotes/{quote_id}/derive-material`

Crea un quote NUEVO derivado del original con otro material. Copia client/pieces/options, recalcula todo. Status: `draft`. Sin docs.

**Auth:** Cookie

**Request body:**

```ts
interface DeriveMaterialRequest {
  material: string;              // min 1, max 500
  thickness_mm?: number;         // 1-100, opcional
}
```

**Response 200:**

```ts
interface DeriveMaterialResponse {
  ok: true;
  quote_id: string;             // ID del nuevo quote
  material: string;
  total_ars: number;
  total_usd: number;
  derived_from: string;         // ID del original
}
```

**Side effects:**
- `parent_quote_id` del nuevo apunta al original (o al root si el original ya tenía parent)
- `messages = []`, `change_history = []` — chat limpio en el derive
- `conversation_id` NO se copia

**Errores:**
- `400 {"detail": "El presupuesto original no tiene piezas. No se puede derivar."}`
- `400 {"detail": "Error al calcular con material 'X': <reason>"}` — material no encontrado, etc.
- `404 {"detail": "Presupuesto original no encontrado"}`

---

## Flow 9 · Email draft + Resumen Obra

### `GET /api/quotes/{quote_id}/email-draft`

Borrador de email comercial generado por IA. Lazy cache — regenera solo si hay invalidación (cambio en quote, sibling, o resumen_obra).

**Auth:** Cookie

**Response 200:**

```ts
interface EmailDraft {
  subject: string;
  body: string;
  generated_at: string;  // ISO datetime
  validated: boolean;    // operador marcó como OK
  // snapshots de updated_at usados para invalidación de cache
  quote_updated_at_snapshot: string;
  resumen_updated_at_snapshot: string | null;
  sibling_updated_at_snapshots: Record<string, string>;
}
```

**Errores:**
- Códigos custom desde `EmailDraftError` — el backend mapea a HTTP status. 404, 400, 500 según el caso.

---

### `POST /api/quotes/{quote_id}/email-draft/regenerate`

Fuerza regeneración del draft, bypass del cache.

**Auth:** Cookie

**Response 200:** `EmailDraft` (ver arriba)

---

### `POST /api/quotes/resumen-obra`

Genera PDF de "resumen de obra" consolidado de N quotes del mismo cliente. Persiste el record en cada quote seleccionado.

**Auth:** Cookie

**Request body:**

```ts
interface ResumenObraRequest {
  quote_ids: string[];        // 1 <= N <= 20
  notes?: string;             // max 1000 chars
  force_same_client?: boolean; // bypass de la validación de "mismo cliente"
}
```

**Response 200:**

```ts
interface ResumenObraRecord {
  pdf_url: string;
  drive_url: string | null;
  drive_file_id?: string | null;
  notes: string;
  generated_at: string;       // ISO datetime
  quote_ids: string[];
  client_name: string;
  project: string;
}
```

**Validaciones:**
- Mismo `client_name` en todos los quotes (a menos que `force_same_client`)
- Todos en `validated`
- 1 <= N <= 20
- `notes` <= 1000 chars

**Side effects:**
- Persiste `resumen_obra` en cada quote del set
- Invalida `email_draft` cache de cada quote (regen on next GET)

**Errores:**
- Custom desde `ResumenObraError` con status correspondiente

---

### `POST /api/quotes/client-match-check`

Preview: ¿estos quotes son del mismo cliente? Sirve al frontend para decidir si mostrar diálogo de confirmación antes de POST a `/resumen-obra`.

**Auth:** Cookie

**Request body:**

```ts
interface ClientMatchCheckRequest {
  quote_ids: string[];
}
```

**Response 200:**

```ts
interface ClientMatchCheckResponse {
  same: boolean;
  reason: "exact" | "fuzzy" | "ambiguous";
  distinct_names: string[];
}
```

**Errores:**
- `400 {"detail": "quote_ids vacío"}`
- `404 {"detail": "Presupuestos no encontrados: [...]"}`

---

### `POST /api/quotes/merge-client`

Renombra `client_name` de N quotes a un único valor canónico. Para unificar duplicados después de confirmar.

**Auth:** Cookie

**Request body:**

```ts
interface MergeClientRequest {
  quote_ids: string[];
  canonical_client_name: string;  // 1-500 chars
}
```

**Response 200:**

```ts
interface MergeClientResponse {
  ok: true;
  updated_ids: string[];      // los que efectivamente cambiaron
  client_name: string;
  quote_ids: string[];
}
```

**Side effects:**
- Invalida `email_draft` de los quotes (los names afectan el prompt)

**Errores:**
- `400 {"detail": "canonical_client_name requerido"}` / `"demasiado largo"` / `"quote_ids vacío"`
- `404 {"detail": "Presupuestos no encontrados: [...]"}`

---

## Flow 10 · Plan zone selection + Dual read retry

### `POST /api/quotes/{quote_id}/zone-select`

Recibe la selección de rectángulo del operador sobre una página del plano. Convierte bbox normalizado (0-1) a píxeles, persiste en `quote_breakdown.page_data` y `zone_default`.

**Auth:** Cookie

**Request body:**

```ts
interface ZoneSelectRequest {
  bbox_normalized: { x1: number; y1: number; x2: number; y2: number };  // 0-1 range
  page_num: number;  // default 1
}
```

**Response 200:**

```ts
interface ZoneSelectResponse {
  ok: true;
  bbox_px: [number, number, number, number];  // [x1, y1, x2, y2] en píxeles
  image_size: [number, number];                // [width, height]
}
```

**Errores:**
- `404 {"detail": "Quote not found"}`

---

### `POST /api/quotes/{quote_id}/dual-read-retry`

Operador-triggered. Cuando las medidas del despiece no coinciden con el plano, el frontend ofrece "Las medidas no coinciden" → este endpoint llama a Opus directamente sobre el crop guardado y reconcilia con el resultado Sonnet previo.

**Auth:** Cookie · **Timeout largo** (Opus vision toma 60-120s)

**Response 200:**

```ts
interface DualReadRetryResponse {
  // Mismo shape que dual_read_result en el chat SSE — ver sse-spec.md
  source: "DUAL" | "SOLO_OPUS";
  sectores: SectorDualRead[];
  m2_warning?: string;
  opus_error?: string;  // si Opus falló: card previa de Sonnet intacta + flag
  _retry: true;
  _crop_path: string;
}
```

**Errores:**
- `400 {"detail": "No prior dual read result found"}` — no hay despiece previo
- `400 {"detail": "Crop not saved — cannot retry"}` — falta el crop en disco
- `400 {"detail": "Crop file missing on disk"}`
- `404`

---

## Flow 11 · Files

### `GET /files/{file_path}`

Sirve archivos generados (PDFs, Excel, planos, sources). Resuelve a `OUTPUT_DIR/{file_path}` con protección path-traversal. Si el archivo NO está en disco local pero existe registro en `files_v2` con `drive_url` → redirect 302 a Drive (fallback para Railway con filesystem efímero).

**Auth:** Cookie

**Response 200:** bytes del archivo + `Content-Type` inferido por extensión.
**Response 302:** redirect a Drive download URL.

**Errores:**
- `403 "Acceso denegado"` — path traversal detectado
- `404 "Archivo no encontrado"`

**Ejemplos:**
- `GET /files/{quote_id}/<client> - <material> - <date>.pdf`
- `GET /files/{quote_id}/<client> - <material> - <date>.xlsx`
- `GET /files/{quote_id}/sources/plano.pdf`
- `GET /files/{quote_id}/page_1.jpg` — render rasterizado del plano

---

## Flow 12 · Catalog management

15 catálogos disponibles, identificados por `name`:

```
labor · delivery-zones · sinks · architects · config · stock
materials-silestone · materials-purastone · materials-dekton ·
materials-neolith · materials-puraprima · materials-laminatto ·
materials-granito-nacional · materials-granito-importado · materials-marmol
```

### `GET /api/catalog/`

Lista todos los catálogos con metadata.

**Auth:** Cookie

**Response 200:**

```ts
type ListCatalogsResponse = Array<{
  name: string;
  item_count: number;
  last_updated: string | null;  // ISO datetime
  size_kb?: number;
}>;
```

---

### `GET /api/catalog/{catalog_name}`

Devuelve el contenido completo del catálogo (array u objeto JSON, según el tipo).

**Auth:** Cookie

**Response 200:** JSON literal del catálogo. Ver `catalog/*.json` en este directorio para el shape de cada uno.

**Errores:**
- `404 {"detail": "Catálogo no encontrado"}`

---

### `PUT /api/catalog/{catalog_name}`

Actualiza el contenido de un catálogo. Crea backup `.bak` antes. Escritura atómica (temp file + rename).

**Auth:** Cookie

**Request body:**

```ts
interface CatalogUpdateRequest {
  content: object | object[];  // Union[list, dict] — depende del catálogo
}
```

**Response 200:**

```ts
interface CatalogUpdateResponse {
  ok: true;
  catalog: string;
}
```

**Side effects:**
- Invalida cache del catálogo en memoria
- Si es `config`: invalida también `company_config` cache

**Errores:**
- `403 {"detail": "Catálogo no permitido"}` — name no está en `ALLOWED_CATALOGS`

---

### `POST /api/catalog/{catalog_name}/validate`

Valida un body de catálogo SIN guardarlo. Detecta cambios de precio > 30% (warning, no bloqueante).

**Auth:** Cookie

**Request body:** mismo que `PUT`.

**Response 200:**

```ts
interface CatalogValidateResponse {
  valid: boolean;
  warnings: Array<{
    type: "warning" | "error";
    sku?: string;
    message: string;
  }>;
  item_count: number;
}
```

---

### `POST /api/catalog/import-preview`

Sube un archivo de export Dux (`.xls`, `.xlsx`, `.csv`) → parsea → genera preview de cambios por catálogo. NO modifica nada.

**Auth:** Cookie · **Content-Type:** `multipart/form-data`

**Form fields:**
- `file: UploadFile` — el export Dux

**Response 200:** estructura de preview agrupada por catálogo (updated/new/missing/zero_price + warnings).

**Errores:**
- `400 {"detail": "Archivo sin nombre"}`
- `400 {"detail": "Formato no soportado: <ext>..."}`
- `400 {"detail": "Archivo vacío"}`

---

### `POST /api/catalog/import-apply`

Aplica el import preview-eado. Side effects: actualiza catálogos + crea backup.

**Auth:** Cookie · **Content-Type:** `multipart/form-data` (mismo file que preview)

**Response 200:** `{ok: true, applied: {...}}`

---

### `GET /api/catalog/backups/{catalog_name}`

Lista backups de un catálogo.

**Auth:** Cookie

**Response 200:** array de `{id, created_at, source_file, stats}`.

---

### `POST /api/catalog/backups/{backup_id}/restore`

Restaura un backup específico.

**Auth:** Cookie

**Response 200:** `{ok: true, catalog: <name>}`

---

## Flow 13 · Observability (audit log)

Endpoints **bajo `/api/admin/...`** — uso interno solamente. Marina no los ve, son para developers/operadores con sesión JWT.

### `GET /api/admin/quotes/{quote_id}/audit`

Timeline ascendente de eventos del quote (max 500).

**Auth:** Cookie · **Rechaza API key** (solo JWT user)

**Response 200:**

```ts
interface AuditTimelineResponse {
  quote_id: string;
  events: AuditEvent[];
  coverage: {
    first_event_date: string | null;     // ISO
    has_events_for_quote: boolean;
  };
}

// Ver schemas/audit_events.md para AuditEvent completo
```

---

### `GET /api/admin/observability`

Vista global de events con filtros + paginación.

**Auth:** Cookie

**Query params:**

```ts
interface GlobalAuditQuery {
  event_type?: string;
  actor?: string;
  success?: boolean;
  quote_id?: string;
  source?: string;
  from?: string;   // ISO datetime, alias del query param "from"
  to?: string;     // ISO datetime, alias del query param "to"
  limit?: number;  // 1-200, default 50
  offset?: number; // default 0
}
```

**Response 200:**

```ts
interface GlobalAuditResponse {
  events: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}
```

---

### `GET /api/admin/observability/quotes`

Vista agrupada por `quote_id` (para listing en `/admin/observability`). Cada row resume events del quote.

**Auth:** Cookie

**Query params:**

```ts
interface ObservabilityQuotesQuery {
  q?: string;             // search en quote_id o client_name
  actor?: string;
  has_errors?: boolean;
  has_debug?: boolean;
  from?: string;          // ISO
  to?: string;            // ISO
  limit?: number;
  offset?: number;
}
```

**Response 200:**

```ts
interface ObservabilityQuotesResponse {
  quotes: Array<{
    quote_id: string;
    client_name: string | null;
    actor: string | null;          // primer actor del quote
    events_count: number;
    errors_count: number;
    has_debug_payloads: boolean;
    first_event_at: string;
    last_event_at: string;
  }>;
  total: number;
  limit: number;
  offset: number;
}
```

---

### `GET /api/admin/audit/coverage`

Devuelve `first_event_date` global (sirve para el empty state "audit log empezó el ...").

**Auth:** Cookie

**Response 200:**

```ts
interface AuditCoverageResponse {
  first_event_date: string | null;  // ISO
  total_events: number;
}
```

---

### `POST /api/admin/audit/cleanup`

Retention manual. Lo invoca un Railway scheduled job con `curl POST`.

**Auth:** Cookie

**Query params:**

```ts
interface AuditCleanupQuery {
  retention_days?: number;  // 1-3650, default 90
}
```

**Response 200:**

```ts
interface AuditCleanupResponse {
  rows_deleted: number;
  retention_days: number;
}
```

**Side effects:**
- Loguea su propia ejecución como `audit.cleanup_run`

---

### `GET /api/admin/system-config/global-debug`

Estado del modo debug global (Phase 2 observability — captura payloads grandes).

**Auth:** Cookie · **Rechaza API key**

**Response 200:**

```ts
interface GlobalDebugStatus {
  enabled: boolean;
  mode: "1h" | "end_of_day" | "manual" | null;
  until: string | null;          // ISO
  started_at: string | null;     // ISO
  started_by: string | null;     // username
  remaining_seconds: number | null;
}
```

---

### `POST /api/admin/system-config/global-debug`

Activa/desactiva el modo debug global.

**Auth:** Cookie · **Rechaza API key**

**Request body:**

```ts
interface GlobalDebugToggleRequest {
  mode: "1h" | "end_of_day" | "manual" | "off";
}
```

**Response 200:** `GlobalDebugStatus`

**Side effects:**
- Audit `audit.global_debug_toggled` con previous_state + new_state

**Errores:**
- `400 {"detail": "Modo inválido: 'X'"}`
- `403 {"detail": "Endpoint solo accesible con sesión JWT (API key rechazada)."}`

---

### `POST /api/admin/audit/global-debug-shutoff`

Cron auto-shutoff del modo debug. Lo llama Railway scheduled job. Apaga si `until < NOW()` o si `manual + started_at > 24h`. Idempotente.

**Auth:** Cookie

**Response 200:**

```ts
interface GlobalDebugShutoffResponse {
  apagados: number;
  razones: { expired: number; manual_24h_cap: number; };
}
```

**Side effects:**
- Si apaga: audit `audit.global_debug_auto_disabled`
- Siempre: audit `audit.global_debug_shutoff_run` (breadcrumb del cron)

---

## Flow 14 · Usage (token tracking)

Tracking de gasto Anthropic API (Sonnet 4.5 + Opus 4.6).

### `GET /api/usage/dashboard`

Resumen del mes actual + alertas.

**Auth:** Cookie

**Response 200:**

```ts
interface UsageDashboardResponse {
  month: string;             // "2026-05"
  month_label: string;       // "May 2026"
  spent_usd: number;         // round 4 decimals
  limit_usd: number;
  pct_used: number;          // 0-100
  daily_avg: number;
  daily_budget: number;
  projected: number;         // proyectado a fin de mes
  days_passed: number;
  days_left: number;
  requests: number;
  alert: "ok" | "yellow" | "red" | "blocked";
  enable_hard_limit: boolean;
}
```

**Alertas:**
- `ok`: < 80% del budget
- `yellow`: >= 80%
- `red`: proyectado > limit
- `blocked`: spent >= limit (hard limit triggered)

---

### `GET /api/usage/daily`

Breakdown diario últimos 30 días.

**Auth:** Cookie

**Response 200:**

```ts
type DailyUsageResponse = Array<{
  date: string;             // "2026-05-04" (zona AR)
  cost_usd: number;
  requests: number;
  input_tokens: number;
  output_tokens: number;
}>;
```

---

### `PATCH /api/usage/budget`

Actualiza el monthly budget limit en `config.json`.

**Auth:** Cookie

**Request body:**

```ts
interface BudgetUpdateRequest {
  monthly_budget_usd?: number;
  enable_hard_limit?: boolean;
}
```

**Response 200:** `{ ok: true }`

**Side effects:**
- Persiste en `config.json` → `ai_engine` section
- Invalida `_ai_config_cache`

---

## Flow 15 · API pública (web bot)

### `POST /api/v1/quote`

Endpoint público para crear quotes desde el chatbot externo. Auth via API key (no cookie).

**Auth:** Header `X-API-Key: <key>` (skipeado si `QUOTE_API_KEY` env vacío en dev)

**Request body:** `QuoteInput` — ver `schemas/brief.md` para shape completo. Resumen:

```ts
interface QuoteInput {
  client_name: string;            // 1-200
  project?: string;               // max 200, default ""
  material: string | string[];
  pieces?: PieceInput[] | null;   // null si manda notes en lugar de medidas estructuradas
  localidad: string;              // 1-100
  colocacion?: boolean;           // default true
  pileta?: PiletaType;
  sink_type?: SinkType;
  pileta_sku?: string;            // max 64
  anafe?: boolean;
  frentin?: boolean;
  pulido?: boolean;
  skip_flete?: boolean;
  plazo?: string;                 // 1-100, default desde config.json
  discount_pct?: number;          // 0-100
  date?: string;                  // DD/MM/YYYY
  conversation?: object[];        // chat history del bot
  notes?: string;                 // texto libre
}
```

**Response 200:**

```ts
interface QuoteResponse {
  ok: boolean;
  quotes: QuoteResultItem[];     // 1 por cada material en la lista
  error?: string;
}

interface QuoteResultItem {
  quote_id: string;              // "web-<uuid>"
  material: string;
  material_m2: number;
  material_price_unit: number;
  material_currency: "USD" | "ARS";
  material_total: number;
  mo_items: Array<{
    description: string;
    quantity: number;
    unit_price: number;
    total: number;
  }>;
  total_ars: number;
  total_usd: number;
  merma: { aplica: boolean; desperdicio: number; sobrante_m2: number; motivo: string };
  discount: { aplica: boolean; porcentaje: number; monto: number };
  pdf_url: null;          // siempre null — operator valida via /validate
  excel_url: null;
  drive_url: null;
}
```

**Comportamiento:**
- 1 quote DB por cada material en `material[]`
- Si llega `pileta_sku` y matchea catálogo → se agrega como producto físico
- Si NO llega `pieces` pero sí `notes`: intenta parsear texto con Claude. Si falla → quote DRAFT vacío.
- Si llega `pieces` válidas → quote `status=PENDING` con breakdown calculado, **sin docs** (operador valida después)
- Si NO llega `pieces` y `notes` está vacío → quote `status=DRAFT`
- Resuelve `pileta` desde `pileta_sku` o `sink_type` si `pileta` no viene explícito
- Persiste el body raw en `Quote.web_input` (PR #400)

**Errores:**
- `401 {"detail": "API key inválida o faltante"}` — si `QUOTE_API_KEY` está seteado y no matchea
- `422` — Pydantic validation (campos faltantes, tipos mal)
- Response con `ok: false, error: "..."` para errores de cálculo (material no encontrado, etc.)

---

### `POST /api/v1/quote/{quote_id}/files`

Sube archivos (planos, fotos) a un quote web existente.

**Auth:** Header `X-API-Key` · **Content-Type:** `multipart/form-data`

**Form fields:**
- `files: UploadFile[]` — hasta 5

**Response 200:**

```ts
interface UploadFilesResponse {
  ok: true;
  saved: number;
  errors: string[];
  files: SourceFile[];
  // PR #394: si el quote es source=web Y se guardaron archivos:
  estimate_skipped?: true;
  estimate_skip_reason?: "web_upload_manual_review";
  message?: string;  // texto para mostrar al cliente del bot
}
```

**Comportamiento:**
- Restricciones: PDF/JPEG/PNG/WEBP, max 10MB c/u, max 5 archivos
- Guarda en `OUTPUT_DIR/{quote_id}/sources/` (con fallback a `/tmp` si falla permission)
- Sube a Drive ("Archivos Origen" subfolder) — best effort
- **PR #394:** quotes web con `source="web"` que reciben archivo NO disparan auto-estimate. El operador revisa manual.
- Quotes con otros sources que reciben archivo SÍ disparan procesamiento automático en background (Valentina lee plano → calcula → persiste breakdown)

**Errores:**
- `200` con `ok: false, error: "Quote not found"` — sí, devuelve 200 con error en body
- `200` con `ok: false, error: "Maximum 5 files per request"`

---

### `GET /api/v1/business-rules`

Reglas de negocio v0 que el chatbot externo necesita para capturar leads sin romper.

**Auth:** Header `X-API-Key`

**Response 200:** schema `BusinessRulesV0` (ver `api/app/modules/business_rules/schema.py` en backend para shape completo).

**Headers:**
- `Cache-Control: public, max-age=3600`
- `ETag: "<sha256-16chars>"` — usable en `If-None-Match`

**Response 304** si `If-None-Match` coincide con el ETag actual.

---

## Flow 16 · Admin endpoints

Solo para sysadmins con sesión JWT.

### `POST /api/admin/analyze-plans-vectorality`

Analiza últimos N quotes y clasifica `source_files` como `vectorial_clean` / `vectorial_and_raster` / `raster_only` / `unknown`. Útil para decidir si el fast-path vectorial vale la pena.

**Auth:** Cookie

**Query params:**

```ts
interface AnalyzeVectoralityQuery {
  limit?: number;  // 1-1000, default 200
}
```

**Response 200:**

```ts
interface AnalyzeVectoralityResponse {
  total_analyzed: number;
  counts: Record<string, number>;
  percentages: Record<string, number>;
  recommend_2d: boolean;
}
```

---

### `POST /api/admin/backfill-drive`

Re-genera PDF/Excel y sube a Drive para quotes validados que no tienen `drive_pdf_url`. Idempotente — skipea quotes que ya tienen Drive URLs. Lee del breakdown existente, NO recalcula.

**Auth:** Cookie

**Response 200:**

```ts
interface BackfillDriveResponse {
  total: number;
  results: Array<{
    id: string;
    client?: string;
    material?: string;
    status: "ok" | "skipped" | "error";
    reason?: string;
    drive_pdf?: boolean;
    drive_excel?: boolean;
  }>;
}
```

---

## Health check

### `GET /health` — público

**Auth:** ninguna

**Response 200:**

```ts
interface HealthResponse {
  status: "ok";
  service: "marble-operator-api";
  db: "connected";
}
```

**Response 503** si la DB no responde:

```ts
interface UnhealthyResponse {
  status: "unhealthy";
  service: "marble-operator-api";
  db: "unreachable";
}
```

---

## Mapeo mockup ↔ endpoint

Para Sprint 2, los mockups del Master §6 se mapean así (referencia rápida — el detalle está en cada flow arriba):

| Paso (Mockup) | Endpoints relevantes |
|---|---|
| **Paso 1 · Brief** (00-A/B/C) | `POST /api/quotes` (crear vacío) → `POST /api/quotes/{id}/chat` (subir plano + brief, multipart) → SSE stream |
| **Paso 2 · Contexto** (01-A, 02-B, 03-C) | `GET /api/quotes/{id}` (leer breakdown) · `PATCH /api/quotes/{id}` (editar campos) · `POST /api/quotes/{id}/chat` (chat scoped) · `POST /api/quotes/{id}/reopen-context` (volver atrás) |
| **Paso 3 · Despiece** (04-A1/2, 04-P, 05-B, 06-C) | `POST /api/quotes/{id}/chat` (Valentina llama `list_pieces` tool) · `POST /api/quotes/{id}/zone-select` (operador marca zona) · `POST /api/quotes/{id}/dual-read-retry` (re-trigger Opus) · `POST /api/quotes/{id}/reopen-measurements` |
| **Paso 4 · Cómputo** (07-A v3/v4, 08-B, 09-C) | `POST /api/quotes/{id}/chat` (Valentina llama `calculate_quote` tool) · `PATCH /api/quotes/{id}` (editar pieces, anafe, etc.) |
| **Paso 5 · Cotización** (18-A, 19-B, 20-C, 21-D, 22-E) | `POST /api/quotes/{id}/validate` (genera docs + status=validated) · `POST /api/quotes/{id}/regenerate` (re-emite sin recalcular) · `GET /api/quotes/{id}/email-draft` · `GET /files/{quote_id}/<filename>.pdf` |
| **Paso 5-D · Diff drawer** (21-D) | `GET /api/quotes/{id}/compare` + `GET /api/quotes/{id}/compare/pdf` |
| **Paso 5-E · Vencido** (22-E) | `PATCH /api/quotes/{id}/status` (transition `validated → draft` para "renovar") |
| **Bloque E · Dashboard** (23, 24, 25) | `GET /api/quotes` (lista) · `GET /api/quotes/check` (polling) · `GET /api/quotes/{id}` (detalle) · `PATCH /api/quotes/{id}/read` |
| **13 · Audit banner** | `GET /api/admin/quotes/{id}/audit` · `GET /api/admin/system-config/global-debug` |
| **15 · IA error** | Manejado en SSE (event type `error` + flag `done.error: true`) — no endpoint dedicado |
| **16 · Empty despiece** | Estado vacío del frontend — no requiere endpoint |
| **17 · Chat error** | Visualización de mensaje con `flagged: true` — feedback va a audit log via `chat.message_sent` con flag |
| **Comparación variantes** | `POST /api/quotes/{id}/derive-material` (crear variant) → `GET /api/quotes/{id}/compare` |
| **Resumen de obra** | `POST /api/quotes/client-match-check` → `POST /api/quotes/merge-client` (si necesario) → `POST /api/quotes/resumen-obra` |
| **Mobile flow** (10, 11, 12, 23, 24) | Mismos endpoints que desktop. Mobile es read-only para crear quotes (Master §10 decisión 13) — solo lista + detalle. |

Ver `missing-endpoints.md` para endpoints sugeridos por mockups que NO existen hoy en backend.

---

## Archivos backend leídos para derivar este spec

- `api/app/modules/auth/router.py` (125 líneas)
- `api/app/modules/agent/router.py` (2389 líneas — todos los endpoints `/api/quotes/*`, `/api/files/*`, admin)
- `api/app/modules/agent/schemas.py` (141 líneas — Quote* response/request schemas)
- `api/app/modules/quote_engine/router.py` (553 líneas — `/api/v1/quote*`)
- `api/app/modules/quote_engine/schemas.py` (93 líneas — `QuoteInput`, `PieceInput`, `PiletaType`, `SinkType`)
- `api/app/modules/catalog/router.py` (442 líneas)
- `api/app/modules/observability/router.py` (678 líneas — todos `/api/admin/*`)
- `api/app/modules/observability/models.py` (82 líneas — `AuditEvent`)
- `api/app/modules/usage/router.py` (148 líneas)
- `api/app/modules/business_rules/router.py` (66 líneas)
- `api/app/models/quote.py` (119 líneas — modelo `Quote` con `quote_kind`, `quote_breakdown`, etc.)
- `api/API.md` (882 líneas — doc base existente, validada y extendida acá)
