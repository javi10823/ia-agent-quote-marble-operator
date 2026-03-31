# Fórmulas de Cálculo — D'Angelo Marmolería

## Unidad de medida

Todos los materiales se calculan en **m2**.
Los zócalos, alzas y frentines se suman al m2 total de la pieza — no se listan aparte.

> **Alto estándar de zócalo: 0.05m (5cm)** — usar cuando el cliente no especifica alto.

---

## Cálculo base

```
m2 = largo (m) × ancho (m)
```

**Regla de suma de piezas:** NO redondear piezas individualmente. Sumar directo y redondear el total a 3 decimales.
```
m2_total = largo1×ancho1 + largo2×ancho2 + ...
```
Ejemplo: 2.10×0.60 + 2.10×0.05 + 0.60×0.05 = 1.26 + 0.105 + 0.030 = **1.395 m2**


---

### Reglas de medición — siempre aplicar

- **Medida mayor:** si el plano muestra 2 cotas en el mismo eje → usar la más larga
- **Cotas internas:** centros de pileta, huecos entre piletas, distancias internas → ignorar, usar exterior total
- **Formas no rectangulares:** trapecio, L irregular → cotizar ancho máximo × largo máximo (rectángulo envolvente)

---

## Mesada simple

```
m2 = largo × ancho

Ejemplo: 1.65m × 0.70m = 1.155 m2
```

---

## Mesada con zócalos / alzas

Los zócalos y alzas se calculan como rectángulos y se suman al m2 de la mesada.

```
m2 zócalo = largo_del_tramo (m) × alto_zócalo (m)

Ejemplo plano parrillero:
  Mesada:           1.65 × 0.70  = 1.1550 m2
  Zócalo superior:  1.65 × 0.05  = 0.0825 m2
  Zócalo izquierdo: 0.70 × 0.05  = 0.0350 m2
  Zócalo derecho:   0.70 × 0.05  = 0.0350 m2
  ─────────────────────────────────────────
  TOTAL:                           1.3075 m2
```

---

## Mesada en L

Se calcula cada tramo por separado y se suman.

```
Tramo A: largo_A × ancho_A
Tramo B: largo_B × ancho_B
Total = Tramo A + Tramo B + zócalos si hubiere

Ejemplo:
  Tramo A: 2.41 × 0.60 = 1.446 m2
  Tramo B: 1.37 × 0.60 = 0.822 m2
  Total mesada: 2.268 m2
  (+ zócalos si aplica)
```

---

## Alzas en tramos

Cuando el alza va en tramos (no continua), se calcula cada tramo por separado.

```
Alza tramo 1: largo × alto
Alza tramo 2: largo × alto
...
Total alzas = suma de todos los tramos
```

---

## Frentin / Regrueso

El frentin se calcula igual que un zócalo — como rectángulo — y se suma al m2 total.

```
m2 frentin = largo_frente (m) × alto_frentin (m)
```

Si el frentin figura en el plano, calcularlo directamente sin preguntar.
Si NO figura en el plano, preguntar al cliente si lleva frentin o regrueso.
Para piedra sinterizada de 12mm (Dekton, Neolith, Laminatto, Puraprima)
siempre sugerir frentin por el perfil fino.

El frentin también genera ítems de **mano de obra** adicionales que se cobran
por metro lineal (ml), independientemente del m2 de material:

### Mano de obra de frentin/regrueso — CRÍTICO

**Regrueso** (granito, mármol, Silestone, Purastone, materiales 20mm):
- Es el canto visible de la piedra — no es una pieza pegada, es el mismo material terminado
- **SÍ suma m² al total de material:** `m² regrueso = ml_total × alto` (ej: 6.27ml × 0.05m = 0.31 m²)
- SKU MO: `REGRUESO` × ml total — **NUNCA FALDON ni CORTE45**
- En PDF/Excel bloque material: 1 sola línea informativa `REGRUESO  X.XX ml` (sin desglose por tramo)
- Los m² están incluidos en el total general — no se listan como fila separada con precio

