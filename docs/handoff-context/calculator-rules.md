# Reglas del motor de cálculo

> **Fuente:** `api/app/modules/quote_engine/calculator.py` + `api/app/modules/agent/tools/validation_tool.py`.
> **Derivado de:** lectura del código en `sprint-3/extract-calc-contracts`.
> **Última actualización:** 2026-05-13.
>
> Cada regla cita las líneas exactas (`calculator.py:LXX-LYY`). Las constantes (`merma.*`, `discount.*`, etc.) salen de `api/catalog/config.json`; los valores entre paréntesis son los defaults vigentes.

El Master §16 menciona "7 reglas". El código real implementa **más de 7**. Abajo van todas las encontradas; al final se listan las que el Master define pero el código NO implementa (deuda).

---

## Regla 1 · Merma (desperdicio de placa)

**Descripción:** material extra que se factura por el recorte de placa en materiales sintéticos.
**Trigger:** material es sintético (silestone, dekton, neolith, puraprima, purastone, laminatto) y NO es edificio.
**Excepciones (nunca merma):** edificio (`:949-950`), Granito Negro Brasil (`:954-956`), cualquier piedra natural fuera de `SINTETICOS` (`:958-961`).
**Cálculo:** `:942-1000`
- Silestone usa **media placa** como referencia (`MERMA_MEDIA_PLACA`, placa default 4.20 m² → 2.10) (`:964-967`).
- Resto de sintéticos usan **placa entera** (4.20 m²) (`:971-981`).
- `desperdicio = ceil(needed / ref) × ref − needed` (`:983`).
- Si `desperdicio < small_piece_threshold_m2` (default 1.0) → no se factura sobrante (`:985-992`).
- Si no, **`sobrante = desperdicio / 2`** (se factura la mitad del recorte) (`:994`).
**Código:** `calculator.py:942-1000`

---

## Regla 2 · IVA (×1.21)

**Descripción:** todos los catálogos guardan precios sin IVA; el motor los lleva a precio final.
**Trigger:** siempre, al construir cada línea (material + cada MO).
**Cálculo:**
- Material USD: `price_unit = floor(price_base × 1.21)` (validado en `validation_tool.py:64`).
- Material ARS: `price_unit = round(price_base × 1.21)`.
- MO (ARS): `unit_price = round(base_price × 1.21)` (`validation_tool.py:89`).
- Líneas con `price_includes_vat: true` → `unit == base` (no se re-aplica).
**Edge case:** ítems de edificio se dividen ÷1.05 (ver Regla 9) ANTES o en combinación con IVA — el validador espera `round(base×1.21)/1.05`.
**Código:** material `calculator.py:1388-1393`; MO en construcción `:1477-1704`; verificación `validation_tool.py:64-140`

---

## Regla 3 · Descuento arquitecta

**Descripción:** descuento sobre el material para clientes que matchean en `architects.json`.
**Trigger:** `check_architect(client_name)` encuentra match (`calculator.py:1268-1278`), o `discount_pct` pasado explícito.
**Cálculo:** `:1442-1466`
- Material **USD** (importado) → `discount.imported_percentage` (default **5%**).
- Material **ARS** (nacional) → `discount.national_percentage` (default **8%**).
- `discount_amount = round(material_total × pct / 100)` — **solo sobre material**, nunca sobre MO ni flete.
**Código:** `calculator.py:1268-1278, 1442-1466`

---

## Regla 4 · Descuento edificio

**Descripción:** descuento por volumen para obras de edificio grandes.
**Trigger:** `is_edificio = true` + `total_m2 ≥ building_min_m2_threshold` (default 15) + sin descuento previo.
**Cálculo:** `discount_pct = building_percentage` (default **18%**) (`:1449-1460`).
**Código:** `calculator.py:1449-1460`

---

## Regla 5 · Mano de obra (MO) — piletas

**Descripción:** costo de agujero/pegado/apoyo de pileta según tipo.
**Trigger:** `pileta` en `{empotrada_cliente, empotrada_johnson, apoyo}` y `pileta_qty > 0`.
**Cálculo:** `:1485-1494`
- Empotrada (cliente o johnson): SKU `PILETADEKTON/NEOLITH` (sintético) o `PEGADOPILETA` (resto), "Agujero y pegado pileta" × `pileta_qty`.
- Apoyo: `PILETAAPOYODEKTON/NEO` o `AGUJEROAPOYO`.
- **1 PEGADOPILETA por pileta, no por mesada** (regla de negocio del Master).
- `pileta_qty = 0` → sin línea de pileta.
**Código:** `calculator.py:1485-1494`

---

## Regla 6 · MO — anafe, frentín, inglete, regrueso, tomas, pulido

