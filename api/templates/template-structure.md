# Template Structure — D'Angelo Marmolería

Documentación técnica para generación de PDF y Excel sin necesidad de explorar los archivos en cada sesión.

---

## Excel — `quote-template-excel.xlsx`

### Hoja: `Factura`

#### Celdas mergeadas relevantes
| Rango | Uso |
|-------|-----|
| A12:D12 | "Presupuesto" (título) |
| A13:B13 | Fecha |
| A15:B15 | Label "Cliente:" |
| A16:B16 | Valor cliente |
| C15:D15 | Label "Forma de pago" |
| C16:D16 | Valor forma de pago |
| A17:B17 | Label "Proyecto" |
| A18:B18 | Valor proyecto |
| C18:D18 | Label "Fecha de entrega" |
| C19:D19 | Valor fecha de entrega |
| A22:C22 | Header "Descripción" |
| A23:C23 | Primera fila de contenido (material) |
| A39:F39 | Grand total |
| A40:F40 | Footer note (ej: "No se suben mesadas...") |
| A41:F41 | Nota cotización oficial |
| A42:F42 | Condiciones y formas de pago |

#### Celdas de escritura directa (top-left del merge)
```
A13  → "Fecha: DD/MM/YYYY"
A16  → nombre cliente
C16  → forma de pago
A18  → proyecto
C19  → fecha de entrega
```

#### Estructura de contenido — filas dinámicas (desde fila 23)
```
Fila 23:   Material header
             A23 = nombre material + espesor (bold)
             D23 = m² (número puro, format 0.00)
             E23 = precio unitario USD (número puro)
             F23 = "=D23*E23"

Filas 24-N: Sub-filas de piezas
             A = descripción pieza (small, normal)
             D, E, F = vacías

Fila N+1:  TOTAL USD
             E = "TOTAL USD" (bold)
             F = valor numérico (bold)

Fila N+2:  Spacer vacío

Fila N+3:  "MANO DE OBRA" (bold, col A)

Filas MO:  Una por ítem
             A = descripción con unidad (ej: "COLOCACIÓN x m²")
             D = cantidad (número puro)
             E = precio unitario ARS (número puro)
             F = "=D*E"

Fila final MO:
             E = "Total PESOS" (bold)
             F = "=SUM(F_inicio:F_fin)" (bold)

Fila GT:   **A39** = "PRESUPUESTO TOTAL: ..." (bold) — esta es la celda con el recuadro/borde del template. SIEMPRE usar fila 39, nunca otra fila.
Fila FN:   A40 = "No se suben mesadas que no entren en ascensor" (bold italic)
```

#### Anchos de columna recomendados
```
A → 50  |  D → 12  |  E → 20  |  F → 16
```

## Reglas de formato — TODOS los clientes

### Posición exacta del TOTAL USD/ARS — estructura validada

```
[Material bold] | m² | USD XXX | USD XXX     ← fila material
[SECTOR 1]                                    ← subencabezado sector
[Primera pieza del sector] | | TOTAL USD | USD XXXX  ← TOTAL en misma fila que 1ra pieza
[Segunda pieza]
...resto de piezas y sectores
```

- TOTAL USD/ARS va en col E y F de la **misma fila que la primera pieza del primer sector**
- NO tiene fila propia separada
- NO hay fila vacía entre material y sectores
- El TOTAL es bold en E y F



### Regla de totales — NUNCA más de 2
- **1 TOTAL USD** → solo si hay material importado (en USD)
- **1 Total PESOS** → suma TODO lo que sea ARS: piletas + MO + material nacional
- **NUNCA** "Total PESOS piletas" separado — las piletas van sumadas al Total PESOS final
- Si hay material nacional + MO: `Total PESOS = material_ars + piletas + MO`
- Si hay material importado + MO: `Total USD = material` | `Total PESOS = piletas + MO`


Cuando existe un Excel validado por D'Angelo, SIEMPRE copiarlo como base y solo sobreescribir los valores. NUNCA reconstruir desde el template desde cero.

```python
import shutil
shutil.copy('/ruta/excel_correcto.xlsx', '/home/claude/nuevo_presupuesto.xlsx')
wb = load_workbook('/home/claude/nuevo_presupuesto.xlsx')
# Solo modificar valores — estructura, alturas, anchos, bordes y formatos se preservan
```

Esto garantiza: alturas de fila correctas, anchos de columna exactos, bordes y formatos idénticos al original validado.

#### Presupuestos largos — RECONSTRUIR desde fila 22
Cuando el contenido supera ~12 filas (muchas piezas, piletas + MO), NO intentar encajar en el template. En su lugar:
1. Hacer unmerge de TODAS las celdas mergeadas del template
2. Limpiar todo el contenido desde fila 22
3. Reconstruir fila por fila con control total
4. Grand total: crear borde manualmente con `Border(left/right/top/bottom=thin)` + `merge_cells`

