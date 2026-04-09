# UX Mockups — Importador de Catálogos v2

## Flujo completo (5 pasos)

```
[1. Upload] → [2. Detección] → [3. Preview/Diff] → [4. Confirmar] → [5. Resultado]
```

Acceso: desde el panel Config, el botón "Importar" existente abre el modal expandido.

---

## Paso 1 — Upload

```
┌──────────────────────────────────────────────────────────────┐
│  Importar precios                                        ✕   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │           ↑  Arrastrá un archivo o hacé click          │  │
│  │                                                        │  │
│  │         .xls  .xlsx  .csv  (exportado de Dux)          │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  El archivo se analiza automáticamente.                      │
│  Los precios se toman SIN IVA.                               │
│  No se modifica ningún catálogo hasta confirmar.             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Cambios vs hoy:**
- Acepta .xls y .xlsx (además de .csv/json)
- El archivo se envía al backend (`POST /catalog/import-preview`) en vez de parsearse en el browser
- Muestra spinner "Analizando archivo..." mientras el backend procesa

---

## Paso 2 — Detección y clasificación

Aparece automáticamente después del upload, sin intervención del usuario.

```
┌──────────────────────────────────────────────────────────────┐
│  Importar precios                                        ✕   │
│                                                              │
│  📄 ListadePrecio_servicios.xls                              │
│  Formato: Dux Servicios (ARS) · 79 items detectados          │
│                                                              │
│  ┌─ Catálogos afectados ──────────────────────────────────┐  │
│  │                                                        │  │
│  │  ☑ labor                    34 items    🟢 sin cambios  │  │
│  │  ☑ delivery-zones           29 items    🟡 1 precio     │  │
│  │  ☐ materials-laminatto       5 items    ⚪ nuevos       │  │
│  │                                                        │  │
│  │  ⚠ 16 items no matchean con ningún catálogo            │  │
│  │    (ver detalle abajo)                                 │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│                                      [Cancelar] [Ver cambios]│
└──────────────────────────────────────────────────────────────┘
```

**Elementos clave:**
- Nombre de archivo + formato detectado
- Lista de catálogos afectados con checkboxes (operador elige cuáles importar)
- Indicador rápido por catálogo: 🟢 todo coincide / 🟡 hay cambios / 🔴 hay errores / ⚪ solo items nuevos
- Warning de unmatched items

---

## Paso 3 — Preview / Diff de cambios

El operador hace click en "Ver cambios". Se expande la tabla de diff por catálogo seleccionado.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Importar precios                                                    ✕  │
│                                                                         │
│  [labor ▾]  [delivery-zones]  [unmatched]                               │
│                                                                         │
│  delivery-zones — 29 items · 1 actualizado · 0 nuevos · 3 faltantes    │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  SKU              Ubicación              Actual     Nuevo    Δ%  │   │
│  │ ─────────────────────────────────────────────────────────────── │   │
│  │  ENVBER    ⬛ CAP BERMUDEZ          $68.181  → $86.776  +27%   │   │
│  │  ENVIOROS     ROSARIO                $42.975    $42.975    —    │   │
│  │  ENVFUNES     FUNES                  $61.983    $61.983    —    │   │
│  │  ...                                                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ⚠ Faltantes (en catálogo pero no en archivo):                          │
│     ENVALV ($30.000) · sin cambios, se mantienen                        │
│                                                                         │
│  ℹ Los items faltantes NO se eliminan. Solo se actualizan               │
│    los que están en el archivo.                                         │
│                                                                         │
│                                [Cancelar] [← Volver] [Importar (2)]    │
└──────────────────────────────────────────────────────────────────────────┘
```

**Filas coloreadas:**
- 🟡 Fondo ámbar suave: precio actualizado (muestra viejo → nuevo + %)
- 🟢 Fondo verde suave: item nuevo (no existía en catálogo)
- ⚪ Sin color: sin cambios
- 🔴 Fondo rojo suave: item con precio $0 (se skipea, no se importa)

**Tab "unmatched":** muestra los items que no matchean con ningún catálogo. Información solo, no se importan.

---

## Paso 3b — Warnings especiales

Si hay situaciones de riesgo, se muestran ANTES del botón Importar.

