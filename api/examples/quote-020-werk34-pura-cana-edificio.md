# Ejemplo 020 — WERK Constructora (Edificio Werk 34 — Pura Cana)

## Tipo
**EDIFICIO** — cocinas + lavaderos, Purastone Pura Cana USD, patas de isla, zócalos laterales y traseros, anafes, múltiples correcciones de lectura de plano

## Datos del cliente
- **Cliente:** WERK Constructora
- **Proyecto:** Edificio Werk 34 — Mendoza 525, Rosario
- **Fecha:** 14/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** A convenir

## Planos utilizados
| Plano | Tipo | Cant | Notas |
|-------|------|------|-------|
| MC1 | Cocina piso 1° | 2 (1 izq + 1 der) | 1 pata isla lado derecho, anafe, bacha viene en bacha |
| MC2 | Cocinas 2°-12° | 22 (11 izq + 11 der) | 2 patas isla, anafe, bacha viene en bacha |
| ML1 | Lavadero piso 1° | 2 (1 izq + 1 der) | Zócalo atrás + lateral izq/der |
| ML2 | Lavaderos 2°-12° | 22 (11 izq + 11 der) | Zócalo atrás + lateral izq/der |

## Material
- **Purastone Pura Cana — 20mm** (USD)
- SKU: PURACANA — USD 286 sin IVA
- Precio con IVA: floor(286 × 1.21) = USD 346/m²
- Descuento edificio: floor(346 / 1.18) = **USD 293/m²**
- Total m² > 15 → descuento aplica

## Desglose de m²

### Mesadas
| Pieza | Medida | Cant | m² |
|-------|--------|------|----|
| MC1 mesada pared | 2.41×0.62 | ×2 | 2.9884 |
| MC1 isla | 1.88×0.84 | ×2 | 3.1584 |
| MC2 mesada pared | 2.57×0.62 | ×22 | 35.0548 |
| MC2 isla | 1.96×0.84 | ×22 | 36.2208 |
| ML1 lavadero | 0.67×**0.60** | ×2 | 0.804 |
| ML2 lavadero | 1.38×0.60 | ×22 | 18.216 |
| **Subtotal mesadas** | | | **96.4424** |

### Patas de isla (material adicional)
| Pieza | Medida | Cant | m² |
|-------|--------|------|----|
| MC1 pata | 0.84×0.88 | ×2 | 1.4784 |
| MC2 patas | 0.84×0.88 | ×44 | 32.5248 |
| **Subtotal patas** | | | **34.0032** |

### Zócalos lavaderos
Leer VISTA ZOCALO LATERAL: cota horizontal (15cm) = alto del zócalo. Cota vertical (58cm) = profundidad mesada → ignorar.
| Pieza | Medida | Cant | m² |
|-------|--------|------|----|
| ML1 zócalo atrás | 0.67×0.15 | ×2 | 0.201 |
| ML1 zócalo lateral | **0.60**×0.15 | ×2 | 0.18 |
| ML2 zócalo atrás | 1.38×0.15 | ×22 | 4.554 |
| ML2 zócalo lateral | **0.60**×0.15 | ×44 | 3.96 |
| **Subtotal zócalos** | | | **8.895** |

**TOTAL MATERIAL: 139.34 m² × USD 293 = USD 40.827**

## Mano de obra (todos ÷1.05 excepto flete)
| Ítem | SKU | Cant | Precio c/desc | Total |
|------|-----|------|---------------|-------|
| Agujero y pegado de pileta | PEGADOPILETA | 48 | $56.922 | $2.732.256 |
| Pata lateral — corte a 45° | CORTE45 | 77.28 ml | $6.486 | $501.238 |
| Agujero anafe | ANAFE | 24 | $37.656 | $903.744 |
| Pulido cara interna patas | — | 46 | $9.524 | $438.104 |
| Flete Rosario + toma de medidas | ENVIOROS | 9 | $52.000 | $468.000 |
| **TOTAL MO** | | | | **$5.043.342** |

**Grand total: $5.043.342 + USD 40.827 Mano de obra + material**

## CORTE45 patas — cálculo
- MC1 ×2 unidades, 1 pata por isla: 0.84 × 2 × 2u = 3.36 ml
- MC2 ×22 unidades, 2 patas por isla: 0.84 × 2 × 2 × 22u = 73.92 ml
- **Total: 77.28 ml**

## Piezas físicas para flete
| Tipo | Piezas/unidad | Unidades | Total piezas |
|------|--------------|----------|-------------|
| MC1 (pared + isla) | 2 | 2 | 4 |
| MC2 (pared + isla) | 2 | 22 | 44 |
| ML1 | 1 | 2 | 2 |
| ML2 | 1 | 22 | 22 |
| **TOTAL** | | | **72 piezas** |
ceil(72/6) = **12 viajes** → operador ajustó a **9** (entran más piezas por viaje)

## Reglas clave aprendidas / confirmadas
1. **Pata lateral = material adicional** → m² = prof_mesada × alto_pata. NO solo MO
2. **CORTE45 patas en MO**: ml = prof_mesada × 2. Lleva descuento ÷1.05 en edificios
3. **"PATA LATERAL — CORTE A 45°"** — sin PEGADO en el concepto
4. **Pulido cara interna patas** → solo si operador lo indica, precio por unidad
5. **VISTA ZOCALO LATERAL**: cota horizontal = alto zócalo. Cota vertical = profundidad mesada (ignorar para el alto)
6. **Zócalo lateral largo = profundidad real de la mesada** (0.60m), no la cota interna del dibujo
7. **Profundidad lavadero = 0.60m**, no 0.62m
8. **ANAFE se cobra** por cada unidad que lleva anafe (MC1×2 + MC2×22 = 24)
9. **TODA la MO en edificios ÷1.05 EXCEPTO flete**
10. **Validación en texto plano** antes de generar PDF — operador confirma antes de proceder
