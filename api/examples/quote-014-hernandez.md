# Presupuesto 014 — Hernandez
**Fecha:** 10/03/2026
**Cliente:** Hernandez
**Arquitecto:** Arq. Rafael Araya (conocido — descuento aplica)
**Forma de pago:** 80% seña / 20% contra entrega
**Proyecto:** Mesada Toilete
**Localidad:** Rosario
**Plazo entrega:** 20 días desde toma de medidas (excepción puntual — config no modificado)

---

## Lectura del plano

- Líneas tachadas (hatching) en lado izquierdo y lado superior → **pared** → sin frentin en esos lados
- Lados libres: frente (0.68ml) y lateral derecho (0.41ml) → frentin 15cm anotado en plano para la mesada
- **Pileta:** plano dice "DESAGUE Ø12cm" sin especificar modelo → **pileta de apoyo** → SKU: `PILETAAPOYODEKTON/NEO`
- Agujero grifería a 23cm del centro de la bacha a 45° → **incluido en SKU de pileta, no se cobra por separado**
- Estante suelto 0.68 × 0.41 × **4cm de espesor** → Dekton es 12mm → espesor aparente 40mm → frentin a 45° en lados libres (frente 0.68ml + lateral 0.41ml, iguales que la mesada)
- **Material en stock** → sin merma, cobrar m2 exactos

---

## Material

**Dekton Soke - 12MM** (importado, USD, piedra sinterizada) — SKU: DEKSOKE — `in_stock: true`

### Piezas

| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada | 0.68m | 0.41m | 0.2788 m2 |
| Frentin mesada frente | 0.68m | 0.15m | 0.1020 m2 / 0.68ml |
| Frentin mesada lateral der. | 0.41m | 0.15m | 0.0615 m2 / 0.41ml |
| Estante suelto | 0.68m | 0.41m | 0.2788 m2 |
| Frentin estante frente | 0.68m | 0.04m | 0.0272 m2 / 0.68ml |
| Frentin estante lateral der. | 0.41m | 0.04m | 0.0164 m2 / 0.41ml |
| **TOTAL** | | | **0.7647 m2** |

**Total frentin ml: 2.18ml** (0.68 + 0.41 mesada + 0.68 + 0.41 estante)

**Sin merma** — material en stock (`in_stock: true`) → cobrar 0.76 m2 exactos

### Precio material
- Precio s/IVA: USD 759.00/m2
- Precio c/IVA (×1.21): USD 918.39/m2
- Bruto: 0.76 × USD 918.39 = USD 702.29
- Descuento 5% (Arq. Araya — arquitecto conocido): −USD 35.11
- **Total material neto: USD 667.18**

---

## Mano de obra

| Tarea | SKU | Cant. | Precio unit. | Total |
|---|---|---|---|---|
| Agujero pileta apoyo Dekton/Neolith | PILETAAPOYODEKTON/NEO | 1 | $59.767,00 | $59.767,00 |
| Colocación Dekton/Neolith | COLOCACIONDEKTON/NEOLITH | 1.0 m2 | $82.755,00 | $82.755,00 |
| Armado faldon Dekton/Neolith | FALDONDEKTON/NEOLITH | 2.18 ml | $23.835,00 | $51.960,30 |
| Corte a 45 Dekton/Neolith | CORTE45DEKTON/NEOLITH | 4.36 ml | $8.513,00 | $37.116,68 |
| Refuerzo suplemento | MDF | 1 | $186.082,00 | $186.082,00 |
| Flete + toma de medidas Rosario | ENVIOROS | 1 | $45.000,00 | $45.000,00 |
| **TOTAL MO** | | | | **$462.680,98** |

**Notas MO:**
- Colocación: 0.76 m2 real → se cobra **1 m2 mínimo** → `max(0.76, 1.0) = 1.0`
- Faldon 2.18ml = mesada (0.68+0.41) + estante (0.68+0.41) → todos los frentines de todas las piezas
- Corte 45 × 2 lados × 2.18ml = 4.36ml total
- MDF (refuerzo) → 1 unidad por trabajo, aplica por frentin en Dekton

---

## Total

```
PRESUPUESTO TOTAL: $462.681 mano de obra + USD667 material
```
*(grand total siempre en enteros, sin decimales)*

---

## Aprendizajes / reglas confirmadas

1. **Líneas tachadas en plano = pared** → sin frentin en ese lado. Lados sin tachar = cantos libres.
2. **DESAGUE Ø sin modelo de pileta** → siempre pileta de apoyo. Solo es empotrada si se especifica modelo (ej: "Bacha Johnson Ø300", "bacha 32cm empotrada"). Ante la duda → preguntar.
3. **Agujero grifería** → siempre incluido en el SKU de pileta (PEGADOPILETA / PILETADEKTON / PILETAAPOYODEKTON). Nunca cobrar por separado, nunca preguntar.
4. **Espesor aparente** → cuando el plano especifica espesor mayor al del material (ej: 4cm en Dekton 12mm), se resuelve con frentin a 45° en los cantos libres de esa pieza. Material: ml × espesor (m) = m2. MO: FALDON + CORTE45.
5. **Frentin total ml** → sumar frentines de todas las piezas del trabajo para calcular FALDON y CORTE45.
6. **Stock sin merma** → `in_stock: true` en JSON del material → cobrar m2 exactos. `in_stock: false` → aplicar reglas de merma.
7. **Colocación mínimo 1 m2** → si m2 total < 1.0 → cobrar 1.0. Aplica para todos los materiales.
8. **Grand total sin decimales** → el box de PRESUPUESTO TOTAL siempre muestra enteros. Las filas de detalle mantienen decimales.
9. **SKUs diferenciados Dekton/Neolith** → pileta apoyo: `PILETAAPOYODEKTON/NEO`, colocación: `COLOCACIONDEKTON/NEOLITH`, faldon: `FALDONDEKTON/NEOLITH`, corte 45: `CORTE45DEKTON/NEOLITH`. Nunca usar SKUs estándar para estos materiales.
10. **SKU MDF** → refuerzo granito en DUX. 1 unidad por trabajo cuando hay frentin en Dekton/Neolith/Puraprima/Laminatto.
11. **Plazo de entrega** → agente usa default config.json (40 días). D'Angelo ajusta manualmente por excepción sin tocar config.
