# Ejemplo 034 — Alejandro Gavilán — Granito Negro Brasil / Cocina + Isla + Parrilla

## Tipo
**PARTICULAR** — 3 sectores en 1 presupuesto (cocina en L + isla + parrilla), múltiples zócalos explícitos, 2 piletas empotradas, sin merma (Negro Brasil)

## Datos del cliente
- **Cliente:** Alejandro Gavilán
- **Proyecto:** Cocina + Isla + Parrilla
- **Fecha:** 27/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** 30 días desde la toma de medidas
- **Localidad:** Rosario (ENVIOROS)
- **Descuento:** Ninguno

## Material
- **Granito Negro Brasil Extra 20mm** — SKU: GRANITONEGROBRASIL
- USD 228 sin IVA → **USD 275/m²** c/IVA (floor)
- **Sin merma** — regla especial Negro Brasil: nunca merma

## Lectura de planos — 4 pasadas

### Imagen 1 — PARRILLA y ISLA
**Parrilla (sector bacha):**
- Largo: 1.387m | Prof: 0.77m
- 1 zócalo 139cm + 2 zócalos 77cm → explícitos en especificaciones
- 1 pileta empotrada (X en planta) → PEGADOPILETA
- Eje bacha 35cm → c/p → ignorar

**Isla:**
- Largo: 1.90m | Prof: 0.80m
- 1 zócalo 0.25m (alto) — especificado como "1 ZÓCALO DE 0.25 cm" → interpretado como 0.25m de largo del zócalo a 5cm de alto
- Sin pileta indicada

### Imagen 2 — COCINA + PIEZA SUELTA
**Cocina en L:**
- Tramo A: 2.59 × 0.60m
- Tramo B (perpendicular): 0.65 × 0.60m
- Zócalos: 2×1.30m + 1×1.23m + 2×0.60m → explícitos en especificaciones
- 1 pileta empotrada (rectángulo con doble línea) → PEGADOPILETA. Eje bacha 1.10 = c/p → ignorar
- Sin anafe dibujado → no se cobra ANAFE

**Pieza suelta 0.60×0.60m:** tramo adicional de cocina (Tramo C)

## Desglose de piezas

### PARRILLA
| Pieza | Medida | m² |
|-------|--------|----|
| Mesada parrilla | 1.387 × 0.77 | 1.0680 |
| ZÓCALO 2.93 ml x 0.05 m | (1.39+0.77+0.77)×0.05 | 0.1465 |
| **Subtotal** | | **1.2145** |

### ISLA
| Pieza | Medida | m² |
|-------|--------|----|
| Mesada isla | 1.90 × 0.80 | 1.5200 |
| ZÓCALO 0.25 ml x 0.05 m | 0.25×0.05 | 0.0125 |
| **Subtotal** | | **1.5325** |

### COCINA
| Pieza | Medida | m² |
|-------|--------|----|
| Tramo A | 2.59 × 0.60 | 1.5540 |
| Tramo B | 0.65 × 0.60 | 0.3900 |
| Tramo C (pieza suelta) | 0.60 × 0.60 | 0.3600 |
| ZÓCALO 5.03 ml x 0.05 m | (2×1.30+1.23+2×0.60)×0.05 | 0.2515 |
| **Subtotal** | | **2.5555** |

| **TOTAL** | | **5.30 m²** |

**Total material: round(5.30 × 275) = USD 1.458**

## Mano de obra

| Ítem | SKU | Cant | Precio c/IVA | Total |
|------|-----|------|--------------|-------|
| Agujero y pegado de pileta x u | PEGADOPILETA | 2 | $65.147 | $130.294 |
| Colocación x m² | COLOCACION | 5.30 | $60.135 | $318.716 |
| Flete + toma medidas Rosario x u | ENVIOROS | 1 | $52.000 | $52.000 |
| **TOTAL MO** | | | | **$501.010** |

## Grand total
**$501.010 ARS + USD 1.458 — Mano de obra + material**

## Reglas clave aplicadas
1. **Negro Brasil** → NUNCA merma sin excepción
2. **Pieza suelta 0.60×0.60** → tramo adicional de cocina (Tramo C), no elemento separado
3. **Zócalos explícitos en especificaciones** → leer ml directamente del texto, no del dibujo
4. **Eje bacha** → siempre c/p → ignorar para presupuesto
5. **Sin anafe dibujado** → no se cobra ANAFE aunque sea cocina
6. **2 piletas empotradas** (parrilla + cocina) → 2 × PEGADOPILETA
7. **Excel con muchas piezas** → hacer unmerge de B37:D37, A39:F39, A40-42:F40-42 antes de escribir
