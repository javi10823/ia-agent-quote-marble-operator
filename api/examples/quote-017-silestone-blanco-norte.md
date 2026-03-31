# Quote Example 017 — Cliente / Mesada Cocina — Silestone Blanco Norte

## Datos del trabajo
- **Cliente:** (sin nombre — simulación)
- **Proyecto:** Mesada cocina
- **Fecha:** 12/03/2026
- **Forma de pago:** a confirmar
- **Fecha de entrega:** 40 dias desde la toma de medidas
- **Ubicación:** Rosario

## Input del usuario
- Material solicitado: Purastone blanco / más económico en blanco
- Zócalo: 0.60ml × 2.10ml
- Pileta: propia (empotrada — hay anafe → cocina → empotrada siempre)
- Anafe embutido: sí
- Colocación: sí

## Lectura del pedido

### Medidas
- Profundidad no indicada → estándar 0.60m
- Alto zócalo no indicado → estándar 0.05m (5cm)

| Pieza | Cálculo | M2 |
|---|---|---|
| Mesada | 2.10 × 0.60 | 1.26 |
| Zócalo fondo | 2.10 × 0.05 | 0.105 |
| Zócalo lateral | 0.60 × 0.05 | 0.030 |
| **Total** | | **1.395** |

> Sin redondeo intermedio — sumar directo.

### Pileta
- Trae pileta propia + hay anafe → cocina → empotrada → SKU `PEGADOPILETA`
- No preguntar tipo de pileta cuando hay anafe

## Flujo de selección de material

### Paso 1 — Stock
Buscar Purastone blanco/claro en stock.json con largo ≥ 2.10m y margen ≥ 20%.

| Material | Piezas disponibles | Largo máx | Margen | Válido |
|---|---|---|---|---|
| PURASTONE PALOMA | 1.60×1.18 (mayor pieza) | 1.60m | — | ✗ largo < 2.10m |
| resto Purastone blancos | ninguna pieza ≥ 2.10m | — | — | ✗ |

→ **Sin stock válido.**

### Paso 2 — Sustitución Silestone
Cliente pidió Purastone → aplica regla de sustitución.
```
desperdicio = 2.10 (media placa) - 1.395 = 0.705 < 1.0 → entra en media placa ✓
→ Ofrecer Silestone equivalente
```
D'Angelo vende media placa de Silestone pero no de Purastone.

### Paso 3 — No aplica (resuelto en paso 2)

## Opciones ofrecidas al cliente
| Material | USD/m2 | Total mat |
|---|---|---|
| Silestone Blanco Norte ⭐ | USD519 | USD724 |
| Silestone White Storm | USD519 | USD724 |
| Silestone Norte Suede | USD585 | USD816 |
| Silestone Blanco Zeus | USD692 | USD965 |

## Cálculo final — Silestone Blanco Norte

### Material
```
price_usd s/IVA: 429.00
precio_unitario = floor(429 × 1.21) = floor(519.09) = USD519
total = round(1.395 × 519) = round(723.005) = USD724
Sin sobrante: desperdicio 0.705 < 1.0 ✓
```

### Mano de obra
| SKU | Descripción | Cantidad | Precio ARS | Total ARS |
|---|---|---|---|---|
| PEGADOPILETA | agujero y pegado de pileta | 1 | $59.767 | $59.767 |
| ANAFE | agujero anafe | 1 | $39.538 | $39.538 |
| ENVIOROS | flete + toma de medidas Rosario | 1 | $52.000 | $52.000 |
| COLOCACION | colocacion (min 1m2, usa 1.395) | 1.395 | $55.170 | $76.962,15 |

> ENVIOROS: $42.975,21 s/IVA × 1.21 = $52.000 c/IVA

**Total MO: $228.267,15**

## Resumen del presupuesto
```
Material: 1.395 m2 × USD519 = USD724     Total USD USD724
MO:                            $228.267,15
                               ──────────
PRESUPUESTO TOTAL: $228.267 mano de obra + USD724 material
```

## Reglas aplicadas
- Profundidad no indicada → 0.60m estándar ✓
- Alto zócalo no indicado → 0.05m estándar ✓
- M2 sin redondeo intermedio: 1.26 + 0.105 + 0.030 = 1.395 ✓
- Anafe → cocina → pileta empotrada → PEGADOPILETA (no AGUJEROAPOYO) ✓
- Stock Purastone: ninguna pieza con largo ≥ 2.10m → sin stock válido ✓
- Sustitución Silestone: desperdicio 0.705 < 1.0 → ofrecer Silestone ✓
- Precio floor: 429×1.21=519.09 → USD519 ✓
- Flete con IVA: $42.975,21 × 1.21 = $52.000 ✓
- Sin sobrante: desperdicio < 1.0 ✓
