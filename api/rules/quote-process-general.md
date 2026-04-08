# Proceso de Presupuesto — D'Angelo Marmoleria

## Flujo completo
```
1. Cliente pasa medidas aproximadas → presupuesto
2. Cliente paga 80% sena
3. Toma de medidas en obra (reales)
4. Diferencia > 0.5 m2 → actualizar presupuesto | <= 0.5 m2 → mantener
5. Cliente paga 20% restante con ajuste
```

---

## Paso 1 — Relevar medidas
Plano, boceto o medidas sueltas. Sin medidas no se puede presupuestar.

## Paso 2 — Seleccion de material

### Orden de evaluacion:
**1. Consultar stock.json Y preguntar al operador:**
a) Buscar material en stock.json: `largo_pieza >= largo_max_trabajo` + `m2_pieza >= m2_trabajo x 1.20`
b) Pieza valida → informar al operador
c) Sin pieza → preguntar al operador (archivo puede estar desactualizado)
d) NUNCA asumir sin stock sin preguntar
e) Stock confirmado → sin merma
f) Sin stock → merma normal (ver calculation-formulas.md)

**2. Sustitucion Purastone → Silestone** (si trabajo entra en media placa Silestone con desp < 1.0 m2)

**3. Merma normal** (ver calculation-formulas.md)

### Cliente NO especifico material:
Preguntar gama color, con/sin veta, interior/exterior. Ofrecer stock primero, luego 6-8 opciones (ver materials-guide.md). Hasta 4 opciones.

### Cliente especifico material:
Verificar stock → aptitud (materials-guide.md) → hasta 4 opciones juntas.

## Paso 3 — Datos del cliente
- Nombre y apellido (requerido) | Empresa (opcional) | Proyecto (opcional)
- Fecha: automatica

## Paso 4 — Preguntas segun tipo

### Todos los trabajos:
- Localidad → zona flete | ¿Colocacion? | ¿Pulido cantos? (del enunciado o preguntar) | ¿Flete? | ¿Zocalos?
- Plazo: del enunciado o default config.json (NO preguntar)

### Cocina/Isla (ademas):
- ¿Pileta? ¿propia o Johnson? | ¿Anafe? | ¿Frentin/regrueso?
- Isla: ¿patas laterales?

### Bano (ademas):
- ¿Frentin/regrueso? | ¿Zocalos? | Tipo pileta: integrada/apoyo

> Cocina + anafe → pileta SIEMPRE empotrada.

### Sinterizada 12mm:
Sugerir frentin. Formulas en calculation-formulas.md.

## Paso 5 — Checklist antes de generar

| Dato | Req |
|---|---|
| Nombre cliente | ✅ |
| Material(es) max 4 | ✅ |
| Medidas/plano | ✅ |
| Localidad | ✅ |
| Colocacion | ✅ |
| Flete | ✅ |
| Pileta (cocina/bano) | ✅ |
| Anafe (cocina/isla) | ✅ |
| Frentin/regrueso | ✅ |

## Paso 5b — Validacion previa al PDF
Presentar calculo completo: desglose m², total material, descuentos, cada MO, grand total. Esperar confirmacion.

## Paso 6 — Estructura
Un PDF por material. No mezclar.

```
BLOQUE MATERIAL: nombre + espesor, medidas, m2, precio, subtotal
BLOQUE MO: cada tarea con cant, precio, subtotal (ARS)
TOTALES: ARS (MO + material nacional + piletas) + USD (material importado)
PIE: condiciones estandar
```

## Paso 7 — Ajuste por toma de medidas
```
Diferencia > 0.5 m2 → actualizar | <= 0.5 m2 → mantener
```

## Reglas importantes
- Presupuesto con medidas aproximadas
- No toma de medidas sin sena
- No subir mesadas por escalera
- Precios incluyen IVA
- Sujeto a variacion de precio
- Toma medidas max 30 dias desde confirmacion
