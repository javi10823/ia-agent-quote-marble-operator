# Schema · audit_events

> **Fuente:** `api/app/modules/observability/models.py` + `observability/router.py` + `observability/__init__.py`.
> **Última actualización:** 2026-05-05.

Tabla append-only. Cada acción operacional del sistema (creación de quote, edits, generación de docs, fallos de la IA, retries del operador) deja un row. Sirve a **dos casos de uso**:

1. **Timeline per-quote** (`/admin/quotes/{id}/audit`) — alimenta el panel `.aud-trail` que aparece en el mockup `13-audit-banner-on` y en cada row con `data-audit=on`.
2. **Vista global** (`/admin/observability` + `/admin/observability/quotes`) — debugging cross-quote: "todos los regenerate_docs por usuario X en los últimos 7 días", "qué quotes tuvieron errores de calculate_quote esta semana".

---

## Tabla `audit_events` — columnas

```ts
interface AuditEventRow {
  id: string;                         // UUID v4 — PK, generado en cliente Python
  created_at: string;                 // TIMESTAMPTZ NOT NULL — generado en client Python
                                      // (NO server-default NOW() — preserva orden de inserción
                                      //  dentro de una misma transacción)

  event_type: string;                 // VARCHAR(64) NOT NULL — ver enum abajo
  source: string;                     // VARCHAR(32) NOT NULL — qué módulo lo emitió:
                                      // "router" | "agent" | "validator" | "cron" | "calc"
                                      // | "observability"

  quote_id: string | null;            // VARCHAR(64) — FK lógica a quotes.id (no enforced)
  session_id: string | null;          // VARCHAR(64) — populado con quote_id cuando aplica;
                                      // reservado para sesiones multi-quote en el futuro

  actor: string;                      // VARCHAR(120) NOT NULL — username del JWT, "api-key", o "system"
  actor_kind: "user" | "api_key" | "system";  // VARCHAR(20) NOT NULL

  request_id: string | null;          // VARCHAR(64) — correlation ID por HTTP request
                                      // (set por middleware) — busca todos los events
                                      // de una misma llamada HTTP
  turn_index: number | null;          // INTEGER — índice en Quote.messages cuando aplica chat

  summary: string;                    // TEXT NOT NULL — frase humana corta para listar UI
                                      // sin parsear payload (max 8000 chars truncado server-side)
  payload: object;                    // JSONB NOT NULL DEFAULT '{}' — sanitizado + truncado
  payload_truncated: boolean;         // flag explícito para que la UI muestre "payload truncado"
  debug_payload: boolean;             // TRUE si grabado con global_debug activo
                                      // (payload puede pesar hasta 16 KB con
                                      //  tool_input/tool_result/brief completos)

  success: boolean;                   // default true — false si la acción falló
  error_message: string | null;       // TEXT — solo si success=false
  elapsed_ms: number | null;          // INTEGER — duración de la acción
}
```

---

## Event types

Lista de event_types emitidos hoy (verificado contra grep `log_event(...event_type=` en el repo):

### Lifecycle del quote

| event_type | Source | Trigger | Payload típico |
|---|---|---|---|
| `quote.created` | `router` | `POST /api/quotes` | `{status: "draft"}` |
| `quote.patched` | `router` | `PATCH /api/quotes/{id}` | `{fields: ["client_name", "material"]}` (sanitizer redacta phone/email) |
| `quote.status_changed` | `router` | `PATCH /api/quotes/{id}/status` | `{from: "draft", to: "validated"}` |
| `quote.reopened` | `router` | `/reopen-measurements` o `/reopen-context` | `{kind: "measurements" \| "context", msgs_pre: N, msgs_post: M, truncate_matched: bool}` |
| `quote.calculated` | `agent` o `calc` | `calculate_quote()` exitoso | `{material_m2, total_ars, total_usd, sectors_count}` (truncated to 4KB para "heavy event") |
| `quote.calc_failed` | `agent` | `calculate_quote()` falló | `{error, input_summary}` |

### Chat + agent loop

| event_type | Source | Trigger |
|---|---|---|
| `chat.message_sent` | `router` | `POST /api/quotes/{id}/chat` arranca |
| `agent.tool_called` | `agent` | Cada `<tool_use>` block emitido por Claude |
| `agent.tool_result` | `agent` | Cada `<tool_result>` evaluado |
| `agent.iteration_completed` | `agent` | Fin de un iteration del loop |
| `agent.stream_done` | `agent` | Fin del SSE stream |
| `agent.error` | `agent` | Excepción no recuperable |
| `agent.rate_limit_retry` | `agent` | 429 de Anthropic, reintentando |
| `agent.overloaded_retry` | `agent` | 529 de Anthropic, reintentando |

### Documentos (Paso 5)

| event_type | Source | Trigger |
|---|---|---|
| `docs.generated` | `agent` | Tool `generate_documents` exitosa |
| `docs.regenerated` | `router` | `POST /api/quotes/{id}/regenerate` |
| `docs.validation_failed` | `agent` | Validador profundo rebotó (ej. m² mismatch) |
| `drive.upload_failed` | `agent` o `router` | Drive API falló |

### Card / dual read

| event_type | Source | Trigger |
|---|---|---|
| `dual_read.executed` | `agent` | Lectura visual del plano (Sonnet+Opus) |
| `dual_read.retry_requested` | `router` | `POST /api/quotes/{id}/dual-read-retry` |
| `context_analysis.emitted` | `agent` | Card de contexto generada |
| `zone_select.recorded` | `router` | `POST /api/quotes/{id}/zone-select` |

### Resumen + email

