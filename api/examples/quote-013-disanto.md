# Presupuesto 013 — Di Santo
**Fecha:** 19/02/2026
**Cliente:** Di Santo
**Forma de pago:** contado / cheque 0-15 días
**Fecha de entrega:** 30 días desde la toma de medidas

---

## Material

**Purastone Blanco Paloma - 20MM** (importado, USD) — SKU: PALOMA

### Piezas

| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada (en dos tramos) | 3.24m | 0.63m | 2.041 m2 |
| Alza | 2.49m | 0.50m | 1.245 m2 |
| Alza | 0.76m | 0.23m | 0.175 m2 |
| **TOTAL** | | | **3.461 ≈ 3.46 m2** |

### Merma
Purastone Blanco Paloma — placa estándar 4.20 m2
- m2 necesarios: 3.46 > 2.10 (mitad placa) → NO aplica merma

### Precio material
- Precio s/IVA: USD 337.19/m2 (aprox al momento de emisión feb 2026)
- Precio c/IVA (×1.21): USD 408/m2
- Bruto: 3.46 × USD 408 = USD 1.412
- Descuento 5% (material importado, m2 > 6? No... → revisar)

> **Nota:** el descuento de USD 70 fue aplicado manualmente. m2 = 3.46 < 6 y Di Santo no está en architects.json. Posible descuento comercial discrecional de D'Angelo. El agente debe consultar si aplica descuento en casos donde no se cumplan las condiciones automáticas.

- DESC: USD 70
- **Total material neto: USD 1.342**

### Presentación en presupuesto (formato DUX)
```
PURASTONE BLANCO PALOMA   3,46   USD408   USD1412
3,24 X 0,63 * EN DOS TRAMOS
2,49 X 0,50 ALZ
0,76 X 0,23 ALZ
                                  DESC     USD70
                           TOTAL USD       USD1342
```

---

## Mano de obra

| Tarea | SKU | Cant. | Precio unit. | Total |
|---|---|---|---|---|
| Agujero y pegado de pileta | PEGADOPILETA | 1 | $59.767,00 | $59.767,00 |
| Agujero anafe | ANAFE | 1 | $39.538,00 | $39.538,00 |
| Agujero tomas | TOMAS | 1 | $7.172,00 | $7.172,00 |
| Flete + toma de medidas Rosario | ENVIOROS | 1 | $45.000,00 | $45.000,00 |
| Colocación | COLOCACION | 3.46 m2 | $59.767,00 | $206.793,82 |
| **TOTAL MO** | | | | **$358.270,82** |

> ⚠️ Colocación a $59.767/m2 — precio diferente al COLOCACION estándar ($55.170). Verificar si hubo actualización de precios entre presupuestos o si corresponde a SKU diferente.

---

## Total

```
PRESUPUESTO TOTAL: $358.271 mano de obra + USD1342 material
```

---

## Aprendizajes / reglas confirmadas

1. **Presentación del descuento** — línea separada con etiqueta *DESC* en columna precio unitario, monto en precio total. El TOTAL USD/ARS ya muestra el neto. Si no hay descuento, omitir la línea.
2. **Descuento discrecional** — D'Angelo puede aplicar descuento manualmente aunque no se cumplan las condiciones automáticas (m2 < 6, cliente no en architects.json). El agente no aplica descuento en esos casos, pero D'Angelo puede ajustarlo en DUX.
3. **Colocación** — precio puede variar según fecha. Siempre tomar de labor.json.
