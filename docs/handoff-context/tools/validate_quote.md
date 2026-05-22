# Tool · `validate_quote` → `validate_despiece()`

> **Fuente:** `api/app/modules/agent/tools/validation_tool.py`; invocación en `agent.py:7061` y `agent.py:5693`.
> **Derivado de:** lectura en `sprint-3/extract-calc-contracts`.
> **Última actualización:** 2026-05-13.

## ⚠️ Aclaración importante

**NO existe un tool Anthropic llamado `validate_quote`** en la lista de TOOLS del agente (`agent.py:1212-1221`). La validación es un **módulo interno** (`validate_despiece`) que el handler de `calculate_quote` y de `generate_documents` invocan automáticamente — Valentina no lo llama como tool explícito.

> El router HTTP tiene un endpoint `POST /quotes/{id}/validate` (`router.py:803`), pero ese es OTRA cosa: regenera PDF/Excel/Drive desde el breakdown guardado y cambia el status a `validated`. NO corre `validate_despiece`. No confundir.

Este doc documenta `validate_despiece` porque es el contrato que un sub-PR de Sprint 3 necesita para mockear la validación del paso 4.

## Propósito

Verifica que el output de `calculate_quote` sea consistente antes de generar documentos: IVA bien aplicado, totales que cierran, reglas de merma respetadas, PEGADOPILETA presente, m² coherentes. Función pura, sin I/O.

## Input

El dict resultado de `calculate_quote` (`qdata`).

## Output

`ValidationResult` dataclass (`validation_tool.py:19-23`):

```json
{ "ok": true, "errors": [], "warnings": [] }
```

`ok = (len(errors) == 0)` (`validation_tool.py:55`). Un check que crashea se degrada a warning (no rompe la validación, `:50-52`).

## Sub-validadores (`validation_tool.py:34-45`)

| Check | Línea | Severidad | Qué verifica |
|---|---|---|---|
| `_check_iva_material` | `:64` | **error** | `material_price_unit == floor(base×1.21)` (USD) / `round(base×1.21)` (ARS) |
| `_check_iva_mo` | `:89` | **error** | cada MO `unit == round(base×1.21)`; edificio ÷1.05; `price_includes_vat` → `unit==base` |
| `_check_material_total` | `:142` | **error** | `material_total == round(m2×price_unit) − discount` (skip en products-only) |
| `_check_merma_rules` | `:173` | **error**/warn | Negro Brasil + `merma.aplica` → **error**; sintético sin merma (desperdicio≥1.0) → warn; natural con merma → warn |
| `_check_pegadopileta` | `:201` | **error**/warn | empotrada necesita exactamente 1 MO pileta/pegado; 0 → error, >1 → warn |
| `_check_piece_m2` | `:237` | **error** | por pieza `m2 == largo×dim2` (skip override/frentín); `material_m2 == sum(m2×qty)` |
| `_check_mo_item_totals` | `:296` | warn | MO `total ≈ qty×unit` (tol. max($50, 0.1%)) |
| `_check_colocacion_qty` | `:331` | warn | colocación qty `== max(material_m2, 1.0)` |
| `_check_regrueso_consistency` | `:368` | **error** | suma m² piezas regrueso vs `regrueso_ml×0.05` (tol. 0.05) — anti doble-conteo/sub-conteo |
| `_check_products_only_consistency` | `:453` | **error** | `_quote_mode=="products_only"`: material_m2=0, mo vacío, sinks no vacío, `total_ars==sum(sinks)−discount` (tol. 1 ARS) |

## Invocación en el flow

- **Post `calculate_quote`:** `validate_despiece(calc_result)` en `agent.py:7061`. Errores bloquean `generate_documents` (adjunta `_validation_note`).
- **Pre `generate_documents` (doble gate):** shim `_validate_quote_data(qdata)` (`agent.py:31`, llamado `:5676`) + deep `validate_despiece(qdata)` (`agent.py:5693`). Los `.errors` bloquean con instrucción de recalcular-y-regenerar (`:5694-5706`).
- Import: `agent.py:22` (`from ...validation_tool import validate_despiece`).

## Código

- Módulo: `api/app/modules/agent/tools/validation_tool.py`
- Entry: `validate_despiece(qdata) -> ValidationResult` (`:29`)
- Tests: `api/tests/test_validation.py`, `test_validator_includes_vat_flag.py`
