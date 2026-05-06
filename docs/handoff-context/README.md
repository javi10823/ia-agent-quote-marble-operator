# Handoff Context · Specs Técnicas Backend

> **Audiencia:** frontend Sprint 2-5 del operator panel D'Angelo (Marina + Valentina).
> **Fuente:** código backend FastAPI real del repo `ia-agent-quote-marble-operator`.
> **Last commit:** PR `sprint-1.5/extract-api-contracts` — 2026-05-05.

Esta carpeta contiene las **specs técnicas del backend** que el frontend Sprint 2 va a usar para mockear contra contratos reales (`useMockClient()` → `useApiClient()` switch en Sprint 3 inicial). Las specs son **derivadas del código backend** — no documentación inventada.

---

## Estado

🟢 **Cerrado** por PR `sprint-1.5/extract-api-contracts` el 2026-05-05.

Cualquier cambio futuro en el backend se sincroniza vía nuevo PR contra `sprint-1.5/master-handoff` (ver "Cómo se mantiene actualizado" más abajo).

---

## Estructura

```
handoff-context/
├── README.md                  ← este archivo (índice)
├── endpoints-spec.md          ← ~50 endpoints REST agrupados por flow del Master §6
├── sse-spec.md                ← protocolo SSE chat Valentina (7 event types)
├── missing-endpoints.md       ← endpoints sugeridos por mockups que NO existen hoy
├── schemas/
│   ├── quote.md               ← modelo Quote completo + QuoteBreakdown JSON
│   ├── audit_events.md        ← schema audit_events + lista de event_types
│   ├── brief.md               ← Paso 1 (operator multipart vs web bot QuoteInput)
│   └── context.md             ← Paso 2 (columnas Quote + cards IA + verified_context)
└── catalog/
    ├── README.md              ← reglas de sanitización + lista de archivos
    ├── architects.json        ← Cueto-Heredia canon + 7 placeholders
    ├── config.json            ← literal (no PII)
    ├── delivery-zones.json    ← Rosario canon + 31 sintetizadas
    ├── labor.json             ← 5 SKUs MO Cueto-Heredia + 29 sintetizados
    ├── materials-silestone.json   ← SILESTONENORTE canon + 4 samples
    ├── materials-purastone.json   ← 5 samples sintéticos
    ├── materials-granito-nacional.json
    ├── materials-granito-importado.json
    ├── materials-dekton.json
    ├── materials-neolith.json
    ├── materials-marmol.json
    ├── materials-puraprima.json
    ├── materials-laminatto.json
    ├── sinks.json             ← 12 samples (de 85 originales)
    └── stock.json             ← 5 retazos sample
```

**Tamaño total:** ~228 KB · **Líneas Markdown:** 3786 · **Archivos JSON:** 16.

---

## Cómo leer este handoff

Orden recomendado para alguien que arranca Sprint 2:

1. **`endpoints-spec.md`** — entender el universo de endpoints que el frontend va a tocar. Especialmente la sección "Mapeo mockup ↔ endpoint" al final.
2. **`sse-spec.md`** — entender el protocolo del chat con Valentina. Es el endpoint más complejo y donde más errores se cometen.
3. **`schemas/quote.md`** — modelo central. Los demás schemas se entienden mejor después de este.
4. **`schemas/brief.md`** + **`schemas/context.md`** — específicos de Paso 1 y Paso 2 (el alcance principal de Sprint 2).
5. **`schemas/audit_events.md`** — relevante para Sprint 3 (`/admin/quotes/{id}/audit` panel).
6. **`catalog/`** — fixtures sanitizadas para mockear `GET /api/catalog/{name}`.
7. **`missing-endpoints.md`** — qué falta y cómo workaroundear.

---

## Cifras canónicas Cueto-Heredia preservadas (Master §13)

Como pide el PR (regla 6 — "NO sanitizar datos del Master"), estas cifras viven literal en los specs y catálogos para que el frontend Sprint 2 pueda armar fixtures que producen exactamente:

```
PRESUPUESTO TOTAL: $660.890 mano de obra + USD 1.538 material
```

