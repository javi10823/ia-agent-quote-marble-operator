# Reglas para EDIFICIOS

### Identificacion
Preguntar si es particular o edificio. Indicadores: enunciado lo dice, multiples unidades, nombre archivo/plano indica cantidad.

### Descuento por volumen
- m2 total material > 15 m2 → **18% descuento** sobre material
- Siempre, sin excepcion, cuando supera umbral
- Solo sobre material, NUNCA MO
- **m² TOTAL:** sumar m² de TODOS los materiales del edificio. Si total > 15 → 18% a TODOS.
  - Ej: Boreal 12.6 + Brasil 4.3 + Sahara 37.2 = 54.1 m² > 15 → descuento a los 3.
- **METODO:** `precio_unitario_desc = precio_con_iva × 0.82` (18% real).
- CLIENTE OBLIGATORIO — si no se tiene, pedirlo antes de generar PDF.

### MO en edificios
- **TODA la MO lleva ÷1.05 EXCEPTO flete:** `round(precio_con_iva / 1.05)`
- Aplica a: PEGADOPILETA, piletas, CORTE45, ANAFE, FALDON, REGRUESO, PUL, etc.
- Flete: precio normal con IVA, sin descuento.

### Colocacion
**NO se cobra en edificios** — constructora coloca. Sin excepcion.

### Toma de medidas
Incluida en SKU de flete — NO cobrar por separado.

### Flete
- Contar **piezas fisicas** (no unidades/dptos, no faldones): `cant_fletes = ceil(piezas/8)`
- Ej: 120 piezas → ceil(120/6) = 20 fletes
- Una sola linea con SKU zona x cant_fletes
- Toma de medidas incluida

### Cantidad mesadas
Nombre archivo (`cantidad_3`) o plano. Si no → preguntar.

### Pata lateral isla
- Material: `prof_mesada x alto_pata` x cant patas → sumar m²
- MO: CORTE45 = ml x 2 (ml = profundidad)
- En edificios: CORTE45 y pulido ÷1.05
- Ej: isla 1.96x0.84, pata 0.88, 2 patas → 0.84x0.88x2 = 1.48 m² | CORTE45: 0.84x2x2 = 3.36ml

### Piletas edificios — cocinas
- 1 pileta/mesada, siempre empotrada → PEGADOPILETA (÷1.05)
- "(VIENE EN BACHA)" → solo PEGADOPILETA, sin pileta
- Griferia nunca aparte

### Piletas edificios — banos
Apoyo o empotrada — si no claro → preguntar.

### Formato desglose
- `LARGO X PROF X CANT UNID` | 1 unidad → omitir cant
- Mismas medidas → agrupar | Diferencia 1cm → separar
- Subencabezado COCINAS / BANOS

### Presupuestos separados
Un PDF por material. Separar adicionales solo si cliente pide.

### Zocalos / Receptaculos de ducha
- MO: REGRUESO por ml (x1.21)
- **Simple:** mitad precio x ml | **Doble:** precio completo x ml + material x 2
- NO PUL en receptaculos
- Default simples. "Doble" explicito → doble.
- Formato: `1 X 0.15 X 10 UNID` / `1 X 0.15 X 2 X 10 UNID`

### Media placa Silestone
Media placa real = 3.00 x 0.70 = 2.10 m². Merma < 1 m² → sin sobrante.

### Zocalos en edificios — alto desde la VISTA
Leer alto de VISTA especifica. Si ML1 y ML2 comparten VISTA → mismo alto.

### Largo maximo placa
- Purastone: max 3.20m. Mesada > 3.20m → cotizar a 3.20m.

### Alzada y costado
Piezas material (largo x alto) → sumar m², incluir en colocacion.

### Descuento — operador puede indicar no aplicar
Operador tiene ultima palabra.

### Mesada en L
- 2 tramos rectos complementarios. NUNCA cobrar cota exterior como pieza adicional.
- Union 90° → NO CORTE45 (salvo pedido explicito, solo MO)

### Zocalos de mesada
- Mismo material → sumar m² al total
- NO tienen MO (ni FALDON, ni REGRUESO)
- Alto default 5cm. Leer plano, cobrar TODOS los marcados.
- Listar como piezas separadas bajo "ZOCALOS"

### PUL
- NUNCA automatico — solo si operador indica
- Solo cantos sin zocalo | PUL (20mm) / PUL2 (sinterizados)
- Mesada en L: cantos del encuentro no se pulen

