# Missing Endpoints — sugeridos por mockups, no implementados

> **Cuándo crear este archivo:** solo si encontrás un mockup que sugiere una llamada al backend que NO existe hoy.
> **Última revisión:** 2026-05-05.

Audité los 30 mockups del Master §6 contra los routers reales del backend (commit `1915317`). La mayoría de las interacciones de mockup mapean a endpoints existentes — ver tabla "Mapeo mockup ↔ endpoint" al final de `endpoints-spec.md`. Este archivo lista **lo que falta o está ambiguo**.

> **Severidad:** P1 = bloqueante para Sprint 2. P2 = nice-to-have, frontend puede mockear sin romper. P3 = sugerencia de naming/cleanup.

---

## P2 · `POST /api/quotes/{id}/brief` (dedicated)

**Mockups donde aparece:** `00-paso1-A-vacio`, `00-paso1-B-subido`, `00-paso1-C-procesando`.

**Qué hace:** subir el brief inicial (PDF + fotos + textarea + chips IA) ANTES de empezar el chat con Valentina. El mockup B muestra un botón "Continuar a contexto" que sugiere una transición distinta del chat normal.

**Realidad backend:** **NO EXISTE endpoint dedicado.** El brief se manda dentro del primer turno del chat vía multipart `POST /api/quotes/{id}/chat`. Detalle en `schemas/brief.md`.

**Sugerencia:**

- **Opción A (sin cambios backend):** frontend Sprint 2 manda todo en `POST /chat`. El "Continuar a contexto" del mockup arranca el primer SSE stream → Valentina emite `context_analysis` que aparece en el mockup `01-A`.
- **Opción B (backend agrega `/brief`):** un endpoint nuevo `POST /api/quotes/{id}/brief` que solo persiste files + textarea + chips, SIN arrancar el agente. Después un endpoint `POST /api/quotes/{id}/process` arranca el chat. Ventaja: separa "subir" de "procesar" — el operador puede subir, navegar a otra cosa, volver. Desventaja: complejidad extra.

**Decisión recomendada:** Opción A para Sprint 2. Mockear el flow completo contra `POST /chat`. Si Marina pide "guardar borrador sin procesar" en QA, evaluar Opción B en Sprint 3.

---

## P2 · Estructura para `BriefChip[]`

**Mockup:** `00-paso1-B-subido` muestra brief chips con marca "IA" y "+ agregar" custom.

**Realidad backend:** El backend NO conoce el concepto "brief chip". Marina escribe libre en el textarea, y Valentina extrae chips durante `context_analysis`. El data model del Master §10 menciona `BriefChip[]` pero como abstracción del frontend.

**Sugerencia:** frontend Sprint 2 mantiene `BriefChip[]` como state local. Al mandar el `POST /chat`, concatena los chips al `message` con un separador (ej. `[Brief: cocina + baño] [Material: silestone] [Plazo: urgente] <textarea libre>`). Valentina los procesa como parte del brief.

**Si hace falta endpoint:** crear `POST /api/quotes/{id}/brief-chips` que solo persiste el array — el frontend lee del response del `GET /quotes/{id}` que tendría un campo `brief_chips: BriefChip[]` nuevo en el modelo. Por ahora innecesario.

---

## P3 · `POST /api/quotes/{id}/share-pdf`

**Mockups donde aparece:** `20-paso5-C-generado` muestra "Compartir con cliente" + opciones email/whatsapp/copy link.

**Realidad backend:** **NO EXISTE.** El frontend tendría que:

- Email → mandar al cliente vía mailto: link o un sistema externo (no hay endpoint que mande email desde el server)
- WhatsApp → web link `https://wa.me/<phone>?text=<encoded url del PDF>`
- Copy link → URL pública del PDF en Drive (`drive_url`) o link interno (`/files/{quote_id}/...` con auth)

**Decisión Master §10 #20:** "Compartir con cliente: Solo PDF (Excel es interno del taller)". El frontend ya puede implementar esto sin endpoint backend nuevo — el `drive_url` del quote es público (compartido vía Service Account, link sharing on).

