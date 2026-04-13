# Interpretacion de Planos — D'Angelo Marmoleria

## Reglas criticas de lectura — SIEMPRE aplicar

### Zocalos en formas no rectangulares (trapezoides)
- **m² pieza** → dimension maxima (rectangulo envolvente)
- **ml zocalo** → dimension REAL de cada lado del plano
- Ej M09 TRANSCADEN: prof max=0.75m (para m²), zocalo izq=0.41m (real)

### Zocalos — leer cada mesada individualmente
- NO asumir simetria ni generalizar
- Rasterizar y revisar mesada por mesada antes de asignar lados
- **CADA lado que toca pared lleva zocalo** — verificar los 4 lados: fondo, izquierda, derecha, frente
- En mesadas en L: el tramo corto tiene zocalo lateral en su lado libre si toca pared
- Ejemplo cocina en L: tramo principal 1.72×0.75 + tramo corto 0.60×1.55 → zocalos: fondo 1.55ml, lateral izq tramo corto 0.60ml, fondo tramo principal 1.72ml (o inferior 1.74ml si hay cota), **lateral derecho tramo principal 0.75ml**
- Si hay duda sobre si un lado toca pared: incluir el zocalo (mejor sobrar que faltar)

### 2+ cotas en mismo eje → usar la mas larga
La menor es detalle interno.

### Cotas internas → ignorar para m²
c/p, distancias entre piletas, huecos internos → ignorar. Usar medida exterior total.

### Formas no rectangulares
Rectangulo envolvente: ancho max x largo max.

### Profundidad
SIEMPRE buscarla en el plano. Si no figura → decirlo al operador.

### Convenciones de texto
- **"INGLETE"** → CORTE45 en MO
- **"Bordes/Cantos pulidos"** → PUL en MO (explicito del plano)
- **"Frente revestido" en isla** → pata frontal, NO alzada → no TOMAS automatico
- **"Tomas (X)"** → X unidades TOMAS en MO

### Posicion de cotas
- Cota **ARRIBA** del borde → **ZOCALO** (sube por pared)
- Cota **ABAJO** del borde → **FRENTIN/FALDON** (cuelga abajo)
- Posicion determina que es — regla absoluta

---

## Busqueda web
Antes de preguntar al operador sobre producto/pileta/modelo → buscar en web primero.

---

## Renderizado individual — PRIMER PASO OBLIGATORIO

Sin excepcion, antes de las 4 pasadas:
1. Rasterizar a 300 DPI
2. Crop individual por cada mesada
3. Leer cada imagen individual antes de asignar medidas

**Nunca confiar en vista general del plano completo.**

## Protocolo de lectura — 4 pasadas obligatorias

**Pasada 1 — Inventario:** contar y nombrar piezas. Sin medir.

**Pasada 2 — Paredes vs libres:** cada pieza: lados contra pared (hatching) vs libres. Sin medidas.

**Pasada 3 — Medidas:** leer cada cota. Si no esta → decirlo, no asumir.

**Pasada 4 — Verificacion (⛔ AUTO-REVISION OBLIGATORIA):**

4a. Releer cada cota del plano (sin mirar notas). Comparar. Plano manda.
4b. Contar piezas plano vs inventario. Contar cotas vs medidas. Deben coincidir.
4c. Coherencia dimensional: largo x prof = m². Si no da → error.
4d. Sentido comun: ¿mesada 1m en plano chico? ¿zocalo 3m en mesada 0.60m?

**Recien despues de auto-revision → calcular m².**

---

## Vistas a analizar
- **Planta:** forma, lados libres vs pared
- **Frontal:** ancho y alto frentin
- **Lateral:** profundidad, frentin lateral
- **Corte:** espesores, frentines colgantes

---

## Deteccion de frentin

### Indicadores
- Cota vertical en borde frontal/lateral (100mm, 120mm, 150mm, 180mm)
- En corte: rectangulo colgante bajo mesada
- Espesor visible > espesor material
- "frentin" o "regrueso" escrito

### Pared = sin frentin
Hatching/rayado = pared → NO canto expuesto → NO frentin. Lados sin tachar = evaluar.

### Frentin/Regrueso — TODO lo que se ve
- Frentin en TODOS los lados visibles (frente + costados libres)
- Lados con pared → NO
- Medidas costados del PLANO, NUNCA asumir 0.60m
- MO: ver calculation-formulas.md