**Faldón** (Dekton, Neolith, Laminatto, Puraprima — sinterizados 12mm):
- SKU: `FALDONDEKTON/NEOLITH` × ml + `CORTE45DEKTON/NEOLITH` × ml×2

| Material | SKU MO | Cálculo |
|---|---|---|
| Granito / Mármol / Silestone / Purastone | REGRUESO | ml_total × precio_regrueso |
| Dekton / Neolith / Laminatto / Puraprima | FALDONDEKTON/NEOLITH + CORTE45DEKTON/NEOLITH | ml×faldon + ml×2×corte45 |

### Ejemplo — Vanitorys con frentin Neolith

```
Vanitoy 1 frentin: 1.503 × 0.180 = 0.2705 m2  →  1.503 ml
Vanitoy 2 frentin: 1.360 × 0.100 = 0.1360 m2  →  1.360 ml
Total frentin: 0.4065 m2  →  2.863 ml

Mano de obra (precios en labor.json):
  Faldon Neolith (FALDONDEKTON/NEOLITH):   2.863 ml × precio_labor
  Corte 45 Neolith (CORTE45DEKTON/NEOLITH): 2.863 ml × 2 × precio_labor
```

---

## Isla con patas laterales

Las patas laterales de una isla son piezas independientes que se calculan como rectángulos
y se suman al m2 total. Pueden tener frentin propio (frentin lateral de pata).

```
Pata exterior: largo_pata × ancho_visible
Pata interior: largo_pata × ancho_visible

Frentin lateral pata: ml_frente_pata × alto_frentin
```

---

## Solías y umbrales

Se calculan como rectángulos simples.

```
m2 = largo × ancho

Ejemplo: 0.73 × 0.27 = 0.197 m2
```

Si son varias piezas se suman todas.

---

## Escaleras

Cada escalón se calcula por separado — NO se usa el m2 total corrido.

```
Huella: largo × profundidad_huella
Contrahuella: largo × alto_contrahuella

Por escalón: huella + contrahuella
Total: suma de todos los escalones
```

---

## Merma — Solo materiales sintéticos

Aplica únicamente para: **Silestone, Dekton, Neolith, Puraprima, Purastone, Laminatto**
No aplica para piedra natural (granito, mármol).

> **GRANITO NEGRO BRASIL — regla especial:** NUNCA se cobra merma, sin excepción, independientemente del m² trabajado.

### Tamaño de placa estándar

| Tipo | Dimensiones | M2 por placa | Materiales |
|---|---|---|---|
| Especial | 3.20m × 1.60m | 5.12 m2 | Puraprima, Dekton, Neolith, Laminatto (confirmado) |
| Estándar | 3.00m × 1.40m | 4.20 m2 | Silestone, Purastone (pendiente confirmar modelos individuales) |

### Regla de merma — TODOS los sintéticos

**Regla universal:** la merma solo aplica cuando el **desperdicio** es **≥ 1 m2**.

**El material principal SIEMPRE se cobra por m2 exactos.**
La merma/desperdicio se ofrece al cliente como línea separada **SOBRANTE** — nunca se suma al m2 principal.

```
desperdicio = m2_referencia - m2_necesarios

SI desperdicio < 1.0  → NO hay sobrante → cobrar m2_necesarios exactos
SI desperdicio >= 1.0 → ofrecer SOBRANTE = desperdicio / 2
                        Material principal: m2_necesarios exactos
                        Línea SOBRANTE: (desperdicio/2) m2 × mismo precio unitario
```

**¿Qué es m2_referencia según material?**
- **Silestone y Dekton** → m2_referencia = **media placa** (placa / 2)
- **Purastone, Neolith, Puraprima, Laminatto** → m2_referencia = **placa entera**