**Sugerencia:** mockear como function client-side. Si Sprint 4-5 pide tracking de "cuántas veces el cliente abrió el PDF" → ahí sí hace falta endpoint backend.

---

## P3 · Tracking de visitas al PDF (mockup `22-paso5-E-vencido`)

**Mockup:** `22-paso5-E-vencido` muestra "tracking visitas" del PDF.

**Realidad backend:** **NO EXISTE.** El backend no instrumenta clicks al PDF de Drive ni al endpoint `/files/`.

**Sugerencia:**

- Si solo querés saber "el cliente abrió el PDF" → usar Drive API view tracking (Google Workspace ya provee analytics básicas — no requiere código)
- Si querés UI rich con timestamps por visita → endpoint nuevo `POST /api/quotes/{id}/pdf-view` que registra cada GET a `/files/{quote_id}/...pdf` (instrumenta el endpoint files con audit log) y `GET /api/quotes/{id}/pdf-views` que lista los hits.

**Decisión recomendada:** Sprint 4-5. No bloqueante para Sprint 2. Frontend muestra "tracking visitas: —" como placeholder.

---

## P3 · Renovar presupuesto vencido (mockup `22-paso5-E-vencido`)

**Mockup:** botón "Renovar (genera v2)".

**Realidad backend:** existe el flow para crear v2 — `PATCH /api/quotes/{id}/status` con `validated → draft` → operador edita → `POST /quotes/{id}/regenerate`. NO hay un único endpoint "renovar" que haga todo.

**Sugerencia:** frontend Sprint 4-5 puede componer la secuencia. Si se vuelve común, agregar `POST /api/quotes/{id}/renew` que internamente:

1. Cambia status a draft
2. Append a change_history `{action: "renewed", reason: "vencimiento"}`
3. Devuelve el quote actualizado

No bloqueante.

---

## P3 · Audit per-row endpoint dedicado

**Mockups:** `13-audit-banner-on` + cualquier row con `data-audit=on` (mockup 02, 05, etc.).

**Realidad backend:** existe `GET /api/admin/quotes/{id}/audit` que devuelve TODOS los events del quote (max 500). El mockup muestra un panel `.aud-trail` específico de UNA row (ej. ediciones de la cell "client_name").

**Sugerencia:** el frontend puede:

- Pedir el timeline completo y filtrar client-side por field/cell — está OK para 500 events
- O agregar query param `?field=<field_name>` al endpoint para filtrar server-side

No bloqueante. La filtración client-side es trivial.

---

## P2 · "Pegar URL" en dropzone (mockup `00-paso1-A-vacio`)

**Mockup:** botón secundario "Pegar URL" alternativo al "Subir plano".

**Realidad backend:** **NO EXISTE.** El backend solo acepta uploads multipart, no URLs externas.

**Sugerencia:**

- Frontend descarga la URL → upload normal multipart (problema CORS si la URL es de dominio externo)
- Backend nuevo: `POST /api/quotes/{id}/fetch-url` que accept `{url: string}` y descarga server-side. Validaciones: `https://` only, max 20MB descarga, allowed mime, etc.

**Decisión recomendada:** Sprint 4-5. No bloqueante. Mockup tiene el botón pero podría ser greyed-out con tooltip "próximamente".

---

## P2 · Cambio explícito de `exchange_rate` (USD/ARS)

**Mockup:** `07-paso4-A-v4` muestra chip `USD/ARS @ 1430` clickeable → modal cambiar.

**Realidad backend:** El `exchange_rate` se setea internamente en `calculate_quote()` desde `config.json` o un default hardcoded. **NO HAY endpoint para cambiarlo on-demand desde el frontend** — está embebido en el cálculo.

**Sugerencia:**

- **Opción A (sin endpoint):** chip muestra el valor pero NO es editable. Cambios al exchange rate van por `PUT /api/catalog/config` (que ya existe).
- **Opción B (agregar param):** `calculate_quote` tool acepta `exchange_rate` opcional. El frontend manda override al chat: "recalculá con cotización 1430". Valentina lo respeta.

**Decisión recomendada:** Opción A. El operador edita el config raras veces, no necesita UI inline.

