# Tool · `calculate_quote`

> **Fuente:** definición en `api/app/modules/agent/agent.py:1220`; handler en `agent.py:6170`; motor en `calculator.py:1178`.
> **Derivado de:** lectura en `sprint-3/extract-calc-contracts`.
> **Última actualización:** 2026-05-13.

## Propósito

Paso 4 del flow. Envuelve el motor `calculate_quote()` de `calculator.py` para uso del agente. Toma las piezas + material + opciones de obra y produce el desglose monetario completo (material, merma, MO, piletas, flete) con dos totales nativos (ARS + USD).

Es la **única** vía para cálculos — la descripción del tool dice "SIEMPRE usar para cálculos". Para cambios de metadata sin recalcular (cliente, status, plazo) se usa `update_quote`; para tocar solo MO, `patch_quote_mo`.

## Input schema

`agent.py:1220`. Required: `["client_name", "project", "material", "pieces", "localidad", "plazo"]`.

```jsonc
{
  "client_name": "string",
  "project": "string",
  "material": "string",
  "pieces": [
    {
      "description": "string",
      "largo": 2.4,          // metros (required)
      "prof": 0.6,
      "alto": 0.05,
      "quantity": 1,         // unidades físicas (edificios); default 1
      "m2_override": 0.0     // si se pasa, NO computa largo×prof — usa este m²
    }
  ],
  "localidad": "string",
  "colocacion": true,
  "is_edificio": false,
  "pileta": "empotrada_cliente | empotrada_johnson | apoyo",
  "pileta_qty": 1,
  "pileta_sku": "string",
  "anafe": false,
  "anafe_qty": 1,
  "frentin": false,
  "frentin_ml": 0.0,
  "regrueso": false,
  "regrueso_ml": 0.0,
  "inglete": false,
  "pulido": false,
  "tomas_qty": 0,            // requiere alzada + pedido explícito del operador
  "skip_flete": false,       // true solo si retira en fábrica
  "flete_qty": 1,            // override del operador
  "plazo": "string",
  "discount_pct": 0,
  "mo_discount_pct": 0       // descuento comercial sobre MO (excl. flete)
}
```

Notas de campos clave:
- `m2_override`: usar SOLO cuando el operador declara el m² en una planilla de cómputo (edificios con valores pre-calculados). Desactiva el fallback de profundidades inversas.
- `tomas_qty`: requiere `alzada` en `pieces` + pedido explícito. Sin alzada el calculador lo ignora con warning.
- `mo_discount_pct`: solo si el operador lo pide explícito (ej. "5% sobre MO").

## Output schema

Motor `calculator.py:1880-1940`. Ver `calculator.md` § Outputs para la tabla completa. Forma resumida:

```jsonc
{
  "ok": true,
  "material_name": "SILESTONE BLANCO NORTE",
  "material_currency": "USD",
  "material_m2": 1.30,
  "material_price_unit": 627,      // con IVA
  "material_price_base": 519,      // sin IVA
  "material_total": 815,           // neto, post-descuento
  "discount_pct": 0, "discount_amount": 0,
  "mo_discount_pct": 0, "mo_discount_amount": 0,
  "merma": { "aplica": false, "desperdicio": 0.80, "sobrante_m2": 0, "motivo": "..." },
  "sobrante_m2": 0, "sobrante_total": 0,
  "piece_details": [ /* ... */ ],
  "mo_items": [
    { "description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 65146, "base_price": 53840, "total": 65146 }
  ],
  "total_mo_ars": 177281,
  "total_ars": 245458,             // total general
  "total_usd": 815                 // material si USD; 0 si ARS
}
```

En fallo: `{ "ok": false, "error": "..." }` (cliente faltante `:1189`, project faltante `:1209`, material no encontrado `:1371`).

**Modo products-only** (piezas vacías + sinks/pileta, sin colocación/regrueso/anafe): retorno separado `calculator.py:1129-1160` con `material_m2: 0`, `mo_items: []`, `_quote_mode: "products_only"`.

## Comportamientos importantes

- **Compute delegado al motor:** el handler llama `calculate_quote(inputs)` (`agent.py:6943`), importado en `agent.py:21` (`from app.modules.quote_engine.calculator import calculate_quote`).
- **Quote independiente por material:** si el material difiere y el quote ya tiene docs generados, el handler auto-crea/reusa un quote separado (`agent.py:6171-6209`).
- **Validación post-cálculo:** corre `validate_despiece(calc_result)` (`agent.py:7061`); si falla adjunta `_validation_errors/_validation_warnings/_validation_note` y NO permite generar documentos. Ver `tools/validate_quote.md`.
- **Render:** siempre arma `_paso2_rendered` (markdown vía `build_deterministic_paso2`) y persiste breakdown + change log (`agent.py:7084+`).

## Código

- Definición tool: `api/app/modules/agent/agent.py:1220`
- Handler: `api/app/modules/agent/agent.py:6170-7090`
- Motor: `calculator.py:1178` (`calculate_quote`)
- Reglas: ver `calculator-rules.md`
