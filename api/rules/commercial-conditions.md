# Condiciones Comerciales — D'Angelo Marmolería

## Formas de pago

- Contado / transferencia / débito
- Crédito (consultar planes)
- Cheques: 15 días para materiales importados, 30 días para nacionales

## Seña y saldo

- **80% seña** al confirmar el trabajo
- **20% restante** contra entrega, ajustado por medidas reales si corresponde

## Cotización dólar

- Materiales importados: se cotizan en USD, se pagan en pesos al **dólar venta BNA del día de confirmación**
- El presupuesto no convierte USD a ARS — se muestran separados

## Fecha de entrega

- Plazo estándar: **40 días desde la toma de medidas**
- Este valor es **parametrizable** — puede cambiar según demanda operativa
- Excepciones por tipo de obra:
  - Obras pequeñas (< 1 m2, solías, piezas simples): 10-15 días
  - Obras medianas estándar: 30 días
  - Obras grandes (> 15 m2, múltiples unidades): 60/70 días
- La fecha de entrega la define siempre D'Angelo — el agente usa el plazo estándar
  salvo que D'Angelo indique un valor diferente

## Toma de medidas

- No se realiza sin seña confirmada y pagada
- No puede superar los **30 días desde la confirmación**
- Pasado ese plazo, el 20% restante se actualiza según el índice de la construcción

## Ajuste por medidas reales

```
Diferencia = |m2 reales - m2 presupuestados|

SI diferencia > 0.5 m2 → actualizar presupuesto y DUX
SI diferencia ≤ 0.5 m2 → mantener presupuesto original
```

## Descuentos

Los descuentos son a criterio exclusivo de D'Angelo. No hay porcentaje fijo.

**Regla de descuento:**
- Material importado (USD): **5%** (parametrizable en `config.json`)
- Material nacional (ARS): **8%** (parametrizable en `config.json`)
- **Solo aplica sobre el material — nunca sobre mano de obra**
- Se aplica automáticamente cuando:
  - Obra mayor a **6 m2** (parametrizable)
  - Cliente arquitecto con relación comercial frecuente (ver `architects.json`)

```
# Material importado
descuento_usd = total_material_usd × 0.05
total_material_neto_usd = total_material_usd - descuento_usd

# Material nacional
descuento_ars = total_material_ars × 0.08
total_material_neto_ars = total_material_ars - descuento_ars
```

El agente aplica el descuento automáticamente cuando se cumple alguna condición.
La mano de obra nunca recibe descuento.

**Presentación del descuento en el presupuesto:**

El descuento se muestra como una línea separada dentro del bloque de material, inmediatamente después de las sub-filas de piezas, siguiendo el formato del sistema DUX:

```
NOMBRE MATERIAL     3,46    USD408    USD1412
3,24 X 0,63 * EN DOS TRAMOS
2,49 X 0,50 ALZ
0,76 X 0,23 ALZ
                            DESC      USD70
                    TOTAL USD         USD1342
```

- La columna "Precio unitario" muestra la etiqueta *DESC* (en itálica)
- La columna "Precio total" muestra el monto descontado (positivo, no negativo)
- La fila "TOTAL USD/ARS" muestra el neto ya descontado
- Si NO hay descuento → omitir la línea DESC completamente

## Flete compartido entre presupuestos

- Cuando hay **varios presupuestos para la misma obra** (ej: cocina en Purastone + baños en Silestone), el flete va en **uno solo** de los PDFs.
- El operador indica en cuál incluirlo.
- No cobrar flete duplicado.
- Ref: quote-029.

## Precio especial fuera de catálogo

- El operador puede indicar un precio especial no estándar (ej: "precio ÷1.15").
- El precio especial **NO se acumula** con descuento de arquitecta ni otros descuentos.
- Solo aplicar **UN mecanismo** de descuento/precio especial por presupuesto.
- Ref: quote-029.

## Restricciones operativas

- No se suben mesadas por escalera
- No se suben mesadas que no entren por ascensor (edificios) — incluir nota en PDF: "NO SE SUBEN MESADAS QUE NO ENTREN POR ASCENSOR"
- Los precios incluyen IVA

## Notas estándar del presupuesto

- Presupuesto sujeto a variación de precio
- Materiales importados según cotización dólar venta Banco Nación al momento de la confirmación
- Presupuesto definitivo según medidas tomadas en obra
- Por ser el granito y mármol producto de la naturaleza, las tonalidades, vetas y manchas pueden diferir de las muestras exhibidas
