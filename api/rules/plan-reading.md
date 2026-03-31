# Interpretación de Planos — D'Angelo Marmolería

Guía para analizar planos arquitectónicos y extraer correctamente todas las medidas y elementos relevantes para el presupuesto.

---

## Reglas críticas de lectura — SIEMPRE aplicar

### Zócalos en formas no rectangulares (trapezoides)
- El **m² de la pieza** → usar dimensión máxima (rectángulo envolvente)
- Los **ml de zócalo** → usar la dimensión REAL de cada lado tal como aparece en el plano
- Ejemplo M09 TRANSCADEN: profundidad max = 0.75m (para m²), pero zócalo lado izq = 0.41m (real del plano)

### Zócalos — leer cada mesada individualmente del plano
- NO asumir que si hay zócalo en un lado también va en el otro
- NO generalizar: cada mesada puede tener diferente combinación de lados
- SIEMPRE rasterizar y revisar mesada por mesada antes de asignar lados
- Errores frecuentes confirmados en TRANSCADEN:
  - M04: solo trasero+derecho — NO izquierdo aunque parezca simétrica
  - M05: trasero+izquierdo — NO solo izquierdo
  - M09: zócalo izq = 0.41m (real) NO 0.75m (max de la pieza)




- Si en un mismo eje aparecen 2 o más cotas → **usar siempre la más larga**
- La cota menor es un detalle interno (recorte, columna, voladizo) — nunca define el tamaño de la pieza

### Cotas internas — ignorar para m²
- Cotas de centros de pileta (c/p), distancias entre piletas, huecos internos → **ignorar completamente**
- Usar siempre la **medida exterior total** de la mesada
- Ejemplo: mesada con 2 piletas mostrando 64 + 90 + 189 = 343cm → cotizar 343cm, no las parciales

### Formas no rectangulares (trapezoides, L, etc.)
- Cotizar siempre el **rectángulo envolvente**: ancho máximo × largo máximo
- Ejemplo trapecio: lados de 41cm y 75cm de profundidad → usar **75cm**
- Los recortes y variaciones de forma son desperdicio incluido en la pieza


- SIEMPRE buscarla en el plano antes de asumir 0.60m
- Si no figura → decirlo al operador, no asumir

### Convenciones de texto en plano
- **"INGLETE"** → unión a 45° → cobrar CORTE45 en MO
- **"Bordes pulidos" / "Cantos pulidos"** → cobrar PUL en MO — es explícito del plano, no hace falta que lo diga el operador
- **"Frente revestido"** en isla → es la **pata frontal**, NO una alzada → no aplica TOMAS automático
- **"Tomas (X)"** → cobrar X unidades de TOMAS en MO


- Cota **ARRIBA** del borde de la mesada → **ZÓCALO** (sube por la pared)
- Cota **ABAJO** del borde de la mesada → **FRENTIN / FALDÓN** (cuelga hacia abajo)
- Esta regla es absoluta — la posición de la cota en el dibujo determina qué es

---

## Regla de búsqueda web — aplicar siempre

Antes de preguntar al operador sobre cualquier producto, pileta, modelo o característica técnica que no esté en los catálogos:
1. **Buscar en web primero** — tipo de pileta, modelo, características, etc.
2. Solo preguntar al operador si la búsqueda no resuelve la duda
3. Nunca hacer perder tiempo al operador con preguntas que Google responde en segundos

Ejemplos:
- ¿La Z52/18 es empotrada o de apoyo? → buscar antes de preguntar
- ¿El modelo X existe en empotrada? → buscar antes de preguntar



## Renderizado individual — PRIMER PASO OBLIGATORIO ANTES DE CUALQUIER CÁLCULO

**Sin excepción. Sin importar cuántas mesadas tenga el plano. Antes de las 4 pasadas.**

Más tiempo al principio = cero regeneraciones. Un error de zócalo o medida cuesta mucho más que 2-3 minutos de renderizado.

