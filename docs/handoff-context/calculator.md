# Motor de cálculo · `api/app/modules/quote_engine/calculator.py`

> **Fuente:** código backend real (`api/app/modules/quote_engine/calculator.py`, 2258 líneas).
> **Derivado de:** lectura completa del motor en branch `sprint-3/extract-calc-contracts` (commit base `dc94e8d`).
> **Última actualización:** 2026-05-13 (PR `sprint-3/extract-calc-contracts`).
>
> **Audiencia:** sub-PRs del Sprint 3 que implementan paso 3 (despiece) y paso 4 (cálculo). Mockear contra estos contratos; el switch a backend real consume el mismo shape.
>
> **Importante:** este motor NO usa LLM. Es Python puro y determinístico — mismo input ⇒ mismo output. La IA (Valentina) sólo arma el input (extrae piezas del plano) y narra el output.

---

## Overview

`calculator.py` es el motor que convierte una lista de piezas + un material + opciones de obra en un presupuesto completo con desglose por rubro y dos totales (ARS y USD nativos, sin conversión cruzada).

El flujo del producto lo invoca en dos momentos:

- **Paso 1 (despiece):** `list_pieces()` formatea las piezas y calcula el total de m². No cotiza precios — solo arma la tabla de piezas que Marina revisa.
- **Paso 4 (cálculo):** `calculate_quote()` toma esas piezas + material + opciones y produce el desglose monetario completo.

Los precios salen de los 15 catálogos JSON en `api/catalog/` (material, MO/labor, piletas, fletes, descuentos de arquitectas). Todos los catálogos guardan precios **sin IVA** (`price_includes_vat: false`); el motor aplica IVA ×1.21 al construir cada línea.

## Archivos del motor

El cálculo vive principalmente en `calculator.py`, pero el flujo lo orquesta el agente:

| Archivo | Rol |
|---|---|
| `api/app/modules/quote_engine/calculator.py` | Motor: `list_pieces`, `calculate_m2`, `calculate_merma`, `calculate_quote`, `_find_material`, `_find_flete`, renderers paso1/paso2 |
| `api/app/modules/agent/agent.py` | Define los tools Anthropic (`list_pieces` `:1212`, `calculate_quote` `:1220`) y sus handlers que invocan el motor |
| `api/app/modules/agent/tools/validation_tool.py` | `validate_despiece()` — valida el output del motor antes de generar documentos |
| `api/app/modules/agent/tools/catalog_tool.py` | Lookup de precios de material + `check_architect` (descuento) |

## Inputs

`calculate_quote(input_data: dict) -> dict` — entry point en `calculator.py:1178`.

Campos del input (ver `tools/calculate_quote.md` para el schema completo del tool):

- **Requeridos:** `client_name`, `project`, `material`, `pieces[]`, `localidad`, `plazo`
- **Piezas:** cada una `{description, largo, prof|alto, quantity?, m2_override?}` — `largo`/`prof` en metros
- **Opciones de obra:** `colocacion`, `is_edificio`, `pileta` (enum), `pileta_qty`, `anafe`, `anafe_qty`, `frentin`/`frentin_ml`, `regrueso`/`regrueso_ml`, `inglete`, `pulido`, `tomas_qty`
- **Comerciales:** `discount_pct`, `mo_discount_pct`, `skip_flete`, `flete_qty`

## Outputs

Output dict (éxito, `calculator.py:1880-1945`). Campos principales:

| Campo | Tipo | Notas |
|---|---|---|
| `ok` | bool | `false` + `error` en fallo |
| `material_name` / `material_type` | str | resuelto vía `_find_material` |
| `material_m2` | float | suma de m² de piezas (incl. zócalos en ml, regrueso) |
| `material_price_unit` / `material_price_base` | number | con IVA / sin IVA |
| `material_currency` | "USD" \| "ARS" | define en qué total cae el material |
| `material_total` | int | neto, post-descuento |
| `discount_pct` / `discount_amount` | number | descuento sobre material |
| `mo_discount_pct` / `mo_discount_amount` | number | descuento comercial sobre MO (excl. flete) |
| `merma` | dict | `{aplica, desperdicio, sobrante_m2, motivo}` |
| `sobrante_m2` / `sobrante_total` | number | material extra facturado |
| `piece_details` | dict[] | piezas con m² individual |
| `mo_items` | dict[] | líneas de MO: `{description, quantity, unit_price, base_price, total}` |
| `total_mo_ars` | int | subtotal MO |
| `total_ars` | int | **total general** (MO + material/sinks ARS) |
| `total_usd` | int | total material si currency USD, si no `0` |
| `sectors` / `sinks` | list | para el PDF |

