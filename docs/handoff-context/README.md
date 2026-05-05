# Handoff Context · Specs Técnicas Backend

Esta carpeta contiene las **specs técnicas del backend FastAPI** que el frontend necesita para wire-up. Las specs son derivadas del código backend real, NO documentación inventada.

## Estado actual

🟡 **Vacío al momento del handoff inicial.**

Se llena con el PR `sprint-1.5/extract-api-contracts` antes de arrancar Sprint 2.

## Estructura esperada (post-PR extract-api-contracts)

handoff-context/
endpoints-spec.md ← cada endpoint REST que el frontend usa
sse-spec.md ← protocolo SSE del chat Valentina
schemas/
quote.md ← modelo Quote completo
audit_events.md ← schema audit_events
brief.md ← modelo Brief
context.md ← 11 campos paso 2
catalog/ ← 9 catálogos JSON sanitizados
materials.json
labor.json
sinks.json
architects.json
config.json
delivery-zones.json
stock.json
finishes.json (si existe)
edges.json (si existe)
missing-endpoints.md ← (si aplica) endpoints sugeridos por mockups que NO existen en backend

## Quién lo escribe

Claude Code, en el PR `sprint-1.5/extract-api-contracts`. Ver Master Notion sección 21.8 para alcance, reglas y criterios de audit.

## Quién lo lee

Sprint 2+ del frontend. Cuando un sub-PR de Sprint 2 implementa paso 1 o paso 2, lee de acá los shapes de request/response para tipar los hooks y mockear las llamadas API.

## Cómo se mantiene actualizado

Cuando el backend cambia (nuevo endpoint, nueva regla, nueva tool):

1. Backend hace el cambio en su repo (separado).
2. Claude Code abre PR a este branch con la spec actualizada (Markdown derivado, no código crudo).
3. Master/Audit (instancia Claude separada) audita el PR.
4. Javi mergea.
5. Claude Code lee la spec nueva en su próximo prompt de feature.

NUNCA se actualiza automáticamente. Toda actualización es vía PR auditado.
