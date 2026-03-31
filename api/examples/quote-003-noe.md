# Ejemplo 003 — NOE

## Datos del cliente
- **Cliente:** NOE
- **Proyecto:** Mesada de cocina (mixta: importado + nacional)
- **Fecha:** 24/2/2026
- **Forma de pago:** ctdo - cheque 0-15 días
- **Fecha de entrega:** 20/30 días desde la toma de medidas

## Tipo de trabajo
Mesada de cocina con zócalos — interior
Caso especial: **dos materiales en el mismo presupuesto** (importado + nacional)

## Materiales

### Material 1 — Silestone Blanco Norte 20MM (cuarzo, importado USD)
- SKU: SILESTONENORTE

#### Medidas

| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada | 2.10m | 0.60m | 1.260 m2 |
| Zócalo (3.30 ml × 0.05m) | 3.30m | 0.05m | 0.165 m2 |
| **TOTAL** | | | **1.425 m2** |

#### Merma
- Material sintético (Silestone) → aplica merma
- Placa estándar: 4.20 m2, mitad: 2.10 m2
- M2 necesarios: 1.425 < 2.10 → SÍ aplica merma
- Sobrante: 4.20 - 1.425 = 2.775 m2
- Merma a cobrar: 2.775 / 2 = 1.3875 m2
- **M2 a cobrar: 1.425 + 1.3875 = 2.8125 m2**

> ⚠️ Nota: el presupuesto original muestra 1.425 m2 — sin aplicar merma.
> Verificar con D'Angelo si en este caso particular se aplicó merma o no.

#### Cálculo de material
```
Precio catálogo s/IVA: USD 429.00/m2
Precio c/IVA: USD 429 × 1.21 = USD 519.09/m2 → USD 519 en presupuesto
Total material: 1.425 × USD 519 = USD 739
```

---

### Material 2 — Granito Gris Mara (granito, nacional ARS)
- SKU: GRISMARA

#### Medidas

| Pieza | Largo | Ancho | M2 |
|---|---|---|---|
| Mesada | 2.00m | 0.60m | 1.200 m2 |
| **TOTAL** | | | **2.00 m2** |

#### Merma
- Granito nacional = piedra natural → NO aplica merma
- **M2 a cobrar: 2.00 m2**

#### Cálculo de material
```
Precio catálogo s/IVA: ARS 166.529/m2 (aprox — precio lista dic 2025)
Precio c/IVA: ARS 166.529 × 1.21 = ARS 201.500/m2
Total material: 2.00 × ARS 201.500 = ARS 403.000
```

---

## Mano de obra

| Ítem | SKU | Cantidad | Precio unit. | Total |
|---|---|---|---|---|
| Agujero y pegado de pileta | PEGADOPILETA | 1 | $59.767 | $59.767 |
| Agujero anafe | ANAFE | 1 | $39.538 | $39.538 |
| Flete + toma de medidas Rosario | ENVROSARIO | 1 | $45.000 | $45.000 |
| Colocación | COLOCACION | 1.425 m2 | $55.170 | $78.617 |
| **TOTAL PESOS** | | | | **$222.922** |

## Totales
```
Total material nacional ARS: $403.000
Total mano de obra ARS:      $222.922
─────────────────────────────────────
TOTAL ARS:                   $625.922

PRESUPUESTO TOTAL: $625.922 mano de obra + USD739 material
```

## Notas del ejemplo
- Caso mixto: un material importado (USD) y uno nacional (ARS) en el mismo presupuesto
- La colocación se calcula solo sobre los m2 del material importado (1.425) — no sobre el total
- El granito nacional se suma directamente al total ARS
- Llevar el anafe: presupuesto incluye agujero de anafe como ítem separado
- Zócalos especificados en ml (3.30ml × 0.05m) — convertir a m2 para el cálculo
