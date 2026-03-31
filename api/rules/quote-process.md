# Proceso de Presupuesto — D'Angelo Marmolería

## Descripción general

Para confeccionar un presupuesto se necesita recolectar información específica
antes de generarlo. El agente debe reunir todos los datos requeridos ya sea del
cliente directamente o del plano/boceto que aporte. Máximo 4 opciones de material
por presupuesto.

---

---

## Reglas para EDIFICIOS

### Identificación
Al recibir un pedido, preguntar si es **particular o edificio**. Indicadores claros:
- El enunciado lo dice explícitamente
- Hay múltiples unidades del mismo tipo (ej: "16 mesadas", "cantidad: 3")
- El nombre del archivo o el plano indica piso/cantidad (ej: `mesada_P1_2_3_01_cantidad_3`, o anotación dentro del plano)

### Descuento por volumen
- Si m2 total de material > 15 m2 → aplicar **18% de descuento** sobre el material
- Se aplica **siempre**, sin excepción, cuando se supera el umbral
- Solo aplica sobre material — **nunca sobre mano de obra**
- **CRÍTICO — m² por MATERIAL:** El descuento se calcula sumando solo los m² del **mismo material** en todo el pedido.
  - Ejemplo: pedido con mesadas Boreal (17.08 m²) + receptáculos Boreal (2.535 m²) = 19.615 m² Boreal → descuento aplica a todo el Boreal
  - Ejemplo: receptáculos Dallas (2.535 m²) en el mismo pedido → menos de 15 m² Dallas → sin descuento en Dallas
  - Nunca mezclar m² de materiales distintos para calcular el umbral
- **CLIENTE OBLIGATORIO:** El campo cliente nunca puede estar vacío. Si no se tiene, pedirlo antes de generar cualquier PDF.
- **TODA LA MO en edificios lleva descuento ÷1.05 — EXCEPTO el flete:**
  - `precio_mo_edif = round(precio_mo_con_iva / 1.05)`
  - Aplica a: PEGADOPILETA, piletas, CORTE45, ANAFE, FALDON, REGRUESO, PUL, y cualquier otro SKU de MO
  - El flete NO lleva descuento — se cobra a precio normal con IVA
- **PILETAS y PEGADOPILETA en edificios:** aplicar descuento adicional dividiendo el precio con IVA por 1.05:
  - `precio_pileta_edif = round(precio_pileta_con_iva / 1.05)`
  - `precio_pegado_edif = round(precio_pegado_con_iva / 1.05)`
- **MÉTODO DE CÁLCULO DESCUENTO MATERIAL — CRÍTICO:** El descuento NO se resta como porcentaje. Se divide el precio unitario con IVA por 1.18:
  - `precio_unitario_desc = precio_con_iva / 1.18`
  - `total_material = round(precio_unitario_desc × m2_total)`
  - Ejemplo: $260.409 / 1.18 = $220.686/m² (precio que se muestra en el presupuesto)
- El precio unitario mostrado en el presupuesto **ya incluye el descuento** — no se muestra línea DESC separada

### Colocación
- **NO se cobra colocación en edificios** — D'Angelo entrega el material y la constructora lo coloca. El servicio directamente no se presta, sin excepción

### Toma de medidas
- **Incluida en el SKU de flete** — NO se cobra por separado en edificios

### Flete
- Contar **piezas físicas** (no unidades/departamentos) — una mesada + una isla = 2 piezas
- `cant_fletes = ceil(cant_piezas_fisicas / 6)`
- Ejemplo: 96 departamentos con 120 piezas físicas → ceil(120/6) = **20 fletes**
- Precio por flete: según localidad en `delivery-zones.json` × 1.21 (sin IVA)
- En el presupuesto: **una sola línea** con SKU `ENVIOROS` (o el de la localidad), cantidad = `cant_fletes`
- **La toma de medidas está incluida en el SKU de flete** — NO agregar línea separada

### Cantidad de mesadas
- Puede venir en el nombre del archivo (ej: `cantidad_3` → 3 unidades), o indicada dentro del plano
- Si no está en ninguno de los dos → preguntar al cliente