```
┌──────────────────────────────────────────────────────────────┐
│  ⚠ ATENCIÓN                                                  │
│                                                              │
│  ⚠ ENVBER: cambio de +27.3% ($68.181 → $86.776)             │
│  ⚠ 8 items con precio $0 — NO se importan                   │
│  ⚠ 3 items en catálogo no están en el archivo — se mantienen │
│                                                              │
│  ☐ Incluir items nuevos (5 items que hoy no existen)         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Si solo existe columna "Con IVA"** (sin columna de precio sin IVA):

```
┌──────────────────────────────────────────────────────────────┐
│  🔴 PRECIO CON IVA DETECTADO                                 │
│                                                              │
│  El archivo solo tiene la columna "Precio De Venta Con IVA". │
│  Los catálogos almacenan precios SIN IVA.                    │
│                                                              │
│  No se puede importar sin confirmación explícita             │
│  de que los precios deben dividirse por 1.21.                │
│                                                              │
│  [Cancelar]                [Confirmar conversión ÷1.21]      │
└──────────────────────────────────────────────────────────────┘
```

---

## Paso 4 — Confirmación + Importación

```
┌──────────────────────────────────────────────────────────────┐
│  Importar precios                                        ✕   │
│                                                              │
│  ⏳ Importando...                                            │
│                                                              │
│  ☑ Backup de delivery-zones guardado                         │
│  ☑ delivery-zones: 1 actualizado                             │
│  ☑ Backup de labor guardado                                  │
│  ☑ labor: sin cambios                                        │
│                                                              │
│  ████████████████████████████░░░  80%                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Paso 5 — Resultado

```
┌──────────────────────────────────────────────────────────────┐
│  Importar precios                                        ✕   │
│                                                              │
│  ✅ Importación completada                                    │
│                                                              │
│  Archivo: ListadePrecio_servicios.xls                        │
│  Fecha: 09/04/2026 15:54                                     │
│                                                              │
│  delivery-zones    1 actualizado · 0 nuevos                  │
│  labor             0 actualizados · 0 nuevos                 │
│                                                              │
│  Se crearon 2 backups automáticos.                           │
│  Podés restaurar desde Historial de backups.                 │
│                                                              │
│                                                    [Cerrar]  │
└──────────────────────────────────────────────────────────────┘
```

---

## Historial de backups (sección nueva en Config)

Debajo del editor de catálogo, o como tab adicional.

```
┌──────────────────────────────────────────────────────────────┐
│  Historial de backups — delivery-zones                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  09/04/2026 15:54                                      │  │
│  │  Archivo: ListadePrecio_servicios.xls                  │  │
│  │  Items: 32 · Antes de importar                         │  │
│  │                                          [Restaurar]   │  │
│  │────────────────────────────────────────────────────────│  │
│  │  07/04/2026 10:20                                      │  │
│  │  Archivo: actualizacion_manual                         │  │
│  │  Items: 30 · Antes de importar                         │  │
│  │                                          [Restaurar]   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Restaurar reemplaza el catálogo actual con el backup        │
│  seleccionado. Se crea un nuevo backup de seguridad antes.   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Componentes principales

| Componente | Archivo | Descripción |
|------------|---------|-------------|
| `ImportModal` | Expandir `CsvImportModal.tsx` | Modal de 5 pasos. Reemplaza el flujo actual. |
| `DiffTable` | Nuevo componente inline en modal | Tabla de diff con filas coloreadas |
| `WarningBanner` | Inline en modal | Banners ámbar/rojo para warnings |
| `BackupHistory` | Nuevo en config page | Lista de backups + botón restore |

## API functions nuevas en `api.ts`

```typescript
importPreview(file: File): Promise<ImportPreviewResult>
importApply(file: File, catalogs: string[], includeNew: boolean): Promise<ImportApplyResult>
listBackups(catalogName: string): Promise<BackupEntry[]>
restoreBackup(backupId: number): Promise<{ok: boolean}>
```

---

## Estados críticos

### Error de parse
```
🔴 Error al analizar archivo
   "No se encontró columna de SKU/Código en el archivo"
   [Intentar con otro archivo]
```

### IVA ambiguo
```
🔴 Solo se encontró "Precio De Venta Con IVA($)"
   No se puede usar como base sin confirmación explícita.
   [Cancelar]  [Confirmar conversión ÷1.21]
```

### Material no encontrado
```
⚠ 16 items no matchean con ningún catálogo
   LAMCEMENTO · LAMAMBER · LAM · ...
   Estos items se ignoran. Si son válidos, agregalos
   manualmente al catálogo correspondiente.
```

### Restore exitoso
```
✅ Catálogo delivery-zones restaurado
   Backup del 09/04/2026 15:54 aplicado.
   Se creó backup de seguridad del estado anterior.
```
