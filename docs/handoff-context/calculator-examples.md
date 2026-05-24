# Ejemplos worked del motor de cálculo

> **Fuente:** tests reales del backend (`api/tests/test_quote_engine.py`, `test_validation.py`, `test_regrueso_mo.py`, `test_zocalo_m2_quantity.py`, `conftest.py`) + ejemplos validados en `api/examples/`.
> **Derivado de:** lectura en `sprint-3/extract-calc-contracts`.
> **Última actualización:** 2026-05-13.
>
> **Cantidad real:** el Master §16 menciona "34 examples". Los 34 archivos en `api/examples/` (quote-001…034) son **narrativas de razonamiento** (input + tablas + totales en prosa), NO fixtures ejecutables — `CONTEXT.md:178` lo dice explícito ("son REFERENCIAS de formato/lógica, NO datos para copiar"). Los ejemplos **reproducibles** (asertados en tests Python) son los de abajo. Marco cada uno como `[TEST]` (asertado en código) o `[EJEMPLO]` (de `api/examples/`, prosa) o `[MOCK]` (solo en docs de design, no reproducible).

---

## A · m² (`calculate_m2`) `[TEST]`

`api/tests/test_quote_engine.py:14-41`

| Input | Output |
|---|---|
| `[{largo:2.0, prof:0.6}]` | `1.2 m²` |
| mesada + zócalo `[{2.0×0.6}, {2.0, alto:0.05}]` | `1.3 m²` |
| mesada en L `[{2.41×0.6}, {1.37×0.6}]` | `2.27 m²` (1.446+0.822=2.268 → half-up 2dp) |
| `[]` | `0` |

## B · Merma (`calculate_merma`) `[TEST]`

`api/tests/test_quote_engine.py:44-74`

| Input | `aplica` | Nota |
|---|---|---|
| `(1.80, "SILESTONE BLANCO NORTE")` | `False` | desperdicio < 1.0 m² |
| `(0.80, "SILESTONE BLANCO NORTE")` | `True` | `sobrante_m2 ≈ desperdicio/2` |
| `(0.5, "GRANITO NEGRO BRASIL")` | `False` | motivo: "Negro Brasil" (nunca merma) |
| `(2.0, "GRANITO GRIS MARA")` | `False` | motivo: "natural" |
| `(2.0, "PURASTONE BLANCO PALOMA")` | `True` | placa entera 4.20 m² ref |

## C · Resolución de material (`_find_material`) `[TEST]`

`api/tests/test_quote_engine.py:80-90`

| Input | Resultado |
|---|---|
| `"Silestone Blanco Norte"` | `found:True, currency:USD` |
| `"GRANITO"` / `"Silestone"` / `"Dekton"` (bare) | `found:False, ambiguous_family:True` → pide SKU |

---

## 1 · Quote completo · Silestone Blanco Norte `[TEST]`

`api/tests/test_validation.py:26-100` — golden válido, IVA-consistente.

**Inputs (resumidos):**
```json
{
  "client_name": "Juan Carlos", "project": "Cocina",
  "material": "SILESTONE BLANCO NORTE", "material_currency": "USD",
  "pieces": [
    {"description": "Mesada", "largo": 2.0, "prof": 0.60},
    {"description": "Zocalo", "largo": 2.0, "alto": 0.05}
  ],
  "pileta": "empotrada_johnson", "colocacion": true, "localidad": "Rosario"
}
```

**Cálculo (IVA = 1.21):**
- Material: base USD 519/m² → `unit = floor(519 × 1.21) = 627`; m² = 1.30 → `material_total = round(1.30 × 627) = 815 USD`
- MO pileta: base 53.840 → `round(×1.21) = 65.146`
- MO colocación: base 49.699 → `60.136`, × 1.30 m²
- MO flete Rosario: base 42.975 → `51.999`

**Expected output:**
```json
{ "material_total": 815, "total_usd": 815, "total_ars": 245458 }
```

## 2 · Quote completo · Silestone + anafe (fixture e2e) `[TEST]`

`api/tests/conftest.py:110-136` (`sample_quote_data`), reusado en `test_e2e_flow.py`.

- Material Silestone Blanco Norte, m² 1.30, `material_price_unit = 628 USD`
- MO: pileta 65.147 + anafe 43.097 + colocación @1.30 → 60.135 + flete 52.000
- **`total_ars: 238420`, `total_usd: 816`**

## 3 · Multi-material (agrega Purastone) `[TEST]`

`api/tests/conftest.py:141-147` + `test_e2e_flow.py`.

- Segundo material Purastone Blanco Paloma: `material_price_unit = 407 USD` → `total_usd: 529`
- Un quote independiente por material (no se suman).

## 4 · Regrueso por metro lineal `[TEST]`

