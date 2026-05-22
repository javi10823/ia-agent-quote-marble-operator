# Tool · `list_pieces`

> **Fuente:** definición en `api/app/modules/agent/agent.py:1212`; handler en `agent.py:5497`; motor en `calculator.py:809`.
> **Derivado de:** lectura en `sprint-3/extract-calc-contracts`.
> **Última actualización:** 2026-05-13.

## Propósito

Paso 1 obligatorio del flow. Formatea la lista de piezas (mesadas, zócalos, alzadas, frentines) que Valentina extrajo del plano/brief y calcula el total de m². **No cotiza precios** — solo arma la tabla de piezas que Marina revisa en el paso 1 (despiece).

Zócalos salen en metros lineales; el total de m² los incluye.

## Input schema

`agent.py:1212`. Required top-level: `["pieces"]`.

```json
{
  "pieces": [
    {
      "description": "string",
      "largo": 2.4,
      "prof": 0.6,
      "alto": 0.05,
      "tipo": "mesada | zocalo | alzada | frentin"
    }
  ]
}
```

- Por pieza, required: `["description", "largo"]`.
- `tipo` es **OBLIGATORIO cuando hay plano adjunto** (imagen/PDF), opcional en briefs de texto puro. Ver `plan-reader-v1.md`.
- Medidas en metros.

## Output schema

`calculator.py:857-861`.

```json
{
  "ok": true,
  "pieces": [
    { "label": "Mesada — 2.4 x 0.6", "m2": 1.44 },
    { "label": "2.0ML X 0.05 ZOC", "m2": 0.1 },
    { "label": "1.2 × 0.1 Alzada", "m2": 0.12, "qty": 2 }
  ],
  "total_m2": 1.66
}
```

- `qty` solo aparece cuando > 1.
- `m2` por entrada = `round_half_up(m2 × qty, 2)`.

### Reglas de label (`calculator.py:837-849`)

| `tipo` | Label |
|---|---|
| zocalo | `"{largo}ML X {dim2} ZOC"` (en ml) |
| alzada | `"{largo} × {dim2} Alzada"` |
| frentin | `"{largo}ML FALDON"` (m² = 0, solo cuenta para MO) |
| mesada | `"{desc} — {largo} x {dim2}"`; agrega `" (SE REALIZA EN 2 TRAMOS)"` si `largo ≥ 3.0` y no es edificio |

## Comportamientos importantes

- **Gate de validación de plano:** si hay plano y NO es edificio, corre `_validate_plan_pieces(...)` (`agent.py:5526-5537`); si las piezas son inválidas retorna `{"ok": false, "error": "⛔ Piezas inválidas..."}`.
- **Edificio:** se invoca como `list_pieces(pieces, is_edificio=True)` — relaja el requerimiento de `tipo`.
- **Side effects del handler** (`agent.py:5546-5567`): persiste `paso1_pieces` + `paso1_total_m2` en `quote_breakdown`; adjunta `result["_paso1_rendered"]` (markdown vía `build_deterministic_paso1`).
- **Auditoría m²:** el validador de superficie compara el total contra la planilla en `agent.py:5232`.

## Código

- Definición tool: `api/app/modules/agent/agent.py:1212`
- Handler: `api/app/modules/agent/agent.py:5497-5567`
- Motor: `calculator.py:809` (`list_pieces`) → `calculate_m2` (`calculator.py:817`)
- Render: `build_deterministic_paso1` (`calculator.py:864-939`)
