# SSE Spec · Chat Valentina

> **Fuente:** código backend real (`api/app/modules/agent/router.py` líneas 2342-2389 + `agent.py` event yields).
> **Endpoint:** `POST /api/quotes/{quote_id}/chat`
> **Última actualización:** 2026-05-05.

El chat con Valentina usa **Server-Sent Events** (SSE) sobre HTTP/1.1. El backend stream chunks JSON en formato `data: {...}\n\n`. El frontend consume con `EventSource` o `fetch().body.getReader()`.

---

## Conexión

### Request

```http
POST /api/quotes/{quote_id}/chat HTTP/1.1
Cookie: auth_token=<jwt>
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="message"

Texto del operador
--boundary
Content-Disposition: form-data; name="plan_files"; filename="plano.pdf"
Content-Type: application/pdf

<bytes>
--boundary--
```

**Form fields:**

| Campo | Tipo | Required | Validación |
|---|---|---|---|
| `message` | string | Sí | Texto del operador. Puede contener markers especiales (ver abajo). |
| `plan_files` | file[] | No | Hasta **10** archivos. PDF/JPEG/PNG/WEBP. Max **10MB** c/u. PDFs deben ser **1 página**. |

**Markers reservados en `message`:**

- `[DUAL_READ_CONFIRMED]` — operador confirmó la card de despiece
- `[CONTEXT_CONFIRMED]` — operador confirmó la card de contexto (con respuestas inline)
- `[SYSTEM_TRIGGER:<event>]` — handlers internos (no escribir manualmente)

### Response headers

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
Connection: keep-alive
```

`X-Accel-Buffering: no` es **crítico** — sin él, Railway/nginx bufferean el stream y los chunks llegan en bloque al final.

---

## Format de chunks

Cada chunk es una línea SSE:

```
data: {"type": "<type>", "content": "<content>", ...}

```

(Doble newline al final separa chunks.)

**Excepción** — keepalive:

```
: keepalive

```

(Comment SSE, sin `data:`.) El cliente ignora estos.

---

## Event types

7 tipos reales emitidos por el backend (verificado contra `agent/router.py:2354-2380` + yields en `agent.py`):

### `text` — fragmento de respuesta

Token-by-token streaming de la respuesta de Valentina.

```ts
interface TextEvent {
  type: "text";
  content: string;  // delta — concatenar para reconstruir el mensaje
}
```

**Frecuencia:** alta — varios por segundo durante streaming. El frontend debe coalescer con `requestAnimationFrame` para no saturar React (1 update por frame).

**Contenido:** texto plano + markdown limitado (`**bold**`, `\n`, links `[label](url)`, tablas pipe-separated). El componente `MessageBubble` del frontend ya lo parsea.

---

### `action` — tool use en progreso

Banner de loading mientras Valentina ejecuta una tool del agente loop.

```ts
interface ActionEvent {
  type: "action";
  content: string;  // descripción humana del tool en ejecución
}
```

**Ejemplos de `content`:**

- `"⚙️ Ejecutando: catalog_batch_lookup..."`
- `"⚙️ Ejecutando: list_pieces..."`
- `"📐 Leyendo medidas del plano..."`
- `"⚙️ Ejecutando: calculate_quote..."`
- `"⚙️ Ejecutando: generate_documents..."`
- `"⏳ Esperando disponibilidad... (5s)"` (rate limit retry)
- `"⏳ Servicio ocupado, reintentando... (10s)"` (Anthropic 529)
- `"✏️ Aplicando cambios al card..."` (card_editor)

**Render del frontend:** mapeable al `<StatusBar>` con `vbubble` think animation (Master §9). Cuando llega un nuevo `action`, reemplaza el anterior. Cuando llega un `text`, ocultar la status-bar.

---

### `dual_read_result` — card de despiece

Card del Paso 3 (despiece) emitida después de leer un plano. `content` es un **JSON string** (no objeto) que el frontend debe `JSON.parse()`.

```ts
interface DualReadResultEvent {
  type: "dual_read_result";
  content: string;  // JSON string de DualReadResult
}