> **Excepción — piezas muy pequeñas:** m2 total < 0.5 m2 → NO aplica.
> **Excepción — material en stock:** consultar `stock.json` — si el material figura y el trabajo
> entra en una pieza disponible, aplicar sin merma. Para que una pieza sea válida debe cumplir:
>
> 1. **Dimensión física:** el largo de la pieza ≥ largo máximo del trabajo (no solo m2 total)
> 2. **Margen mínimo 20%:** `(m2_pieza - m2_trabajo) / m2_pieza ≥ 0.20` — no usar piezas justas
>
> Si no hay ninguna pieza que cumpla ambas condiciones → aplicar regla de merma normal.
> El agente NO pregunta al cliente sobre stock — lo verifica directamente en stock.json.

### Ejemplo — Purastone Gris Zen (referencia = placa entera 4.20 m2)

```
M2 necesarios: 2.03
desperdicio = 4.20 - 2.03 = 2.17 ≥ 1.0 → ofrecer sobrante
sobrante = 2.17 / 2 = 1.085 m2

Línea principal:  2.03 m2 × USD550 = USD1.116
Línea SOBRANTE:   1.085 m2 × USD550 = USD597  (separada, opcional)
Grand total mat:  USD1.116 + USD597 = USD1.713
```

### Ejemplo — Silestone Gris Expo (referencia = media placa 2.10 m2)

```
M2 necesarios: 2.03
desperdicio = 2.10 - 2.03 = 0.07 < 1.0 → sin sobrante
Línea principal: 2.03 m2 × USD665 = USD1.350
```

### Ejemplo — Silestone con sobrante (referencia = media placa 2.10 m2)

```
M2 necesarios: 0.80
desperdicio = 2.10 - 0.80 = 1.30 ≥ 1.0 → ofrecer sobrante
sobrante = 1.30 / 2 = 0.65 m2

Línea principal: 0.80 m2 × precio = X
Línea SOBRANTE:  0.65 m2 × precio = Y
```

### Sobrante de placa

Cuando queda material remanente significativo luego del corte, se puede ofrecer
al cliente adquirir el sobrante como ítem opcional adicional.

```
Sobrante = m2_placa - m2_necesarios - merma_cobrada
Se cotiza al mismo precio unitario del material (con IVA).
```

**Presentación en el presupuesto:**
- Se muestra como un bloque de material **separado e independiente** con su propio subtotal (Total USD o Total ARS)
- El grand total suma el material principal + el sobrante
- Se aclara como opcional para que el cliente decida si lo quiere

Ejemplo:
```
PURASTONE GRIS ZEN    2.03    USD550    USD1116
2,89 × 0,62
3,49ML × 0,07 ZOC.
                      Total USD         USD1116

SOBRANTE              1.085   USD550    USD597
                      Total USD         USD597

PRESUPUESTO TOTAL: $XXX MO + USD1713 material
```

---

## Descuentos

Los descuentos se aplican a criterio del negocio. No hay regla fija de porcentaje.
Casos habituales: obras grandes por volumen, clientes frecuentes, negociación puntual.

```
Total material bruto = m2 × precio_unitario
Descuento = monto fijo o porcentaje acordado
Total material neto = total bruto - descuento
```

Se muestra como línea separada en el presupuesto.

---

## Perforaciones y agujeros

Las perforaciones no afectan el cálculo de m2 — no se descuenta el área
del agujero de la superficie total.

| Ítem | Cuándo se usa |
|---|---|
| Agujero y pegado de pileta | Pileta empotrada o bajo cubierta — incluye perforación de grifería monocomando |
| Agujero pileta apoyo | Pileta de apoyo — solo perforación, sin pegado |
| Agujero anafe | Perforación para anafe — se cobra aparte |
| Agujero tomas | Tomacorrientes — se cobra por unidad |

---

## Frentin por espesor aparente

Cuando el plano especifica que una pieza debe verse con mayor espesor que el material (ej: piedra sinterizada 12mm pero se pide apariencia de 40mm), se resuelve con un **frentin a 45° en los cantos expuestos**.

