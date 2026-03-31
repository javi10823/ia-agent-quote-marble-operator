# Ejemplo 011 — Arq. Nadia (Multi-ambiente)

## Datos del cliente
- **Cliente:** Arq. Nadia
- **Proyecto:** Cocina + Baño + Estante
- **Fecha:** 13/1/2026
- **Forma de pago:** ctdo - cheque 0-15 días
- **Fecha de entrega:** 30 días desde la toma de medidas

## Tipo de trabajo
Múltiples ambientes en un mismo presupuesto: cocina + baño + estante
Caso especial: **un solo material para todos los ambientes, alzas en cocina, zócalo en baño, estante**

## Material
- **Granito Negro Brasil Extra - 20MM** (granito importado, USD)
- SKU: GRANITONEGROBRASIL

## Medidas

### COCINA
| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada cocina 1 | 1.02m | 0.60m | 0.612 m2 |
| Mesada cocina 2 | 1.02m | 0.38m | 0.388 m2 |
| Mesada cocina 3 | 1.76m | 0.65m | 1.144 m2 |
| Alza 1 | 1.76m | 0.60m | 1.056 m2 |
| Alza 2 | 0.65m | 0.60m | 0.390 m2 |
| Alza 3 | 1.02m | 0.60m | 0.612 m2 |

### BAÑO
| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada baño | 0.59m | 0.30m | 0.177 m2 |
| Zócalo | 0.89m | 0.05m | 0.045 m2 |

### ESTANTE
| Pieza | Largo | Ancho | Unid. | M2 |
|---|---|---|---|---|
| Estante | 0.20m | 0.15m | 2 | 0.060 m2 |

| **TOTAL** | | | | **4.484 m2** |

## Merma
- Granito = piedra natural → NO aplica merma
- **M2 a cobrar: 4.48 m2**

## Cálculo de material
```
Precio c/IVA: USD 276/m2
Total: 4.48 × USD 276 = USD 1.236
```

## Mano de obra

| Ítem | SKU | Cantidad | Precio unit. | Total |
|---|---|---|---|---|
| Agujero y pegado de pileta | PEGADOPILETA | 1 | $59.767 | $59.767 |
| Agujero pileta apoyo | AGUJPILETA | 1 | $39.538 | $39.538 |
| Agujero anafe | ANAFE | 1 | $39.538 | $39.538 |
| Flete + toma de medidas Rosario | ENVROSARIO | 1 | $45.000 | $45.000 |
| Agujero tomas | TOMAS | 8 | $7.172 | $57.376 |
| Colocación | COLOCACION | 4.42 m2 | $55.170 | $243.851 |
| **TOTAL PESOS** | | | | **$485.070** |

> Nota: la colocación se aplica sobre 4.42 m2 (no sobre 4.48) — posible redondeo o exclusión del estante.

## Totales
```
PRESUPUESTO TOTAL: $485.070 mano de obra + USD1.236 material
```

## Notas del ejemplo
- Multi-ambiente: cocina + baño + estante en un solo presupuesto con el mismo material
- Dos tipos de agujero de pileta distintos en el mismo presupuesto:
  - Cocina: agujero y pegado ($59.767) — pileta empotrada
  - Baño: agujero pileta apoyo ($39.538) — pileta de apoyo
- 8 agujeros tomas — precio actualizado respecto a Kawano ($7.172 vs $6.520)
- Colocación aplicada sobre m2 ligeramente menor al total — el estante puede no llevar colocación
- Las alzas se calculan igual que cualquier otra pieza (largo × ancho) y se suman al total
