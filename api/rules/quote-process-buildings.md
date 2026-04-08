# Reglas para EDIFICIOS

### Identificacion
Preguntar si es particular o edificio. Indicadores: enunciado lo dice, multiples unidades, nombre archivo/plano indica cantidad.

### Descuento por volumen
- m2 total material > 15 m2 → **18% descuento** sobre material
- Siempre, sin excepcion, cuando supera umbral
- Solo sobre material, NUNCA MO
- **m² por MATERIAL:** sumar m² del MISMO material. No mezclar materiales para umbral.
  - Ej: Boreal 19.6 m² → descuento. Dallas 2.5 m² mismo pedido → sin descuento.
- **METODO:** `precio_unitario_desc = precio_con_iva / 1.18`. Precio mostrado YA incluye descuento.
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
- Contar **piezas fisicas** (no unidades/dptos): `cant_fletes = ceil(piezas/6)`
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
- Tipos: arquitecta 5% USD, cantidad 5% USD/>6m² o 8% ARS/>6m², edificio 18%/>15m², manual
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
Leyenda **(SE REALIZA EN 2 TRAMOS)**. Alzada en enunciado → 1 TOMAS.

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
