# Ejemplo 026 — Luciana Pacor (Particular)

## Tipo
**PARTICULAR** — baño, Purastone Blanco Paloma 20mm, pileta empotrada, curva/redondeo en esquina, zócalos, stock confirmado, descuento arquitecta

## Datos del cliente
- **Cliente:** Luciana Pacor
- **Proyecto:** Baño — Purastone Blanco Paloma
- **Fecha:** 18/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** 15 días desde la toma de medidas
- **Localidad:** Funes (ENVFUNES)
- **Arquitecta:** Sí → DESC 5% aplicado

## Material
- **Purastone Blanco Paloma — 20mm** (cuarzo USD)
- SKU: PALOMA — USD 337.17 sin IVA
- Precio con IVA: floor(337.17 × 1.21) = **USD 407/m²**
- DESC 5% arquitecta → **USD 387/m²**
- Stock confirmado → **sin merma**

## Desglose de m²
| Pieza | Medida | m² |
|-------|--------|----|
| Mesada | 1.00 × 0.55 | 0.55 |
| Zócalo atrás | 1.00 × 0.05 | 0.05 |
| Zócalo lateral derecho | 0.55 × 0.05 | 0.0275 |
| **TOTAL** | | **0.6275 m²** |

`USD 407 × 0.6275 = USD 255 → DESC -USD 12 → USD 243`

## Stock verificado
- PURASTONE PALOMA en stock.json: 3 piezas válidas
  - 1.41×0.60 = 0.85 m² ✅ (largo ≥ 1.05m, m² ≥ 0.753)
  - 1.41×0.60 = 0.85 m² ✅
  - 1.60×1.18 = 1.89 m² ✅
- Operador confirmó uso → sin merma

## Mano de obra
| Ítem | SKU | Cant | Precio | Total |
|------|-----|------|--------|-------|
| Agujero y pegado de pileta | PEGADOPILETA | 1 | $59.768 | $59.768 |
| Colocación | COLOCACION | 1.00 m² | $55.170 | $55.170 |
| Pulido de forma | — | 1 | $30.000 | $30.000 |
| Flete + toma de medidas Funes | ENVFUNES | 1 | $90.000 | $90.000 |
| **TOTAL MO** | | | | **$234.938** |

**Grand total: $234.938 + USD 243 Mano de obra + material**

## Reglas clave aplicadas
1. **Curva/redondeo en plano** → rectángulo completo, cobrar PULIDO DE FORMA (precio indicado por operador = $30.000 en este caso). Cota del redondeo (40cm) ignorada
2. **3 puntitos al costado del óvalo** = agujeros de fijación, no grifería → pileta empotrada → PEGADOPILETA
3. **Óvalo en baño con grifería monocomando** → leer contexto → en este caso es baño → PEGADOPILETA
4. **Stock válido**: largo_pieza ≥ largo_max + 0.05m Y m² ≥ m²_trabajo × 1.20
5. **Descuento arquitecta** = 5% sin umbral de m², no acumulativo
6. **Luciana Pacor** registrada en architects.json como arquitecta con descuento
7. **Validación previa al PDF** es bloqueante — siempre mostrar resumen y esperar confirmación
8. **Zócalo lateral** largo = profundidad real de la mesada (0.55m), no la cota del redondeo