```bash
# 1. Rasterizar a 300 DPI
pdftoppm -jpeg -r 300 -f 1 -l 1 plano.pdf /tmp/plano

# 2. Crop individual por cada mesada
python3 -c "
from PIL import Image
img = Image.open('/tmp/plano-1.jpg')
# Crop de cada mesada por separado y guardar
img.crop((x1,y1,x2,y2)).save('/tmp/m01.jpg')
img.crop((x3,y3,x4,y4)).save('/tmp/m02.jpg')
# etc.
"

# 3. Leer cada imagen individual antes de asignar medidas o zócalos
```

**Nunca confiar en la vista general del plano completo.**

## Protocolo de lectura — 4 pasadas obligatorias

Ante cualquier plano, ejecutar SIEMPRE estas 4 pasadas en orden. **No calcular hasta completar la pasada 4.**

**Pasada 1 — Inventario**
Solo contar y nombrar las piezas presentes. No medir, no calcular. ¿Cuántas mesadas? ¿Hay isla, alzada, zócalos?

**Pasada 2 — Paredes vs. lados libres**
Para cada pieza, identificar qué lados van contra pared (hatching/rayado) y cuáles están libres. Sin medidas todavía. Esto determina dónde va frentin/regrueso.

**Pasada 3 — Medidas**
Leer cada cota explícita del plano para cada lado de cada pieza. Si una medida no está en el plano → decirlo al operador, no asumir ningún valor.

**Pasada 4 — Verificación**
Cruzar todo: ¿las cotas suman correctamente? ¿Hay elementos que no son mesada (columnas, ventanas, proyecciones)? ¿Hay vistas auxiliares que agregan o contradicen lo de la planta? ¿Algún lado marcado como libre que en realidad va contra algo?

**Recién después de las 4 pasadas → calcular m².**

---

## Vistas a analizar

Siempre revisar **todas** las vistas disponibles antes de extraer medidas:

- **Vista planta**: muestra la forma en planta (L, U, recta), lados libres vs. contra pared
- **Vista frontal**: muestra ancho y alto del frentin
- **Vista lateral**: muestra profundidad y frentin lateral si existe
- **Corte**: muestra espesores, frentines colgantes, detalles constructivos

---

## Detección de frentin

### Indicadores en el plano
- Cota vertical en borde frontal o lateral de la mesada (ej: 100mm, 120mm, 150mm, 180mm)
- En corte: rectángulo colgante debajo de la mesada
- Espesor visible mayor al del material
- Palabra "frentin" o "regrueso" escrita explícitamente

### Símbolo de pared en planos
- Líneas tachadas (hatching/rayado) en un lado de la pieza = **pared** → ese lado NO tiene canto expuesto → NO lleva frentin
- Lados sin tachar = cantos libres → evaluar si llevan frentin según contexto

### Frentin frontal
Siempre que haya una cota vertical en el frente → calcular frentin frente.

### Frentin / Regrueso — regla crítica: TODO lo que se ve
- El frentin/regrueso va en **todos los lados visibles** — frente + cada costado expuesto donde no hay pared
- Los lados con pared (hatching/rayado) → NO llevan frentin
- Las medidas de los costados se leen **siempre del plano** — NUNCA asumir 0.60m para los costados
- Si la mesada va **entre paredes** en todos sus lados → frentin **solo en el frente**
- Si hay **un lado libre** → frentin en frente + ese costado
- Si hay **dos lados libres** (ej: isla) → frentin en frente + ambos costados
- **Cada costado tiene su propia medida en el plano** — leerla explícitamente

### Mano de obra de regrueso/frentin — CRÍTICO
- **Regrueso** (granito, mármol, Silestone, Purastone): SKU `REGRUESO` × ml total — **NUNCA FALDON ni CORTE45**
- **Faldón** (Dekton, Neolith, Puraprima, Laminatto): SKU `FALDONDEKTON/NEOLITH` × ml + `CORTE45DEKTON/NEOLITH` × ml×2
- No mezclar estos SKUs entre tipos de material ni entre regrueso y faldón

### Ejemplos confirmados
| Caso | Situación | Frentin |
|---|---|---|
| Vanitoy 1 (plano Furigo, Sole-Mosqui) | Entre paredes | Solo frente 1.503ml × 180mm |
| Vanitoy 2 (plano Furigo, Sole-Mosqui) | Lado libre derecho | Frente 1.360ml × 100mm + lateral 0.400ml × 100mm |

