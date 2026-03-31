# Quote Example 015 — ESTUDIO MUNGE / OBRA CATAMARCA 3228 — Purastone Gris Zen

## Datos del trabajo
- **Cliente:** ESTUDIO MUNGE
- **Proyecto:** OBRA CATAMARCA 3228
- **Fecha:** 10/03/2026
- **Forma de pago:** ctdo - cheque 0-15 dias
- **Fecha de entrega:** 20/30 dias desde la toma de medidas

## Input del usuario
- Material: Purastone Gris Zen 20mm
- Plano: mesada cocina con zócalos, bacha empotrada Johnson Luxor Mini SI55, anafe embutido
- Ubicación: Rosario
- Stock: NO

## Lectura del plano

### Piezas
| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada | 2.89m | 0.62m | 1.79 |
| Zócalo total | 3.49ml | 0.07m | 0.24 |

- Zócalo total = fondo 2.89ml + lateral 0.60ml = 3.49ml
- M2 total = 1.7918 + 0.2443 = 2.0361 → **2.03** (D'Angelo redondeó a 2.03)

### Pileta
- Johnson Luxor Mini SI55 → empotrada → D'Angelo la vende → SKU `LUXORMINI`
- MO: `PEGADOPILETA`
- Agujero de grifería: incluido en SKU pileta — no se cobra por separado

### Anafe
- Embutido → MO: `ANAFE`

### Cantos / frentin
- Sin frentin (entre paredes, sin cantos libres)

## Cálculo de material

### Merma — Purastone (referencia = placa entera 4.20m2)
```
desperdicio = 4.20 - 2.03 = 2.17 ≥ 1.0 → ofrecer SOBRANTE
sobrante = 2.17 / 2 = 1.085 m2
```

### Precio
```
price_usd s/IVA: 454.54
precio_unitario = floor(454.54 × 1.21) = floor(549.99) = USD549
→ D'Angelo usó USD550 en este presupuesto (redondeo manual)
Material:  2.03 × 550 = USD1.116 (int)
Sobrante:  1.085 × 550 = USD597 (round)
Grand total material: USD1.713
```

> Nota: el agente usará floor() → USD549. D'Angelo puede ajustar manualmente.

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
Material principal:  2.03 m2 × USD550 = USD1.116    Total USD USD1.116
SOBRANTE:           1.085 m2 × USD550 = USD597       Total USD USD597
Pileta LUXORMINI:                        $211.532,00
MANO DE OBRA:                            $256.300,10
                                         ──────────
Total PESOS:                             $467.832,10

PRESUPUESTO TOTAL: $467.832 mano de obra + USD1.713 material
```

## Reglas aplicadas
- Merma: desperdicio 2.17 ≥ 1.0 → SOBRANTE separado ✓
- Material principal: m2 exactos (2.03), no se suma merma ✓
- Mínimo colocación 1m2: 2.03 > 1.0 → aplica normal ✓
- Pileta empotrada comprada en D'Angelo → LUXORMINI + PEGADOPILETA ✓
- Agujero grifería: incluido en LUXORMINI, no se cobra ✓
- Entrega 20/30 dias: rango habilitado en config ✓
