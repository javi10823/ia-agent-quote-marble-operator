# Ejemplo 023 — WERK Constructora (Edificio Werk 34 — Blanco Paloma)

## Tipo
**EDIFICIO** — baños, Purastone Blanco Paloma USD, pileta bajo mesada Ferrum Cadria (trae cliente), zócalos solo atrás

## Datos del cliente
- **Cliente:** WERK Constructora
- **Proyecto:** Edificio Werk 34 — Mendoza 525, Rosario
- **Fecha:** 14/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** A convenir

## Planos utilizados
| Plano | Tipo | Cant | Notas |
|-------|------|------|-------|
| MB1 | Baño secundario | 24 (12 izq + 12 der) | Zócalo solo atrás 14cm, Ferrum Cadria bajo mesada (trae cliente) |
| MB2 | Baño principal | 24 (12 izq + 12 der) | Zócalo solo atrás 14cm, Ferrum Cadria bajo mesada (trae cliente) |

## Material
- **Purastone Blanco Paloma — 20mm** (USD)
- SKU: PALOMA — USD 337.17 sin IVA
- Precio con IVA: floor(337.17 × 1.21) = USD 407/m²
- Descuento edificio: floor(407 / 1.18) = **USD 344/m²**
- Total m² > 15 → descuento aplica

## Desglose de m²

### Mesadas
| Pieza | Medida | Cant | m² |
|-------|--------|------|----|
| MB1 mesada | 1.31×0.50 | ×24 | 15.72 |
| MB2 mesada | 1.26×0.50 | ×24 | 15.12 |
| **Subtotal mesadas** | | | **30.84** |

### Zócalos baños (solo atrás, alto 14cm por plano)
| Pieza | Medida | Cant | m² |
|-------|--------|------|----|
| MB1 zócalo atrás | 1.31×0.14 | ×24 | 4.4016 |
| MB2 zócalo atrás | 1.26×0.14 | ×24 | 4.2336 |
| **Subtotal zócalos** | | | **8.635** |

**TOTAL MATERIAL: 39.48 m² × USD 344 = USD 13.581**

## Mano de obra (todos ÷1.05 excepto flete)
| Ítem | SKU | Cant | Precio c/desc | Total |
|------|-----|------|---------------|-------|
| Agujero y pegado de pileta | PEGADOPILETA | 48 | $56.922 | $2.732.256 |
| Flete Rosario + toma de medidas | ENVIOROS | **5** | $52.000 | $260.000 |
| **TOTAL MO** | | | | **$2.992.256** |

**Grand total: $2.992.256 + USD 13.581 Mano de obra + material**

## Piezas físicas para flete
- MB1: 24 piezas | MB2: 24 piezas = 48 piezas
- ceil(48/6) = 8 viajes teóricos → operador ajustó a **5** (entran más por viaje)

## Reglas clave aplicadas
1. **Ferrum Cadria "de bajo poner"** → bajo mesada, trae el cliente → solo PEGADOPILETA, sin cobrar la pileta
2. **Zócalos baños = material** del mismo tipo, sin MO (el cliente los pega)
3. **Alto zócalo = 14cm** según cota explícita en plano MB1/MB2
4. **PEGADOPILETA ÷1.05** en edificios
5. **Flete sin descuento** — se cobra a precio normal con IVA
6. **Flete ajustable** por el operador según capacidad real del camión
