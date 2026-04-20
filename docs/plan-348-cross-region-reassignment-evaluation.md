# Plan Técnico #348 — Cross-region cota reassignment (evaluación)

> **Status:** NO-GO, evidence-based.
> **Decision type:** Architectural — do not re-open without new data.
> **Revisit only if:** `pool_starved_region=true` aparece en >30% de regiones
> de planos distintos (§6), acumulando ≥10 planos de evidencia en prod.
> **Superseded by:** —

**Fecha:** 2026-04-20
**Contexto previo:** PR #344 (Plan B topology cache), #345 (rescue span_based), #346 (orphan trigger + pool_starved), #347 (context reconcile).
**Artefactos:** sin código producido. Solo análisis + simulación numérica con coordenadas reales de Erica Bernardi.

---

## 0. TL;DR (lectura de 30 segundos)

**Voto: NO-GO** para cross-region reassignment tal como fue planteado.

Razones numéricas, no intuitivas:

1. La simulación con coordenadas reales de Bernardi muestra que reassignment naive por proximidad **no resuelve R1/R2** (todas las cotas rejected están más cerca de R3 que de las regiones starved).
2. La simulación reveló un bug más profundo que no estaba en radar: **R3 mide INCORRECTAMENTE** (2.05 en vez de 1.60) con confidence 0.65 y se promueve a `CONFIRMADO`. La 2.05 realmente le toca a R2.
3. Resolver el Hallazgo 2 requiere desconfirmar una medida ya tomada — entra en territorio PR #333 redux (el `global_fallback` revertido).
4. Alternativas de menor riesgo existen y se evalúan en la sección 5.

---

## 1. Hallazgo que invalida el marco original

Cuando abrimos este frente, la hipótesis era: *"R1 y R2 están starved porque sus cotas reales están en el pool de R3. Transferirlas debería resolver Bernardi."*

**La simulación numérica dice otra cosa.**

### 1.1 Distancias reales cotas ↔ bboxes (Bernardi)

Imagen: `(4963, 3509)`. Bbox_rel del topology cacheado (`plan_hash=d811083c0d1f7ac4`):

- **R1** = `{x:0.35, y:0.65, w:0.25, h:0.08}` → bbox_px `{x:1737, y:2280, x2:2977, y2:2560}`, horizontal.
- **R2** = `{x:0.78, y:0.45, w:0.08, h:0.35}` → bbox_px `{x:3871, y:1579, x2:4268, y2:2807}`, vertical.
- **R3** = `{x:0.35, y:0.45, w:0.25, h:0.08}` → bbox_px `{x:1737, y:1579, x2:2977, y2:1859}`, horizontal.

Distancias de las cotas rejected de R3 al borde del bbox de cada región:

| Cota | Coord    | Dist→R1 | Dist→R2 | Dist→R3 | Más cercana |
|------|----------|---------|---------|---------|-------------|
| 2.75 | (1577, 1340) | 954 | 2306 | **288** | R3 |
| 2.35 | (2836, 1458) | 822 | 1042 | **121** | R3 |
| 1.60 | (2119, 1267) | 1013 | 1780 | **312** | R3 |

Las 3 cotas que R3 rechazó están espacialmente MÁS CERCA de R3 que de R1 o R2. No es que R3 "robó" cotas lejanas — están dibujadas sobre el bbox que el topology le asignó a R3.

### 1.2 El bug real descubierto por la simulación

Despiece esperado de Bernardi (según brief + plano):

- R1 (cocina con pileta+anafe) = **2.35**
- R2 (L vertical) = **2.05**
- R3 (isla) = **1.60**

Lo que midió el sistema:

- R1 = `null` (pool_starved)
- R2 = `null` (pool_starved)
- R3 = **2.05** (CONFIRMADO, confidence 0.65)

**R3 midió 2.05 cuando debería haber medido 1.60.** La 2.05 realmente le pertenece a R2. Pero el topology puso el bbox de R3 en la franja horizontal central (donde está la cocina L horizontal, NO la isla), y R3 eligió la cota que le queda mejor geométricamente.

El sistema actual no detecta esta inconsistencia porque:

- R3 tiene features `touches_wall=False` → clasificado como isla.
- R3 midió 2.05 con bucket `preferred` (score 80).
- **Ninguna regla dice "isla típicamente mide <1.8m, valor >2m es raro".**

**Esto NO es un bug de cross-region reassignment. Es un bug de clasificación del topology + falta de sanity check semántico.**

---

## 2. Diagnóstico completo de Bernardi post-simulación

