# Auditoría técnica y de producto — D'Angelo Marble Operator

---

## 1. Resumen ejecutivo

### Principales problemas

1. **Sin autenticación.** Cualquier persona con la URL puede leer, modificar y eliminar presupuestos, cambiar precios de catálogo, y acceder a documentos. Es el riesgo #1.
2. **Google Drive bloquea el event loop.** Las llamadas síncronas de `googleapiclient` congelan TODAS las requests concurrentes mientras sube un archivo a Drive. Bajo carga real, el sistema se traba.
3. **God components en frontend.** `quote/[id]/page.tsx` tiene 750 líneas con 11 componentes. 100% inline styles. Zero responsiveness. Cero componentes reutilizables.
4. **Errores silenciosos.** Migraciones de DB fallan sin log. Dashboard no muestra error si la API cae. Sidebar traga excepciones. El operador nunca sabe que algo falló.

### Mayores oportunidades

1. **Migrar a Tailwind real** (ya instalado, sin usar) eliminaría hover hacks, habilitaría responsive y reduciría JSX un 40%.
2. **Centralizar estado con Context/Zustand** eliminaría fetches redundantes (sidebar hace fetch en cada navegación).
3. **`asyncio.to_thread()`** en Drive/PDF/Excel desbloquearía el event loop con cambio mínimo.
4. **Auth básica con API key** protegería endpoints críticos con esfuerzo bajo.

### Mayores riesgos

- Path traversal en upload de archivos (filenames no sanitizados)
- Catálogos modificables sin auth → manipulación de precios
- Documentos accesibles sin auth vía `/files/`
- Multi-commit no atómico en generación de documentos → estado inconsistente

---

## 2. Hallazgos por categoría

### UX/UI

| Problema | Impacto | Propuesta |
|----------|---------|-----------|
| **Zero responsiveness** — sin media queries, sidebar fija 212px, tablas no colapsan | Inutilizable en tablet/móvil | Migrar a Tailwind, agregar breakpoints responsive |
| **100% inline styles** — hover via JS, sin pseudo-clases, JSX lleno de objetos style | Imposible hacer hover/focus real, mantenimiento muy difícil | Migrar a Tailwind (ya instalado) |
| **Sin estados de error** — dashboard silencia fetches fallidos, config no muestra error en save | Operador no sabe si algo falló | Agregar error boundaries + estados de error explícitos |
| **Sin empty states** — tabla vacía sin mensaje | Confuso si no hay presupuestos | Agregar ilustración/mensaje "No hay presupuestos" |
| **Sin confirmación en cambio de estado** — un click cambia draft→validated sin undo | Click accidental irreversible | Agregar confirmación o undo de 5 seg |
| **Botón "Exportar CSV" no funciona** — `onClick={() => {}}` | Genera desconfianza | Implementar o remover |
| **Sin keyboard navigation** — tabla con `<tr onClick>` sin tabIndex | Accesibilidad rota | Agregar `tabIndex`, `onKeyDown`, ARIA labels |
| **Sin ARIA labels** — SVGs, botones, inputs sin labels | Screen readers no funcionan | Agregar `aria-label` a elementos interactivos |

### Performance

| Problema | Causa | Propuesta |
|----------|-------|-----------|
| **Google Drive bloquea event loop** | `googleapiclient` es síncrono, llamado desde async | Wrap con `asyncio.to_thread()` |
| **PDF/Excel "fake async"** | `asyncio.gather` no paraleliza I/O síncrono | Wrap `_generate_pdf`/`_generate_excel` con `asyncio.to_thread()` |
| **Sidebar fetch en cada navegación** | `useEffect` depende de `path`, hace fetch completo | Cache global con Context o SWR/React Query |
| **`list_quotes` carga messages** | `select(Quote)` trae columna JSON pesada | Excluir `messages` del SELECT del listado |
| **Sistema prompt lee disco cada request** | 6-9 archivos leídos por request | Cache en memoria con TTL |
| **Sin memoización en dashboard** | `filteredQuotes`, `statusCounts` recalculados en cada render | `useMemo` |
| **SSE setState itera todo el array** | `setMessages(p => p.map(...))` en cada chunk | Usar ref para el mensaje en curso |

### Arquitectura / código

