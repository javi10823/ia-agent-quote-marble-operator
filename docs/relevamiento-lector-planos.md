# Relevamiento — Problemas leyendo planos arquitectónicos (D'Angelo Marble Operator)

**Fecha:** 2026-04-19
**Autor:** Javier (dueño) + Claude Opus 4.7 (asistente — me mandé varias cagadas iterando, este doc busca segunda opinión)
**Objetivo:** Pedirle a otra IA / persona externa que nos ayude a resolver el problema de lectura de planos. Claude Opus 4.7 ya iteró varias veces y empeoró el resultado en más de una oportunidad. Necesitamos perspectiva fresca.

> Este documento es **self-contained**: incluye arquitectura, código relevante, caso de falla concreto, hipótesis y preguntas. No hace falta clonar el repo para opinar.

---

## 1. Contexto del sistema

**Valentina** es un agente IA que arma presupuestos para D'Angelo Marmolería (empresa argentina de mesadas de cocina/baño). El operador sube un plano en PDF/imagen y Valentina tiene que:

1. **Leer el plano**: detectar cuántas mesadas hay (islas, L, U, rectas), medirlas (largo × ancho × alto).
2. Armar un despiece.
3. Calcular precios (material + mano de obra + merma).
4. Generar PDF/Excel + subirlo a Drive.

**Stack:**
- Backend: FastAPI + Python 3.12, SQLAlchemy async, Postgres (Railway).
- Frontend: Next.js 14 + TypeScript (Vercel).
- VLM: Anthropic Claude (Sonnet 4.5 principal, Opus 4.x para retry de alta precisión).

**Este relevamiento se enfoca en el punto 1 — lectura del plano.** Los demás pasos funcionan bien.

---

## 2. Arquitectura del lector de planos