| Problema | Severidad | ¿Lo resuelve cross-region? |
|----------|-----------|----------------------------|
| R1 pool_starved (2.35 no está en su pool) | Alta | Parcial — si se amplía expansion a +600px |
| R2 pool_starved (2.05 no está en su pool) | Alta | **No** — la 2.05 ya fue "tomada" por R3 |
| R3 midió 2.05 pero correcto es 1.60 | **CRÍTICA** | **No** — requiere desconfirmar R3 |
| Topology asignó bboxes con geometría ↔ clasificación invertida (R3 en franja L horizontal clasificado como isla) | Muy alta | **No** — toca Plan B |

**El problema prioritario no es cross-region. Es que R3 confirma 2.05 como isla sin sanity check.**

---

## 3. Las 8 preguntas obligatorias (6 de GPT + 2 extras)

### 3.1 Cuándo una región es candidata a RECIBIR cotas ajenas

Criterios:

- `pool_starved_region=true` (post-rescue devolvió []).
- `local_cotas_count == 0`.
- Región válida (no descartada).

**Evaluación:** Trigger claro y limpio. Bernardi R1/R2 disparan bien.

### 3.2 Cuándo una región puede DONAR

Criterios:

- `rejected_candidates` de la región donante contiene cotas en [1.0, 4.0].
- La región donante ya eligió su propia cota (no la privamos de su mejor opción).
- Threshold mínimo de donante: `expanded_pool_count ≥ 5` para que "le sobren".

**Evaluación:** Superficialmente OK. Pero la simulación muestra que en Bernardi las cotas donadas siguen espacialmente más cerca del donante → semánticamente no corresponden al receptor. **Transferirlas es arbitrario.**

### 3.3 Qué cotas pueden migrar y cuáles jamás

Propuesta:

- **Pueden migrar:** cotas en `rejected_candidates`, valor en [1.0, 4.0], no eran top del donante.
- **Nunca migran:** perímetros (>3m fuera tight), absurd values (<0.1 o >6), `top_preferred` del donante, cotas con `exclude_code="probable_perimeter"`.

**Evaluación:** Las reglas cubren los casos obvios. Pero no previenen el caso Bernardi: 2.35 es legítimamente rechazada por R3 (tenía 2.05 más cerca) pero migrarla a R1 (que está 822 píxeles lejos) es una apuesta sin base espacial.

### 3.4 Cómo se evita robarle la mejor cota a una región sana

Propuesta:

- Donante retiene su `top_preferred` siempre.
- Solo se donan cotas cuyo score en el donante era weak/unlikely.
- Donante marca en sus logs que donó: `donated_to=["R1"]`.

**Evaluación:** Protege R3 de que le saquen 2.05. **Pero el bug real es que R3 tiene 2.05 que NO le corresponde (es de R2). Proteger la respuesta incorrecta empeora la situación: garantiza que R3 conserve la medida errónea.**

### 3.5 Cuál es el confidence/status máximo

Propuesta:

- Receptor: bucket forzado a `weak`, confidence cap 0.4 (más estricto que rescue 0.5).
- `suspicious_reasons`: `"cross_region_reassignment_from_R3"`.
- Status final: SIEMPRE DUDOSO.

**Evaluación:** Correcto. El operador ve la cota con bandera de "revisión obligatoria". Pero esto no cambia el problema de que la cota asignada puede ser incorrecta — solo lo hace visible.

### 3.6 Cómo se loggea

Propuesta:

```
[multi-crop/cross-region-check] starved=[R1, R2] donors=[R3] rejected_pool=[2.75, 2.35, 1.6]
[multi-crop/cross-region-assign] cota=2.35 from=R3 to=R1 reason=proximity dist=822px orientation_match=True
[multi-crop/cross-region-result] R1 received=2.35 final_rescue_pool=[2.35, 0.6, 0.6]
```

**Evaluación:** Formato OK. Sigue patrón de `[rescue-check]` del PR #346.

### 3.7 Tests de no regresión anti-PR-#333

El PR #333 se revirtió porque: *"R2 recibió 13 cotas globales, eligió 4.15 que era cota de perímetro de la isla"*.

Tests necesarios:

1. Perímetros (valores >3m fuera de tight) nunca migran — incluso si son el único pool del donante.
2. Donante con `expanded_pool_count < 5` no dona.
3. Si donante recibió su `top_preferred` por rescue propio, no puede donar.
4. Reassignment solo entre regiones del MISMO plano (`plan_hash`) — nunca cross-quote.

**Evaluación:** Cobertura razonable. Pero los tests no detectarían el caso Bernardi porque ahí las cotas donadas caen en rango [1.0, 4.0] y son legítimamente de mesada — solo que no la mesada que están recibiendo.

### 3.8 (Extra) Simulación con Bernardi real ANTES de codear