---

## Detección de pileta

- Identificar símbolo de pileta en vista planta
- Determinar tipo observando el símbolo y la descripción:
  - **Pileta de apoyo** → cuenco que descansa SOBRE la mesada, sin encastrar. Símbolo: círculo simple sin líneas de corte en la mesada. SKU: `AGUJEROAPOYO`
  - **Pileta empotrada** → encastrada dentro de la mesada (se corta la piedra para alojarla). Símbolo: rectángulo o círculo con líneas de corte visibles en planta. SKU: `PEGADOPILETA`
- **Clave de interpretación:** la descripción "bacha de loza sobre mesada" puede referirse a una pileta de apoyo visualmente, pero si el plano muestra líneas de corte → es empotrada → `PEGADOPILETA`
- Ante duda entre apoyo y empotrada → preguntar al cliente
- Anotar modelo si está especificado (ej: Johnson Ø300, Ferrum Tori K060 40×34)
- Anotar grifería si está especificada (ej: FV Coty)
- **El agujero de grifería NUNCA se cobra aparte** — está incluido tanto en `PEGADOPILETA` como en `AGUJEROAPOYO`. Nunca preguntar al cliente, nunca agregar como ítem separado.

### Ejemplos confirmados de piletas
| Caso | Descripción en plano | Tipo | SKU |
|---|---|---|---|
| Vanitoy 1 y 2 (Furigo, Sole-Mosqui) | Ferrum Tori Cuenco K060 — sobre mesada | Apoyo | AGUJEROAPOYO |
| Cocina p02 (Alma Estudio) | Bacha Redonda Ø300 Lisa Johnson | Empotrada | PEGADOPILETA |
| Cocina p03 (Alma Estudio) | Bacha redonda 32cm diámetro | Empotrada | PEGADOPILETA |
| Antebaño p01 (Alma Estudio) | Bacha redonda de loza sobre mesada | Apoyo | AGUJEROAPOYO |

---

## Detección de anafe / tomas

- Símbolo de hornallas o tomas en vista planta → SKU: ANAFE / TOMAS
- Anotar cantidad de tomas si hay más de una

---

## Anotaciones en planos — convenciones

| Anotación | Significado | Para presupuesto |
|---|---|---|
| **c/p** | centro de pileta | Ignorar — es referencia para obra |
| **F de X cm** | frentin/regrueso de X cm | En TODOS los lados visibles (frente + costados libres). Material: ml × alto. MO: REGRUESO (granito/mármol/Silestone/Purastone) o FALDON+CORTE45 (Dekton/Neolith/sinterizados) |
| **Z de X cm** | zócalo de X cm de alto | En los lados donde aparece la Z |
| **89 Z** / **118 Z** | largo del zócalo en cm | Usar esa medida para calcular ml de zócalo |

> Si la F aparece solo en el frente → frentin únicamente en el frente. No asumir laterales.
> **Regla absoluta: donde dice Z → lleva zócalo.** Sin excepciones, aunque parezca que va contra pared.
> Si la Z aparece en varios lados → sumar todos los ml de zócalo de cada lado.

### Profundidad de mesada
- Si no hay cota de profundidad en el plano → usar **0.60m** como estándar.
- Si el 0.60 está explícito en el plano → usarlo.
- Si aparece una cota que no es ni el largo ni la profundidad obvia de la mesada → evaluar si es un tramo adicional (misma altura = tramo separado) o un detalle estructural (columna, voladizo) → ignorar solo en ese último caso.

---

## Lectura de medidas

- Todas las cotas en plano suelen estar en **milímetros** salvo aclaración
- Convertir siempre a metros para el cálculo (ej: 1503mm → 1.503m)
- Si hay cotas parciales y totales, verificar que sumen correctamente
- Ante ambigüedad, preguntar al cliente antes de presupuestar

### Dos cotas a la misma altura
Si hay dos cotas a la misma altura en el plano → son **dos tramos de mesada separados** (piezas independientes contiguas).
**NUNCA interpretar dos tramos contiguos como una mesada en L.** Una mesada en L solo existe si el plano muestra explícitamente un quiebre de 90° con cotas en dos ejes (horizontal y vertical). Si las cotas están todas sobre el mismo eje → son piezas rectas separadas.
Nunca ignorar una cota como detalle estructural salvo que claramente corresponda a una columna u otro elemento que esté fuera de la mesada.

