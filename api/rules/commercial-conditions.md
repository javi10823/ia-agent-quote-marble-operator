# Condiciones Comerciales — D'Angelo Marmoleria

## Formas de pago
Contado / transferencia / debito. Credito (consultar). Cheques: 15d importados, 30d nacionales.

## Sena y saldo
**80% sena** al confirmar | **20% restante** contra entrega (ajustado por medidas reales si corresponde)

## Cotizacion dolar
Importados en USD, se pagan en pesos al **dolar venta BNA del dia de confirmacion**. No se convierte en presupuesto.

## Fecha de entrega
Estandar: **40 dias desde toma de medidas** (parametrizable). Excepciones: < 1m² → 10-15d | estandar → 30d | >15m² → 60-70d. D'Angelo define el plazo.

## Toma de medidas
Sin sena no se hace. Max **30 dias desde confirmacion**. Pasado plazo: 20% restante se actualiza segun indice construccion.

## Ajuste por medidas reales
```
Dif > 0.5 m2 → actualizar presupuesto + DUX
Dif <= 0.5 m2 → mantener original
```

## Descuentos
- Importado USD: **5%** | Nacional ARS: **8%** (parametrizable config.json)
- Solo material, nunca MO | Aplica: >6m² o arquitecta (architects.json)
- Presentacion: linea separada en bloque material, "DESC" en col precio, monto en col total, TOTAL muestra neto

## Flete compartido
Varios presupuestos misma obra → flete en uno solo (operador indica cual). (ref: quote-029)

## Precio especial
Operador puede indicar precio no estandar. NO acumular con otros descuentos. (ref: quote-029)

## Restricciones
- No subir mesadas por escalera / que no entren en ascensor (nota en PDF)
- Precios incluyen IVA

## Notas estandar del presupuesto
- Sujeto a variacion de precio
- Importados segun dolar venta BNA al momento de confirmacion
- Definitivo segun medidas en obra
- Granito/marmol: tonalidades y vetas pueden diferir de muestras