**Ya ejecutada.** Output con la heurística "asignar cota rejected a la región starved más cercana":

| Cota rejected de R3 | Asignación naive | Asignación esperada | ¿Match? |
|---------------------|------------------|----------------------|---------|
| 2.35 | → R1 (dist 822) | → R1 (correcto) | ✅ |
| 2.75 | → R1 (dist 954) | → ? (no existe en despiece) | ❌ ruido |
| 1.60 | → R1 (dist 1013) | → R3 (correcto, isla) | ❌ |

Resultado: R1 recibe pool enriquecido con `[2.35, 2.75, 1.60, 0.6, 0.6]`. Solo 2.35 es la respuesta correcta para R1. Las otras 2 son ruido o pertenecen a R3.

**R2 no recibe nada.** Todas las rejected están más cerca de R1 que de R2. R2 sigue pool_starved.

**R3 sigue midiendo 2.05 (INCORRECTO).**

### 3.9 (Extra) Criterio de no-go explícito

Condiciones que deberían disparar no-go (AND):

1. Simulación con Bernardi real NO produce R1 correcto con ≥70% certeza heurística.
2. Simulación con Bernardi real deja R2 sin pool útil.
3. El diseño no detecta ni corrige R3 midiendo incorrecto (2.05 cuando debería ser 1.60).
4. La heurística de asignación depende de parámetros ajustables por caso (bias hacia ajuste post-hoc).

**Las 4 condiciones se cumplen.** No-go justificado.

---

## 4. Voto final: NO-GO

### 4.1 Por qué, explícito

1. **Cross-region naive no resuelve Bernardi.** La simulación muestra R1 mejorado parcialmente, R2 sin cambios, R3 con bug crítico no detectado.

2. **Cross-region sofisticado (con sanity checks semánticos como "isla mide <1.8m") entra en territorio PR #333.** Son reglas ad-hoc por categoría que se vuelven frágiles cuando cambia el stock de casos.

3. **El bug más grave descubierto (R3 confirma valor incorrecto) es ortogonal a cross-region.** Requiere sanity checks semánticos + posiblemente mejor topology.

4. **Costo vs beneficio:**
   - **Costo:** ~300 líneas de código + logs + tests. Riesgo de regresión en casos simples.
   - **Beneficio:** en Bernardi, R1 mejora probabilísticamente (~33% chance de elegir 2.35 de un pool de 3 candidates), R2 igual, R3 igual.

### 4.2 Comparación con alternativas

| Intervención | Resuelve R1 | Resuelve R2 | Resuelve R3 | Riesgo | Costo |
|--------------|-------------|-------------|-------------|--------|-------|
| Cross-region naive | Parcial (~33%) | No | No | Medio | 300 LOC |
| Cross-region + semantic checks | Parcial (~50%) | Parcial | Parcial | Alto | 500+ LOC |
| Sanity check `"isla <1.8m"` post-measure | No | No | Flag DUDOSO | Bajo | ~50 LOC |
| Expansion pool +600px | Probable | Puede introducir ruido | No | Medio | ~30 LOC |
| Aceptar techo, operador edita | — | — | — | Cero | Cero |

---

## 5. Alternativas viables (más livianas que cross-region)

Si se quiere abrir OTRO frente más chico en vez de cross-region, dos opciones concretas:

### 5.1 Sanity check semántico post-measure (~50 LOC)

Regla nueva en `_aggregate`:

- Si `sector=="isla"` y `largo_m > 1.8m` → agregar `suspicious_reason="isla_largo_inusual"` → status DUDOSO.
- Si `sector=="cocina"` con pileta+anafe y `largo_m < 1.5m` → suspicious.
- Reglas mínimas, bien acotadas. **No cambian valor — solo lo flagean.**

Para Bernardi: R3=2.05 con `sector=isla` → DUDOSO con bandera clara al operador.

### 5.2 Expansion pool configurable +600px (~30 LOC)

Cambio en `_measure_region`:

- Si `pool_starved_region=true`, hacer un segundo intento con expansion +600px (vs +300 actual).
- Cap confidence 0.35. `suspicious_reason="deep_expansion"`.

Quick check numérico:

- **R1** bbox_expanded (+600): `[737, 1301] × [3977, 3542]`. Cota 2.35 @ (2836, 1458): x ∈ [737, 3977] ✓, y ∈ [1301, 3542] ✓. **Sí entra.**
- **R2** bbox_expanded (+600): `[3071, 799] × [5268, 4007]`. Cota 2.05 @ (2506, 1875): x=2506 NO ∈ [3071, 5268]. **No entra aún con +600.** R2 seguiría starved.

Esta alternativa resuelve ~50% de Bernardi (R1) con costo/riesgo bajo.

