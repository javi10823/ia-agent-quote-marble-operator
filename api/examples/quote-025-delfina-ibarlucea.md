# Ejemplo 025 — Delfina (Particular) — Obra Ibarlucea

## Tipo
**PARTICULAR** — cocina con isla, alzada y costado, Purastone (cuarzo USD), merma 2 placas, toma de corriente

## Datos del cliente
- **Cliente:** Delfina
- **Proyecto:** Cocina — Obra Ibarlucea
- **Fecha:** 16/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** 30 días desde la toma de medidas
- **Localidad:** Ibarlucea (ENVIBAR)

## Material
- **Purastone Terrazo White — 20mm** (cuarzo USD)
- SKU: PURATERRAZO — USD 337.17 sin IVA
- Precio con IVA: floor(337.17 × 1.21) = **USD 407/m²**
- Sin descuento — operador indicó no aplicar
- Purastone → aplica merma, placa estándar **4.2 m²**, largo máximo **3.20m**

## Piezas
| Pieza | Medida | m² | Nota |
|-------|--------|----|------|
| Mesada cocina | 0.60 × **3.20** | 1.92 | Plano decía 3.25 pero largo máx placa = 3.20 |
| Isla | 0.80 × 3.15 | 2.52 | |
| Alzada | 1.20 × 0.73 | 0.876 | Vista superior del plano |
| Costado | 2.00 × 0.10 | 0.20 | |
| **Total mesadas** | | **5.516** | |
| SOBRANTE merma | | 1.442 | 2 placas × 4.2 = 8.4 → (8.4-5.516)/2 |
| **TOTAL a cobrar** | | **6.958 m²** | |

`USD 407 × 6.958 = USD 2.832`

## Merma
- Trabajo: 5.516 m² → necesita 2 placas (4.2 × 2 = 8.4 m²)
- Desperdicio: 8.4 - 5.516 = 2.884 m² ≥ 1.0 → SOBRANTE = 2.884/2 = 1.442 m²

## Mano de obra
| Ítem | SKU | Cant | Precio | Total |
|------|-----|------|--------|-------|
| Agujero anafe | ANAFE | 1 | $39.539 | $39.539 |
| Agujero y pegado de pileta | PEGADOPILETA | 1 | $59.768 | $59.768 |
| Agujero toma de corriente | TOMAS | 1 | $7.172 | $7.172 |
| Colocación | COLOCACION | 5.516 m² | $55.170 | $304.118 |
| Pulido de cantos | — | 1 | $30.000 | $30.000 |
| Flete + toma de medidas Ibarlucea | ENVIBAR | 1 | $75.000 | $75.000 |
| **TOTAL MO** | | | | **$515.597** |

**Grand total: $515.597 + USD 2.832 Mano de obra + material**

## Reglas clave aprendidas
1. **Largo máximo placa Purastone = 3.20m** — si el plano indica más, usar 3.20m
2. **Alzada y costado = piezas de material** → sumar m², incluir en colocación
3. **Pieza de arriba en corte/vista** → leer sus dimensiones del plano y cotizarla como pieza adicional
4. **TOMAS** — agujero de toma de corriente, SKU propio en labor.json
5. **Colocación sobre m² reales de mesadas** (sin sobrante de merma)
6. **Sin descuento** aunque se cumplan condiciones — el operador tiene la última palabra
7. **Preguntar siempre**: pulido de cantos y plazo de entrega