---

## P3 · Bulk operations en Dashboard

**Mockups:** `25-paso-dashboard-C-desktop` muestra checkboxes y bulk actions ("Marcar como leídos", "Exportar selección a CSV").

**Realidad backend:** **NO EXISTE.** Las operaciones son individuales (PATCH /quotes/{id}, etc.).

**Sugerencia:** Sprint 4-5. Frontend puede iterar individualmente al principio. Si performance se vuelve issue, agregar:

- `POST /api/quotes/bulk-read` con `{ids: string[]}` — marca N como leídos
- `POST /api/quotes/bulk-export` con `{ids: string[], format: "csv"}` — devuelve CSV download

No bloqueante.

---

## P3 · KPI cards del Dashboard

**Mockup:** `25-paso-dashboard-C-desktop` muestra 4 cards (Total mes, En curso, Aprobados, Vencidos) con números agregados.

**Realidad backend:** **NO EXISTE endpoint dedicado de KPIs.** El frontend tendría que:

- Pedir `GET /api/quotes` con filtros + contar
- O contar localmente sobre el state

**Sugerencia:** crear `GET /api/quotes/kpis` que devuelve agregaciones precomputadas:

```ts
interface KPIsResponse {
  current_month: {
    total_count: number;
    total_ars_sum: number;
    total_usd_sum: number;
    by_status: Record<QuoteStatus, number>;
  };
  in_progress: number;
  approved: number;
  expired: number;
  // etc.
}
```

**Decisión recomendada:** Sprint 4-5 (cuando se implementa el dashboard). Para Sprint 2 mockear contra dataset compartido (Master §13 dataset 47 quotes).

---

## P3 · Empty states

**Mockup:** `16-empty-despiece-lateral` con paths "Subir plano" / "Completar a mano".

**Realidad backend:** los 2 paths del mockup se mapean a:

- "Subir plano" → `POST /chat` con archivo (existe)
- "Completar a mano" → arranca un chat con texto "no tengo plano" → Valentina pregunta medidas (existe)

**Sin endpoint nuevo.** El frontend solo tiene que manejar la decisión del operador y disparar el chat correspondiente.

---

## Resumen

| # | Endpoint sugerido | Severidad | Sprint sugerido |
|---|---|---|---|
| 1 | `POST /api/quotes/{id}/brief` | P2 | Skip — usar `/chat` |
| 2 | `BriefChip[]` estructurado | P2 | Skip — frontend state local |
| 3 | `POST /api/quotes/{id}/share-pdf` | P3 | Sprint 4-5 |
| 4 | Tracking visitas PDF | P3 | Sprint 4-5 (opcional) |
| 5 | `POST /api/quotes/{id}/renew` | P3 | Sprint 4-5 |
| 6 | Audit per-row con filtro | P3 | Skip — filtrar client-side |
| 7 | `POST /api/quotes/{id}/fetch-url` (dropzone URL) | P2 | Sprint 4-5 |
| 8 | Editar `exchange_rate` inline | P2 | Skip — usar `PUT /catalog/config` |
| 9 | Bulk operations dashboard | P3 | Sprint 4-5 |
| 10 | `GET /api/quotes/kpis` | P3 | Sprint 4-5 (cuando se implemente dashboard) |

**Conclusión para Sprint 2:** ningún endpoint de los listados arriba bloquea Sprint 2. El frontend puede arrancar el wire-up de Paso 1 + Paso 2 contra los endpoints existentes hoy. Las features marcadas P2 que afectan UX inmediata (pegar URL, exchange rate inline) tienen workarounds aceptables.

Si durante el wire-up de Sprint 2 el frontend descubre algo que NO está en esta lista y NO tiene endpoint → agregar entry a este archivo en un PR de actualización al handoff branch (no bloquear el PR de Sprint 2 — abrir issue separado).

---

## Archivos backend revisados para confirmar gaps

- Todos los routers (`api/app/modules/*/router.py`)
- Lista exhaustiva de endpoints en `endpoints-spec.md`
- Mockups del Master §6 (referencia visual en `docs/handoff-design/design_files/*.html`)
