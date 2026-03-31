# Ejemplo 019 — Metrolatina Constructora (Edificio Muniagurria)

## Tipo
**EDIFICIO** — múltiples unidades, granito nacional ARS + granito importado USD, receptáculos de ducha simples/dobles

## Datos del cliente
- **Cliente:** Metrolatina Constructora
- **Proyecto:** Edificio Muniagurria
- **Fecha:** 13/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** A convenir

## Planos
- 6 planos PDF con nombre tipo `mesada PISO_TIPO cantidad_N.pdf`
- La cantidad de unidades se lee del nombre del archivo (`cantidad_N`) o del plano

## Material
- **Granito Negro Boreal Extra — 20mm** (nacional ARS)
- SKU: BOREALNAC (precio con IVA: $260.409/m²)
- Descuento edificio: $260.409 / 1.18 = **$220.686/m²**

## Piezas — mesadas (17.08 m² total)

| Archivo | Cant | Pieza 1 | Pieza 2 |
|---------|------|---------|---------|
| P1_2_3_01 | ×3 | 1.50×0.60 | 0.42×0.60 |
| P1_2_3_02 | ×3 | 1.50×0.60 | 0.43×0.60 |
| P1_03 | ×1 | 0.82×0.60 | 0.36×0.60 |
| P2a6_03 | ×5 | 1.63×0.60 | — |
| P4a6_01 | ×3 | 1.50×0.60 | — |
| PB_03 | ×1 | 1.47×0.60 | 0.36×0.60 |

**Formato en presupuesto:**
```
COCINAS
1.50 X 0.60 X 6 UNID
0.42 X 0.60 X 6 UNID
...
```

## Receptáculos de ducha
- 10 piezas: 1.00×0.15 m | 6 piezas: 1.15×0.15 m
- **Total: 16.9 ml**
- Material simple: 16.9 × 0.15 = 2.535 m²
- Material doble: 2.535 × 2 = 5.07 m²

## Descuento edificio
- m² Boreal mesadas (17.08) > 15 → descuento aplica
- m² Boreal receptáculos sumados al total Boreal → también con descuento
- m² Dallas receptáculos (2.535) < 15 → **sin descuento**
- Método: `precio_con_iva / 1.18` — NO restar 18%

## Cálculos — 4 PDFs generados

### PDF 1: Mesadas Boreal + Receptáculos Boreal Simple
- Material: 17.08 + 2.535 = 19.615 m² × $220.686 = **$3.769.317**
- REGRUESO simple: $7.665/ml × 16.9 = $129.538
- PEGADOPILETA ×16: $56.922 × 16 = $910.752
- Piletas Johnson E37/18 ×16: $91.861 × 16 = $1.469.776
- Flete Rosario ×3: $52.000 × 3 = $156.000
- **Total MO: $2.666.066**
- **Grand total: $6.435.383 Mano de obra + material**

### PDF 2: Mesadas Boreal + Receptáculos Boreal Doble
- Material: 17.08 + 5.07 = 22.15 m² × $220.686 = **$4.888.195**
- REGRUESO doble: $15.330/ml × 16.9 = $259.077
- PEGADOPILETA + Piletas + Flete = mismos que PDF 1
- **Total MO: $2.795.605**
- **Grand total: $7.683.800 Mano de obra + material**

### PDF 3: Mesadas Boreal + Receptáculos Dallas Simple
- Material Boreal: 17.08 m² × $220.686 = $3.769.317 (ARS)
- Material Dallas: 2.535 m² × USD 217 = **USD 550** (sin descuento)
- MO igual que PDF 1
- **Grand total: $6.435.383 + USD 550 Mano de obra + material**

### PDF 4: Mesadas Boreal + Receptáculos Dallas Doble
- Material Dallas: 5.07 m² × USD 217 = **USD 1.100**
- **Grand total: $6.564.922 + USD 1.100 Mano de obra + material**

## Reglas clave aprendidas en este ejemplo
1. **Flete**: `ceil(piezas_físicas / 6)` — 16 mesadas (cada una = 1 pieza) → ceil(16/6) = **3 fletes**
2. **Piletas edificio**: precio_con_iva / 1.05
3. **PEGADOPILETA edificio**: precio_con_iva / 1.05
4. **Descuento por material**: sumar m² del mismo material en TODO el pedido, no por pieza
5. **Grand total**: un solo ARS si todo es ARS; USD separado solo si hay material importado
6. **Etiqueta grand total**: siempre "Mano de obra + material"
7. **Receptáculos ducha simple**: solo REGRUESO ÷2, sin PUL
8. **Receptáculos ducha doble**: REGRUESO completo + material ×2
