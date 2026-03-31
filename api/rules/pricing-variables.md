# Variables de Precio — D'Angelo Marmolería

## Regla general de IVA

El IVA (21%) se aplica al generar el presupuesto, no al facturar.
La factura se emite sobre un presupuesto que ya tiene el IVA incluido.

---

## Materiales Importados (USD)

- Se almacenan en el catálogo **sin IVA** en USD.
- Al generar el presupuesto se agrega el 21% de IVA sobre el precio USD.
- El presupuesto muestra el precio final **en USD con IVA incluido**.
- El total de materiales importados se presenta en USD, separado de los ARS.
- La conversión a ARS **no se realiza en el presupuesto**.
- Al confirmarse el trabajo y pagarse la seña, se convierte a ARS usando
  el tipo de cambio **dólar venta Banco Nación (BNA) del día de la confirmación**.

**Fórmula:**
```
Precio catálogo USD (sin IVA)
    × 1.21
    = Precio presupuesto USD (con IVA)

Precio presupuesto USD (con IVA)
    × m2
    = Total USD que figura en el presupuesto

Total USD
    × tipo de cambio dólar venta BNA del día de confirmación
    = Total ARS que se carga en DUX y se factura
```

---

## Materiales Nacionales (ARS)

- Se almacenan en el catálogo **sin IVA** en ARS.
- Al generar el presupuesto se agrega el 21% de IVA sobre el precio ARS.
- El presupuesto muestra el precio final **en ARS con IVA incluido**.
- Se aclara en el presupuesto que el precio incluye IVA.

**Fórmula:**
```
Precio catálogo ARS (sin IVA)
    × 1.21
    = Precio presupuesto ARS (con IVA)

Precio presupuesto ARS (con IVA)
    × m2
    = Total ARS que figura en el presupuesto
```

---

## Mano de Obra (ARS)

- Los precios en `labor.json` están **sin IVA**.
- Al generar el presupuesto aplicar **× 1.21** para obtener el precio con IVA.
- Siempre en ARS.

**Fórmula:**
```
Precio labor.json (sin IVA)
    × 1.21
    = Precio presupuesto ARS (con IVA)
```

> Lo mismo aplica para `delivery-zones.json` — precios sin IVA, multiplicar × 1.21.
> Lo mismo aplica para `sinks.json` — precios sin IVA, multiplicar × 1.21.

---

## Presentación del total en el presupuesto

Cuando hay materiales importados y nacionales en el mismo presupuesto,
los totales se presentan por separado:

```
Total ARS = mano de obra + materiales nacionales (con IVA)
Total USD = materiales importados (con IVA en USD)

PRESUPUESTO TOTAL: $XXX.XXX mano de obra + USDXXX material
```

Si hay solo materiales nacionales:
```
PRESUPUESTO TOTAL: $XXX.XXX (IVA incluido)
```

---

## Tipo de cambio

- Se usa siempre el **dólar venta Banco Nación (BNA)** oficial.
- El tipo de cambio no se fija en el presupuesto — se aplica al momento
  de la confirmación y pago de la seña.
- El presupuesto aclara explícitamente que los materiales importados
  se pagan en pesos según la cotización del día.

---

## Condición de variación de precio

- Todo presupuesto está sujeto a variación de precio.
- Los materiales importados se actualizan según la cotización dólar venta
  BNA al momento de la confirmación.
- Si la toma de medidas supera los 30 días desde la confirmación,
  el 20% restante se actualiza según el índice de la construcción.
