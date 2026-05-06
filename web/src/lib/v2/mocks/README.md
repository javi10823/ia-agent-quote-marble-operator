# Mocks · v2

Esta carpeta queda vacía en el scaffold. Se llena en sub-PR
`sprint-2/paso-1-brief-upload` con:

- `quotes.ts` — fixtures basadas en cifras canon Cueto-Heredia
  (Master §13: PRES-2026-018, $660.890 ARS + USD 1.538)
- `catalogs.ts` — wrapper de los JSONs sanitizados de
  `docs/handoff-context/catalog/`
- `chat-stream.ts` — replay de SSE event types reales documentados
  en `docs/handoff-context/sse-spec.md`

Pattern esperado (`useMockClient()` vs `useApiClient()` switch):
mock-first hasta Sprint 3 inicial, luego swap a backend real con
1 PR de inversión en hooks.

Ver `docs/handoff-context/README.md` para el contrato completo.