| Donde | Valor canon |
|---|---|
| `architects.json` | `CUETO-HEREDIA ARQUITECTAS` (5% importado) |
| `labor.json` | COLOCACION $49.698,65 · PEGADOPILETA $53.840 · ANAFE $35.617,36 · REGRUESO $13.810 · TOMAS $6.461 (todos base s/IVA) |
| `delivery-zones.json` | ENVIOROS Rosario $52.000 base (= $62.920 c/IVA) |
| `materials-silestone.json` | SILESTONENORTE USD 206 base (= USD 249 c/IVA — cifra del mockup, **bug P2 a propósito** Master §12) |
| `endpoints-spec.md` (ejemplos) | totales completos del case |
| `schemas/quote.md` (cifras canon) | breakdown completo + ChatMessage examples |

---

## Métricas del PR `extract-api-contracts`

- **Endpoints documentados:** ~50 (incluye ~30 del operator, 3 del web bot, 8 admin observability + audit, 3 usage, 1 business-rules, 8 catalog management)
- **Schemas:** 4 documentos (quote, audit_events, brief, context)
- **SSE event types:** 7 reales documentados (text, action, dual_read_result, context_analysis, zone_selector, done, error) + ping keepalive
- **Catálogos sanitizados:** 15 archivos JSON (~32 KB total)
- **Missing endpoints:** 10 sugeridos por mockups, **ninguno bloqueante para Sprint 2**

## Archivos backend leídos para derivar este spec

Detalle al final de cada archivo. Resumen consolidado:

- `api/app/modules/auth/router.py` (125 líneas)
- `api/app/modules/agent/router.py` (2389 líneas)
- `api/app/modules/agent/schemas.py` (141 líneas)
- `api/app/modules/quote_engine/router.py` (553 líneas)
- `api/app/modules/quote_engine/schemas.py` (93 líneas)
- `api/app/modules/quote_engine/calculator.py` (~1950 líneas — solo el shape de return)
- `api/app/modules/quote_engine/context_analyzer.py` (782 líneas)
- `api/app/modules/quote_engine/dual_reader.py` (líneas 461, 657 — shape DualReadResult)
- `api/app/modules/catalog/router.py` (442 líneas)
- `api/app/modules/observability/router.py` (678 líneas)
- `api/app/modules/observability/models.py` (82 líneas)
- `api/app/modules/observability/sanitizer.py` + `system_config.py` + `cleanup.py`
- `api/app/modules/usage/router.py` (148 líneas)
- `api/app/modules/business_rules/router.py` (66 líneas)
- `api/app/models/quote.py` (119 líneas)
- `api/CONTEXT.md` (referencia de SKUs y cifras canon)
- `api/API.md` (882 líneas — doc base existente, validada y extendida)
- 15 catálogos JSON en `api/catalog/`

---

## Quién lo escribe (sólo para referencia post-handoff)

Claude Code, en el PR `sprint-1.5/extract-api-contracts`. Ver Master sección 21.8 + 22 (roles) para alcance, reglas y criterios de audit.

## Quién lo lee

Sprint 2+ del frontend. Cuando un sub-PR de Sprint 2 implementa paso 1 o paso 2, lee de acá los shapes de request/response para tipar los hooks y mockear las llamadas API.

## Cómo se mantiene actualizado

Cuando el backend cambia (nuevo endpoint, nueva regla, nueva tool):

1. Backend hace el cambio en su repo (separado).
2. Claude Code abre PR a este branch (`sprint-1.5/master-handoff`) con la spec actualizada (Markdown derivado, no código crudo).
3. Master/Audit (instancia Claude separada) audita el PR.
4. Javi mergea.
5. Claude Code lee la spec nueva en su próximo prompt de feature.

NUNCA se actualiza automáticamente. Toda actualización es vía PR auditado.

---

## Próximos pasos post-merge

1. **Audit del PR** — instancia separada de Claude (Master/Audit) revisa coherencia con mockups + cifras canon presentes + sin código de producción + sin credenciales.
2. **Merge a `sprint-1.5/master-handoff`** — Javi mergea con `gh pr merge`.
3. **Apertura de `sprint-2/main`** — branch integrador del Sprint 2.
4. **Primer sub-PR `sprint-2/scaffold`** — Claude Code arranca Sprint 2 leyendo este `handoff-context/` + `handoff-design/`.
