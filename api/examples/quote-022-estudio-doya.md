# Ejemplo 022 — Estudio Doya (Particular)

## Tipo
**PARTICULAR** — mesada de baño, Dekton sinterizado USD, pileta de apoyo, material en stock (sin merma), descuento 10%

## Datos del cliente
- **Cliente:** Estudio Doya
- **Proyecto:** Baño — Córdoba 1825, Rosario
- **Fecha:** 14/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** A convenir
- **Localidad:** Rosario

## Material
- **Dekton Nebbia — 12mm** (sinterizado, USD)
- SKU: DEKNEB
- Precio con IVA: floor(598 × 1.21) = **USD 723/m²**
- Descuento 10%: floor(723 / 1.10) = **USD 657/m²**
- **Material en stock → sin merma** (cobrar solo m² reales)

## Piezas
- Mesada baño: **1.50 × 0.50 = 0.75 m²**

## Material
`USD 723 × 0.75 = USD 542 → DESC 10% = - USD 49 → Total: USD 493`

## Mano de obra
| Ítem | SKU | Cant | Precio | Total |
|------|-----|------|--------|-------|
| Agujero pileta de apoyo Dekton | PILETAAPOYODEKTON/NEO | 1 | $59.768 | $59.768 |
| Pulido Dekton/Neolith | PUL2 | 2.50 ml | $10.115 | $25.288 |
| Colocación Dekton | COLOCACIONDEKTON/NEOLITH | **1.00 m²** | $82.755 | $82.755 |
| Flete + toma de medidas Rosario | ENVIOROS | 1 | $52.000 | $52.000 |
| **TOTAL MO** | | | | **$219.811** |

## Grand total
**$219.811 + USD 493 Mano de obra + material**

## PUL — cantos sin zócalo
- Sin zócalo → todos los cantos visibles: frente (1.50) + 2 laterales (0.50 + 0.50) = **2.50 ml**
- Canto trasero va a pared → no se pula

## Reglas clave aplicadas en este ejemplo
1. **SKUs Dekton — siempre usar los específicos**, nunca los genéricos:
   - Pileta de apoyo → `PILETAAPOYODEKTON/NEO` (NO `AGUJEROAPOYO`)
   - Pileta empotrada → `PILETADEKTON/NEOLITH` (NO `PEGADOPILETA`)
   - Pulido → `PUL2` (NO `PUL`)
   - Colocación → `COLOCACIONDEKTON/NEOLITH` (NO `COLOCACION`)
   - Faldón → `FALDONDEKTON/NEOLITH` (NO `FALDON`)
   - Corte 45° → `CORTE45DEKTON/NEOLITH` (NO `CORTE45`)
   - **Regla general:** para cualquier material sinterizado (Dekton, Neolith, Laminatto, Puraprima), buscar SIEMPRE el SKU específico en labor.json antes de usar el genérico
2. **Colocación mínimo 1 m²** — el trabajo tiene 0.75 m² pero se cobra 1.00 m²
3. **Material en stock → sin merma** — cobrar solo los m² reales del trabajo
4. **Descuento sobre material**: precio_con_iva / 1.10 (método ÷ no resta %)
5. **PUL2** en todos los cantos sin zócalo para Dekton/sinterizados