### Pata lateral de isla (cocinas)
- **Es una pieza de material adicional** → sumar m² al total (m² = prof_mesada × alto_pata)
- En MO: cobrar **CORTE45 en ml × 2** (ml = profundidad de la mesada donde va la pata)
- Si el operador lo indica explícitamente: cobrar pulido cara interna de la pata por unidad
- En edificios: CORTE45 y pulido llevan descuento ÷1.05
- Ejemplo: isla 1.96×0.84, alto pata 0.88, 2 patas → material: 0.84×0.88×2 = 1.4784 m² | CORTE45: 0.84×2×2 = 3.36ml

### Piletas en edificios — cocinas
- 1 pileta por mesada — siempre empotrada (rectángulo dibujado en plano = agujero)
- SKU: `PEGADOPILETA` por cada mesada — precio ÷1.05 (descuento edificio)
- Si el plano dice "(VIENE EN BACHA)" o el cliente aclara que trae la pileta → cobrar **solo PEGADOPILETA**, sin la pileta
- Si el enunciado menciona modelo sin aclarar que la trae el cliente → presupuestar pileta + PEGADOPILETA
- Agujero de grifería NUNCA se cobra aparte

### Piletas en edificios — baños
- Puede ser de apoyo o empotrada
- Si el plano no lo deja claro → **preguntar o aclarar con el cliente**

### Formato desglose de piezas en presupuesto
- Cada pieza: `LARGO X PROF X CANT UNID` (ej: `1.50 X 0.60 X 6 UNID`)
- Si es 1 unidad → omitir `X CANT UNID` (ej: `1.47 X 0.60`)
- Piezas con las mismas medidas de distintos archivos → agrupar en una sola línea sumando cantidades
- Si las medidas difieren aunque sea 1cm → líneas separadas
- Agrupar bajo subencabezado `COCINAS` o `BAÑOS` según corresponda

### Presupuestos separados
- **Un PDF por material** — no mezclar materiales en un mismo presupuesto
- Separar en presupuestos adicionales solo si el cliente lo pide (ej: zócalos simple vs doble)
- Si hay zócalos de ducha en 2 materiales distintos → 2 presupuestos de zócalos por separado

### Zócalos / Receptáculos de ducha
- SKU mano de obra: **REGRUESO** — se cobra por ml — `price_includes_vat: false` → aplicar ×1.21
- **Simple:** REGRUESO a **mitad de precio** (`round(regrueso_con_iva / 2)`) × ml
- **Doble:** REGRUESO a precio completo × ml + material doble (m² × 2)
- **NO se cobra PUL en receptáculos** — solo REGRUESO (simple o doble)
- Por defecto son simples — si el plano no especifica, preguntar al cliente
- Si dice explícitamente "doble" → cotizar como doble
- Si el cliente pide ambas opciones → presupuestar simple y doble por separado
- Ejemplo: 10 receptáculos de 1.00m = 10ml de REGRUESO
- Formato desglose: `1 X 0.15 X 10 UNID` / `1 X 0.15 X 2 X 10 UNID` (el ×2 indica doble cara)

### Media placa en Silestone
- Silestone permite pedir **media placa** cuando el trabajo es pequeño
- **Media placa real = 3.00m × 0.70m = 2.10 m²** (dimensiones reales, no la mitad de la placa entera)
- Si el operador indica media placa → usar 2.10 m² como base para calcular merma
- **Merma < 1 m²** → NO se cobra sobrante (solo se cobra el m² real del trabajo)
- Merma ≥ 1 m² → aplicar regla de sobrante normal (sobrante / 2)

### Zócalos en edificios — alto siempre desde la VISTA
- El alto del zócalo se lee SIEMPRE de la VISTA específica del plano
- Si hay VISTA ZOCALO ATRAS → leer su cota horizontal = alto
- Si ML1 y ML2 comparten la misma VISTA → mismo alto para ambos
- Ejemplo Werk 34: VISTA ZOCALO LATERAL muestra 15cm → aplica tanto a ML1 como ML2

### Largo máximo de placa por material
- **Purastone**: largo máximo = **3.20m** — si la mesada mide más, cotizar a 3.20m (se verifica en obra)
- Si el plano indica una medida mayor al largo máximo de la placa → usar el largo máximo del material
- Verificar siempre el largo máximo antes de calcular m²