| event_type | Source | Trigger |
|---|---|---|
| `resumen_obra.generated` | `router` | `POST /api/quotes/resumen-obra` |
| `email_draft.generated` | `router` | `GET /api/quotes/{id}/email-draft` (cuando regenera) |
| `email_draft.regenerated` | `router` | `POST /api/quotes/{id}/email-draft/regenerate` |
| `client.merged` | `router` | `POST /api/quotes/merge-client` |

### Sistema / observability

| event_type | Source | Trigger |
|---|---|---|
| `audit.cleanup_run` | `observability` | `POST /api/admin/audit/cleanup` (cron) |
| `audit.global_debug_toggled` | `observability` | `POST /api/admin/system-config/global-debug` |
| `audit.global_debug_auto_disabled` | `observability` | Cron auto-shutoff cumplió condición |
| `audit.global_debug_shutoff_run` | `observability` | Breadcrumb del cron (siempre, incluso rows=0) |

**Nota:** la lista anterior es exhaustiva al momento del audit. Si encontrás un `event_type` distinto en producción, asumir que está sin documentar (no es bug — solo doc-debt).

---

## Sanitización de `payload`

Antes de persistir, el helper `log_event()` aplica:

1. **Lista negra de keys** (case-insensitive substring match):
   ```
   password, token, secret, api_key, apikey, authorization, cookie,
   phone, telefono, whatsapp, address, direccion, dni, cuit, email,
   client_name, cliente, nombre_cliente
   ```
   Valor de cualquier key que matchee → `"<redacted>"`.

2. **Truncado por bytes**:
   - Default: 2 KB
   - Heavy events (`quote.calculated`, `docs.generated`, `docs.regenerated`): 4 KB
   - Modo debug global activo: 16 KB

   Si excede → payload reemplazado por `{key: "<truncated>"}` (preserva shape) + `payload_truncated=true`.

3. **No filtra por valor** (no busca patrones tipo "número de teléfono"). Solo por nombre de key. **Trade-off explícito:** simplicidad > completitud heurística.

---

## Modo debug global

Toggle on-demand para capturar payloads grandes (tool_input, tool_result, message_text completos) durante debugging.

```ts
interface GlobalDebugStatus {
  enabled: boolean;
  mode: "1h" | "end_of_day" | "manual" | null;
  until: string | null;              // ISO — auto-off
  started_at: string | null;
  started_by: string | null;
  remaining_seconds: number | null;
}
```

**Cuándo se activa:**

- Operador clickea toggle en `/admin/observability`
- Modos: `1h` (60min), `end_of_day` (23:59 AR), `manual` (hard cap 24h)

**Cuándo se desactiva:**

- Operador toggle off
- Cron `/admin/audit/global-debug-shutoff` (Railway scheduled job)

**Efecto:** mientras está ON, `log_event()` graba `debug_payload=true` y permite payloads hasta 16KB con datos sensibles (tool_input puede tener brief completo, tool_result puede tener despiece raw).

**Bundle copy del frontend NO incluye** payloads de events con `debug_payload=true` — placeholder `<debug payload available in /admin/quotes/X/audit, NOT included in bundle>`. Se ven en la UI con login JWT.

---

## Índices

```sql
CREATE INDEX idx_audit_event_quote_created ON audit_events (quote_id, created_at DESC);
CREATE INDEX idx_audit_event_type_created  ON audit_events (event_type, created_at DESC);
CREATE INDEX idx_audit_event_actor_created ON audit_events (actor, created_at DESC);
CREATE INDEX idx_audit_event_request_id    ON audit_events (request_id);
```

Diseñados para los queries frecuentes:

- Timeline de un quote (`WHERE quote_id = ? ORDER BY created_at`)
- Filtro global por event_type / actor / fecha
- Correlation por request_id

---

## Render en frontend

### Card `.aud-trail` (per-row)

Cuando `data-audit="on"` en el body:

- Cada celda editable muestra un `.aud-i` (ⓘ trigger)
- Click → expande `.aud-trail` panel inline con events filtrados a esa cell
- Style: monospace, dim, max 5 events visibles + "ver todos" link

### Banner `.audit` (top de pantalla)

Mockup `13-audit-banner-on`:

- Fondo rojo, dot pulse, copy mono
- Lista contador agregado: "AUDIT MODE · 3 ediciones humanas en este flujo · ver auditoría"
- Click → drawer con timeline completo del quote

### Timeline `/admin/quotes/{id}/audit`

Vista dedicada para developers/operadores. Lista de events ordenados ASC con:

- Timestamp + event_type + actor
- Summary (humana)
- Botón "Ver payload" (toggle del JSON sanitizado)
- Filtro por success/error
- Bundle copy → genera string para Slack/ticket

---

## Performance

Mediciones reales del query principal (10K events, 200 quotes):

- `/admin/observability/quotes`: p95 = 6.81ms
- `/admin/quotes/{id}/audit`: p95 < 5ms (limit 500, índice quote_id+created_at)

Ambos endpoints son seguros para llamarse desde el banner de audit (que se encience con cada nueva entry del quote actual).

---

## Archivos backend leídos para derivar este schema

- `api/app/modules/observability/models.py` (82 líneas — `AuditEvent` SQLAlchemy)
- `api/app/modules/observability/router.py` (líneas 47-115 — response schemas + endpoints)
- `api/app/modules/observability/__init__.py` (resumen del módulo)
- `api/app/modules/observability/sanitizer.py` (lista negra de keys + truncado)
- `api/app/modules/observability/system_config.py` (modelo `SystemConfig` para `global_debug`)
- `api/app/modules/observability/cleanup.py` (retention manual)