### Mesadas con ampliación
- Si el plano indica que una mesada existente se amplía, usar la **medida final total** (no la original ni el incremento por separado)
- Ejemplo: mesada de 1.14m que se amplía a 1.55m → presupuestar 1.55m

### Recorte o material aportado por el cliente
- Si el plano indica "se utiliza recorte/material que posee el cliente" → **ignorar esa nota para el cálculo de m2**
- Siempre presupuestar la pieza completa según sus medidas totales
- El cliente puede decidir no usar su material → se factura la pieza entera de todas formas
- Nunca descontar m2 por material que aporte el cliente

---

---

## Planos de edificio — convenciones especiales

### Mesadas múltiples en un plano
- Dos mesadas al lado de la otra con espacio en el medio (cocina/anafe) = **dos piezas separadas**, no una sola mesada
- Un tramo largo + un tramo corto adicional = dos piezas separadas (el largo lleva la pileta)
- Calcular y listar cada pieza por separado
- **Detalles de columna u otros elementos estructurales** en el plano → ignorar completamente para el presupuesto
- Leer siempre **largo × ancho** de la mesada. Si hay cotas que no corresponden a la mesada (columnas, voladizos, detalles constructivos) → ignorarlas

### Rectángulo dibujado en plano
- Rectángulo interior en la mesada = **agujero de pileta empotrada**
- 1 rectángulo = 1 pileta → SKU `PEGADOPILETA`
- No preguntar si lleva pileta si el rectángulo está dibujado

### Cantidad de mesadas en edificios
- **Prioridad de lectura:**
  1. Nombre del archivo: `cantidad_3` = 3 unidades (caso más común)
  2. Dentro del plano: número suelto que no corresponde a ninguna cota de medida
  3. En el enunciado del pedido: el cliente lo indica directamente
  4. Si no aparece en ninguno → preguntar antes de presupuestar
- Multiplicar m2 de 1 unidad × cantidad para el total
- **CRÍTICO:** Un número suelto dentro del PDF puede ser ruido del renderizado — verificar siempre contra el nombre del archivo primero

### Profundidad en planos de edificio
- Si un plano no tiene cota de profundidad explícita → usar **0.60m** sin excepción
- **CRÍTICO:** Si en el plano aparecen dos cotas horizontales (ej: `1.47` y `0.36`), son **largo tramo 1** y **largo tramo 2** — NUNCA interpretar la segunda cota como profundidad
- La profundidad siempre va perpendicular al largo. Si no está explícita → 0.60m

### Agrupación de piezas iguales para mostrar en presupuesto
- Piezas con las mismas medidas provenientes de distintos archivos se **agrupan en una sola línea** con la cantidad total
- Ejemplo: P1_2_3_01 ×3 y P1_2_3_02 ×3 ambas con tramo 1.50×0.60 → mostrar como `1.50 X 0.60 X 6 UNID`
- Si las medidas difieren (aunque sea 1cm) → líneas separadas. Ejemplo: 0.42×0.60 y 0.43×0.60 son líneas distintas
- Formato de línea: `LARGO X PROF X CANT UNID` (ej: `1.50 X 0.60 X 6 UNID`). Si es 1 unidad, omitir `X CANT UNID`
- Agrupar bajo subencabezado `COCINAS` o `BAÑOS` según corresponda

## Checklist antes de presupuestar

- [ ] ¿Cuántas piezas hay? (mesadas, alzas, zócalos, estantes, etc.)
- [ ] ¿Alguna pieza tiene forma de L o U? → calcular tramos por separado
- [ ] ¿Hay frentin? ¿Solo frente o también lateral?
- [ ] ¿Qué tipo de pileta? ¿Cuántas?
- [ ] ¿Hay anafe? ¿Tomas eléctricas?
- [ ] ¿La obra es en Rosario o localidad del interior? → flete
- [ ] ¿El cliente quiere colocación incluida?