### Alzada y costado — piezas de material
- **Alzada**: pieza vertical visible (ej: frente de isla visto de costado) → sumar m² al material
- **Costado**: pieza lateral visible → sumar m² al material
- Ambas se cobran como material y se incluyen en la colocación
- Leer sus dimensiones del plano (largo × alto)

### Descuento — el operador puede indicar no aplicar
- Si el operador indica explícitamente no hacer descuento → no aplicarlo aunque se cumplan las condiciones
- El operador tiene la última palabra sobre los descuentos a aplicar

### Mesada en L
- Siempre son **2 tramos rectos que se complementan** — juntos forman la L sin pisarse
- **Nunca cobrar la cota exterior total** como pieza además de los 2 tramos — sería duplicar material
- Verificar: `prof_tramo1 + largo_tramo2 ≈ cota_exterior` → si se cumple, esa cota es redundante, no es pieza
- Cobrar solo los 2 tramos individuales con sus propias medidas
- La unión es a **90° — NO lleva CORTE45**
- Si el cliente pide corte a 45° explícitamente → agregar CORTE45 en MO **pero el material no cambia** (el desperdicio es igual que a 90°)

### Zócalos de mesada (cocinas, baños y lavaderos)
- Son piezas del **mismo material** que la mesada → **sumar m² al total del material**
- **NO tienen mano de obra** — ni FALDON, ni REGRUESO, ni ningún otro SKU
- m² = largo × alto del zócalo (según cota en el plano)
- **Alto default: 5cm (0.05m)** si no hay cota explícita en el plano — siempre
- **CRÍTICO — leer el plano y cobrar TODOS los zócalos indicados:** puede haber 1, 2 o 3 zócalos por mesada según las marcas. No asumir cantidad — leer cada lado marcado y cotizarlo por separado
- Cada lado marcado = 1 pieza de zócalo con su propio largo × alto
- Zócalo trasero → largo = largo de esa cara de la mesada
- Zócalo lateral → largo = profundidad de esa cara de la mesada
- En mesada en L puede haber zócalos en múltiples lados: lateral del tramo 1, trasero de la L (cota exterior), trasero de otro tramo — todos se cotizan por separado
- Listar en el presupuesto como piezas separadas bajo subencabezado "ZÓCALOS"
- **Pata lateral de isla (cocinas):**


### PUL — pulido de cantos
- **NUNCA se cobra automáticamente** — solo si el operador lo indica explícitamente
- Es un precio que D'Angelo cobra aparte — no incluirlo por defecto
- No asumir ni inferir del plano — si no está mencionado, no va
- Cuando se indica: cobrar solo los cantos que NO llevan zócalo (el zócalo cubre ese canto)
- SKU: **PUL** para granito/silestone/purastone/mármol | **PUL2** para Dekton/sinterizados
- En mesada en L: los cantos del encuentro entre tramos (unión a 90°) no se pulen

### Descuentos — reglas generales
- **Cálculo de descuento**: precio × (1 - desc%) — **NUNCA dividir por 1.05, 1.15, 1.18, etc.**
  - 5% → × 0.95 | 8% → × 0.92 | 15% → × 0.85 | 18% → × 0.82
- **Siempre mostrar fila explícita de descuento** antes del Total USD en PDF y Excel
- Formato: concepto = "Descuento X%" | monto = "- USD XX" — nunca mencionar el motivo (arquitecta, precio especial, etc.)
- El cliente debe ver claramente qué descuento se aplicó y por cuánto

- **NO son acumulativos** — solo se aplica UN descuento por presupuesto
- Si aplican dos (ej: arquitecta + cantidad de m²) → usar el **más beneficioso para el cliente** (el mayor %)
- Solo se acumulan si el operador lo indica explícitamente en el enunciado
- Tipos de descuento posibles:
  - Arquitecta: 5% importado, sin umbral de m²
  - Cantidad: 5% importado si >6m², 8% nacional si >6m²
  - Edificio: 18% si >15m²
  - Manual: lo que indique el operador en el enunciado

### Descuento arquitecta
- Descuento: **5% sobre material importado USD** (config.json → discount.imported_percentage)
- Se aplica **siempre**, sin umbral mínimo de m² — diferente al descuento general que requiere >6m²
- Acumulable con descuento de cantidad solo si el operador lo indica