| Problema | Impacto técnico | Propuesta |
|----------|----------------|-----------|
| **God component 750 líneas** | Imposible testear, refactorizar o reutilizar | Extraer a 5-6 componentes + hooks |
| **205 líneas de dead code** | `_build_html` (138L) + `calculate_tool.py` (67L) nunca usados | Eliminar |
| **Módulos fantasma** | `modules/documents/` y `modules/storage/` vacíos | Eliminar |
| **6 commits en un tool call** | Si crashea entre commits → estado inconsistente | Agrupar en 1 commit o usar savepoint |
| **IVA duplicado en 3 lugares** | Bug si se cambia en uno y no en otros | Centralizar en una función |
| **Tailwind instalado sin usar** | Build overhead, confusión | Migrar UI o desinstalar |
| **Pydantic Config deprecated** | Warnings en pydantic v2 | Migrar a `model_config = ConfigDict(...)` |

### Robustez / errores / validaciones

| Problema | Impacto | Propuesta |
|----------|---------|-----------|
| **`except Exception: pass` en migraciones** | Fallas de DB invisibles | Loggear excepciones, solo ignorar `DuplicateColumn` |
| **Path traversal en filenames** | Escritura arbitraria en filesystem | `pathlib.Path(filename).name` para sanitizar |
| **MIME validation buggy** | Podría aceptar tipos no permitidos | Simplificar a `content_type in ALLOWED_MIME_TYPES` |
| **No validación de existencia en PATCH** | `update_status`, `patch_quote`, `mark_as_read` retornan OK para IDs inexistentes | Verificar existencia o usar `returning()` |
| **Sin pool config en DB** | TimeoutError bajo carga concurrente | Agregar `pool_size`, `max_overflow` |
| **Temp files nunca limpiados** | `plan_tool.py` acumula archivos en `/tmp` | Cleanup después de procesamiento |

### Producto / operativa del usuario

| Fricción | Impacto operativo | Propuesta |
|----------|--------------------|-----------|
| **Sin búsqueda por fecha** | Operador no puede filtrar por período | Agregar date picker al filtro |
| **Sin indicador de presupuestos activos** | No ve cuántos necesitan acción | KPI cards o badges en sidebar |
| **Sin notificaciones de web quotes** | Presupuestos web pasan desapercibidos | Badge "Nuevo" ya implementado (✅), agregar sonido/push futuro |
| **Sin historial de cambios** | No sabe quién cambió qué | Audit log en DB |
| **Chat no permite editar mensajes** | Error de tipeo obliga a reenviar | Menor — aceptable por ahora |
| **Sin preview de PDF antes de generar** | Operador debe confiar en el cálculo | Ya tenemos preview de validación (✅) |

---

## 3. Plan priorizado

### P0 — Crítico

| # | Mejora | Problema | Esfuerzo | Área | Riesgo |
|---|--------|----------|----------|------|--------|
| 1 | **Auth básica con API key** | Endpoints públicos → manipulación de precios/datos | Bajo | Backend | Bajo |
| 2 | **Sanitizar filenames en uploads** | Path traversal → escritura arbitraria | Bajo | Backend | Bajo |
| 3 | **`asyncio.to_thread()` en Drive** | Event loop bloqueado → sistema congelado | Bajo | Backend | Bajo |
| 4 | **Fix silent `except Exception: pass`** | Migraciones fallan sin aviso | Bajo | Backend | Bajo |

### P1 — Alto impacto

| # | Mejora | Problema | Esfuerzo | Área | Riesgo |
|---|--------|----------|----------|------|--------|
| 5 | **Error states en frontend** | Operador no sabe si algo falló | Bajo | Frontend | Bajo |
| 6 | **Excluir `messages` de list_quotes** | Query lenta cargando JSON innecesario | Bajo | Backend | Bajo |
| 7 | **Eliminar dead code** | 205+ líneas confusas | Bajo | Backend | Bajo |
| 8 | **Atomizar commits en generate_docs** | Estado inconsistente en crash | Medio | Backend | Medio |
| 9 | **Migrar UI a Tailwind** | Inline styles → no hover/focus/responsive | Alto | Frontend | Medio |
| 10 | **Extraer componentes reutilizables** | God component 750L inmantenible | Medio | Frontend | Medio |

### P2 — Importantes no urgentes

| # | Mejora | Problema | Esfuerzo | Área |
|---|--------|----------|----------|------|
| 11 | Estado global (Context/SWR) | Fetches redundantes, sin invalidación | Medio | Frontend |
| 12 | Pool config en DB | Timeouts bajo carga | Bajo | Backend |
| 13 | AbortController en fetches | SSE streams no cancelables | Bajo | Frontend |
| 14 | `asyncio.to_thread()` en PDF/Excel | `asyncio.gather` no paraleliza realmente | Bajo | Backend |
| 15 | Tipar `quote_breakdown` | `any` por todos lados | Medio | Frontend |
| 16 | Cache sistema prompt en memoria | Disco leído 6-9 veces por request | Bajo | Backend |
| 17 | Confirmación en cambio de estado | Click accidental irreversible | Bajo | Frontend |
| 18 | Empty states en dashboard | Tabla vacía sin mensaje | Bajo | Frontend |