```python
# Unmerge todo
for merged in list(ws.merged_cells.ranges):
    ws.unmerge_cells(str(merged))
# Limpiar desde fila 22
for row in ws.iter_rows(min_row=22, max_row=100):
    for cell in row:
        cell.value = None
```


Cuando el contenido supera la fila 34 (muchas piezas), hay que hacer unmerge antes de escribir:
```python
for rng in ['B37:D37','A39:F39','A40:F40','A41:F41','A42:F42']:
    try: ws.unmerge_cells(rng)
    except: pass
```
En estos casos el grand total y footer van en filas dinámicas después del contenido, no en fila 39 fija.


Antes de hacer `present_files` del Excel, verificar contra el PDF:
- ¿El grand total está en la fila 39 (celda con recuadro)?
- ¿Los valores USD muestran "USD X.XXX" y no "$"?
- ¿El Total PESOS tiene valor real (no vacío)?
- ¿Coinciden todos los montos con el PDF?


- Columnas D y E: siempre números puros, NUNCA texto con unidades
- Conceptos con unidad van en col A: "COLOCACIÓN x m²", "AGUJERO x u"
- Fórmula col F: siempre `=D*E`, nunca valor hardcodeado
- Total USD: número real, nunca placeholder
- **Material en USD → aplicar formato `"USD "#,##0` en celdas E y F del material y en la fila TOTAL USD** — nunca dejar formato "$" en materiales USD
- NUNCA usar `ws[merged_cell] =` directamente — usar solo la celda top-left del merge

---

## PDF — generación desde HTML

### Tool: `wkhtmltopdf`
```bash
wkhtmltopdf --quiet --page-size A4 \
  --margin-top 0 --margin-bottom 0 \
  --margin-left 0 --margin-right 0 \
  "input.html" "output.pdf"
```

### CRÍTICO: remover Google Fonts antes de generar
El servidor no tiene acceso a fonts.googleapis.com → error `HostNotFoundError`.
Antes de llamar a wkhtmltopdf, eliminar la línea `@import url(...)` del HTML:
```bash
sed -i 's|@import url.*Barlow.*||' "archivo.html"
```
O directamente no incluirla al generar el HTML.

### Template HTML — placeholders
El template `quote-template.html` usa `{{variable}}` para:
```
{{fecha}}                → "23/03/2026"
{{cliente}}              → nombre cliente
{{forma_pago}}           → siempre "Contado" (nunca "A convenir")
{{proyecto}}             → descripción
{{fecha_entrega}}        → "30 días desde la toma de medidas"
{{material_nombre}}      → "GRANITO NEGRO BRASIL EXTRA - 20mm"
{{material_m2}}          → "3,71"
{{material_precio_unitario}} → "USD 275"
{{material_total}}       → "USD 1.020"
{{material_total_neto}}  → "USD 1.020"
{{total_pesos}}          → "$452.113"
{{grand_total}}          → "$452.113 mano de obra + USD 1.020 material"
```

### Flujo completo de generación
```
1. Leer precios de catálogos (labor.json, delivery-zones.json, material)
2. Calcular m², MO, totales
3. Generar HTML con datos reemplazados (sin @import Google Fonts)
4. wkhtmltopdf → PDF
5. Generar Excel con openpyxl (sin leer SKILL.md)
6. Copiar ambos a /mnt/user-data/outputs/
7. present_files
```

### Naming
```
"Cliente - Material - DD.MM.YYYY.pdf"
"Cliente - Material - DD.MM.YYYY.xlsx"
```
Ejemplo: `"Juan Carlos - Negro Brasil - 23.03.2026.pdf"`

---

## Precios MO con IVA — referencia rápida (labor.json × 1.21)
*Actualizado: 25/03/2026 — suba general 9%*

| SKU | Precio sin IVA | Con IVA (×1.21) |
|-----|---------------|-----------------|
| PEGADOPILETA | $53.840,17 | **$65.147** |
| AGUJEROAPOYO | $35.617,36 | **$43.097** |
| ANAFE | $35.617,36 | **$43.097** |
| REGRUESO | $13.810,06 | **$16.710** |
| COLOCACION | $49.698,65 | **$60.135** |
| CORTE45 | $6.134,74 | **$7.423** |
| FALDON | $15.336,84 | **$18.558** |
| TOMAS | $6.460,84 | **$7.818** |
| ANAFEDEKTON/NEOLITH | $53.840,17 | **$65.147** |
| COLOCACIONDEKTON/NEOLITH | $74.547,98 | **$90.203** |
| FALDONDEKTON/NEOLITH | $21.471,58 | **$25.981** |
| CORTE45DEKTON/NEOLITH | $7.668,42 | **$9.279** |
| PUL | $5.384,03 | **$6.515** |
| PUL2 | $9.111,42 | **$11.025** |
| MDF | $167.627,94 | **$202.830** |

## Flete Rosario con IVA
| SKU | Sin IVA | Con IVA |
|-----|---------|---------|
| ENVIOROS | $42.975,21 | **$52.000** (sin cambio) |