### Arquitectas con descuento — agregar automáticamente
Si el operador indica que el cliente tiene descuento por ser arquitecta:
- Agregar automáticamente al archivo `catalog/architects.json` sin que el operador lo pida
- El operador no debería tener que recordarlo — el sistema debe aprenderlo solo
- Descuento: 5% sobre material importado USD (mismo que config.json discount.imported_percentage)

### PEGADOPILETA — por pileta, no por mesada
- Cobrar **1 PEGADOPILETA por cada pileta**, no por mesada
- Si una mesada tiene 2 piletas → 2 PEGADOPILETA
- Siempre contar piletas del plano, no mesadas

### Transparencia durante el proceso
- **Siempre mostrar en chat** lo que se va calculando, leyendo o interpretando — paso a paso
- El operador valida en tiempo real antes de llegar al PDF
- Incluye: lectura de plano (4 pasadas), cálculos de m², precios, decisiones sobre stock/merma/descuentos
- No saltar directo al resultado — el proceso visible es la herramienta de validación

### Zócalos de mesada — presentación en PDF/Excel
- **SIEMPRE mostrar una línea explícita de zócalo** en el presupuesto — si no aparece, el cliente cree que no está incluido
- Formato: `ZÓCALO X.XX ml x 0.05 m` — una sola línea con el **total de ml** (NO desglosar lado por lado)
- Los m² del zócalo ya están sumados al total del material
- En la validación previa al PDF sí se puede mostrar desglose por lado — en el PDF/Excel solo el total


- **Si el enunciado NO menciona que el cliente quiere presupuestar una pileta → asumir que ya la tiene**
- En cocina → cobrar solo `PEGADOPILETA`, sin presupuestar la pileta. No preguntar.
- Solo presupuestar pileta Johnson si el enunciado la menciona explícitamente

### Mesada de más de 3 metros
- Si una mesada tiene largo > 3.00m → agregar leyenda **(SE REALIZA EN 2 TRAMOS)** al lado de esa fila en el presupuesto (PDF y Excel)
- **Alzada en enunciado** → cobrar al menos **1 agujero de toma de corriente** (SKU: `TOMAS`)
- Estas reglas se aplican automáticamente sin que el operador lo pida

### Material no encontrado en catálogo
Si el cliente pide un material específico que no está en catálogo:
- **Informar al operador** que no se encontró ese material exacto en el catálogo
- **Preguntar al operador** cuál usar — nunca sugerir alternativas por cuenta propia
- No ofrecer materiales similares sin que el operador lo pida — es una pérdida de tiempo

### Flete — valor del operador tiene prioridad
- Si el operador indica un valor fijo de flete → usar ese valor, no el del catálogo
- Ejemplo: "flete + toma de medidas $100.000 final" → usar $100.000
- El catálogo delivery-zones.json es referencia, pero el operador puede ajustarlo

### Colocación — particulares
- Solo aplica en particulares — **nunca en edificios**
- Cobrar si: el enunciado lo dice explícitamente O el operador lo indica
- Si el enunciado menciona colocación → cobrarla sin preguntar
- Si no se menciona → preguntar al operador si el cliente la pidió
- Mínimo 1 m²: `m2_colocacion = max(m2_total_material, 1.0)` — siempre
- **Colocación se calcula sobre el TOTAL de m² de material — incluyendo zócalos** (todo se pega en obra)
- Aplica para TODOS los materiales: granito, mármol, Dekton, Silestone, Purastone, Neolith, etc.

### ANAFE — cobrar por unidad
- Cobrar ANAFE por cada unidad/departamento que tenga anafe en el plano
- No cobrar un ANAFE global — contar uno por cada cocina que lo tenga

### SKUs específicos para Dekton/Neolith/Puraprima/Laminatto
**Regla general:** para cualquier material sinterizado, buscar SIEMPRE el SKU específico en labor.json antes de usar el genérico. Si existe un SKU específico para ese material → usarlo sin excepción.

| Tarea | SKU genérico ❌ | SKU Dekton/Neolith ✅ |
|-------|----------------|----------------------|
| Pileta de apoyo | AGUJEROAPOYO | PILETAAPOYODEKTON/NEO |
| Pileta empotrada | PEGADOPILETA | PILETADEKTON/NEOLITH |
| Pulido cantos | PUL | PUL2 |
| Colocación | COLOCACION | COLOCACIONDEKTON/NEOLITH |
| Faldón | FALDON | FALDONDEKTON/NEOLITH |
| Corte 45° | CORTE45 | CORTE45DEKTON/NEOLITH |

