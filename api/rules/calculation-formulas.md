# Formulas de Calculo — D'Angelo Marmoleria

## Unidad de medida

Todos los materiales en **m2**. Zocalos, alzas, frentines se suman al m2 total — no se listan aparte.

> **Alto estandar zocalo: 0.05m (5cm)** — usar cuando el cliente no especifica.

## Calculo base

```
m2 = largo (m) x ancho (m)
```

**NO redondear piezas individualmente.** Sumar directo, redondear total a 2 decimales.

### Politica de redondeo — CENTRALIZADA

| Valor | Redondeo | Ejemplo |
|-------|----------|---------|
| m² por pieza | SIN redondear | 3.00 x 0.62 = 1.86 |
| m² total | round 2 dec | 3.8844 → 3.88 |
| Precio USD unitario | floor (truncar) | floor(379.85 x 1.21) = 459 |
| Total material USD | round entero | round(3.88 x 459) = 1781 |
| Precio ARS MO | round entero | round(49698.65 x 1.21) = 60135 |
| Colocacion qty | = m² total (2 dec) | max(3.88, 1.0) = 3.88 |

### Reglas de medicion
- **Medida mayor:** 2 cotas en mismo eje → usar la mas larga
- **Cotas internas:** c/p, huecos entre piletas → ignorar, usar exterior total
- **Formas no rectangulares:** ancho max x largo max (rectangulo envolvente)

---

## Mesada simple
```
m2 = largo x ancho
Ej: 1.65 x 0.70 = 1.155 m2
```

## Mesada con zocalos/alzas
Zocalos/alzas = rectangulos sumados al m2.
```
m2 zocalo = largo_tramo x alto_zocalo
Ej: Mesada 1.65x0.70=1.155 + Zoc sup 1.65x0.05=0.0825 + Zoc izq 0.70x0.05=0.035 + Zoc der 0.70x0.05=0.035 = 1.3075 m2
```
⛔ **Cada zocalo es una pieza SEPARADA en el despiece** — NUNCA sumar los ml de todos los zocalos en una sola linea.
- Correcto: `1.74ML X 0.07 ZOC` + `1.55ML X 0.07 ZOC` + `0.75ML X 0.07 ZOC` (3 lineas)
- Incorrecto: `4.04ML X 0.07 ZOC` (1 linea con todo sumado)

## Mesada en L
Cada tramo por separado, sumar.
```
Tramo A: largo_A x ancho_A + Tramo B: largo_B x ancho_B + zocalos
```

## Alzas en tramos
Cada tramo por separado, sumar.

## Frentin / Regrueso

### ⛔ Faldón/frentín listado como pieza separada en brief → MO SOLO
Cuando el operador lista el faldón como **concepto separado de material**
con solo ml declarados (ej: `"Faldón recto — 2.90 ml"`, sin altura ni
m²), **NO sumar m² al material**. El material ya está contabilizado en
las piezas del despiece (planilla de cómputo del comitente). El faldón
solo aporta MO:
- SKU `FALDON` (o `FALDONDEKTON/NEOLITH` sinterizados) × ml.
- CORTE45 solo si operador lo pide explícito.

Caso DINALE 14/04/2026: brief dijo `"Faldón recto — 2.90 ml (listarlo
como concepto separado de material)"`. Al agregarlo como pieza con altura
default (0.05m) se duplicaba: sumaba 0.145 m² al material bruto **y**
se cobraba como Armado frentín. El calculator ahora detecta piezas cuya
descripción empieza con `faldón`/`frentín` y las excluye del m² de material.

```
m2 frentin = largo_frente x alto_frentin   # SOLO si el operador declara altura
```
Si figura en plano con altura → calcular directo y sumar al m². Si solo
hay ml → MO únicamente. Sinterizado 12mm → sugerir frentin.

### Mano de obra frentin/regrueso — CRITICO

**Regrueso** (granito, marmol, Silestone, Purastone — 20mm):
- Canto visible de la piedra, no pieza pegada
- SI suma m²: `ml_total x alto` (ej: 6.27ml x 0.05m = 0.31 m²)
- SKU MO: `REGRUESO x ml` — NUNCA FALDON ni CORTE45
- PDF/Excel: 1 linea `REGRUESO X.XX ml` (sin desglose por tramo)

**Faldon** (Dekton, Neolith, Laminatto, Puraprima — sinterizados 12mm):
- SKU: `FALDONDEKTON/NEOLITH x ml` + `CORTE45DEKTON/NEOLITH x ml x 2`

| Material | SKU MO | Calculo |
|---|---|---|
| Granito/Marmol/Silestone/Purastone | REGRUESO | ml_total x precio |
| Dekton/Neolith/Laminatto/Puraprima | FALDON + CORTE45 | ml x faldon + ml x 2 x corte45 |

## Isla con patas laterales
Patas = rectangulos sumados al m2. Pueden tener frentin propio.

## Solias y umbrales
`m2 = largo x ancho`. Si varias, sumar.

## Escaleras
Cada escalon por separado: huella + contrahuella. NO m2 total corrido.

---

## Merma — Solo sinteticos

Aplica: **Silestone, Dekton, Neolith, Puraprima, Purastone, Laminatto**
NO aplica: piedra natural (granito, marmol).