---

## Deteccion de pileta

| Tipo | Simbolo | SKU |
|---|---|---|
| Apoyo | Circulo simple sin lineas de corte | AGUJEROAPOYO |
| Empotrada | Rectangulo/circulo con lineas de corte | PEGADOPILETA |

- "bacha de loza sobre mesada" con lineas de corte → empotrada → PEGADOPILETA
- Duda → preguntar
- Griferia NUNCA se cobra aparte — incluida en SKU
- "DESAGUE" sin modelo → apoyo (AGUJEROAPOYO) | Con modelo → empotrada (PEGADOPILETA)
- 3 puntitos junto a ovalo → empotrada (PEGADOPILETA)

---

## Deteccion de anafe/tomas
Simbolo hornallas/tomas en planta → ANAFE/TOMAS. Anotar cantidad.

---

## Anotaciones en planos

| Anotacion | Significado | Presupuesto |
|---|---|---|
| c/p | Centro pileta | Ignorar |
| F de X cm | Frentin X cm | Todos los lados visibles. MO: ver calculation-formulas.md |
| Z de X cm | Zocalo X cm alto | En lados marcados |
| 89 Z / 118 Z | Largo zocalo cm | Usar esa medida |

> Z → lleva zocalo. Sin excepciones.
> Alto zocalo: si no hay cota → **5cm (0.05m)** por defecto. NUNCA preguntar.

### Profundidad de mesada
- Sin cota → 0.60m estandar
- Cota no obvia → evaluar si es tramo adicional o detalle estructural

---

## Lectura de medidas

- Cotas en mm salvo aclaracion → convertir a metros
- Verificar parciales + totales sumen
- Ambiguedad → preguntar

### Dos cotas misma altura
= dos tramos separados (piezas independientes contiguas). NUNCA interpretar como L salvo quiebre 90° explicito con cotas en 2 ejes.

### Mesadas con ampliacion
Usar medida final total, no original ni incremento.

### Recorte/material del cliente
Ignorar nota. Presupuestar pieza completa.

---

## Planos de edificio

### Mesadas multiples
- Dos mesadas con espacio = 2 piezas separadas
- Detalles columna/estructurales → ignorar
- Leer largo x ancho de mesada, ignorar cotas de otros elementos

### Rectangulo interior
= agujero pileta empotrada → PEGADOPILETA. No preguntar.

### Cantidad mesadas
Prioridad: 1) nombre archivo (`cantidad_3`) 2) numero en plano 3) enunciado 4) preguntar.
Multiplicar m2 x cantidad. Numero suelto en PDF puede ser ruido — verificar contra nombre archivo.

### Profundidad edificio
Sin cota explicita → 0.60m. Dos cotas horizontales = 2 largos de tramo, NO profundidad.

### Agrupacion piezas iguales
Mismas medidas → agrupar: `LARGO X PROF X CANT UNID`. Diferencia 1cm → lineas separadas.

### Dos cotas profundidad en mismo largo
= dos tramos separados con diferente profundidad. (ref: quote-024)

## Checklist antes de presupuestar
- ¿Cuantas piezas? (mesadas, alzas, zocalos, estantes)
- ¿L o U? → tramos separados
- ¿Frentin? ¿Solo frente o lateral?
- ¿Tipo pileta? ¿Cuantas?
- ¿Anafe? ¿Tomas?
- ¿Localidad? → flete
- ¿Colocacion?
- ¿Cotas oblicuas? → ignorar
- ¿"FRENTE"? → zocalo frontal
- ¿Piezas sueltas cerca de sector? → incluir en ese sector

### Simbolos en plano — guia rapida
| Simbolo | Significado |
|---------|-----------|
| Rayado/hatching | Pared → no frentin |
| c/p / Eje bacha | Centro pileta → ignorar |
| 3 puntitos junto a ovalo | Pileta empotrada (PEGADOPILETA) |
| "INGLETE" | CORTE45 |
| "Bordes pulidos" | PUL |
| "DESAGUE" sin modelo | Apoyo → AGUJEROAPOYO |
| "FRENTE X cm" | Zocalo frontal (material) |
| Cota oblicua | Ignorar para m² |