## Flujo completo del presupuesto

```
1. Cliente pasa medidas aproximadas
2. Se genera el presupuesto y se envía al cliente
3. Cliente paga el 80% de seña — confirmación del trabajo
4. Se realiza la toma de medidas en obra (medidas reales)
5. Se compara con las medidas aproximadas del presupuesto original
   → Si la diferencia es > 0.5 m2: se actualiza el presupuesto
     (tanto el que se envía al cliente como el de DUX)
   → Si la diferencia es ≤ 0.5 m2: se mantiene el presupuesto original
6. Cliente paga el 20% restante con el ajuste por diferencia,
   descontando lo ya abonado en la seña
```

---

## Paso 1 — Identificar el tipo de trabajo

Primero identificar el tipo de trabajo, ya que esto determina qué materiales son
adecuados y qué preguntas adicionales hacer.

**Tipos de trabajo:**
- Mesada de cocina
- Isla de cocina
- Mesada de baño
- Piso
- Revestimiento
- Escaleras
- Umbrales
- Solías
- Tapas de mesa
- Lavadero (especificar si es interior o exterior)
- Cocina + isla combinadas

---

## Paso 2 — Relevar medidas

El cliente debe aportar alguna de las siguientes opciones:
- Plano de obra
- Boceto con medidas aproximadas
- Medidas sueltas

Sin medidas aproximadas no se puede confeccionar el presupuesto.
Si el cliente no tiene ninguna, se le solicita que las consiga o estime
antes de continuar.

---

## Paso 3 — Selección de material

### Orden de evaluación — siempre seguir este orden:

**1. Consultar stock.json Y preguntar al operador — SIEMPRE**
Antes de calcular merma, seguir este proceso obligatorio:

a) Buscar el material en stock.json. Una pieza es válida si cumple:
   - Largo: `largo_pieza ≥ largo_max_trabajo` (si entra justo es válido — con 1cm de sobra ya alcanza)
   - M²: `m2_pieza ≥ m2_trabajo × 1.20` (20% de margen mínimo)

b) Si hay pieza válida en stock.json → informar al operador: "Encontré esta placa en stock: [detalle]. ¿Querés usarla?"

c) Si NO hay pieza válida en stock.json → igual preguntar al operador: "No encontré stock válido en el sistema, ¿tenés este material en stock? El archivo puede estar desactualizado."

d) **NUNCA asumir que no hay stock sin preguntarlo al operador.**

e) Si el operador confirma que tiene el material en stock → **sin merma**, cobrar solo los m² reales del trabajo.

f) Solo si el operador confirma que NO hay stock → aplicar merma normalmente.

