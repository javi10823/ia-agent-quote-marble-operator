# Lectura de cotas en planos de cocina — guía para extracción visual

## Qué es una vista PLANTA
Vista desde arriba (cenital). Muestra el layout del espacio sin techo. Las mesadas aparecen como rectángulos o polígonos pegados a las paredes.

## Anatomía de una cota
Una cota es una medida de distancia entre dos puntos del plano:
- **Línea de cota**: horizontal o vertical, con extremos marcados (flechas, cruces o ticks)
- **Número**: el valor en cm (salvo que diga otra unidad)
- **Líneas de referencia**: líneas finas perpendiculares que bajan desde el objeto hasta la línea de cota

## 5 tipos de cotas

### 1. Cota explícita con línea
El caso más claro. Hay una línea con extremos marcados y un número.
→ Usar directamente como medida de mesada.

### 2. Cota embebida en texto descriptivo
El número aparece dentro de una etiqueta de texto que describe un elemento (ej: "proyección alacena 120"). Si hay una línea de alcance asociada que abarca un tramo de mesada, el número mide ese tramo.
→ Extraer el número aunque el texto describa otro elemento.

### 3. Cota de objeto propio
El número está dentro del rectángulo de un objeto (anafe, pileta, heladera). Indica una dimensión del objeto en sí.
→ IGNORAR. No es una pieza de mesada. No confundir con cotas de mesada.

### 4. Cotas encadenadas
Varias cotas alineadas que se suman. Cada una mide un tramo y juntas dan el largo total.
→ Sumar todos los tramos para obtener el largo total del segmento.

### 5. Cota de profundidad
Cota perpendicular a la pared. Mide qué tan fondo entra la mesada desde la pared hacia el centro del ambiente.
→ Es la profundidad (ancho) de la mesada. Típicamente 55-65cm.

## Regla de oro
- Número con línea que conecta dos puntos del espacio = **cota de distancia** → usar
- Número flotando dentro de un objeto = **dimensión del objeto** → ignorar

## Qué ignorar SIEMPRE
- Cotas de espacios para heladera, lavarropas, microondas, lavavajillas
- Nichos técnicos (nicho para agua, nicho para gas)
- Ancho total del ambiente
- Símbolos de carpintería o herrería
- Cotas de muebles bajo mesada (melamina)
- Cotas de alacenas superiores (salvo que la línea de alcance mida el tramo de mesada debajo)

## Tabla resumen
| Situación | Acción |
|-----------|--------|
| Número con línea y extremos marcados | Cota de distancia → usar directamente |
| Número en texto con línea de alcance sobre mesada | Extraer número → mide ese tramo |
| Número dentro de símbolo de objeto | Dimensión del objeto → IGNORAR |
| Cotas encadenadas alineadas | Sumar → largo total del tramo |
| Cota perpendicular a pared | Profundidad de mesada |
| Cota ausente en un tramo | NO inferir → dejar como "unknown" y preguntar |

## Mesadas en U

Una mesada en U tiene 3 tramos: lateral izquierdo + fondo + lateral derecho. Se detecta cuando la mesada cubre 3 paredes o tiene 2 tramos laterales conectados por un fondo.

### Cómo calcular los tramos

1. **Total fondo**: sumar todas las cotas horizontales de la pared del fondo (incluir el espacio del anafe si lo hay — se cobra como material completo)
2. **Tramo fondo neto**: total_fondo - profundidad_izq - profundidad_der (restar las esquinas)
3. **Tramo izquierdo**: largo del lateral izquierdo (cotas verticales)
4. **Tramo derecho**: largo del lateral derecho (cotas verticales)

### Formato en segments_m
Para U: `segments_m = [tramo_izq, tramo_fondo_neto, tramo_der]`

El tramo fondo YA tiene las esquinas restadas, por lo que el cálculo de m² es simplemente la suma de los 3 tramos × profundidad, sin restar esquinas adicionales.

### Anafe en tramo fondo
Si el anafe está en el tramo del fondo, el material se cobra completo (incluyendo el espacio del anafe) porque el desperdicio es inevitable — la piedra se compra entera y se corta.