// Después de JSON.parse(content):
interface DualReadResult {
  source: "DUAL" | "SOLO_OPUS" | "SOLO_SONNET";  // qué modelos contribuyeron
  sectores: Sector[];
  requires_human_review: boolean;
  conflict_fields: string[];
  view_type: "top_view" | "side_view" | "unknown";
  view_type_reason?: string;
  m2_warning?: string;            // si la suma del despiece no matchea la planilla declarada
  pending_questions?: PendingQuestion[];
  opus_error?: string;            // si /dual-read-retry fue triggered y Opus falló
  _retry?: true;                  // flag interno post-retry
  _crop_path?: string;            // path interno del crop guardado en disco
}

interface Sector {
  tipo: "cocina" | "baño" | "isla" | "lavadero" | "l" | "u" | "recta";
  tramos: Tramo[];
  m2_total: FieldValue<number>;
  ambiguedades: Ambiguedad[];
}

interface Tramo {
  id: string;
  descripcion: string;
  largo_m: FieldValue<number>;
  ancho_m: FieldValue<number>;
  m2: FieldValue<number>;
  zocalos?: Zocalo[];
  _derived?: true;     // para tramos auto-generados (ej. patas de isla)
  _kind?: "isla_pata" | "alzada" | string;
}

interface Zocalo {
  lado: "frente" | "atrás" | "izquierda" | "derecha";
  ml: number;
  alto_m: number;
}

// Cada FieldValue contiene el valor consolidado + qué modelo lo aportó
interface FieldValue<T = number> {
  opus?: T | null;
  sonnet?: T | null;
  valor: T;
  status: "CONFIRMADO" | "DUAL_AGREE" | "DUAL_DIVERGENT" | "SOLO_OPUS" | "SOLO_SONNET";
}

interface Ambiguedad {
  field: string;
  detail: string;
}

interface PendingQuestion {
  id: string;          // ej. "anafe_count", "pileta_simple_doble"
  question: string;    // texto humano
  options?: string[];  // opciones predefinidas (radio buttons)
}
```

**Side effect del backend:** persiste el card en `Quote.messages` con marker `__DUAL_READ__<json>` para poder reconstruir la conversación al reabrir el quote.

**Render del frontend:** Master §9 menciona `<EditableTable cols-despiece>` para la card del Paso 3. Ver mockups `04-despiece-A`, `05-despiece-B`, `06-despiece-C`.

---

### `context_analysis` — card de análisis de contexto

Card emitida ANTES del despiece (PR G — flow nuevo). Resume lo que Valentina detectó del brief + plano + análisis técnico.

```ts
interface ContextAnalysisEvent {
  type: "context_analysis";
  content: string;  // JSON string de ContextAnalysis
}

// Después de JSON.parse(content):
interface ContextAnalysis {
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
  field: string;        // ej. "client_name", "material", "localidad"
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
  field: string;                                    // ej. "tomas_count", "anafe_count"
  detected: boolean;
  status: "verified" | "needs_confirmation";
  confidence: number;
  detail?: string;                                  // descripción humana
  options?: string[];                               // si needs_confirmation
}
```

**Side effect del backend:** persiste con marker `__CONTEXT_ANALYSIS__<json>` en `messages`.

**Render del frontend:** mapeable al panel de Paso 2 (Master §6 mockups `01-A`, `02-B`, `03-C`). Cada tech_detection con `needs_confirmation` se renderea con radio buttons inline.

---

### `zone_selector` — selector de zona en plano

Aparece cuando el agente necesita que el operador marque una zona del plano (visual_pages flow para edificios). Frontend muestra la imagen + permite dibujar rectángulo + manda `POST /api/quotes/{id}/zone-select`.

```ts
interface ZoneSelectorEvent {
  type: "zone_selector";
  content: string;  // JSON string
}