### P3 — Polish

| # | Mejora | Problema | Esfuerzo | Área |
|---|--------|----------|----------|------|
| 19 | `useMemo` en dashboard | Re-renders innecesarios en búsqueda | Bajo | Frontend |
| 20 | Implementar o remover "Exportar CSV" | Botón muerto | Bajo | Frontend |
| 21 | Cleanup temp files en plan_tool | Acumulación en /tmp | Bajo | Backend |
| 22 | ARIA labels y keyboard nav | Accesibilidad | Medio | Frontend |
| 23 | Pydantic `model_config` migration | Deprecation warnings | Bajo | Backend |
| 24 | Desinstalar deps muertas (python-jose, alembic) | Attack surface + imagen Docker | Bajo | Backend |
| 25 | Health check en Dockerfile + non-root user | Best practices de deploy | Bajo | Infra |

---

## 4. Quick wins (alto valor, bajo esfuerzo)

1. **Sanitizar filenames** — 1 línea: `filename = Path(filename).name`
2. **Fix silent except** — cambiar `pass` por `logging.warning(f"Migration: {e}")`
3. **`asyncio.to_thread()`** en 3 funciones de drive_tool
4. **Excluir messages de list_quotes** — agregar `.options(defer(Quote.messages))`
5. **Error state en dashboard** — agregar `.catch(setError)` + renderizar mensaje
6. **Eliminar dead code** — borrar `calculate_tool.py`, `_build_html`, módulos fantasma
7. **Empty state** — 5 líneas de JSX cuando `filteredQuotes.length === 0`
8. **`useMemo`** en `filteredQuotes` y `statusCounts`
9. **MIME validation** — simplificar a `content_type in ALLOWED_MIME_TYPES`
10. **Remover "Exportar CSV"** o implementar con `json2csv`

---

## 5. Refactors estructurales

### A. Migración a Tailwind (estimado: 2-3 días)
- Eliminar todos los inline `style={{}}` de los 8 componentes
- Reemplazar con clases Tailwind
- Eliminar hover hacks JS (`onMouseEnter`/`onMouseLeave`)
- Agregar responsive breakpoints (`sm:`, `md:`, `lg:`)
- Agregar dark mode toggle ready (`dark:` classes)
- Eliminar CSS duplicado de `globals.css`

### B. Extraer componentes (estimado: 1-2 días)
- `QuoteTable` — tabla del dashboard reutilizable
- `StatusBadge` — badge de estado (draft/validated/sent)
- `FileButtons` — grupo de botones PDF/Excel/Drive
- `ConfirmModal` — modal de confirmación genérico
- `ErrorBoundary` — wrapper de error para páginas
- `EmptyState` — componente para estados vacíos
- `ChatPanel` / `DetailPanel` — separar las 2 vistas del quote page
- `ChatInput` — extraer a su propio archivo con custom hook `useChatInput`

### C. Estado global (estimado: 1 día)
- `QuotesProvider` con Context API o Zustand
- Cache de quotes list, invalidación al crear/eliminar
- Sidebar consume del contexto en vez de fetch independiente

### D. Auth layer (estimado: 1 día)
- Middleware FastAPI con API key en header
- Variable de entorno `API_KEY`
- Frontend envía key en cada request
- Opcional: JWT con login simple para operador

### E. Drive async wrapper (estimado: 4 horas)
- Envolver todas las llamadas de `googleapiclient` en `asyncio.to_thread()`
- Cache de credenciales/service objects
- Retry con backoff en errores de red

---

## 6. Roadmap propuesto

### Fase 1 — Seguridad y estabilidad (1-2 días)
- Auth con API key
- Sanitizar filenames
- Fix silent except
- `asyncio.to_thread()` en Drive
- Excluir messages de list_quotes
- Eliminar dead code

### Fase 2 — UX y robustez (3-5 días)
- Error states en todas las páginas
- Empty states
- Migrar a Tailwind (componente por componente)
- Extraer componentes reutilizables
- Estado global para quotes
- Confirmación en cambio de estado
- AbortController en SSE

