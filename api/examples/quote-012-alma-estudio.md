# Presupuesto 012 — Alma Estudio
**Presupuesto DUX Nº:** 00005494
**Fecha:** 09/03/2026
**Cliente:** Alma Estudio (estudio de arquitectura conocido — descuento aplica)
**Proyecto:** Reforma — múltiples ambientes (antebaño + cocina)
**Localidad:** Rosario
**Plazo entrega:** 20 días desde toma de medidas (ajustado manualmente en config — obra sencilla)

---

## Material

**Granito Gris Mara Extra 2 Esp** (nacional, ARS) — SKU: GRISMARA

### Piezas

| Pieza | Ambiente | Largo | Ancho | M2 |
|---|---|---|---|---|
| 01 — Mesada | Antebaño | 1.360m | 0.550m | 0.748 m2 |
| 02 — Mesada | Cocina | 1.900m | 0.640m | 1.216 m2 |
| 03 — Mesada (ampliada) | Cocina | 1.550m | 0.550m | 0.8525 m2 |
| **TOTAL** | | | | **2.8165 ≈ 2.82 m2** |

**Notas sobre medidas:**
- Pieza 03: mesada original de 1.14m ampliada a 1.55m — se presupuesta la medida final total
- El plano indicaba "recorte de granito que posee el cliente (0.41×0.61m)" — el cliente decidió no usarlo. Se presupuesta la pieza completa igual
- No hay frentin en ninguna pieza (no figura en el plano)

### Merma
Granito nacional → NO aplica merma (piedra natural)

### Precio material
- Precio s/IVA: $185.806,03/m2
- Precio c/IVA (×1.21): $224.825,30/m2
- Bruto: 2.82 × $224.825,30 = $634.007,35
- Descuento 8% (cliente arquitecto): −$50.720,59
- **Total material: $583.286,76 ≈ $583.285,98**

---

## Mano de obra

| Tarea | SKU | Cant. | Precio unit. | Total |
|---|---|---|---|---|
| Agujero y pegado de pileta | PEGADOPILETA | 2 | $59.767,00 | $119.534,00 |
| Agujero pileta apoyo | AGUJEROAPOYO | 1 | $39.538,00 | $39.538,00 |
| Colocación | COLOCACION | 2.82 m2 | $55.170,00 | $155.579,40 |
| Flete + toma de medidas Rosario | ENVIOROS | 1 | $45.000,00 | $45.000,00 |
| **TOTAL MO** | | | | **$359.651,40** |

**Piletas:**
- Pieza 01 antebaño: bacha redonda de loza sobre mesada → **apoyo** (AGUJEROAPOYO)
- Pieza 02 cocina: Bacha Redonda Ø300 Lisa Johnson → **empotrada** (PEGADOPILETA)
- Pieza 03 cocina: bacha redonda 32cm diámetro → **empotrada** (PEGADOPILETA)

---

## Totales

| | |
|---|---|
| Subtotal | $993.657,90 |
| Descuento ($50.720,00) | −$50.720,00 |
| **TOTAL** | **$942.937,38** |

> El descuento figura en la línea de material en DUX (8% sobre GRISMARA). No aplica sobre MO.

---

## Aprendizajes / reglas confirmadas

1. **Ampliación de mesada existente** — presupuestar siempre la medida final, no la original
2. **Recorte del cliente** — no descontar m2 aunque el plano lo mencione; el cliente puede decidir no usarlo
3. **"Bacha de loza sobre mesada"** ≠ necesariamente apoyo — revisar el símbolo en planta:
   - Si hay líneas de corte en la piedra → empotrada → PEGADOPILETA
   - Si el cuenco solo apoya sin corte → apoyo → AGUJEROAPOYO
4. **Plazo de entrega** — el default es 40 días pero D'Angelo lo ajusta manualmente en DUX según complejidad
5. **Descuento arquitecto** — aplica aunque m2 < 6 si el cliente está en architects.json
6. **Cotización BNA** — se informa en el presupuesto aunque el material sea nacional (transparencia comercial)
