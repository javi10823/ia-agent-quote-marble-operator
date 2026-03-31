# Quote Example 016 — ESTUDIO MUNGE / OBRA CATAMARCA 3228 — Silestone Gris Expo

## Datos del trabajo
- **Cliente:** ESTUDIO MUNGE
- **Proyecto:** OBRA CATAMARCA 3228
- **Fecha:** 10/03/2026
- **Forma de pago:** ctdo - cheque 0-15 dias
- **Fecha de entrega:** 20/30 dias desde la toma de medidas

## Input del usuario
- Material: Silestone Gris Expo 20mm
- Plano: mismo que quote-015 (mesada cocina, bacha empotrada, anafe embutido)
- Ubicación: Rosario
- Stock: NO

## Lectura del plano

### Piezas
| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada | 2.89m | 0.62m | 1.79 |
| Zócalo total | 3.49ml | 0.07m | 0.24 |

- M2 total = 2.0361 → **2.03** (D'Angelo redondeó a 2.03)

## Cálculo de material

### Merma — Silestone (referencia = media placa 2.10m2)
```
desperdicio = 2.10 - 2.03 = 0.07 < 1.0 → sin sobrante
Total a cobrar = 2.03 m2 exactos
```

### Precio
```
price_usd s/IVA: 550.00
precio_unitario = floor(550 × 1.21) = floor(665.50) = USD665
Material: 2.03 × 665 = USD1.349,95 → round = USD1.350
Grand total material: USD1.350
```

## Mano de obra

| SKU | Descripción | Cantidad | Precio ARS | Total ARS |
|---|---|---|---|---|
| LUXORMINI | Pileta Johnson Luxor Mini | 1 | $211.532 | $211.532 |
| PEGADOPILETA | agujero y pegado de pileta | 1 | $59.767 | $59.767 |
| ANAFE | agujero anafe | 1 | $39.538 | $39.538 |
| ENVIOROS | flete + toma de medidas Rosario | 1 | $45.000 | $45.000 |
| COLOCACION | colocacion (min 1m2) | 2.03 | $55.170 | $111.995,10 |

**Total MO: $467.832,10**

## Resumen del presupuesto

```
Material principal:  2.03 m2 × USD665 = USD1.350    Total USD USD1.350
Pileta LUXORMINI:                        $211.532,00
MANO DE OBRA:                            $256.300,10
                                         ──────────
Total PESOS:                             $467.832,10

PRESUPUESTO TOTAL: $467.832 mano de obra + USD1.350 material
```

## Reglas aplicadas
- Merma: desperdicio 0.07 < 1.0 → sin sobrante ✓
- Silestone usa media placa como referencia de merma ✓
- Precio floor: 665.50 → USD665 ✓
- Total round: 2.03 × 665 = 1349.95 → USD1.350 ✓
- Misma MO que quote-015 (mismo trabajo, distinto material) ✓
- Mínimo colocación 1m2: 2.03 > 1.0 → aplica normal ✓
