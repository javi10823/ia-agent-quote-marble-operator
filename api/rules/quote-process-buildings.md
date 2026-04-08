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
- **MÉTODO DE CÁLCULO DESCUENTO MATERIAL:** Descuento 18% real sobre el precio con IVA:
  - `precio_unitario_desc = precio_con_iva × 0.82`
  - `total_material = round(precio_unitario_desc × m2_total)`
  - Ejemplo: $260.409 × 0.82 = $213.535/m²
- Mostrar el descuento como línea separada: "Descuento 18%: -$X"

### Colocación
- **NO se cobra colocación en edificios** — D'Angelo entrega el material y la constructora lo coloca. El servicio directamente no se presta, sin excepción

### Toma de medidas
- **Incluida en el SKU de flete** — NO se cobra por separado en edificios

### Flete
- Contar **piezas físicas** (no unidades/departamentos) — una mesada + una isla = 2 piezas
- `cant_fletes = ceil(cant_piezas_fisicas / 8)`
- Ejemplo: 96 departamentos con 120 piezas físicas → ceil(120/8) = **15 fletes**
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