**2. Si no hay stock válido → evaluar sustitución Silestone**
Aplica SOLO cuando el cliente pidió Purastone (o material que D'Angelo solo consigue en placa entera).
Si el trabajo entra en media placa de Silestone (desperdicio < 1.0 m2 con referencia media placa),
ofrecer Silestone equivalente — D'Angelo puede comprar media placa de Silestone pero no de Purastone.
Explicar al cliente que es similar y más conveniente para ese metraje.

Si el cliente pidió granito, mármol u otro material que se vende por m2 suelto → NO aplica
esta sustitución. Cotizar directamente con merma normal (paso 3).

**3. Si tampoco aplica sustitución → cotizar con merma normal**
Aplicar regla de desperdicio ≥ 1.0 m2 y ofrecer sobrante si corresponde.

> El stock es un inventario de retazos en taller — sujeto a disponibilidad al momento de confirmar.

### Si el cliente NO especificó material:
Preguntar:
- Qué gama de color busca (tonos cálidos, oscuros, blancos, grises, etc.)
- Si desea con veta o liso (sin veta)
- Si la aplicación es para interior o exterior (ver materials-guide.md)

Ofrecer primero materiales disponibles en stock que coincidan con la preferencia del cliente.
Si no hay stock que coincida, mostrar entre 6 y 8 fotos de materiales recomendados cubriendo
todas las categorías aptas. El cliente elige hasta 4 opciones para presupuestar.

Una vez que el cliente indicó cuáles le interesan (1 a 4), generar el
presupuesto con todas esas opciones juntas — no volver a pedir que elija una.

### Si el cliente YA especificó material(es):
- Verificar en stock.json si está disponible → sin merma si entra en las piezas
- Verificar que sea apto para el tipo de trabajo (ver materials-guide.md)
- Si trae hasta 4 opciones, presupuestar todas juntas directamente
- Si trae más de 4, pedirle que priorice hasta 4

### Regla de sustitución Purastone → Silestone (trabajos pequeños)
Si el cliente pide Purastone pero el trabajo es pequeño y entraría bien en media placa de Silestone
(desperdicio < 1.0 m2), ofrecer Silestone equivalente — D'Angelo puede comprar media placa.
Ver materials-guide.md para más detalle.

---

## Paso 4 — Datos del cliente

Antes de las preguntas técnicas, recolectar siempre:
- [ ] Nombre y apellido del cliente *(requerido)*
- [ ] Empresa *(opcional)*
- [ ] Nombre del proyecto *(opcional — si no lo indica, usar descripción del trabajo)*

La fecha del presupuesto se asigna automáticamente con la fecha del día.

---

## Paso 5 — Preguntas requeridas según tipo de trabajo

### Todos los trabajos — siempre preguntar:
- [ ] Localidad de la obra → determina la zona de entrega y el precio de flete
- [ ] ¿Lleva colocación en obra o no?
- [ ] ¿Lleva pulido de cantos? — si está en el enunciado usarlo, si no → preguntar al operador
- [ ] ¿Cuál es la fecha de entrega / plazo? — si está en el enunciado usarlo directamente, si no → preguntar al operador, nunca asumir valor por defecto
- [ ] ¿Lleva flete o el cliente lo retira?
- [ ] ¿Requiere toma de medidas o el cliente entrega las medidas exactas?
- [ ] ¿Lleva zócalos?

### Mesada de cocina / Isla — preguntar además:
- [ ] ¿Lleva agujero y pegado de pileta?
  - Si sí: ¿el cliente tiene su propia pileta o hay que presupuestarla? (trabajamos con Johnson)
    - Cliente trae pileta propia empotrada → SKU `PEGADOPILETA` (siempre necesita pegado)
    - `AGUJEROAPOYO` es exclusivo para piletas de apoyo — nunca usar para piletas empotradas
    - **Pileta de apoyo** → SKU `AGUJEROAPOYO` — incluye SIEMPRE el agujero de grifería, nunca cobrar grifería por separado
    - **Agujero de grifería NUNCA se cobra aparte** — está incluido en el SKU de pileta (empotrada o apoyo). No preguntar al cliente.
  - Si hay que presupuestar pileta: ¿simple o doble? ¿de pegar arriba o abajo? ¿acero o de color?
    Ofrecer catálogo de piletas Johnson para que el cliente elija.
- [ ] ¿Lleva agujero de anafe?
- [ ] ¿Lleva frentin o regrueso?
  - Si el plano lo muestra, calcularlo directamente sin preguntar.
  - Si NO figura en el plano, preguntar al cliente.
- [ ] Para isla específicamente: ¿lleva patas laterales?

### Baño — preguntar además:
- [ ] ¿Lleva frentin o regrueso?
  - Si el plano lo muestra, calcularlo directamente sin preguntar.
  - Si NO figura en el plano, preguntar al cliente.
- [ ] ¿Lleva zócalos?
- [ ] Tipo de pileta: ¿integrada o de apoyo?
  - Si es integrada: mostrar fotos de modelos disponibles para que el cliente elija
  - Si es de apoyo: ¿requiere agujero y pegado de pileta?

> **Regla cocina vs baño:** si el trabajo lleva anafe → mesada de cocina → pileta SIEMPRE empotrada.
> Pileta de apoyo es exclusiva de baños. No preguntar tipo de pileta cuando hay anafe.

### Piedra sinterizada (Dekton, Neolith, Laminatto, Puraprima) — 12mm de espesor:
- [ ] Siempre sugerir frentin por el perfil fino de 12mm — si el cliente lo acepta,
  calcularlo usando las fórmulas de calculation-formulas.md

### Aplicaciones en exterior — confirmar:
- [ ] Que el material elegido sea apto para exterior (ver guia-materiales.md)

---

## Paso 6 — Checklist antes de generar el presupuesto

Antes de generar el presupuesto, confirmar que se conoce todo lo siguiente:

| Dato | Requerido |
|---|---|
| Nombre y apellido del cliente | ✅ |
| Empresa | ⬜ opcional |
| Nombre del proyecto | ⬜ opcional |
| Tipo de trabajo | ✅ |
| Material(es) seleccionado(s) — máximo 4 opciones | ✅ |
| Medidas aproximadas o plano | ✅ |
| Localidad / zona de entrega | ✅ |
| Lleva colocación | ✅ |
| Lleva flete | ✅ |
| Lleva toma de medidas | ✅ |
| Lleva zócalos | ✅ |
| Agujero y pegado de pileta | ✅ si cocina/baño |
| Agujero de anafe | ✅ si cocina/isla |
| Frentin o regrueso | ✅ si figura en plano o aplica por espesor |
| Patas laterales de isla | ✅ si es isla |
| Pileta a presupuestar (Johnson) | ✅ si se solicitó |

---

## Paso 6b — Validación previa al PDF
Antes de generar cualquier PDF, presentar el cálculo completo en texto plano al operador con:

1. **Desglose de m²** por pieza (mesadas, patas, zócalos)
2. **Total m² × precio unitario = total material**
3. **Sección de descuentos aplicados** — mostrar claramente:
   - Descuento sobre material: sí/no, motivo (edificio ÷1.18 / particular 8% ARS o 5% USD / manual X%) y monto
   - Descuento MO edificio ÷1.05: sí/no
   - Stock: sí/no (si sí → sin merma)
   - Merma: sí/no, m² sobrante
   - Si NO aplica ningún descuento → aclararlo explícitamente
4. **Cada ítem de MO** con cantidad, precio unitario y total
5. **Grand total**

Esperar confirmación explícita antes de generar el PDF.

## Paso 7 — Estructura del presupuesto

Una vez recolectados todos los datos, generar **un presupuesto PDF separado por cada
opción de material** que el cliente mostró interés (hasta 4 PDFs). No mezclar
materiales en un mismo presupuesto. El cliente compara los PDFs y elige al momento
de confirmar y pagar la seña.

```
BLOQUE DE MATERIAL (uno por cada material seleccionado)
  Nombre del material + espesor
  Medidas detalladas (cada pieza)
  Total m2
  Precio unitario (ARS o USD según origen)
  Subtotal (ARS o USD)

BLOQUE DE MANO DE OBRA
  Cada tarea aplicable con cantidad, precio unitario y subtotal — todo en ARS

TOTALES
  Si todo es ARS → un solo total: suma de material ARS + piletas + MO, con etiqueta "Mano de obra + material"
  Si hay material USD → dos líneas: total ARS (material ARS + piletas + MO) + total USD (solo material importado), ambas con etiqueta "Mano de obra + material"
  NUNCA separar MO y material en el grand total si están en la misma moneda

PIE DE PRESUPUESTO (condiciones y formas de pago estándar)
```

---

## Paso 8 — Ajuste por toma de medidas real

Luego de que el cliente paga la seña (80%) y se realiza la toma de medidas
en obra, comparar las medidas reales con las aproximadas del presupuesto:

```
Diferencia = |m2 reales - m2 aproximados|

SI diferencia > 0.5 m2:
  → Actualizar el presupuesto con los m2 reales
  → Enviar presupuesto actualizado al cliente
  → Actualizar en DUX
  → El 20% restante se calcula sobre el nuevo total
    menos lo ya abonado en la seña

SI diferencia ≤ 0.5 m2:
  → Mantener el presupuesto original sin cambios
  → El 20% restante se calcula sobre el total original
    menos lo ya abonado en la seña
```

---

## Reglas importantes

- El presupuesto inicial se confecciona siempre con medidas aproximadas.
- No se realiza toma de medidas sin que el cliente haya confirmado y pagado la seña.
- No se suben mesadas por escalera.
- Los precios incluyen IVA.
- El presupuesto está sujeto a variación de precio.
- La toma de medidas no puede superar los 30 días desde la confirmación.
  Pasado ese plazo, el 20% restante se actualiza según el índice de la construcción.