**Regla:**
- Aplica a cualquier pieza donde el espesor especificado en plano > espesor real del material
- Los cantos a frentinar son los lados **libres** (sin pared) de esa pieza
- Se calcula igual que cualquier frentin:
  - Material: ml × espesor_aparente (en metros) = m2 adicionales
  - MO: FALDONDEKTON/NEOLITH o FALDON según material + CORTE45 × 2

**Ejemplo confirmado — Estante Hernandez (Dekton 12mm, espesor aparente 40mm):**
- Estante: 0.68 × 0.41m, lados libres: frente (0.68ml) y lateral derecho (0.41ml)
- Frentin frente estante: 0.68 × 0.04 = 0.0272 m2 / 0.68 ml
- Frentin lateral estante: 0.41 × 0.04 = 0.0164 m2 / 0.41 ml

> Detectar en plano: cuando figura "X cm de espesor" en una pieza y ese valor supera el espesor del material elegido.

---

## Refuerzo granito

El refuerzo granito se aplica cuando la mesada lleva **frentin en materiales de piedra sinterizada**
(Dekton, Neolith, Puraprima, Laminatto). Provee soporte estructural al canto fino de 12mm.

- **SKU:** `MDF` (REFUERZO-SUPLEMENTO en DUX)
- **Cantidad:** 1 (por trabajo, no por m2)
- **Cuándo aplica:** mesada con frentin en Dekton, Neolith, Puraprima o Laminatto
- **No aplica:** Silestone, Purastone, Granito, Mármol (20mm tienen espesor suficiente)

---

## Precio unitario USD — cálculo y display

El precio unitario se calcula aplicando IVA al precio del JSON:

```
precio_unitario_usd = price_usd (JSON, sin IVA) × 1.21
```

**Regla de display — truncar siempre (floor):**
El precio unitario USD se muestra siempre como entero, truncando los decimales.

```
precio_unitario_usd = floor(price_usd × 1.21)
```

- 550.00 × 1.21 = 665.50 → **665**
- 454.54 × 1.21 = 549.99 → **549**

**Total material:** `round(m2 × precio_unitario_usd)` — entero, sin decimales.

---

## Precio de colocación por tipo de material

Los precios de colocación están en `labor.json` — no se duplican aquí.
Usar siempre el SKU correspondiente al material:

- Estándar (granito, silestone, purastone, mármol) → SKU: `COLOCACION`
- Piedra sinterizada (Dekton, Neolith, Laminatto, Puraprima) → SKU: `COLOCACIONDEKTON`

> No intercambiar SKUs entre categorías.

---

## Orden de cálculo recomendado

```
1. Calcular m2 de cada pieza (mesada, zócalos, alzas, frentin, patas, etc.)
2. Sumar todos los m2 → total bruto
3. Verificar si aplica merma (solo sintéticos, no en piezas < ~0.5 m2)
4. Aplicar merma si corresponde → total a cobrar
5. Aplicar descuento si hay acuerdo comercial
6. Multiplicar total m2 × precio unitario (con IVA) → total material
7. Calcular mano de obra:
   a. Colocación (por m2, al precio del material correspondiente)
   b. Agujeros y perforaciones (por unidad, tipo correcto)
   c. Flete + toma de medidas (por localidad)
   d. Faldon + corte 45 si hay frentin (por ml, SKU correcto según material)
   e. Pileta Johnson u otros ítems especiales si aplica
8. Presentar total ARS + total USD por separado
```
---

## Reglas de catálogo

### Variantes LEATHER
Si un material tiene variante LEATHER y otra sin LEATHER → usar **siempre la sin LEATHER**
salvo que el cliente diga explícitamente "leather".

### Pulido (SKU PUL vs PUL2)
- **PUL** → usar siempre para granito, mármol, Silestone, Purastone (materiales 20mm)
- **PUL2** → solo para Dekton, Neolith, Laminatto, Puraprima (sinterizados)
Regla: siempre el más económico salvo que sea sinterizado.