### 5.3 Aceptar techo + documentar

Cerrar el frente. El operador edita R1/R2 en UI. Sistema cumple fail-loud. Documentar en `CLAUDE.md` que Bernardi-like cases tienen bug residual de topology y que el sistema lo marca DUDOSO sin mentir.

---

## 6. Criterios para reabrir cross-region en el futuro

Condiciones objetivas (medir con data de prod):

1. **`pool_starved_region=true` aparece en >30% de regiones de planos distintos** (no solo Bernardi). Hoy: 2 casos en 1 plano. Necesitaríamos ~20 planos de evidencia.

2. **En esos casos, las cotas rejected de donantes están consistentemente a >500px de la región starved** (indica que la asignación por proximidad sería estable).

3. **No existe una alternativa más barata** que lo resuelva (si 5.1 o 5.2 cubren la mayoría, no vale la pena).

Hasta que se cumplan las 3: **no-go mantenido**.

---

## 7. Recomendación final

- **Hoy:** cerrar el frente cross-region como no-go documentado.
- **Si se quiere ganancia incremental:** evaluar 5.1 (sanity check semántico) o 5.2 (expansion +600px) en futuras sesiones. Ambos chicos, bajo riesgo, efecto medible.
- **Rango de semanas:** dejar que `pool_starved_region=true` y el hallazgo `isla_largo_inusual` (si se implementa 5.1) acumulen data en prod. Con 10+ planos de evidencia, revisitar.
- **Nunca:** implementar cross-region reassignment naive. La simulación con Bernardi real ya probó que no lo resuelve.

---

## Apéndice A — Código de la simulación numérica

```python
from math import sqrt

IMAGE = (4963, 3509)

REGIONS = {
    "R1": {"bbox_rel": {"x": 0.35, "y": 0.65, "w": 0.25, "h": 0.08}},
    "R2": {"bbox_rel": {"x": 0.78, "y": 0.45, "w": 0.08, "h": 0.35}},
    "R3": {"bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08}},
}

# Coords reales de 7 cotas del PDF Bernardi (del test TestBernardiRankingR2)
COTAS = [
    ("0.60", 0.60, 3028, 957),
    ("1.60", 1.60, 2119, 1267),
    ("4.15", 4.15, 3663, 1339),
    ("2.75", 2.75, 1577, 1340),
    ("2.35", 2.35, 2836, 1458),
    ("2.05", 2.05, 2506, 1875),
    ("0.60", 0.60, 1941, 2039),
]

def bbox_to_px(b, img):
    w, h = img
    x = int(b["x"] * w); y = int(b["y"] * h)
    return {"x": x, "y": y, "x2": x+int(b["w"]*w), "y2": y+int(b["h"]*h)}

def dist_to_bbox(cx, cy, b):
    dx = max(0, b["x"] - cx, cx - b["x2"])
    dy = max(0, b["y"] - cy, cy - b["y2"])
    return sqrt(dx*dx + dy*dy)

for rid, r in REGIONS.items():
    r["bbox_px"] = bbox_to_px(r["bbox_rel"], IMAGE)

R3_REJECTED = [2.75, 2.35, 1.6]

for rej_val in R3_REJECTED:
    for label, val, x, y in COTAS:
        if abs(val - rej_val) > 0.01:
            continue
        d1 = dist_to_bbox(x, y, REGIONS["R1"]["bbox_px"])
        d2 = dist_to_bbox(x, y, REGIONS["R2"]["bbox_px"])
        d3 = dist_to_bbox(x, y, REGIONS["R3"]["bbox_px"])
        print(f"{label} at ({x},{y}): R1={d1:.0f} R2={d2:.0f} R3={d3:.0f}")
```

Output:

```
2.75 at (1577,1340): R1=954 R2=2306 R3=288
2.35 at (2836,1458): R1=822 R2=1042 R3=121
1.60 at (2119,1267): R1=1013 R2=1780 R3=312
```

---

## Apéndice B — Historial del frente

- **PR #333** (revertido): primer intento de global_fallback. Falló porque pasaba todas las cotas del plano al LLM per-region y el LLM elegía cotas de otros sectores.
- **PR #344** (Plan B): topology cache cross-quote. Eliminó estocasticidad.
- **PR #345**: rescue pass `span_based` (caso bbox subdimensionado).
- **PR #346**: observabilidad + `orphan_region` trigger + `pool_starved_region` flag.
- **PR #347**: reconciliación brief↔dual_read + Tipo de trabajo en known.
- **Plan #348** (este doc): cross-region reassignment evaluado. **NO-GO.**

---

*Generado con Claude Code tras simulación numérica con coordenadas reales del plano Erica Bernardi. Sin código producido.*
