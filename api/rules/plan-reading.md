# Interpretacion de Planos — D'Angelo Marmoleria

## Reglas criticas de lectura — SIEMPRE aplicar

### Zocalos en formas no rectangulares (trapezoides)
- **m² pieza** → dimension maxima (rectangulo envolvente)
- **ml zocalo** → dimension REAL de cada lado del plano
- Ej M09 TRANSCADEN: prof max=0.75m (para m²), zocalo izq=0.41m (real)

### Zocalos — leer cada mesada individualmente
- NO asumir simetria ni generalizar
- Rasterizar y revisar mesada por mesada antes de asignar lados
- **CADA lado que toca pared lleva zocalo** — verificar cada lado individualmente
- En mesadas en L: el lado donde los dos tramos se unen **NUNCA lleva zocalo** (es la union, no toca pared)
- ⛔ Ejemplo cocina en L: tramo 1 (1.72×0.75) + tramo 2 (0.60×1.55):
  - Zocalo fondo tramo 1 (inferior): **1.74ml** (cota del plano)
  - Zocalo fondo tramo 2: **1.55ml** (va por la pared del fondo del tramo 2)
  - Zocalo lateral derecho: **0.75ml** (profundidad del tramo 1, toca pared)
  - **NO hay zocalo de 0.60ml** — ese es el lado donde los tramos se unen (no toca pared)
  - Total: 3 zocalos, NO 4
- ⛔ **Nombrar zócalos por su ubicación real:** "fondo tramo 1", "fondo tramo 2", "lateral derecho". NUNCA "lateral izquierdo" si en realidad es el fondo de otro tramo.
- Si hay duda sobre si un lado toca pared: mirar el plano — si hay pared/hatching → zocalo. Si conecta con otro tramo → NO zocalo.

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

### ⛔ Modelo de pileta — NUNCA inventar
- **SIEMPRE** buscar el modelo exacto en `sinks.json` con `catalog_lookup("sinks", sku)`
- Si el plano/enunciado dice un nombre que no matchea exacto → hacer **fuzzy match**:
  - Extraer palabras clave del nombre (marca, serie, numero)
  - Ej: "LUXOR COMPACT SI71" → buscar "LUXOR" + "171" → PILETA JOHNSON LUXOR S171
  - Ej: "Johnson Simple SI37" → buscar "Q37" → PILETA JOHNSON QUADRA Q37
  - Los numeros de modelo suelen coincidir con permutaciones: SI71→S171, Q71→Q71A
- Si no hay match claro → **PREGUNTAR al operador** con las opciones mas parecidas de sinks.json
- **NUNCA** usar un nombre de pileta que no exista en sinks.json en el presupuesto final

---

## Deteccion de anafe/tomas
Simbolo hornallas/tomas en planta → ANAFE/TOMAS. Anotar cantidad.

**Brief solo-plano (sin lista MO explícita del operador):** si el plano muestra
anafe/hornallas empotradas → MO obligatoria `anafe=True` + `anafe_qty=N`. Si
muestra pileta empotrada → `pileta="empotrada_cliente"` (o `empotrada_johnson`
si es Johnson). No olvidar ninguno de los dos aunque el brief no los repita en
texto — el plano ES el brief.

⚠️ Esto aplica **solo cuando no hay MO exhaustiva listada** (ver CONTEXT.md
§"MANO DE OBRA LISTADA ES EXHAUSTIVA"). Si el operador listó la MO ítem por
ítem, esa lista manda y Valentina NO agrega anafe/pileta que no figuren ahí.

---

## Anotaciones en planos

| Anotacion | Significado | Presupuesto |
|---|---|---|
| c/p | Centro pileta | Ignorar |
| F de X cm | Frentin X cm | Todos los lados visibles. MO: ver calculation-formulas.md |
| Z de X cm | Zocalo X cm alto | En lados marcados |
| 89 Z / 118 Z | Largo zocalo cm | Usar esa medida |

> Z → lleva zocalo. Sin excepciones.
>
> **Alto zócalo — prioridad de lectura (usar el primer valor disponible):**
> 1. Leyenda explícita tipo `ZÓCALOS H=10cm`, `Z=10`, `H zócalo = 10 cm`.
> 2. Cota suelta en el **borde lateral** de la planta (vertical), valor
>    entre 0.05 y 0.50 m, que no esté etiquetada como "prof" ni como otra
>    cosa y no coincida con la profundidad de mesada.
> 3. Leyenda/rotulado del plano (bloque de notas general).
> 4. Default = **5 cm (0.05 m)** solo si no hay NINGÚN valor leíble.
>
> ⛔ Si en el plano hay cotas verticales en los bordes (ej: `0.10 m`
> arriba y/o abajo del rectángulo de mesada) y NO coinciden con la prof,
> interpretarlas como **alto de zócalo** — no como segundas profundidades.

### Profundidad de mesada
- Sin cota → 0.60m estandar
- Cota no obvia → evaluar si es tramo adicional o detalle estructural

---

## Lectura de medidas

- Cotas en mm salvo aclaracion → convertir a metros
- Verificar parciales + totales sumen
- Ambiguedad → preguntar

### ⛔ Múltiples piezas en planilla — regla de independencia
Cuando la planilla tiene 2+ piezas con medidas separadas y NO hay indicación explícita de esquina, inglete o forma (L, U):
- Tratar como piezas **INDEPENDIENTES**, no como forma compuesta
- **NO asumir L ni U**
- **NO agregar corte 45 ni inglete**
- Cada pieza tiene sus propios zócalos (según lo que diga el plano para esa pieza)

Solo asumir forma compuesta si:
- El operador lo dice explícitamente ("en L", "en U", "con esquina")
- El plano muestra claramente una esquina/quiebre 90° entre las piezas
- Hay una nota de "CORTE 45" o "INGLETE" en la planilla

### Dos cotas misma altura
= dos tramos separados (piezas independientes contiguas). NUNCA interpretar como L salvo quiebre 90° explícito con cotas en 2 ejes.

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