**Descripción:** líneas de MO opcionales según opciones de obra.
**Cálculo:**
- **Anafe:** `ANAFEDEKTON/NEOLITH`/`ANAFE` × `anafe_qty` (`:1496-1506`).
- **Frentín (faldón):** por metro lineal — `FALDONDEKTON/NEOLITH`/`FALDON`, qty = `frentin_ml` (`:1550-1566`).
- **Inglete (corte 45°):** `CORTE45*`, qty = `frentin_ml × 2` (ambos lados) (`:1567-1572`).
- **Regrueso:** SKU `REGRUESO`, "Mano de obra regrueso x ml", qty = `regrueso_ml` (`:1574-1591`). Además suma material: `regrueso_m2 = regrueso_ml × 0.05` (`:1411-1436`).
- **Tomas (toma corriente):** `TOMAS*`, **requiere alzada** en piezas — sin alzada se ignora + warning (`:1664-1704`).
- **Pulido de cantos:** si hay colocación y la zona tiene `pulido_extra=true` → unit = `round(flete_price/2)` (`:1654-1659`).
**Código:** `calculator.py:1496-1704`

---

## Regla 7 · Colocación

**Descripción:** costo de instalación, por m².
**Trigger:** `colocacion = true` (forzado a `false` en edificios).
**Cálculo:** `COLOCACIONDEKTON/NEOLITH`/`COLOCACION`, por m² con mínimo `colocacion.min_quantity` (default 1.0). Si se detectan ≥2 ambientes, se reparte por ambiente; si no, una línea sobre `total_m2` (`:1508-1548`).
**Código:** `calculator.py:1508-1548`

---

## Regla 8 · Flete

**Descripción:** costo de transporte + toma de medidas según zona.
**Trigger:** siempre salvo `skip_flete = true` (cliente retira en fábrica).
**Cálculo:** `:1593-1662`
- Zona vía `_find_flete(localidad)`, fallback a Rosario.
- Cantidad:
  - Override del operador (`flete_qty`) si está presente.
  - Edificio: `ceil(physical_pieces / building.flete_mesadas_per_trip)` (default **6**), excluye zócalo/frentín, mínimo 1, warning si > 20.
  - Residencial: 1.
- Descripción: "Flete + toma medidas {localidad}".
- **El flete nunca recibe descuento** (ni ÷1.05 de edificio ni `mo_discount_pct`).
**Código:** `calculator.py:1593-1662`

---

## Regla 9 · Ajuste de MO para edificios (÷1.05)

**Descripción:** los precios de MO de edificio se dividen por 1.05.
**Trigger:** `is_edificio = true`.
**Cálculo:** cada `mo_item` (excepto flete) → `unit / 1.05`, luego `total = round(unit × qty)` (`:1750-1764`). Edificio además fuerza `colocacion = false` y no aplica merma.
**Código:** `calculator.py:1280-1285, 1750-1764`

---

## Regla 10 · Descuento comercial sobre MO

**Descripción:** descuento porcentual sobre la mano de obra (no flete).
**Trigger:** `mo_discount_pct` pasado explícito por el operador.
**Cálculo:** `mo_discount_amount` sobre `total_mo_ars` excluyendo flete; se resta del subtotal MO (`:1766-1784`).
**Código:** `calculator.py:1766-1784`

---

## Regla 11 · Zócalos en metros lineales

**Descripción:** los zócalos se computan por ml, no por m².
**Trigger:** descripción de pieza empieza con "zócalo"/"zoc".
**Cálculo:** label `"{largo}ML X {prof} ZOC"`; el largo en ml contribuye al m² total (`:837-838, 1805-1815`).
**Código:** `calculator.py:837-838, 1805-1815`

---

## Regla 12 · Redondeo half-up

**Descripción:** redondeo comercial (no banker's rounding) para evitar el bug de float de Python.
**Cálculo:** `_round_half_up` usa `Decimal`/string (`:12-22`). m² por pieza → half-up a 2 decimales antes de sumar (`:778-780`); totales → `round()`.
**Edge case validado:** zócalo M6 `round(0.155, 2)` debe dar **0.16**, no 0.15 (banker's) — ver `test_zocalo_m2_quantity.py`.
**Código:** `calculator.py:12-22, 778-780`

---

## Reglas del Master §16 NO implementadas en el motor (deuda)

- **Redondeo a múltiplos comerciales** (ej. "Negro Brasil debe redondear a entero"): el Master lo menciona como regla, pero **NO existe en `calculator.py`**. El único redondeo es half-up a 2 decimales (Regla 12). Si esta regla se requiere, es trabajo nuevo de un sub-PR de Sprint 3+. — `DEFINIDA EN MASTER PERO NO IMPLEMENTADA`.
- **Conversión USD↔ARS por exchange rate:** el Master §13 muestra cifras canon que parecen mezclar monedas, pero el motor NO convierte (Regla de moneda en `calculator.md`). Los dos totales son nativos. — `DEFINIDA EN MOCK PERO NO IMPLEMENTADA`.