### Descuentos — reglas
- `precio x (1 - desc%)` | NO acumulativos — 1 por presupuesto, el mayor %
- Tipos: arquitecta 5% USD (**SIN minimo m²**), cantidad 5% USD/>6m² o 8% ARS/>6m², edificio 18%/>15m², manual
- ⛔ El mínimo de 6m² solo aplica a descuento por cantidad, NUNCA a descuento de arquitecta
- Mostrar fila DESC | Solo material, nunca MO

### Descuento arquitecta
- 5% material importado, sin umbral m² | Agregar a architects.json automaticamente

### PEGADOPILETA
1 por pileta, no por mesada. 2 piletas = 2 PEGADOPILETA.

### Transparencia
Mostrar en chat paso a paso. Operador valida antes del PDF.

### Zocalos en PDF/Excel
Linea explicita `ZOCALO X.XX ml x 0.05 m` (total ml, no por lado).

### Pileta: si enunciado NO menciona → asumir cliente la tiene
Cocina → solo PEGADOPILETA. Solo presupuestar Johnson si lo menciona.

### Mesada >3m
En edificios NO agregar leyenda "(SE REALIZA EN 2 TRAMOS)" — las tipologías
ya vienen listadas como DC-02 X 6, DC-03 X 8, etc. y la leyenda genera ruido.
Alzada en enunciado → 1 TOMAS.

### ⛔ Sin merma en edificios
Edificios NUNCA llevan merma. El operador maneja el corte por tipología
manualmente. `calculate_quote()` con `is_edificio=True` fuerza
`merma.aplica = false` automáticamente.

### ⛔ Despiece completo — largo y prof obligatorios
NUNCA aceptar solo m² por pieza. Cada tipología debe tener dimensiones
completas (ej: `largo: 2.34, prof: 0.62`). Si el operador/planilla solo
da m² sin dimensiones:
1. Pedir al operador: "¿Cuáles son las medidas completas (largo × prof)
   de cada tipología?"
2. NO inventar dimensiones que multipliquen al m² (ej: 6.00 × 1.00).
3. `calculate_quote()` emite warning si detecta piezas sin `largo` o `prof`.

### Flete edificio
`ceil(piezas_fisicas_totales / flete_mesadas_per_trip)`.
- Contar unidades físicas reales: DC-04 × 8 son 8 piezas, no 1.
- Zócalos viajan con mesadas, NO cuentan como piezas para flete.
- Default `flete_mesadas_per_trip = 6` (config.json, building.flete_mesadas_per_trip).

### ⛔ Override explícito del operador
Si el operador escribe **cantidad de fletes explícita** en el enunciado
(ejemplos: "× 5 fletes", "flete × 3", "5 viajes", "Flete + toma × 5 fletes"):
- USAR esa cantidad EXACTA.
- NO calcular `ceil(piezas/6)` por tu cuenta.
- Pasar `flete_qty: N` en el input a `calculate_quote`.

El cálculo automático SOLO aplica cuando el operador NO especifica cantidad.
El sistema detecta el override con regex en el mensaje del operador y pasa
`flete_qty` automáticamente, pero si lo ves explícito pasalo también por
las dudas — es idempotente.

### ⛔ Flete NUNCA lleva descuento
El flete es un costo fijo de transporte. NO aplicar:
- NO el `÷1.05` de edificio.
- NO el `mo_discount_pct` (descuento comercial sobre MO).
- NO cualquier otro descuento.
El calculator excluye automáticamente el flete de ambos descuentos. Si ves un
total de flete reducido en el preview, es un bug — reportar.

### Descuento comercial sobre MO (`mo_discount_pct`)
Cuando el operador declara "descuento X% sobre MO" en un edificio:
- Pasar `mo_discount_pct: X` en el input a `calculate_quote`.
- Se calcula sobre la suma de MO c/IVA (con ÷1.05 ya aplicado), excluyendo flete.
- Se muestra como línea separada visible en el Paso 2.
- Default: 0 (no aplicar salvo pedido explícito).

### Material no encontrado
Informar operador. Preguntar cual usar — no sugerir alternativas.

### Flete — valor operador prioridad
Operador indica valor fijo → usar ese.

### Colocacion particulares
Solo particulares. Minimo 1 m². Sobre total m² incluyendo zocalos.

### ANAFE por unidad
1 por cocina que tenga anafe, no global.

### SKUs Dekton/Neolith/Puraprima/Laminatto
Buscar SIEMPRE SKU especifico en labor.json antes del generico. Ver tabla en CONTEXT.md.