### Fase 3 — Calidad y escalabilidad (3-5 días)
- Tipar `quote_breakdown` completo en TypeScript
- Pool config en DB
- Cache sistema prompt en memoria
- Atomizar commits en generate_docs
- ARIA labels + keyboard navigation
- Health check Docker
- Desinstalar deps muertas
- Implementar Exportar CSV

---

## 7. Recomendaciones técnicas concretas

### Centralizar reglas de negocio
Ya empezamos con `calculate_quote()` como tool determinístico. Falta:
- Mover la lógica de TOMAS automático (zócalo >10cm, revestimiento) de `calculator.py` a una función `determine_mo_items()` más explícita
- Documentar cada regla con referencia al ejemplo que la origina

### Una sola fuente de verdad para cálculos
`calculate_quote()` → preview → `generate_documents()`. Ya implementado en BUG-045. Mantener.

### Separación datos crudos vs formateados
- Backend: siempre retornar números crudos (int/float)
- Frontend: formatear solo al renderizar (`fmtARS`, `fmtUSD`)
- Nunca guardar strings formateados en DB

### Manejo correcto de números/moneda/IVA
- IVA: centralizar en `catalog_tool.py` (ya está, eliminar duplicados en `calculate_tool.py`)
- USD: `floor(base × 1.21)` — único lugar
- ARS: `round(base × 1.21)` — único lugar

### Estrategia de tests
- ✅ Unit tests: `tests/test_quote_engine.py` (24 tests)
- ✅ Regression: `tests/test_regression.py` (14 tests)
- ✅ Evaluation suite: `tests/evaluation/` (34 × 6 = 204 assertions)
- ❌ Falta: integration tests con API real (httpx TestClient)
- ❌ Falta: frontend tests (Cypress o Playwright para flows críticos)

### Observabilidad
- Logging actual: `logging.info` en agent y tools. Aceptable.
- Falta: structured logging (JSON) para parsear en Railway
- Falta: métricas de latencia por tool call
- Falta: alerta si un quote tarda >60s en generarse
- Falta: tracking de tokens consumidos por request

### Contract typing backend/frontend
- Definir `QuoteBreakdown` como TypedDict en Python y como interface en TypeScript
- Generar uno desde el otro (o usar JSON Schema como fuente de verdad)
- Eliminar todos los `any` en el frontend para breakdown data

---

## 8. Qué NO tocaría todavía

| Qué | Por qué |
|-----|---------|
| **Migrar de SSE a WebSockets** | SSE funciona bien, WS agrega complejidad sin beneficio claro |
| **Migrar de fpdf2 a WeasyPrint** | fpdf2 es estable y rápido; WeasyPrint tiene dependencias nativas pesadas |
| **Agregar Alembic para migraciones** | Las migraciones inline en `database.py` son rudimentarias pero funcionan; Alembic agrega complejidad para 1 tabla |
| **Refactorizar el agentic loop** | `agent.py` es complejo pero funcional; tocarlo riesgo alto de regresión en el flujo core |
| **Multi-tenant** | No hay necesidad todavía — un solo operador |
| **i18n / multi-idioma** | El producto es solo en español para operador argentino |
| **Cambiar modelo de Claude** | Sonnet 4 funciona bien; no cambiar por cambiar |
| **Mobile-first redesign** | El operador trabaja en desktop; responsive básico alcanza |

---

## Top 10 mejoras con mejor retorno sobre esfuerzo

| # | Mejora | Esfuerzo | Impacto | ROI |
|---|--------|----------|---------|-----|
| 1 | Sanitizar filenames (1 línea) | 5 min | Cierra vulnerabilidad crítica | ★★★★★ |
| 2 | `asyncio.to_thread()` en Drive (3 funciones) | 30 min | Desbloquea event loop | ★★★★★ |
| 3 | Fix `except Exception: pass` (1 línea) | 5 min | Visibilidad de errores DB | ★★★★★ |
| 4 | Auth con API key (middleware) | 2 horas | Protege todos los endpoints | ★★★★★ |
| 5 | Error states en dashboard + config | 1 hora | Operador ve cuando algo falla | ★★★★☆ |
| 6 | Excluir messages de list_quotes | 15 min | Query más rápida con historial largo | ★★★★☆ |
| 7 | Eliminar dead code (205 líneas) | 30 min | Codebase más limpio | ★★★★☆ |
| 8 | Empty state + `useMemo` dashboard | 30 min | UX básica correcta | ★★★★☆ |
| 9 | Simplificar MIME validation | 10 min | Cierra edge case de seguridad | ★★★★☆ |
| 10 | AbortController en SSE | 1 hora | Cancela streams al navegar | ★★★☆☆ |