// Después de JSON.parse(content):
interface ZoneSelectorPayload {
  image_url: string;        // ej. "/files/{quote_id}/page_1.jpg"
  page_num: number;
  instruction: string;      // copy humano: "Dibujá un rectángulo sobre la zona de la mesada de mármol"
}
```

**Flow:**

1. Backend emite `zone_selector` + `done`
2. Frontend muestra UI de selección sobre `image_url`
3. Operador marca rectángulo (coordenadas normalizadas 0-1)
4. Frontend hace `POST /api/quotes/{id}/zone-select` con `{bbox_normalized, page_num}`
5. Operador escribe mensaje "ya marqué" en el chat → arranca nuevo turno SSE

---

### `done` — fin del stream

```ts
interface DoneEvent {
  type: "done";
  content: "";       // siempre vacío
  error?: true;      // solo si hubo error en el stream (ver event "error" abajo)
}
```

El frontend cierra la conexión al recibir esto. Si `error: true` viene, el último mensaje del usuario falló — UI debe mostrar opción "reintentar".

---

### `error` — error durante el stream

```ts
interface ErrorEvent {
  type: "error";
  content: string;   // mensaje humano, ej. "⚠️ Error inesperado: <detail>. Intentá de nuevo."
}
```

**Cuándo se emite:**

- Excepción no controlada en el agent loop
- Anthropic API error no recuperable (no 429, no 529)
- Timeout interno

**Siempre seguido por** `data: {"type": "done", "content": "", "error": true}` para cerrar el stream.

**Render frontend:** mostrar el `content` en el bubble de Valentina con styling `.msg.v.error` (mockup 17). Ofrecer botones "Reintentar" / "Reportar".

---

### `ping` — keepalive (no es un data event)

Comment SSE para mantener viva la conexión cuando Valentina está pensando. No se emite como `data:`, va como comment:

```
: keepalive

```

**Cuándo:** el backend lo emite cada ~10s durante operaciones largas (Opus vision para planos complejos puede tomar 60-120s).

**Frontend:** ignorar. La librería SSE estándar no lo expone como event — es transparente.

---

## Flow típico — caso Cueto-Heredia (Master §13)

Operador adjunta plano del depto Cueto-Heredia (Silestone Blanco Norte, 6,50 m²).

```
1.  data: {"type": "action", "content": "📐 Leyendo medidas del plano..."}
2.  data: {"type": "context_analysis", "content": "{...data_known: [...], assumptions: [...], pending_questions: [{id: 'anafe_count', ...}]}"}
3.  data: {"type": "done", "content": ""}
   [operador responde la pending_question + dispara nuevo turno]

4.  data: {"type": "action", "content": "✏️ Aplicando cambios al card..."}
5.  data: {"type": "dual_read_result", "content": "{...sectores: [{tipo: 'cocina', tramos: [...], m2_total: {valor: 6.50, status: 'CONFIRMADO'}}], requires_human_review: false}"}
6.  data: {"type": "done", "content": ""}
   [operador escribe "[DUAL_READ_CONFIRMED]" → confirma despiece]

7.  data: {"type": "action", "content": "⚙️ Ejecutando: catalog_batch_lookup..."}
8.  data: {"type": "action", "content": "⚙️ Ejecutando: calculate_quote..."}
9.  data: {"type": "text", "content": "## PASO 2 — Validación"}
10. data: {"type": "text", "content": "\n\nPRESUPUESTO TOTAL: $660.890 mano de obra + USD 1.538 material"}
11. data: {"type": "done", "content": ""}
   [operador valida → POST /api/quotes/{id}/validate genera PDF/Excel/Drive fuera del SSE]
