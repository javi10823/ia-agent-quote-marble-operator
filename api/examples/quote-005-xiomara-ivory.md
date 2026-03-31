# Ejemplo 005 — Xiomara Noval (Pura Prima Ivory Desert)

## Datos del cliente
- **Cliente:** Xiomara Noval
- **Proyecto:** Mesada de cocina
- **Fecha:** 7/3/2026
- **Forma de pago:** ctdo - cheque 0-15 días
- **Fecha de entrega:** 30 días desde la toma de medidas

## Tipo de trabajo
Mesada de cocina con faldon y zócalos — interior
Caso especial: **sobrante de placa cotizado por separado + pileta Johnson + refuerzo granito**

## Material
- **Pura Prima Ivory Desert - 12MM** (piedra sinterizada, importado USD)
- SKU: PPIVORYDESERT

## Medidas

| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada tramo 1 | 1.50m | 0.60m | 0.900 m2 |
| Mesada tramo 2 | 2.70m | 0.60m | 1.620 m2 |
| Zócalo | 4.80m | 0.04m | 0.192 m2 |
| Faldon | 5.40m | 0.04m | 0.216 m2 |
| **TOTAL** | | | **2.928 m2** |

## Merma
- Material sintético (Pura Prima) → aplica merma
- Placa estándar: 4.20 m2, mitad: 2.10 m2
- M2 necesarios: 2.928 > 2.10 → NO aplica merma automática
- **M2 a cobrar: 2.93 m2** (redondeado)

## Sobrante de placa
El sobrante de material restante de la placa se cotiza por separado como ítem adicional
por si el cliente lo quiere adquirir (ej. para futura reparación o uso adicional).

```
Sobrante: 1.1 m2 × USD 529 = USD 582
```

> El sobrante NO es obligatorio — es opcional para el cliente. Se presenta como línea separada.

## Cálculo de material
```
Precio c/IVA: USD 529/m2
Total mesada: 2.93 × USD 529 = USD 1.550
Total sobrante (opcional): 1.1 × USD 529 = USD 582
TOTAL USD (si toma sobrante): USD 2.132
```

## Pileta
- **Johnson Enkel 55** — $633.000 (precio ARS, se suma al total pesos)
- Incluye agujero y pegado de pileta

## Mano de obra

| Ítem | SKU | Cantidad | Precio unit. | Total |
|---|---|---|---|---|
| Agujero y pegado de pileta | PEGADOPILETA | 1 | $79.077 | $79.077 |
| Agujero anafe | ANAFE | 1 | $59.767 | $59.767 |
| Refuerzo granito | REFUERZOGRANITO | 1 | $90.000 | $90.000 |
| Mano de obra faldon | FALDONDEKTON/NEOLITH | 5.4 ml | $23.835 | $128.709 |
| Corte 45 | CORTE45DEKTON/NEOLITH | 10.8 ml | $8.513 | $91.940 |
| Flete + toma de medidas Rosario | ENVROSARIO | 1 | $45.000 | $45.000 |
| Colocación | COLOCACION | 2.93 m2 | $82.755 | $242.472 |
| **TOTAL PESOS** | | | | **$736.965** |

> + Pileta Johnson Enkel 55: $633.000
> **TOTAL PESOS con pileta: $1.369.965**

## Totales
```
PRESUPUESTO TOTAL: $1.369.965 mano de obra + USD2.132 material (con sobrante)
```

## Notas del ejemplo
- Pura Prima 12mm → usar SKUs FALDONDEKTON/NEOLITH y CORTE45DEKTON/NEOLITH
- Pura Prima 12mm → precio de colocación diferenciado ($82.755 vs $55.170 estándar) — verificar SKU en labor.json
- Refuerzo granito: se agrega cuando la pileta requiere refuerzo estructural bajo la mesada
- Sobrante de placa: opción a ofrecer al cliente cuando queda material remanente significativo
- Pileta Johnson se suma al total ARS como ítem separado de mano de obra
- Faldon en ml: 5.40ml (el alto del faldon es 0.04m, igual que el zócalo)
- Corte 45 = faldon ml × 2 = 10.80ml
