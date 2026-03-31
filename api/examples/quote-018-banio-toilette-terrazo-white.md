# Quote Example 018 — Cliente / Baño Toilette — Purastone Terrazo White

## Datos del trabajo
- **Cliente:** (sin nombre — caso real D'Angelo)
- **Proyecto:** Baño Toilette
- **Fecha:** 12/03/2026
- **Sin flete** — retira el cliente
- **Fecha de entrega:** 40 dias desde la toma de medidas

## Input — lectura del plano

### Plano original
- Mesada: 90cm largo × 50cm prof
- Arriba: 89 Z → zócalo de 89cm
- Laterales: Z en ambos lados → zócalo en ambos laterales (regla: donde dice Z → lleva zócalo)
- F 90 → frentin de 90cm en el frente, 20cm alto
- c/p → centro de pileta, ignorar (solo referencia de obra)
- Pileta de apoyo (círculo en plano) — cliente la trae
- Grifería de pared — debe definirse si lo hacen (pendiente, no afecta presupuesto actual)

### Reglas de lectura aplicadas
- **Z → zócalo** sin excepciones (ambos laterales)
- **c/p** → ignorar, no es dimensión de presupuesto
- **F de X cm** → frentin solo en el frente, NO suma m2 al material → cobrar como FALDON (ml) en MO
- **89 Z** → largo del zócalo arriba = 89cm

## Cálculo de m2

| Pieza | Cálculo | M2 |
|---|---|---|
| Mesada | 0.90 × 0.50 | 0.4500 |
| Zócalo arriba | 0.89 × 0.05 | 0.0445 |
| Zócalo izq | 0.50 × 0.05 | 0.0250 |
| Zócalo der | 0.50 × 0.05 | 0.0250 |
| **Total** | | **0.544** |

> Frentin (0.90 × 0.20) NO se incluye en m2 — se cobra como FALDON en MO.

## Flujo de selección de material

### Paso 1 — Stock
Material: Purastone Terrazo White | Largo máx trabajo: 0.90m | M2 trabajo: 0.544

| Pieza stock | Dimensión | M2 | Dim OK | Margen | Válida |
|---|---|---|---|---|---|
| pieza A | 0.88×0.48 | 0.42 | ✗ | — | ✗ |
| pieza B | 2.00×0.34 | 0.68 | ✓ | -3% | ✗ margen < 20% |
| **pieza C** | **1.66×0.61** | **1.01** | **✓** | **44%** | **✓** |
| pieza D | 1.06×0.50 | 0.53 | ✓ | -32% | ✗ margen < 20% |

→ **Pieza C válida** — cobrar m2 exactos, sin merma.

### Paso 2 y 3 — No aplica (resuelto en paso 1)

## Material

```
price_usd s/IVA: 337.17
precio_unitario = floor(337.17 × 1.21) = floor(408.0) = USD407
total = round(0.544 × 407) = USD221
Sin merma — stock disponible ✓
```

## Mano de obra

| SKU | Descripción | Cantidad | Precio ARS | Total ARS |
|---|---|---|---|---|
| CORTE45 | corte a 45° (laterales) | 1.80ml | $6.810 | $12.258,00 |
| FALDON | faldón recto (frente) | 0.90ml | $17.025 | $15.322,50 |
| COLOCACION | colocación (mín 1m2) | 1.00m2 | $55.170 | $55.170,00 |
| AGUJEROAPOYO | agujero pileta de apoyo | 1 | $39.538 | $39.538,00 |

> Sin flete — retira el cliente.
> AGUJEROAPOYO incluye siempre la grifería — nunca cobrar aparte.
> CORTE45: lateral izq 0.90ml + lateral der 0.90ml = 1.80ml total.
> FALDON: frente 0.90ml.

**Total MO: $122.288,50** ✓ (coincide con presupuesto real D'Angelo)

## Resumen
```
Material (stock, sin merma): 0.544m2 × USD407 = USD221
MO:                                               $122.288,50
```

## Reglas aplicadas
- Z en plano → zócalo en ambos laterales ✓
- c/p ignorado ✓
- Frentin → FALDON (ml) en MO, NO m2 en material ✓
- CORTE45 por uniones laterales con frente ✓
- Stock válido: pieza 1.66×0.61, largo ≥ 0.90, margen 44% ≥ 20% ✓
- Sin merma por stock ✓
- AGUJEROAPOYO para pileta de apoyo (baño) ✓
- Sin flete ✓
- Colocación mínimo 1m2 ✓
