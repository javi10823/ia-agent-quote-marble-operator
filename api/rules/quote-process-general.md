# Proceso de Presupuesto — D'Angelo Marmolería

## Descripción general

Para confeccionar un presupuesto se necesita recolectar información específica
antes de generarlo. El agente debe reunir todos los datos requeridos ya sea del
cliente directamente o del plano/boceto que aporte. Máximo 4 opciones de material
por presupuesto.

---

---

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
- [ ] ¿Cuál es la fecha de entrega / plazo? — si está en el enunciado usarlo directamente, si no → usar el valor por defecto de config.json (40 días). No preguntar.
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