### Regla de moneda (crítica)

**No hay conversión USD↔ARS en el motor.** Los dos totales conviven en su moneda nativa (`calculator.py:1786-1791`):

- Material **USD** → `total_usd` = material neto + sobrante; `total_ars` = MO + piletas (ARS)
- Material **ARS** → todo va a `total_ars`; `total_usd = 0`

Esto significa que un quote típico de material importado tiene **dos totales que NO se suman entre sí**: el cliente paga USD por el material y ARS por la mano de obra + flete.

## Flujo del cálculo

1. **Validación de inputs** (`:1185-1217`) — `client_name`/`project` no vacíos ni placeholder.
2. **Detección products-only** (`:1234-1243`) — si no hay piezas pero sí sinks/pileta → branch `_calculate_quote_products_only`.
3. **Resolución de material** (`_find_material`, `:373-674`) — fuzzy match family-gated; error si ambiguo.
4. **Cálculo de m²** (`calculate_m2`) — suma piezas, zócalos en ml, regrueso, con `_round_half_up` a 2 decimales.
5. **Merma** (`calculate_merma`, `:942-1000`) — solo sintéticos; Negro Brasil y naturales nunca.
6. **Descuentos** (`:1442-1460`) — arquitecta (5% USD / 8% ARS) o edificio (18% si ≥15 m²).
7. **Construcción de MO** (`:1477-1704`) — pileta, anafe, colocación, frentín/inglete, regrueso, flete, pulido, tomas. IVA ×1.21 por línea.
8. **Ajuste edificio** (`:1750-1764`) — MO ÷1.05 excepto flete.
9. **Descuento MO comercial** (`:1766-1784`) — si `mo_discount_pct`, sobre MO excl. flete.
10. **Serialización** (`:1880-1945`) — arma el output dict + renderers markdown paso1/paso2.

## Edge cases manejados

- `client_name`/`project` placeholder o vacío → `ok:false`
- Material no encontrado → `ok:false`; family ambigua ("GRANITO" sin SKU) → pide aclaración al operador
- `variant_negated` (ej. "no leather") → warning, igual cotiza
- Edificio con piezas sin dimensiones → warning
- Flete sin zona (ni fallback Rosario) → warning, sin flete
- `tomas_qty > 0` sin alzada en piezas → ignora + warning
- Regrueso: guard anti-doble-conteo de m² (`:1411-1436`)
- `pileta_qty = 0` → respetado (no cotiza pileta fantasma)
- Sink con shape inválido → se saltea + warning

## Cifras canon de referencia

> ⚠️ **Las cifras "canon" del Master §13 NO son reproducibles ejecutando este motor.** Ver `calculator-examples.md` § "Discrepancia cifras canon" para el detalle completo. Resumen:
>
> - **USD 2.184** (Cueto-Heredia / Negro Brasil) no tiene derivación en ningún lado del repo — es un número suelto en `master.md:432` sin breakdown.
> - **ARS 660.890 + USD 1.538** (Pereyra / Silestone) solo se reproducen contra el breakdown **mock** documentado en `master.md:392`, que usa un precio de Silestone desactualizado (USD 249/m², cuando el catálogo real es USD 519/m² — bug P2 conocido).
> - `master.md` se contradice: §13 línea 430 mapea PRES-2026-017→Pereyra/Silestone; línea 432 mapea PRES-2026-018→Cueto/Negro Brasil/2.184; pero el breakdown canónico (línea 392) y `endpoints-spec.md:69` etiquetan PRES-2026-018 como Silestone/660.890.
>
> Para ejemplos **reproducibles de verdad**, usar los del motor real documentados en `calculator-examples.md` (derivados de `api/tests/`).

## Docs relacionados

- `calculator-rules.md` — las reglas de negocio explícitas con line refs
- `calculator-examples.md` — ejemplos worked input → output (de tests reales)
- `tools/list_pieces.md` · `tools/calculate_quote.md` · `tools/validate_quote.md` — contratos de los tools del agente
- `schemas/quote.md` — modelo Quote persistido