Hay dos pipelines. El nuevo (`multi_crop_reader`, PR #286 hace 2 semanas) reemplazó al viejo (`single-cocina`). El caso donde está fallando corre por el nuevo.

### 2.1 `cotas_extractor` (determinístico, sin LLM)

Extrae del **text layer del PDF** las cotas numéricas (`2,35`, `0,60`, etc.) con sus coordenadas (x, y) en el espacio de la imagen rasterizada (300 DPI). Es pre-procesamiento.

Código: [`api/app/modules/quote_engine/cotas_extractor.py`](../api/app/modules/quote_engine/cotas_extractor.py)

Output: `list[Cota]`, donde `Cota = {text: str, value: float, x: float, y: float, width, height}`.

### 2.2 `multi_crop_reader` (dos pasadas al VLM)

**Fase 1 — topology global:** UNA llamada al VLM con la imagen completa. Devuelve:
```json
{
  "view_type": "planta",
  "regions": [
    {
      "id": "R1",
      "bbox_rel": {"x": 0.3, "y": 0.25, "w": 0.4, "h": 0.25},
      "features": {
        "touches_wall": false,
        "stools_adjacent": true,
        "cooktop_groups": 1,
        "sink_double": false,
        "sink_simple": false,
        "non_counter_upper": false
      },
      "evidence": "hay banquetas al frente, aislada del perímetro"
    }
  ]
}
```

El VLM **solo** identifica regiones + features. No mide.

**Fase 2 — medición por región (en paralelo):** una llamada al VLM por cada región detectada:
- Se rasteriza el bbox de la región + padding 80px.
- Se filtran las cotas cuya posición (x, y) cae dentro del bbox + padding.
- Se le manda al VLM el crop visual + las cotas locales + metadata.
- El VLM elige `largo_m` y `ancho_m` de entre las cotas candidatas.

**Aggregator:** combina topology + resultados y clasifica:
- `touches_wall=true` → cocina (lado de L/U contra pared).
- `touches_wall=false` o `stools_adjacent=true` → isla.
- `non_counter_upper=true` → descarta (alacena superior).

### 2.3 Sistema prompts (VLM)

**Fase 1 — global topology** (`api/app/modules/quote_engine/multi_crop_reader.py`, líneas 57-112):

```
Sos un lector de planos arquitectónicos de marmolería.
Recibís UNA imagen de un plano (vista cenital, planta).

Tu única tarea en esta pasada es identificar la TOPOLOGÍA del plano:
- Cuántas regiones de mesada hay.
- Dónde está cada una (bbox en coordenadas relativas 0-1 respecto a la imagen).
- Qué artefactos tiene cada una (pileta, anafe, horno, isla, etc).

**Señal visual dominante:** las mesadas se dibujan como **regiones rellenas
en gris oscuro**. Todo lo que NO está relleno en gris oscuro (alacenas,
módulos superiores, electrodomésticos free-standing, paredes) NO es mesada.

Devolvé SOLO JSON con features estructuradas (NO etiquetes "isla con anafe"
directamente — el aggregator deriva labels después a partir de las features):

{
  "view_type": "planta" | "render_3d" | "render_fotorrealista" | "elevation" | "mixed" | "unknown",
  "regions": [
    {
      "id": "R1",
      "bbox_rel": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
      "features": {
        "touches_wall": true,
        "stools_adjacent": false,
        "cooktop_groups": 0,
        "sink_double": false,
        "sink_simple": false,
        "non_counter_upper": false
      },
      "evidence": "string corta — qué símbolos viste en la región"
    }
  ],
  "ambiguedades": []
}

Reglas:
- Cada región rellena contigua en gris oscuro = 1 entry en `regions`.
- `touches_wall`: true si la región toca al menos un muro. Las islas
  típicamente NO tocan paredes.
- `stools_adjacent`: true si ves banquetas/sillas adyacentes (suele indicar
  isla con desayunador).
- `cooktop_groups`: cuántos grupos de hornallas visibles (4-6 círculos
  agrupados). Puede haber 2 (gas + eléctrico/vitrocerámica).
- `sink_double`: true si ves 2 óvalos/cubetas contiguas.
- `sink_simple`: true si ves 1 sola cubeta.
- `non_counter_upper`: true SI esta región es en realidad una alacena
  superior (heladera/horno/despensa como módulo alto), NO mesada.
- U + isla = 4 regiones (3 lados + 1 isla). L = 2. Recta = 1.
- bbox_rel: (x,y) top-left + (w,h) relativos a la imagen.
- NO etiquetes "isla" ni "cocina" — eso sale de combinar features.
- NO inventes regiones que no ves.
```

**Fase 2 — per-region measurement** (`api/app/modules/quote_engine/multi_crop_reader.py`, líneas 190-222):

```
Sos un lector de planos de marmolería.

Recibís:
- Un CROP de una mesada específica del plano (región rellena en gris).
- Una lista de cotas candidatas pre-extraídas del text layer del PDF
  (con sus posiciones). Estas son las ÚNICAS medidas válidas — NO inventes
  otras.
- Metadata de la región: sector, si toca paredes, si tiene pileta/anafe.

Tu tarea: elegir de las cotas candidatas cuál es el **largo** y cuál es
el **ancho** de ESTA región.

Reglas:
- Una mesada residencial típica tiene largo ≥ 0.60m y ancho ≈ 0.60m.
- El ancho (profundidad) suele ser el valor más chico y repetido — si
  todas las otras mesadas del plano tienen ancho 0.60, esta también,
  salvo evidencia fuerte en contrario.
- Si sólo ves una cota candidata, podés inferir el largo con ella y
  marcar ancho como 0.60 con confidence baja.
- NO confundas cotas del perímetro del ambiente (típicamente > 3m y
  alineadas con el borde exterior del dibujo) con cotas de la mesada.

Devolvé SOLO JSON:
{
  "largo_m": 2.95,
  "ancho_m": 0.60,
  "confidence": 0.9,
  "reasoning": "texto corto: por qué elegí estas cotas",
  "rejected_candidates": [
    {"value": 4.15, "reason": "cota del perímetro, no de mesada"}
  ]
}
```

---

## 3. Caso de falla — plano de Erica Bernardi

### 3.1 Input

- **PDF:** `api/tests/fixtures/bernardi_erica_mesadas_cocina.pdf` (157 KB, 1 página).
- **Resolución rasterizada:** 4963 × 3509 px @ 300 DPI.
- **Layout:** cocina en L + isla. **3 mesadas físicas en total.**

### 3.2 Medidas reales (dictadas por el operador que conoce el plano)

| Sector | Mesada | Largo × Ancho | m² |
|---|---|---|---|
| Isla | (sin anafe — el anafe va en la cocina) | 1.60 × 0.60 | 0.96 |
| Cocina L | Tramo 1 | 2.35 × 0.60 | 1.41 |
| Cocina L | Tramo 2 | 2.05 × 0.60 | 1.23 |
| | **Total** | | **3.60** |

### 3.3 Cotas extraídas del PDF (text layer)

7 cotas con coordenadas (x, y) en el espacio de la imagen rasterizada:

| Valor | Posición (x, y) |
|---|---|
| 0.60 m | (3028, 957) |
| 1.60 m | (2119, 1267) |
| 4.15 m | (3663, 1339) |
| 2.75 m | (1577, 1340) |
| 2.35 m | (2836, 1458) |
| 2.05 m | (2506, 1875) |
| 0.60 m | (1941, 2039) |

> En los logs de producción aparecen 13 cotas (2 rutas de extracción distintas: `extract_cotas_from_drawing` y una path adicional de multi-crop). El análisis sigue válido — las cotas relevantes están en ambos listados.

### 3.4 Output del sistema (con el bug original + mi fallback global que luego revertí)

| Sector reportado | Largo × Ancho | m² | ¿Correcto? |
|---|---|---|---|
| "Isla — Isla (con 1 anafe)" | 2.35 × 0.60 | 1.41 | ❌ Era el tramo L, no la isla. La isla no tiene anafe. |
| "Cocina — Cocina (Mesada 1)" | 4.15 × 0.60 | 2.49 | ❌ 4.15 es una cota de **perímetro**, no de mesada. |
| "Cocina — Cocina (con pileta)" | 2.95 × 0.60 | 1.77 | ❌ 2.95 no corresponde a ninguna mesada. |
| **Total** | — | **5.67** | ❌ (real: 3.60 — ~60% error) |

### 3.5 Logs de producción

```
[multi-crop] starting — image (4963, 3509), 13 cotas
[multi-crop] global topology detected 2 regions    ← ERROR: hay 3 mesadas
[multi-crop] region R2 has only 0 local cotas (<2) — skip LLM, return DUDOSO
[multi-crop] 1/2 regions measured successfully
```

**PR #334 (recién mergeado)** agrega logs estructurados adicionales (`[multi-crop/topology-detail]` con bboxes completos + features + evidence; `[multi-crop/region-detail]` con el output del LLM por región). Con eso podremos ver qué está clasificando mal. Cuando el operador reproduzca el caso en prod tendremos los logs. Por ahora no están.

---

## 4. Hipótesis de causa

### 4.1 Topology LLM detecta mal la cantidad de regiones

Hay 3 mesadas físicas pero el VLM detectó 2. Posibles motivos:
- La cocina L tiene sus dos tramos **conectados en la esquina** (típico de L). El VLM los interpreta como **una sola región contigua en gris oscuro**.
- O el VLM no vio la isla (es chica y puede pasar desapercibida).

### 4.2 Topology clasifica mal los features

Según el output, una región fue clasificada como "isla con anafe". Pero el anafe está en la cocina, no en la isla. Posibles motivos:
- El VLM confundió los símbolos de pileta + anafe sobre la mesa de la cocina con símbolos sobre la isla.
- Los bboxes asignados no están geográficamente alineados con las regiones reales → el VLM ve el crop como "isla" (porque no toca paredes visualmente en ese crop chico) aunque sea el tramo de la cocina.

### 4.3 Los bboxes del topology están desalineados con las cotas

Las 7 cotas están distribuidas en una franja vertical central del plano (entre y=957 y y=2039). Si el topology asigna a R2 un bbox en otra zona (esquina opuesta, por ejemplo), no caen cotas locales → `insufficient_local_cotas` → DUDOSO sin medida.

### 4.4 Fase de medición confunde cotas de perímetro

El prompt de per-region dice `NO confundas cotas del perímetro del ambiente (típicamente > 3m y alineadas con el borde exterior del dibujo) con cotas de la mesada`. El VLM eligió igual 4.15 como "largo de mesada" — violó la regla.

### 4.5 Multi-crop pipeline estructuralmente frágil para este layout

Comparado con el pipeline anterior (`single-cocina` que le daba al VLM la imagen completa + todas las cotas de una), multi-crop introduce un punto de fallo extra (la topology) que si se equivoca rompe todo el down-stream. En planos simples tipo Bernardi quizás el single-cocina funcionaba mejor.

---

## 5. Qué intentamos y cómo salió

| # | Intento | Resultado |
|---|---|---|
| 1 | Fix del crash `null.toFixed` en el frontend coaccionando null → 0 (PR #330) | Tramos sin medida mostraban "0.00 × 0.00" como si fueran medidas reales. **Regresión.** |
| 2 | Mostrar "—" para null + helper `displayNum` (PR #331) | Arregló el display honesto. ✅ |
| 3 | Fallback escalonado de cotas: si bbox sin cotas → expandir +300px → si sigue, pool global (PR #332) | El global_fallback hacía que el VLM eligiera cotas de OTROS sectores → medidas swappeadas con badge DUDOSO. **Regresión peor.** |
| 4 | Revert del global_fallback (PR #333, este mismo día) | Volvió a comportamiento "— × —" en regiones sin cotas locales. OK pero el problema real sigue. |
| 5 | Logging estructurado (PR #334) | Aún no probado en prod — falta que el operador reproduzca el caso para ver qué devuelve el topology LLM. |

---

## 6. Qué SÍ está funcionando

- El `cotas_extractor` extrae bien las 7 cotas del text layer con posiciones correctas.
- El flow de UI (confirmar medidas, avanzar a Paso 2, editar inline) funciona.
- Cuando el topology acierta (muchos planos simples), todo el pipeline produce resultados correctos.
- Hay validaciones post-LLM en `_measure_region`: detecta fallback silencioso (`largo == ancho`) y valores no anclados a cotas candidatas → los flaguea como `suspicious_reasons` → status DUDOSO.

---

## 7. Preguntas concretas para quien nos ayude

1. **¿Es multi-crop la arquitectura correcta para este tipo de plano?** ¿O el single-cocina (una sola llamada al VLM con imagen completa + todas las cotas) resuelve mejor casos chicos como el de Bernardi y multi-crop solo aporta en planos complejos tipo edificios?

2. **¿Cómo mejoramos el prompt del topology para que detecte N regiones correctamente?** Hoy el VLM a veces fusiona tramos contiguos (L → 1 región en vez de 2) o se pierde islas chicas. ¿Conviene dar ejemplos concretos en el prompt? ¿Few-shot con imágenes? ¿O dividir en dos prompts (un "conta regiones" + un "detalla cada región")?

3. **¿Conviene hacer cross-check con el brief del operador?** El brief dice literalmente "con pileta" y "cocina en L + isla". Si el topology clasifica la pileta en la isla (contra lo que dice el brief), ¿flaguear para retry? ¿Forzar que el VLM revise?

4. **¿Cómo atacamos el "cota de perímetro" que el VLM confunde con medida?** El prompt dice explícitamente no usar cotas > 3m alineadas al borde. No alcanza. ¿Filtrar determinísticamente cotas "candidatas a perímetro" ANTES de pasárselas al VLM? ¿Heurística: cota > 3m + posición cerca del borde del bbox → excluir?

5. **Cuando una región queda con `<2 cotas locales` (ni siquiera con bbox expandido +300px), ¿qué es lo correcto?** Hoy devolvemos "— × —" sin medida (operador completa manual). El fallback global probamos y miente. ¿Hay una opción intermedia decente?

6. **¿Modelos VLM específicos para planos?** Claude y GPT hacen un trabajo razonable pero se pierden en clasificación. ¿Existe algún modelo fine-tuned para planos arquitectónicos / BIM / IFC que valga la pena probar para la fase de topology?

7. **¿Conviene extraer las líneas del PDF (vectores) en vez de rasterizar?** pdfplumber devuelve `lines`, `rects`, `curves`. Quizás con análisis geométrico determinístico podemos derivar las regiones sin VLM: polígonos conectados en gris oscuro = mesadas. Sería más robusto que depender del VLM clasificando píxeles.

8. **¿Hay alguna heurística de "sanity check" post-topology que podamos agregar?** Ejemplo: si el VLM detectó 2 regiones pero hay 7+ cotas distribuidas en 3+ clusters geográficos, probablemente hay 3 regiones → retry con instrucciones específicas.

---

## 8. Qué necesitamos de vos

Cualquier combinación de:

- **Prompt engineering** sobre los prompts actuales.
- **Arquitectura alternativa** (vectorial, multi-pass, fine-tuning, heurística determinística).
- **Crítica** de hipótesis — cuál descartar, cuál priorizar.
- **Casos de referencia** de sistemas similares (tools tipo AutoCAD, SnapADDY, Planner5D) que ya resolvieron esto.

El PDF de Bernardi lo podemos compartir. El repo es privado pero el código relevante está arriba completo.

---

## Apéndice A — Código completo de `_measure_region` (post-revert del global_fallback)

```python
async def _measure_region(
    full_image_bytes: bytes,
    image_size: tuple[int, int],
    region: dict,
    candidate_cotas: list[Cota],
    model: str,
    brief_text: str = "",
) -> dict:
    img_w, img_h = image_size
    bbox = region.get("bbox_rel") or {}
    x = max(0, int((bbox.get("x") or 0) * img_w) - REGION_CROP_PADDING_PX)
    y = max(0, int((bbox.get("y") or 0) * img_h) - REGION_CROP_PADDING_PX)
    w = int((bbox.get("w") or 0) * img_w) + 2 * REGION_CROP_PADDING_PX
    h = int((bbox.get("h") or 0) * img_h) + 2 * REGION_CROP_PADDING_PX
    x2 = min(img_w, x + max(w, 1))
    y2 = min(img_h, y + max(h, 1))
    if x2 - x < 10 or y2 - y < 10:
        return {"error": "region_bbox_too_small", "region_id": region.get("id")}

    # L1: cotas dentro del bbox + padding 80px
    local_cotas = [c for c in candidate_cotas if x <= c.x <= x2 and y <= c.y <= y2]

    MIN_LOCAL_COTAS = 2
    COTA_SEARCH_EXTRA_PX = 300
    cotas_for_llm = local_cotas
    cotas_mode = "local"

    if candidate_cotas and len(local_cotas) < MIN_LOCAL_COTAS:
        # L2: expandir +300px sólo para cota-search (crop visual sigue siendo bbox original)
        ex_x = max(0, x - COTA_SEARCH_EXTRA_PX)
        ex_y = max(0, y - COTA_SEARCH_EXTRA_PX)
        ex_x2 = min(img_w, x2 + COTA_SEARCH_EXTRA_PX)
        ex_y2 = min(img_h, y2 + COTA_SEARCH_EXTRA_PX)
        expanded_cotas = [c for c in candidate_cotas if ex_x <= c.x <= ex_x2 and ex_y <= c.y <= ex_y2]
        if len(expanded_cotas) >= MIN_LOCAL_COTAS:
            cotas_for_llm = expanded_cotas
            cotas_mode = "expanded"
        else:
            # Skip LLM — no inventamos con pool global (ver PR #332 y su revert #333)
            return {
                "error": "insufficient_local_cotas",
                "region_id": region.get("id"),
                "local_cotas_count": len(local_cotas),
                "expanded_cotas_count": len(expanded_cotas),
            }

    # ... (crop + LLM call + sanity checks + return)
```

## Apéndice B — Shape del output `dual_read_result`

```json
{
  "source": "MULTI_CROP",
  "view_type": "planta",
  "requires_human_review": true,
  "sectores": [
    {
      "id": "sector_isla",
      "tipo": "isla",
      "tramos": [
        {
          "id": "R1",
          "descripcion": "Mesada (con 1 anafe) — revisar",
          "largo_m": {"valor": 2.35, "status": "DUDOSO", "opus": null, "sonnet": null},
          "ancho_m": {"valor": 0.60, "status": "DUDOSO", "opus": null, "sonnet": null},
          "m2": {"valor": 1.41, "status": "DUDOSO"},
          "zocalos": [],
          "frentin": [],
          "regrueso": []
        }
      ],
      "ambiguedades": []
    }
  ],
  "conflict_fields": []
}
```

El frontend renderiza cada tramo en una tabla editable. Los tramos con status DUDOSO muestran badge amarillo y se pueden editar inline. Total m² se agrega al pie.
