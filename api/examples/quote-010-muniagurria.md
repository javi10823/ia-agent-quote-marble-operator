# Ejemplo 010 — Muniagurria (Callao 1171)

## Datos del cliente
- **Cliente:** Muniagurria
- **Proyecto:** Callao 1171
- **Fecha:** 26/2/2026
- **Forma de pago:** ctdo - cheque 0-15 días
- **Fecha de entrega:** 30 días desde la toma de medidas

## Tipo de trabajo
Mesadas múltiples de cocina — interior, edificio (restricción de ascensor)
Caso especial: **descuento sobre material, 2 piletas, advertencia de ascensor**

## Material
- **Purastone Terrazo - 20MM** (cuarzo importado, USD)
- SKU: PURATERRAZO

## Medidas

| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada 1 | 1.530m | 0.645m | 0.987 m2 |
| Mesada 2 | 2.067m | 0.645m | 1.333 m2 |
| Mesada 3 | 1.595m | 0.635m | 1.013 m2 |
| Mesada 4 | 0.995m | 0.635m | 0.632 m2 |
| Mesada 5 | 1.650m | 0.600m | 0.990 m2 |
| Zócalo 1 | 2.850m | 0.100m | 0.285 m2 |
| Zócalo 2 | 2.225m | 0.050m | 0.111 m2 |
| **TOTAL BRUTO** | | | **5.351 m2** |

## Merma
- Purastone = sintético → aplica merma
- M2 necesarios: 5.34 > 2.10 → NO aplica merma
- **M2 a cobrar: 5.34 m2**

## Descuento
```
5.34 m2 × USD 408 = USD 2.179
Descuento: USD 109
Total material neto: USD 2.070
```

## Mano de obra

| Ítem | SKU | Cantidad | Precio unit. | Total |
|---|---|---|---|---|
| Agujero y pegado de pileta | PEGADOPILETA | 2 | $59.767 | $119.534 |
| Agujero anafe | ANAFE | 1 | $39.538 | $39.538 |
| Flete + toma de medidas Rosario | ENVROSARIO | 1 | $45.000 | $45.000 |
| Colocación | COLOCACION | 5.34 m2 | $55.170 | $294.608 |
| **TOTAL PESOS** | | | | **$498.680** |

## Totales
```
PRESUPUESTO TOTAL: $498.680 mano de obra + USD2.070 material
```

## Notas del ejemplo
- Purastone 20mm → colocación a precio estándar SKU COLOCACION ($55.170/m2),
  NO usar COLOCACIONDEKTON ($82.755) — ese precio es exclusivo de piedra sinterizada
- 2 piletas → agujero y pegado × 2 unidades
- Descuento sobre material: mostrar como línea negativa en bloque de material
- Edificio: agregar nota "NO SE SUBEN MESADAS QUE NO ENTREN POR ASCENSOR"
  cuando la obra es en edificio — preguntar al cliente si hay restricción de acceso
- Sin faldon en este trabajo a pesar de tener zócalos — el cliente no lo solicitó