`api/tests/test_regrueso_mo.py` (PR #401/#403).

**Inputs:** Silestone Blanco Norte, 1 mesada 2.0×0.6, Rosario, `regrueso=True, regrueso_ml=60.68`.
**Cálculo:**
- MO regrueso: base 13.810,06 ARS/ml → `unit = round(×1.21) = 16.710`; `total = round(16.710 × 60.68)`
- Material: regrueso suma m² → 42.39 + (60.68 × 0.05 = 3.034) = **45.424 m²**
- Auto-detección de variante: piezas con "Regrueso" largos 1.5+0.6 → qty 2.1 ml

## 5 · Zócalos round half-up `[TEST]`

`api/tests/test_zocalo_m2_quantity.py` (PR #408/409).

- Zócalo M6: `round(0.155, 2) = 0.16` (NO 0.15 banker's)
- DYSCON zócalos M1×24 / M6×2 / M7×2 → suma **42.39 m²** (no 37.71)

## 6 · Negro Brasil (sin merma) `[EJEMPLO]`

`api/examples/quote-030-*.md` (Juan Carlos, Negro Brasil Extra).

- 2 mesadas, SKU `GRANITONEGROBRASIL`, base USD 228 → `floor(228 × 1.21) = 275 USD/m²`
- total 3.71 m²; **"NUNCA merma"** aplicado (Regla 1 excepción)

## 7 · Silestone con anafe (referencia formato) `[EJEMPLO]`

`api/examples/quote-017-*.md`.

- Input: mesada 2.10 ml + zócalo, anafe; m² = 1.395
- Material: base 429 → `floor(×1.21) = 519 USD/m²` (⚠️ catálogo viejo decía 429; hoy 519); total `round(1.395 × 519) = 724 USD`
- MO total ARS $228.267,15

## 8 · Validación · Negro Brasil + merma = ERROR `[TEST]`

`api/tests/test_validation.py` (`_check_merma_rules`).

- Si un qdata tiene `material_name` Negro Brasil y `merma.aplica = true` → `validate_despiece` retorna **error** (Negro Brasil nunca mermea).

## 9 · Validación · IVA mismatch = ERROR `[TEST]`

`api/tests/test_validation.py:113-127`.

- `material_price_unit = 999` con base 519 USD → error (esperaba `floor(519×1.21)=627`).
- `material_price_unit = round(519×1.21)=628` para USD → **error** igual (USD usa `floor`, no `round`).

## 10 · Validación · PEGADOPILETA cuenta `[TEST]`

`api/tests/test_validation.py` (`_check_pegadopileta`).

- Pileta empotrada con 0 líneas de "Agujero y pegado pileta" → error.
- Con > 1 → warning. Debe ser exactamente 1 por pileta.

---

## ⚠️ Discrepancia cifras canon (Cueto-Heredia · Pereyra)

> **Reportado para audit.** Las cifras "canon" del Master §13 **NO son reproducibles ejecutando `calculator.py`**. Detalle:

### `[MOCK]` ARS 660.890 + USD 1.538 (Pereyra / Silestone)

- Solo aparecen en `docs/master.md:392` (breakdown mock), `docs/handoff-context/schemas/quote.md:307-340`, y mocks del frontend (`web/src/lib/mocks/canonicalQuote.ts:34`, `dashboardDataset.ts`).
- El breakdown del Master usa **Silestone a USD 249/m²**, pero el catálogo real (`materials-silestone.json`) tiene **USD 429/m² sin IVA → 519 con IVA** (el Master lo marca como bug P2, "−52% diff"). Con el precio real, el material NO da USD 1.538.
- **No hay test Python que asierte 660890 ni 1538.** Solo los E2E del frontend (`web/tests/e2e/dashboard.spec.ts`) verifican el texto, contra **mock data**, no contra un cálculo real.

### `[MOCK]` USD 2.184 (Cueto-Heredia / Negro Brasil)

- **No tiene derivación en ningún lado del repo.** Es un número suelto en `master.md:432` sin breakdown ni test.

### Contradicción interna del Master §13

- `master.md:430` → PRES-2026-017 = Pereyra / Silestone / 6.50 m² / **$660.890**
- `master.md:432` → PRES-2026-018 = Cueto-Heredia / **Negro Brasil** / 8.40 m² / **USD 2.184**
- pero el breakdown canónico (`master.md:392`) y `endpoints-spec.md:69` etiquetan **PRES-2026-018** como Silestone Blanco Norte / 660.890.

→ El spec se contradice sobre qué ID/material/total van juntos.

### Recomendación

Para Sprint 3 (paso 3/4), mockear contra los **ejemplos `[TEST]` de arriba** (reproducibles del motor real). Tratar las cifras canon del Master §13 como **placeholders de design**, no como output esperado del motor. Si se necesita un caso canon reproducible, derivarlo ejecutando `calculate_quote` con inputs reales del catálogo vigente y documentar el resultado obtenido — no forzar el motor a matchear 2.184 / 660.890.

### Fuente de precios (catálogo, sin IVA)

| Material | Catálogo | Precio | Moneda |
|---|---|---|---|
| Negro Brasil Extra | `materials-granito-importado.json` | 228 | USD |
| Negro Brasil Leather | `materials-granito-importado.json` | 252 | USD |
| Silestone Blanco Norte | `materials-silestone.json` | 429 | USD |
