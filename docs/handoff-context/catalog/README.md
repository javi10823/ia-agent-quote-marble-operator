# Catalog · JSONs sanitizados

> **Origen:** `api/catalog/*.json` del backend.
> **Sanitizado:** 2026-05-05 — PR `sprint-1.5/extract-api-contracts`.

15 catálogos copiados desde el backend, con sanitización aplicada según las reglas estrictas del PR (Master §21 — sin precios reales sensibles, sin clientes reales, salvo fixtures canon).

---

## Reglas de sanitización aplicadas

### Cifras canónicas preservadas (Master §13)

Estas se mantienen **literal** porque son los fixtures canon del case Cueto-Heredia que el frontend Sprint 2 va a usar en tests E2E + demo Marina:

- `architects.json`: 1 entry `CUETO-HEREDIA ARQUITECTAS` (descuento 5% importado)
- `labor.json`: 5 SKUs MO con precios reales:
  - `COLOCACION` $49.698,65 base
  - `PEGADOPILETA` $53.840 base
  - `ANAFE` $35.617,36 base
  - `REGRUESO` $13.810 base
  - `TOMAS` $6.461 base
- `delivery-zones.json`: 1 entry `ENVIOROS` (Flete Rosario + Toma de Medidas) $52.000 base
- `materials-silestone.json`: 1 entry `SILESTONENORTE` USD 206 base (= USD 249 c/IVA del mockup canon, **bug P2 incluido a propósito** — Master §12)

### Sintetizado

Todo el resto:

- **Nombres de arquitectas/estudios:** reemplazados por `ARQ. PLACEHOLDER NN` / `Estudio Placeholder NN`
- **Precios:** sintetizados a números limpios deterministic-por-SKU-hash (5000-85000 ARS para labor, 100-800 USD para materials). NO son los precios reales de D'Angelo.
- **Items de materials:** reducidos a 5 items por catálogo (de los 13-45 originales) — sample suficiente para mockear, sin volcar la lista de precios completa.
- **Sinks:** reducidos a 12 items (de 85). Misma estrategia.
- **Stock:** sample sintético de 5 retazos con dimensiones variadas.
- **`photo` paths:** removidos de los items (eran paths a assets internos del repo).
- **`last_updated`:** sintético (`01/01/2026`) salvo para items canon que mantienen su fecha real.

### NO sanitizado

- `config.json`: copia literal. No tiene PII ni precios sensibles — son parámetros del sistema (IVA, delivery_days tiers, descuentos por tipo de cliente, classificación de materiales por familia).

---

## Archivos disponibles

| Archivo | Items | Notas |
|---|---|---|
| `architects.json` | 8 | 1 canon (Cueto-Heredia) + 7 placeholders |
| `config.json` | — | Literal — IVA, descuentos, delivery tiers, AI engine config |
| `delivery-zones.json` | 32 | 1 canon (Rosario) + 31 sintetizadas |
| `labor.json` | 34 | 5 canon (MO Cueto-Heredia) + 29 sintetizadas |
| `materials-silestone.json` | 5 | 1 canon (SILESTONENORTE) + 4 samples |
| `materials-purastone.json` | 5 | sample sintético |
| `materials-granito-nacional.json` | 5 | sample sintético |
| `materials-granito-importado.json` | 5 | sample sintético |
| `materials-dekton.json` | 5 | sample sintético |
| `materials-neolith.json` | 5 | sample sintético |
| `materials-marmol.json` | 5 | sample sintético |
| `materials-puraprima.json` | 5 | sample sintético |
| `materials-laminatto.json` | 5 | sample sintético |
| `sinks.json` | 12 | sample sintético (de 85 originales) |
| `stock.json` | 5 retazos | sample sintético |

---

## Uso desde frontend Sprint 2

Los hooks `useMockClient()` pueden seedear estos JSONs como fixtures:

```ts
// web/src/lib/mocks/catalogs.ts
import laborCatalog from "@/handoff-context/catalog/labor.json";
import architectsCatalog from "@/handoff-context/catalog/architects.json";
import siliestoneCatalog from "@/handoff-context/catalog/materials-silestone.json";
import config from "@/handoff-context/catalog/config.json";

// ... mockear GET /api/catalog/{name} contra estos
```

Para tests E2E del case Cueto-Heredia, los precios canon ya están — el cálculo arroja **$660.890 ARS + USD 1.538** sin necesitar precios reales.

---

## ⚠️ NO usar en producción

Estos catálogos son sample sanitizados — **no reflejan los precios reales de D'Angelo**. Cuando el frontend cambie a `useApiClient()` (Sprint 3 inicial), los datos vienen del backend que usa los catálogos reales en `api/catalog/`.

Si en algún test E2E necesitás un precio que no es canon, agregalo como item nuevo al sample — NO copies precios reales del backend.