```

---

## Reconexión + manejo de errores en cliente

### Connection drop

El backend NO implementa reconexión automática vía `Last-Event-ID`. Si la conexión se corta:

- Frontend re-fetcha el quote completo: `GET /api/quotes/{id}` → renderea desde `messages`
- Si el último turno quedó incompleto en messages, mostrar como interrumpido
- Cliente puede reintentar con un nuevo `POST /chat` — el backend deduplica por hash del plano

### Connect timeout

El cliente debe abortar el fetch si el server no devuelve headers en **60s** (Anthropic puede demorar en arrancar). El frontend ya tiene esto (`web/src/lib/api.ts` con `AbortController` + 60s timeout).

### Stall timeout

Si no llega ningún chunk durante **90s**, abortar. El backend debería estar emitiendo `: keepalive` cada ~10s — si no llega nada, la conexión está muerta.

### Error transitorio (429, 502, 503)

- `429` rate limit del operator panel → mostrar "Esperá un minuto" en el chat
- `502/503/504` → mostrar "El servidor está reiniciando. Esperá unos segundos e intentá de nuevo"
- `429` de Anthropic (interno, no llega como HTTP del operator) → el agent loop reintenta automáticamente con backoff (5s, 10s, 15s) y emite `action` chunks de progreso

---

## Tools del agente Valentina

Aunque las tools NO se exponen como REST, su existencia afecta lo que el SSE emite. Lista de las **9 tools** definidas en `agent.py:1212-1221`:

| Tool | Descripción | Cuándo Valentina la llama |
|---|---|---|
| `list_pieces` | Lista piezas con texto exacto + total m² | Paso 1 obligatorio cuando hay despiece |
| `catalog_lookup` | Precio de 1 SKU | Paso 2 cuando necesita 1 precio |
| `catalog_batch_lookup` | Precios de múltiples SKUs | Preferido sobre lookup individual para 2+ |
| `check_stock` | Retazos disponibles en taller | Antes de calcular merma |
| `check_architect` | Verifica si cliente es arquitecta con descuento | Paso 2 cuando hay nombre |
| `read_plan` | Zoom táctico en zonas del plano | Solo para detalles ilegibles, max 2 crops/llamada |
| `calculate_quote` | Cálculo determinístico (m², MO, totales) | Paso 2 SIEMPRE |
| `generate_documents` | PDF + Excel + Drive | Cuando el operador confirma |
| `update_quote` | Update DB sin recalcular | Cambios menores (delivery_days, etc.) |
| `patch_quote_mo` | Modificar MO específicamente | Edits dirigidos sin recálculo completo |

**Reglas hard del agente** (Master §5, replicadas acá para referencia frontend):

- Cliente Y proyecto bloqueantes — sin los dos, Valentina NO arranca
- PROHIBIDO en Paso 1: `catalog_lookup`, `catalog_batch_lookup`, `calculate_quote`. Solo `list_pieces`.
- `list_pieces` rendera con texto exacto — frontend NO recalcula m² manualmente
- Frases prohibidas en `text` events: "mientras", "voy a buscar", "dejame verificar", "voy a recortar", "¿Es edificio?"

---

## ⚠️ Verificar contra implementación real

- **Reconexión vía `Last-Event-ID`:** no se implementa hoy. Si el frontend Sprint 2 lo necesita, agregarlo via PR backend separado.
- **Order garantías:** dentro de un turno, el orden de events sí está garantizado. Entre turnos, el backend espera al `done` del anterior antes de procesar uno nuevo.
- **Rate limit retry messages:** el formato exacto de `"⏳ Esperando disponibilidad... (Xs)"` puede cambiar — frontend debe NO parsear el contenido, solo mostrar como banner.

---

## Archivos backend leídos para derivar este spec

- `api/app/modules/agent/router.py` (líneas 2342-2389 — el `event_stream()` generator)
- `api/app/modules/agent/agent.py` (yields de los 7 event types — buscar `yield {"type":` y `chunks.append({"type":`)
- `api/app/modules/quote_engine/dual_reader.py` (líneas 461, 657 — shape de `DualReadResult`)
- `api/app/modules/quote_engine/context_analyzer.py` (líneas 747-805 — shape de `ContextAnalysis`)