> **GRANITO NEGRO BRASIL — NUNCA merma, sin excepcion.**

### Tamano placa estandar

| Tipo | Dimensiones | M2 | Materiales |
|---|---|---|---|
| Especial | 3.20 x 1.60 | 5.12 m2 | Puraprima, Dekton, Neolith, Laminatto |
| Estandar | 3.00 x 1.40 | 4.20 m2 | Silestone, Purastone |

### Regla de merma

**Material principal SIEMPRE por m2 exactos.** Merma/sobrante = linea separada SOBRANTE.

```
desperdicio = m2_referencia - m2_necesarios
SI desperdicio < 1.0 → NO sobrante → cobrar m2 exactos
SI desperdicio >= 1.0 → SOBRANTE = desperdicio / 2, mismo precio unitario
```

**m2_referencia:**
- Silestone y Dekton → **media placa** (placa / 2)
- Purastone, Neolith, Puraprima, Laminatto → **placa entera**

> Excepcion piezas < 0.5 m² → NO aplica.
> Excepcion stock: si pieza de stock.json cumple `largo_pieza >= largo_trabajo` Y `(m2_pieza - m2_trabajo)/m2_pieza >= 0.20` → sin merma.

### Ejemplo Purastone (ref = placa 4.20 m2)
```
M2: 2.03 | desp = 4.20-2.03 = 2.17 >= 1.0 → sobrante = 1.085 m2
Principal: 2.03 x USD550 = USD1.116 | SOBRANTE: 1.085 x USD550 = USD597
```

### Ejemplo Silestone (ref = media placa 2.10 m2)
```
M2: 2.03 | desp = 2.10-2.03 = 0.07 < 1.0 → sin sobrante
```

### Presentacion sobrante
Bloque separado e independiente, subtotal propio. Grand total suma principal + sobrante.

---

## Descuentos
```
Total neto = total bruto - descuento (monto fijo o %)
```
Linea separada en presupuesto.

## Perforaciones y agujeros
NO se descuenta area del agujero del m2.

| Item | Cuando |
|---|---|
| PEGADOPILETA | Empotrada/bajo cubierta (incluye griferia) |
| AGUJEROAPOYO | Apoyo (incluye griferia) |
| ANAFE | Solo con evidencia en plano o enunciado |
| TOMAS | Tomacorrientes, por unidad |

> ⛔ ANAFE: solo con simbolo en plano o mencion explicita. Cocina ≠ anafe automatico.

## Frentin por espesor aparente
Espesor plano > espesor real → frentin a 45° en cantos libres.
```
Material: ml x espesor_aparente = m2 adicionales
MO: FALDON + CORTE45 x 2 (segun material)
```

## Refuerzo granito
- SKU: `MDF` | Qty: 1 por trabajo | Aplica: mesada con frentin en sinterizados (Dekton, Neolith, Puraprima, Laminatto)
- No aplica: Silestone, Purastone, Granito, Marmol

## Precio unitario USD
```
precio_unitario = floor(price_usd_json x 1.21)
total_material = round(m2 x precio_unitario)
```

## Colocacion por tipo de material
- Estandar (granito, silestone, purastone, marmol) → SKU: `COLOCACION`
- Sinterizado (Dekton, Neolith, Laminatto, Puraprima) → SKU: `COLOCACIONDEKTON`
- Minimo 1 m²: `max(m2_total, 1.0)`
- Sobre TOTAL m² incluyendo zocalos
- Estantes sueltos (no instalados) → NO colocacion (ref: quote-011)
- Sobrante/merma → NO colocacion

## Orden de calculo
```
1. m2 de cada pieza (mesada, zocalos, alzas, frentin, patas)
2. Sumar → total bruto
3. Merma (solo sinteticos, no piezas < 0.5 m2)
4. Descuento si hay acuerdo comercial
5. total m2 x precio unitario (con IVA) → total material
6. MO: colocacion, agujeros, flete+TM, faldon/corte45, pileta Johnson
7. Total ARS + Total USD separados
```

## Reglas de catalogo

### Variantes LEATHER
Sin LEATHER por defecto, salvo pedido explicito del cliente.

### Pulido (PUL vs PUL2)
- **PUL** → granito, marmol, Silestone, Purastone (20mm)
- **PUL2** → Dekton, Neolith, Laminatto, Puraprima (sinterizados)

## Reglas adicionales de ejemplos

### Stock parcial
Piezas en stock → sin merma. Piezas nuevas → merma normal. Validar dimensiones pieza por pieza. (ref: quote-028)

### Pileta integrada — SKUs especiales
PILETAINTEGRADA A 45 | PILETADESAGUEOCULTO | PILETAINTEGRADARECTA — SKUs propios en labor.json. (ref: quote-008)

### Pulido de forma
Curva/redondeo → PULIDO DE FORMA (precio fija operador). (ref: quote-026)

### Profundidad por ambiente
Cocina: 0.60m | Lavadero: 0.60m | Bano/Isla: leer del plano. (ref: quote-020)

### Grand total — formato
Enteros. Label: `"$XXX.XXX mano de obra + piletas + USD XXX material"` o `"$XXX.XXX mano de obra + material"`. (ref: quote-014, quote-019)
