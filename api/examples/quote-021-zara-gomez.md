# Ejemplo 021 — Zara Gomez (Particular)

## Tipo
**PARTICULAR** — cocina con mesada en L + mesada recta separada, granito nacional ARS, zócalos, 2 bachas que trae el cliente

## Datos del cliente
- **Cliente:** Zara Gomez
- **Proyecto:** Cocina
- **Fecha:** 14/03/2026
- **Forma de pago:** A convenir
- **Fecha de entrega:** A convenir
- **Localidad:** Rosario

## Material
- **Granito Negro Boreal Extra — 20mm** (nacional ARS)
- SKU: BOREAL
- Precio con IVA: $260.409/m²
- Total < 6 m² → sin descuento

## Piezas

### Mesada en L (2 tramos que se complementan)
- **Tramo 1** (lateral): 1.53 × 0.56 = 0.8568 m²
- **Tramo 2** (inferior): 1.315 × 0.60 = 0.789 m²
- La cota exterior 1.86 = 0.56 + 1.315 → es redundante, NO es una pieza
- Unión a 90° → sin CORTE45

### Mesada recta (separada, en medio va la cocina)
- 1.885 × 0.60 = 1.131 m²

### Zócalos (mismo material, sin MO — el cliente los pega)
- 1.53 × 0.05 = 0.0765 m² (lateral tramo 1 — marca verde)
- 1.86 × 0.05 = 0.093 m² (trasero de la L — cota exterior completa)
- 1.885 × 0.05 = 0.09425 m² (atrás mesada recta)
- Alto default 5cm aplicado (no había cota en el plano)

## m² total
| Concepto | m² |
|----------|-----|
| Tramo 1 L | 0.8568 |
| Tramo 2 L | 0.7890 |
| Mesada recta | 1.1310 |
| Zócalo lateral L (1.53) | 0.0765 |
| Zócalo trasero L (1.86) | 0.0930 |
| Zócalo mesada recta (1.885) | 0.0943 |
| **TOTAL** | **3.0406 m²** |

`$260.409 × 3.0406 = $791.800`

## PUL — cantos sin zócalo
| Pieza | Cantos libres | ml |
|-------|--------------|-----|
| Tramo 1 (1.53×0.56) | Frente (zócalo atrás) | 0.56 ml |
| Tramo 2 (1.315×0.60) | Frente + lateral der | 1.915 ml |
| Mesada recta (1.885×0.60) | Frente + 2 laterales (zócalo atrás) | 3.085 ml |
| **TOTAL PUL** | | **5.56 ml** |

## Mano de obra
| Ítem | SKU | Cant | Precio | Total |
|------|-----|------|--------|-------|
| Agujero y pegado de pileta | PEGADOPILETA | 2 | $59.768 | $119.536 |
| Pulido de cantos | PUL | 5.56 ml | $5.977 | $33.232 |
| Colocación | COLOCACION | 2.78 m² | $55.170 | $153.196 |
| Flete + toma de medidas Rosario | ENVIOROS | 1 | $52.000 | $52.000 |
| **TOTAL MO** | | | | **$357.964** |

## Grand total
**$1.149.764 Mano de obra + material**

## Reglas clave aplicadas en este ejemplo
1. **Mesada en L = 2 tramos complementarios** — el 1.86 era cota exterior redundante (0.56 + 1.315 = 1.875 ≈ 1.86), no se cobra como pieza
2. **Unión L a 90°** — sin CORTE45. Solo si el cliente lo pide explícitamente se agrega CORTE45 en MO (el material no cambia)
3. **Zócalos = material, sin MO** — el cliente los pega. Alto default 5cm cuando no hay cota
4. **PUL solo en cantos sin zócalo** — el canto que lleva zócalo no se pula
5. **Bachas traídas por el cliente** → solo PEGADOPILETA, sin cobrar la pileta
6. **Sin descuento** — 2.95 m² < 6 m² y no es arquitecta
