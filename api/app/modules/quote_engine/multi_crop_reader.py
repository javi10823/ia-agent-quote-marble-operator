"""Multi-crop plan reader — arquitectura de lectura por pasadas.

En vez de pedirle al VLM que haga todo a la vez sobre la imagen full-page
(detectar regiones + contar + elegir cotas + medir + emitir JSON), el
pipeline se divide en dos fases:

  1. **Global topology call**: una sola llamada al VLM con la imagen full
     page. Devuelve SOLO topología: cuántas regiones de mesada hay (las
     zonas sombreadas en gris oscuro), dónde están cada una (bbox
     relativo al tamaño de la imagen), qué artefactos tienen
     (pileta/anafes/isla/etc). NO pedimos medidas en esta fase.

  2. **Per-region measurement calls** (en paralelo con asyncio.gather):
     para cada región detectada, croppeamos la imagen a esa zona con un
     padding, filtramos las cotas extraídas del text layer que caen
     cerca de esa región, y le pedimos al VLM SOLO medir largo/ancho
     de ESA región a partir de las cotas candidatas. El VLM ya no
     elige entre 15 cotas globales — elige entre 3-5 cotas locales.

Output shape: idéntico al de `dual_read_crop` (misma `sectores → tramos`
estructura) para ser drop-in replacement sin tocar frontend.

Config flag `multi_crop_enabled` en config.ai_engine apaga/enciende el
feature (default off — el pipeline actual sigue siendo fallback).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from typing import Optional

import anthropic
from PIL import Image

from app.core.config import settings
from app.modules.quote_engine.cotas_extractor import Cota, format_cotas_for_prompt

logger = logging.getLogger(__name__)

GLOBAL_TIMEOUT_SECONDS = 60
REGION_TIMEOUT_SECONDS = 45

# Padding (en píxeles) al croppear cada región para dar contexto visual al
# modelo. Si el bbox del LLM global no está perfecto, el padding evita
# cortar medio grupo de cotas.
REGION_CROP_PADDING_PX = 80


# ─────────────────────────────────────────────────────────────────────────────
# Fase 1: Global topology
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_SYSTEM_PROMPT = """Sos un lector de planos arquitectónicos de marmolería.
Recibís UNA imagen de un plano (vista cenital, planta).

Tu única tarea en esta pasada es identificar la TOPOLOGÍA del plano:
- Cuántos TRAMOS RECTOS de mesada hay.
- Dónde está cada uno (bbox en coordenadas relativas 0-1 respecto a la imagen).
- Qué artefactos tiene cada uno (pileta, anafe, horno, isla, etc).

**Señal visual dominante:** las mesadas se dibujan como **zonas rellenas
en gris oscuro**. Todo lo que NO está relleno en gris oscuro (alacenas,
módulos superiores, electrodomésticos free-standing, paredes) NO es mesada.

**No tenés que medir nada en esta pasada.** Solo identificá tramos.

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
      "evidence": "string corta — qué símbolos viste en el tramo"
    }
  ],
  "ambiguedades": []
}

**Compatibilidad de esquema:** en este JSON, el array `regions` representa
TRAMOS RECTOS COTIZABLES, NO masas grises contiguas. El nombre se mantiene
por retrocompat con el aggregator (que mapea entries → tramos).

**Unidad lógica = tramo recto cotizable.**

- Una cocina en L contra dos paredes se dibuja como UNA masa gris continua,
  pero son DOS tramos cotizables. Devolvé 2 entries: un tramo horizontal y
  uno vertical que se tocan en la esquina.
- Una U son 3 tramos. Una L + isla son 3 entries. Una U + isla son 4.
- Una mesada recta / lineal es 1 tramo.
- NO devuelvas un único bbox grande que abarque toda la L o U.

Cada cambio de dirección ortogonal (esquina de 90° dentro de una masa gris
continua) implica un nuevo tramo.

Reglas de features:
- `touches_wall`: true si el tramo toca al menos un muro. Las islas
  típicamente NO tocan paredes.
- `stools_adjacent`: true si ves banquetas/sillas adyacentes (suele indicar
  isla con desayunador).
- `cooktop_groups`: cuántos grupos de hornallas visibles (4-6 círculos
  agrupados). Puede haber 2 (gas + eléctrico/vitrocerámica).
- `sink_double`: true si ves 2 óvalos/cubetas contiguas.
- `sink_simple`: true si ves 1 sola cubeta.
- `non_counter_upper`: true SI este entry es en realidad una alacena
  superior (heladera/horno/despensa como módulo alto), NO mesada. En ese
  caso NO debería estar en la lista — pero si hay duda, marcalo true para
  que el aggregator lo filtre.
- bbox_rel: (x,y) top-left + (w,h) relativos a la imagen.
- NO etiquetes "isla" ni "cocina" — eso sale de combinar features.
- NO inventes tramos que no ves.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Brief parsing — heurística liviana para darle al VLM un prior de consistencia
# ─────────────────────────────────────────────────────────────────────────────

_SHAPE_L = re.compile(
    r"\b(cocina\s+en\s+l|forma\s+(de|en)\s+l|tipo\s+l|en\s+l)\b",
    re.IGNORECASE,
)
_SHAPE_U = re.compile(
    r"\b(cocina\s+en\s+u|forma\s+(de|en)\s+u|tipo\s+u|en\s+u)\b",
    re.IGNORECASE,
)
_SHAPE_RECTA = re.compile(
    r"\b(recta|lineal|una\s+pared|contra\s+una\s+pared)\b",
    re.IGNORECASE,
)
_MENTIONS_ISLA = re.compile(r"\bislas?\b", re.IGNORECASE)
_EXCLUDES_ISLA = re.compile(
    r"\bsin\s+isla|no\s+(lleva|va|hay)\s+isla",
    re.IGNORECASE,
)


def _infer_expected_region_count(brief_text: str) -> Optional[dict]:
    """Heurística liviana que extrae keywords del brief del operador para
    sugerir al VLM cuántos tramos rectos cotizables son esperables.

    Devuelve None si no hay señales claras — no inventamos un count cuando
    el brief es vago.

    **No usar para lógica dura ni validación bloqueante; solo para
    enriquecer el prompt del topology.** El VLM tiene que priorizar lo
    visible en el plano.
    """
    text = brief_text or ""
    if not text.strip():
        return None

    has_isla = bool(_MENTIONS_ISLA.search(text)) and not _EXCLUDES_ISLA.search(text)

    shape: Optional[str] = None
    base = 0
    if _SHAPE_U.search(text):
        shape, base = "U", 3
    elif _SHAPE_L.search(text):
        shape, base = "L", 2
    elif _SHAPE_RECTA.search(text):
        shape, base = "recta", 1

    if not shape and not has_isla:
        return None

    count = base + (1 if has_isla else 0)
    parts: list[str] = []
    if shape:
        parts.append(f"cocina en {shape}")
    if has_isla:
        parts.append("isla")
    return {"count": count, "description": " + ".join(parts)}


async def _call_global_topology(
    image_bytes: bytes,
    model: str,
    brief_text: str = "",
    extra_user_text: str = "",
) -> dict:
    """Llama al VLM para obtener topology. `extra_user_text` es usado por
    el retry cuando el primer topology contradijo el brief — se agrega
    como bloque adicional para guiar al LLM."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_blocks = []
    if brief_text and brief_text.strip():
        expected_hint = _infer_expected_region_count(brief_text)
        hint_text = ""
        if expected_hint:
            hint_text = (
                f"\n\nEl brief del operador sugiere **aproximadamente "
                f"{expected_hint['count']} tramos rectos cotizables** "
                f"({expected_hint['description']}). Usalo como señal de "
                f"consistencia, pero priorizá lo visible en el plano. "
                f"Si encontrás menos tramos, revisá si fusionaste una L/U "
                f"en un solo entry (error común)."
            )
        user_blocks.append({
            "type": "text",
            "text": (
                "CONTEXTO DEL OPERADOR:\n"
                f"```\n{brief_text.strip()}\n```"
                f"{hint_text}"
            ),
        })
    if extra_user_text:
        user_blocks.append({"type": "text", "text": extra_user_text})
    user_blocks.append({
        "type": "text",
        "text": "Identificá la topología del plano. Devolvé SOLO JSON.",
    })

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=1500,
                system=_GLOBAL_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(image_bytes).decode(),
                            },
                        },
                        *user_blocks,
                    ],
                }],
            ),
            timeout=GLOBAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[multi-crop] global topology timed out ({GLOBAL_TIMEOUT_SECONDS}s)")
        return {"error": "global_topology_timeout"}
    except Exception as e:
        logger.error(f"[multi-crop] global topology API error: {e}")
        return {"error": f"global_topology_error: {e}"}

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        logger.error(f"[multi-crop] global topology JSON parse failed: {text[:400]}")
        return {"error": "global_topology_parse_failed", "_raw": text[:400]}


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2: Per-region measurement
# ─────────────────────────────────────────────────────────────────────────────

_REGION_SYSTEM_PROMPT = """Sos un lector de planos de marmolería.

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

Las cotas candidatas vienen RANKEADAS por compatibilidad geométrica con
la región. Elegir una cota DÉBIL o POCO PROBABLE requiere justificación
visual explícita del crop. NO elegir una EXCLUIDA.

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
"""


# ─────────────────────────────────────────────────────────────────────────────
# PR 2b — Region-aware cota ranking + guardrails
#
# Objetivo: que el VLM elija 2.35 en vez de 2.95 para el tramo vertical de
# Bernardi. El bug es de matching de cotas en pool expanded, no de perímetro.
# 4 capas:
#   1. Hard filter (perímetro + absurdos).
#   2. Ranking SEPARADO para largo y ancho.
#   3. Prompt estructurado (buckets, sin sugerir valores).
#   4. Guardrails post-LLM que bajan confidence cuando ignora el ranking.
# ─────────────────────────────────────────────────────────────────────────────

# Valores por fuera de este rango casi nunca corresponden a mesada residencial
_ABSURD_MIN_M = 0.10
_ABSURD_MAX_M = 6.0

# Perímetro probable: valor alto + lejos del bbox de la región
_PERIMETER_VALUE_THRESHOLD_M = 3.0
_PERIMETER_DISTANCE_THRESHOLD_NORM = 0.20  # suma de distancias x+y normalizadas

# Rangos típicos para cocinas residenciales
_LENGTH_TYPICAL_RANGE = (1.0, 4.0)
_DEPTH_TYPICAL_RANGE = (0.40, 0.80)
_DEPTH_ANCHO_REFERENCE_RANGE = (0.3, 0.8)  # usamos 0.60 y similares como escala

# Umbrales de bucket (score sumatorio 0..100)
_BUCKET_PREFERRED = 60
_BUCKET_WEAK = 40
_BUCKET_UNLIKELY = 20


def _bbox_to_px(bbox: dict, image_size: tuple[int, int]) -> dict:
    """Convierte bbox_rel {x,y,w,h} 0..1 → coords absolutas px."""
    img_w, img_h = image_size
    x = int((bbox.get("x") or 0) * img_w)
    y = int((bbox.get("y") or 0) * img_h)
    w = int((bbox.get("w") or 0) * img_w)
    h = int((bbox.get("h") or 0) * img_h)
    return {"x": x, "y": y, "x2": x + w, "y2": y + h, "w": w, "h": h}


def _cota_in_bbox(
    cota: Cota, bbox_px: dict, *, padding_px: int = 0,
) -> bool:
    x, y, x2, y2 = bbox_px["x"], bbox_px["y"], bbox_px["x2"], bbox_px["y2"]
    return (
        x - padding_px <= cota.x <= x2 + padding_px
        and y - padding_px <= cota.y <= y2 + padding_px
    )


def _is_probable_perimeter(
    cota: Cota, region_bbox_px: dict, image_size: tuple[int, int],
) -> bool:
    """Perímetro = valor grande (>3m) + posición fuera del bbox de la región.

    Dos señales combinadas:
    - value > 3m (cotas de ambiente típicamente son más grandes que mesadas).
    - Posición: la cota está fuera del bbox tight de la región. NO importa
      si está pegada o lejos — si el valor es grande y no cae dentro del
      bbox inmediato, es muy probable que sea cota de perímetro del
      ambiente arrastrada visualmente.

    Contraejemplo que la regla NO rompe: una cota 2.50 en la isla que
    estará fuera del bbox de la isla chica — no es perímetro porque su
    valor <3m. El umbral de 3m captura específicamente las cotas de
    perímetro del ambiente (> 3m típicamente).

    Contraejemplo que SÍ se contempla: una cota 3.50 DENTRO del bbox
    tight → no es perímetro, puede ser una mesada larga.
    """
    if cota.value <= _PERIMETER_VALUE_THRESHOLD_M:
        return False
    # Fuera del bbox tight (sin padding) → probable perímetro
    if not _cota_in_bbox(cota, region_bbox_px, padding_px=0):
        return True
    return False


def _tramo_orientation(region_bbox_px: dict) -> str:
    """'vertical' si h > w, sino 'horizontal'. Determina qué cotas son
    candidatas a largo vs ancho."""
    return "vertical" if region_bbox_px["h"] > region_bbox_px["w"] else "horizontal"


def _cota_aligned_with_long_axis(
    cota: Cota, region_bbox_px: dict, orientation: str,
) -> bool:
    """True si la cota está posicionada a lo largo del eje largo del tramo.

    Para un tramo vertical: la cota de largo se escribe típicamente al
    costado (fuera del rango x del bbox) pero alineada con el rango y.
    Para horizontal: al revés.

    Usamos rango ± 30% de tolerancia para capturar cotas escritas
    ligeramente fuera del bbox estricto.
    """
    if orientation == "vertical":
        y_tol = 0.30 * region_bbox_px["h"]
        return (
            region_bbox_px["y"] - y_tol <= cota.y <= region_bbox_px["y2"] + y_tol
        )
    else:
        x_tol = 0.30 * region_bbox_px["w"]
        return (
            region_bbox_px["x"] - x_tol <= cota.x <= region_bbox_px["x2"] + x_tol
        )


def _estimate_plan_scale(
    regions: list[dict], all_cotas: list[Cota], image_size: tuple[int, int],
) -> Optional[float]:
    """Estima `px_per_m` del plano usando pares (region_bbox, cota chica
    local). Señal DÉBIL — solo se usa para penalizar outliers groseros,
    no para decidir entre cotas plausibles.

    Requiere ≥2 pares confiables para que la mediana tenga sentido.
    Devuelve None si no hay suficiente evidencia.
    """
    candidates: list[float] = []
    for region in regions:
        bbox_px = _bbox_to_px(region.get("bbox_rel") or {}, image_size)
        if bbox_px["w"] < 10 or bbox_px["h"] < 10:
            continue
        # Cotas dentro del bbox que caen en el rango de "ancho de mesada"
        local = [
            c for c in all_cotas
            if _cota_in_bbox(c, bbox_px, padding_px=80)
            and _DEPTH_ANCHO_REFERENCE_RANGE[0] <= c.value <= _DEPTH_ANCHO_REFERENCE_RANGE[1]
        ]
        if not local:
            continue
        # Usar la dimensión CORTA del bbox como referencia del ancho
        short_px = min(bbox_px["w"], bbox_px["h"])
        for c in local:
            if c.value > 0:
                candidates.append(short_px / c.value)
    if len(candidates) < 2:
        return None
    candidates.sort()
    return candidates[len(candidates) // 2]  # mediana


def _score_cota(
    cota: Cota,
    region_bbox_px: dict,
    orientation: str,
    scale: Optional[float],
    *,
    candidate_for: str,  # "length" | "depth"
) -> dict:
    """Score sumatorio 0..100 + bucket + razones.

    `candidate_for`: rankeamos por separado para largo y ancho — una cota
    de 0.60 debe ganar como ancho y perder como largo; 2.35 al revés.
    """
    score = 0
    reasons: list[str] = []

    # ── Proximidad al bbox ─────────────────────────────────────────────
    # Tres niveles discretos + ajuste continuo cuando está afuera.
    # El continuo es clave para diferenciar dos cotas ambas "fuera del
    # expanded": si una está más cerca del bbox, se nota en el score.
    # Sin esto, 2.35 y 2.05 quedaban empatadas en R3 de Bernardi.
    if _cota_in_bbox(cota, region_bbox_px, padding_px=80):
        score += 40
        reasons.append("inside_tight_bbox")
    elif _cota_in_bbox(cota, region_bbox_px, padding_px=380):
        score += 15
        reasons.append("inside_expanded_bbox")
    else:
        # Castigo continuo — más lejos del bbox, más resta.
        dist_x = max(
            0, region_bbox_px["x"] - cota.x, cota.x - region_bbox_px["x2"]
        )
        dist_y = max(
            0, region_bbox_px["y"] - cota.y, cota.y - region_bbox_px["y2"]
        )
        # Restamos 1 punto cada 100px fuera del bbox expandido, cap 30.
        dist_px = dist_x + dist_y
        dist_penalty = min(30, dist_px // 100)
        score -= int(dist_penalty)
        reasons.append(f"outside_expanded_bbox_dist{int(dist_px)}px")

    # ── Rango de valor típico según rol ───────────────────────────────
    if candidate_for == "length":
        lo, hi = _LENGTH_TYPICAL_RANGE
        if lo <= cota.value <= hi:
            score += 15
            reasons.append("value_in_length_range")
        else:
            score -= 10
            reasons.append("value_outside_length_range")
    else:  # depth
        lo, hi = _DEPTH_TYPICAL_RANGE
        if lo <= cota.value <= hi:
            score += 35
            reasons.append("value_in_depth_range")
        else:
            score -= 20
            reasons.append("value_outside_depth_range")

    # ── Orientación vs eje ────────────────────────────────────────────
    if candidate_for == "length":
        if _cota_aligned_with_long_axis(cota, region_bbox_px, orientation):
            score += 25
            reasons.append(f"aligned_with_{orientation}_long_axis")
        else:
            score -= 10
            reasons.append("not_aligned_with_long_axis")
    # Para depth la alineación importa menos — el ancho se escribe típico
    # en cualquier lado.

    # ── Span plausibility — penalización escalonada ──────────────────
    # Solo aplica si hay scale confiable. Señal secundaria al valor +
    # orientación, pero más fuerte que antes: deviations groseras empujan
    # a bucket unlikely, no quedan weak "por cercanía".
    if scale and candidate_for == "length":
        bbox_long_px = max(region_bbox_px["w"], region_bbox_px["h"])
        expected_m = bbox_long_px / scale
        if expected_m > 0.5:
            deviation = abs(cota.value - expected_m) / expected_m
            if deviation > 0.50:
                score -= 50
                reasons.append(f"severe_span_mismatch_{int(deviation * 100)}pct")
            elif deviation > 0.30:
                score -= 30
                reasons.append(f"span_mismatch_{int(deviation * 100)}pct")
            elif deviation > 0.15:
                score -= 20
                reasons.append(f"span_deviation_{int(deviation * 100)}pct")
            else:
                score += 10
                reasons.append("span_matches")

    # ── Clamp + bucket ─────────────────────────────────────────────────
    score = max(0, min(100, score))
    if score >= _BUCKET_PREFERRED:
        bucket = "preferred"
    elif score >= _BUCKET_WEAK:
        bucket = "weak"
    elif score >= _BUCKET_UNLIKELY:
        bucket = "unlikely"
    else:
        bucket = "excluded_soft"
    return {
        "value": cota.value,
        "score": score,
        "bucket": bucket,
        "reasons": reasons,
    }


def _filter_length_by_geometry(
    length_ranking: list[dict],
    all_candidate_cotas: list[Cota],
    region_bbox_px: dict,
    scale: Optional[float],
    excluded_hard: list[dict],
) -> list[dict]:
    """Post-filtro del ranking de largo: mueve a `excluded_hard` cotas
    claramente incompatibles con el span geométrico del tramo, priorizando
    preservar alternativas válidas.

    Dos reglas. Si alguna dispara, la cota se excluye. Si ambas disparan,
    se guardan las DOS razones (lista) para logs y tests.

    Regla A — valor alto con alternativas disponibles:
      - value > 4.0m (proxy para cota de perímetro del ambiente).
      - existe al menos 1 alternativa en rango típico [1.0, 4.0] en el pool.
      - Caso Bernardi R3: el topology agarró 4.15 adentro del bbox tight
        del tramo vertical; había 2.35/2.05 en expanded — las mantenemos,
        la 4.15 se excluye.

    Regla B — severa incompatibilidad con span estimado:
      - scale confiable disponible.
      - deviation entre cota y span esperado > 60%.
      - Caso: bbox de tramo chico (~1m esperado) con cota 3.50m → excluir.

    Safety: si el pool total NO tiene alternativas en [1.0, 4.0] (caso
    edificio con todas las mesadas largas), NO se excluye nada por Regla A
    — puede ser una mesada legítimamente de >4m.
    """
    has_valid_alternative = any(
        _LENGTH_TYPICAL_RANGE[0] <= c.value <= _LENGTH_TYPICAL_RANGE[1]
        for c in all_candidate_cotas
    )

    bbox_long_px = max(region_bbox_px["w"], region_bbox_px["h"])
    expected_m = (bbox_long_px / scale) if (scale and scale > 0) else None

    keep: list[dict] = []
    for entry in length_ranking:
        value = entry["value"]
        reasons: list[str] = []

        # Regla A
        if has_valid_alternative and value > 4.0:
            reasons.append("value_over_4m_with_alternatives_available")

        # Regla B
        if expected_m and expected_m > 0.5:
            deviation = abs(value - expected_m) / expected_m
            if deviation > 0.60:
                reasons.append(
                    f"severe_span_incompatibility_{int(deviation * 100)}pct"
                )

        if reasons:
            excluded_hard.append({
                "value": value,
                "reason": "; ".join(reasons),
            })
        else:
            keep.append(entry)

    return keep


def _rank_cotas_for_region(
    cotas: list[Cota],
    region: dict,
    image_size: tuple[int, int],
    scale: Optional[float],
) -> dict:
    """Genera dos rankings (length + depth) + lista de excluidas duras.

    Excluidas duras (pre-scoring):
    - Perímetro probable por posición (valor >3m + fuera del bbox tight).
    - Valor absurdo (<0.1m o >6m).

    Excluidas duras (post-scoring, solo para length):
    - Incompatibilidad geométrica o valor >4m con alternativas disponibles
      (ver `_filter_length_by_geometry`).

    El resto va a preferred/weak/unlikely según score.
    """
    region_bbox_px = _bbox_to_px(region.get("bbox_rel") or {}, image_size)
    orientation = _tramo_orientation(region_bbox_px)

    length_ranking: list[dict] = []
    depth_ranking: list[dict] = []
    excluded_hard: list[dict] = []
    surviving_cotas: list[Cota] = []  # para el filtro geométrico

    for cota in cotas:
        # Hard exclusions pre-scoring
        if cota.value < _ABSURD_MIN_M or cota.value > _ABSURD_MAX_M:
            excluded_hard.append({
                "value": cota.value,
                "reason": "absurd_value",
            })
            continue
        if _is_probable_perimeter(cota, region_bbox_px, image_size):
            excluded_hard.append({
                "value": cota.value,
                "reason": "probable_perimeter",
            })
            continue
        surviving_cotas.append(cota)
        # Score para ambos roles
        length_ranking.append(
            _score_cota(cota, region_bbox_px, orientation, scale, candidate_for="length")
        )
        depth_ranking.append(
            _score_cota(cota, region_bbox_px, orientation, scale, candidate_for="depth")
        )

    # Post-filtro: exclusión geométrica para length (solo).
    length_ranking = _filter_length_by_geometry(
        length_ranking, surviving_cotas, region_bbox_px, scale, excluded_hard,
    )

    # Ordenar desc por score
    length_ranking.sort(key=lambda r: r["score"], reverse=True)
    depth_ranking.sort(key=lambda r: r["score"], reverse=True)

    return {
        "length": length_ranking,
        "depth": depth_ranking,
        "excluded_hard": excluded_hard,
        "orientation": orientation,
        "scale_px_per_m": scale,
    }


def _format_ranking_for_prompt(ranking: dict) -> str:
    """Prompt estructurado — sin sugerir valores específicos."""
    lines: list[str] = []

    def _bucket_label(bucket: str) -> str:
        return {
            "preferred": "PREFERIDAS",
            "weak": "DÉBILES",
            "unlikely": "POCO PROBABLES",
            "excluded_soft": "POCO PROBABLES",  # collapse para el prompt
        }.get(bucket, "POCO PROBABLES")

    def _format_section(title: str, rows: list[dict]) -> list[str]:
        out = [f"{title}:"]
        if not rows:
            out.append("  (ninguna)")
            return out
        by_bucket: dict[str, list[dict]] = {}
        for r in rows:
            by_bucket.setdefault(r["bucket"], []).append(r)
        # Orden fijo
        for bk in ("preferred", "weak", "unlikely", "excluded_soft"):
            entries = by_bucket.get(bk) or []
            if not entries:
                continue
            out.append(f"  {_bucket_label(bk)}:")
            for e in entries[:6]:  # top 6 por bucket
                reasons = ", ".join(e["reasons"][:3])
                out.append(
                    f"    - {e['value']:.2f}m (score {e['score']}) — {reasons}"
                )
        return out

    lines.append(f"Orientación del tramo: {ranking['orientation']}")
    if ranking.get("scale_px_per_m"):
        lines.append("(escala del plano estimada desde cotas locales)")
    lines.append("")
    lines.extend(_format_section("CANDIDATAS PARA LARGO", ranking["length"]))
    lines.append("")
    lines.extend(_format_section("CANDIDATAS PARA ANCHO", ranking["depth"]))

    hard = ranking.get("excluded_hard") or []
    if hard:
        lines.append("")
        lines.append("EXCLUIDAS (no usar):")
        for h in hard[:6]:
            lines.append(f"  - {h['value']:.2f}m — {h['reason']}")

    lines.append("")
    lines.append(
        "Usá el ranking como prior. Elegir una DÉBIL o POCO PROBABLE "
        "requiere justificación visual explícita del crop."
    )

    # PR 2b.2 — Instrucción explícita cuando no hay candidatas válidas para
    # largo. Sin esto, el VLM tiende a "completar" con el valor del ancho
    # (0.60) o algún default, generando basura tipo 0.60 × 0.60. Mejor null
    # honesto → operador ve DUDOSO y completa manual.
    if not ranking.get("length"):
        lines.append("")
        lines.append(
            "**NO hay candidatas válidas para LARGO** (todas fueron excluidas "
            "por ser perímetro del ambiente o estar fuera de rango razonable). "
            "En este caso devolvé `largo_m: null` en el JSON. NO uses el ancho "
            "como largo. NO uses un default estándar. NO inventes: devolvé "
            "`null` honestamente."
        )
    return "\n".join(lines)


def _apply_guardrails(
    vlm_output: dict, ranking: dict, cotas_mode: str = "local",
) -> dict:
    """Post-LLM: valida elección del VLM contra el ranking determinístico
    y baja confidence cuando la elección es sospechosa.

    Se apoya en el RANKING (geométrico/determinístico), NO en el
    `reasoning` del VLM (puede sonar convincente y ser falso).

    Capas:
    1. Valor no en ranking:
       - Si cae en rango típico del rol (0.60 para depth, 2.xx para
         length) → `inferred_default`, cap 0.6 (no 0.3). El VLM infirió
         un valor estándar razonable sin cota explícita — aceptable.
       - Fuera del rango típico → halucinación dura, cap 0.3.
    2. Valor en ranking pero bucket weak/unlikely habiendo preferred →
       cap 0.5, suspicious con detalle.
    3. cotas_mode == "expanded":
       - Cap duro de confidence 0.65 (evidencia ambigua por naturaleza).
       - Si además eligió valor distinto al top-ranked para largo **O**
         ancho (cada campo evaluado por separado, no se exige AND) →
         cap 0.5.
    """
    largo = vlm_output.get("largo_m")
    ancho = vlm_output.get("ancho_m")
    confidence = vlm_output.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    suspicious: list[str] = list(vlm_output.get("suspicious_reasons") or [])

    # PR 2b.2 — Regla dura defensiva contra fallback silencioso del VLM.
    # Cuando el ranking queda vacío (ej: todas las cotas fueron excluidas
    # como perímetro), el VLM tiende a "completar" con un valor razonable
    # — típicamente agarra el ancho 0.60 y lo reporta como largo también.
    # Eso es basura: un tramo de mesada no tiene largo < 1m.
    # Preferimos None honesto que número falso con apariencia válida.
    try:
        if largo is not None and float(largo) < 1.0:
            suspicious.append(
                f"largo {largo}m < 1.0m — implausible como largo de tramo, invalidado"
            )
            vlm_output["largo_m"] = None
            largo = None
            confidence = min(confidence, 0.2)
    except (TypeError, ValueError):
        pass

    def _find_match(value, rank_list):
        if value is None:
            return None
        for r in rank_list:
            if abs(r["value"] - float(value)) <= 0.02:
                return r
        return None

    length_ranking = ranking.get("length") or []
    depth_ranking = ranking.get("depth") or []

    for field_name, value, rank_list, typical_range in [
        ("largo", largo, length_ranking, _LENGTH_TYPICAL_RANGE),
        ("ancho", ancho, depth_ranking, _DEPTH_TYPICAL_RANGE),
    ]:
        if value is None:
            continue
        chosen = _find_match(value, rank_list)
        if chosen is None:
            # Valor no está en el ranking. ¿Cae en rango típico?
            lo, hi = typical_range
            try:
                value_float = float(value)
            except (TypeError, ValueError):
                value_float = None
            if value_float is not None and lo <= value_float <= hi:
                # Inferred default razonable — VLM usó valor estándar sin
                # cota explícita (ej: 0.60 para ancho). No castigo duro.
                suspicious.append(
                    f"{field_name} {value}m inferred (valor típico, no en ranking)"
                )
                confidence = min(confidence, 0.6)
            else:
                # Fuera de rango típico + no en ranking → halucinación
                suspicious.append(
                    f"{field_name} {value}m no está en ranking ni rango típico"
                )
                confidence = min(confidence, 0.3)
            continue
        if chosen["bucket"] in ("weak", "unlikely", "excluded_soft"):
            top_preferred = next(
                (r for r in rank_list if r["bucket"] == "preferred"),
                None,
            )
            if top_preferred and abs(top_preferred["value"] - float(value)) > 0.02:
                suspicious.append(
                    f"VLM eligió {field_name} {chosen['value']}m (bucket "
                    f"{chosen['bucket']}, score {chosen['score']}) habiendo "
                    f"preferred {top_preferred['value']}m (score "
                    f"{top_preferred['score']}) disponible"
                )
                confidence = min(confidence, 0.5)
            # Si no hay preferred, weak puede ser lo mejor — no castigamos

    # ── Cap duro por cotas_mode=expanded ─────────────────────────────
    # Evidencia ambigua por naturaleza. Dos niveles:
    #   1. Cap base 0.65 siempre que sea expanded.
    #   2. Si además el VLM no eligió el top del ranking en largo O ancho
    #      (cada campo evaluado por separado), cap 0.5.
    # El segundo se evalúa por OR — no se exige AND. Un ancho 0.60
    # inferred_default NO distorsiona el cap del largo.
    if cotas_mode == "expanded":
        if confidence > 0.65:
            confidence = 0.65
            suspicious.append("cotas_mode=expanded → cap confidence 0.65")
        for field_name, value, rank_list in [
            ("largo", largo, length_ranking),
            ("ancho", ancho, depth_ranking),
        ]:
            if value is None or not rank_list:
                continue
            chosen = _find_match(value, rank_list)
            if chosen is None:
                # inferred_default — no computa para este check
                continue
            top = rank_list[0]
            if top and abs(top["value"] - float(value)) > 0.02:
                if confidence > 0.5:
                    confidence = 0.5
                    suspicious.append(
                        f"expanded + {field_name}={value}m no es top "
                        f"({top['value']}m score {top['score']}) → cap 0.5"
                    )
                break  # con que uno dispare alcanza

    vlm_output["confidence"] = confidence
    if suspicious:
        vlm_output["suspicious_reasons"] = suspicious
    return vlm_output


async def _measure_region(
    full_image_bytes: bytes,
    image_size: tuple[int, int],
    region: dict,
    candidate_cotas: list[Cota],
    model: str,
    brief_text: str = "",
) -> dict:
    """Mide una región usando un crop local + cotas candidatas filtradas.

    Fail-hard behavior:
    - Si el bbox es inválido o el crop sale vacío → error, sin LLM call.
    - Si la región tiene < 2 cotas locales en el bbox → error, sin LLM call.
      (el LLM no tiene evidencia suficiente para elegir largo + ancho).
    - Después del LLM: si los valores no anclan a las cotas locales o
      largo == ancho (fallback silencioso del LLM cuando no sabe) →
      flaguea `suspicious_reasons` para que el aggregator lo marque
      DUDOSO en vez de CONFIRMADO.
    """
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

    # Filtrar cotas candidatas ANTES de croppear. Dos niveles:
    #   L1 (local): cotas dentro del bbox + padding estándar.
    #   L2 (expanded): si L1 <2, expandimos +300px SOLO el filtro de cotas
    #       (el crop visual sigue siendo bbox original). Cubre el caso típico:
    #       la cota está dibujada justo al borde del bbox del topology LLM,
    #       pero claramente pertenece a esta región.
    #
    # Lo que NO hacemos: pasar TODAS las cotas del plano al LLM cuando el
    # bbox queda lejos. Ese fallback global hacía que el LLM eligiera cotas
    # de OTROS sectores e inventara medidas plausibles pero incorrectas
    # (ej: caso Bernardi — R2 recibió 13 cotas globales, eligió 4.15 que
    # era una cota de perímetro de la isla, no del tramo de cocina).
    # Prefiero "— × —" honesto antes que un número swappeado que el
    # operador pueda confirmar por error.
    local_cotas: list[Cota] = [c for c in candidate_cotas if x <= c.x <= x2 and y <= c.y <= y2]

    MIN_LOCAL_COTAS = 2
    COTA_SEARCH_EXTRA_PX = 300
    cotas_for_llm: list[Cota] = local_cotas
    cotas_mode: str = "local"

    if candidate_cotas and len(local_cotas) < MIN_LOCAL_COTAS:
        ex_x = max(0, x - COTA_SEARCH_EXTRA_PX)
        ex_y = max(0, y - COTA_SEARCH_EXTRA_PX)
        ex_x2 = min(img_w, x2 + COTA_SEARCH_EXTRA_PX)
        ex_y2 = min(img_h, y2 + COTA_SEARCH_EXTRA_PX)
        expanded_cotas = [
            c for c in candidate_cotas
            if ex_x <= c.x <= ex_x2 and ex_y <= c.y <= ex_y2
        ]
        if len(expanded_cotas) >= MIN_LOCAL_COTAS:
            cotas_for_llm = expanded_cotas
            cotas_mode = "expanded"
            logger.info(
                f"[multi-crop] region {region.get('id')}: {len(local_cotas)} cotas "
                f"en bbox tight → {len(expanded_cotas)} en bbox expandido +{COTA_SEARCH_EXTRA_PX}px "
                f"— retry con pool expandido"
            )
        else:
            logger.info(
                f"[multi-crop] region {region.get('id')}: {len(local_cotas)} local / "
                f"{len(expanded_cotas)} expanded cotas (<{MIN_LOCAL_COTAS}) — "
                f"skip LLM, return DUDOSO (no inventamos medidas con pool global)"
            )
            return {
                "error": "insufficient_local_cotas",
                "region_id": region.get("id"),
                "local_cotas_count": len(local_cotas),
                "expanded_cotas_count": len(expanded_cotas),
            }

    # Crop la imagen con PIL
    try:
        img = Image.open(io.BytesIO(full_image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        crop = img.crop((x, y, x2, y2))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=85)
        crop_bytes = buf.getvalue()
    except Exception as e:
        return {"error": f"crop_failed: {e}", "region_id": region.get("id")}

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # PR 2b — Ranking determinístico ANTES del VLM.
    # Scale estimation pasa TODAS las candidatas (no solo cotas_for_llm)
    # para obtener más evidencia si otras regiones tienen cotas locales.
    plan_scale = _estimate_plan_scale([region], candidate_cotas, image_size)
    ranking = _rank_cotas_for_region(cotas_for_llm, region, image_size, plan_scale)
    ranking_txt = _format_ranking_for_prompt(ranking)

    meta_txt = (
        f"Sector: {region.get('sector') or 'cocina'}\n"
        f"Toca paredes: {region.get('touches_walls')}\n"
        f"Tiene pileta: {region.get('has_pileta')} "
        f"({region.get('pileta_type') or 'n/a'})\n"
        f"Tiene anafe: {region.get('has_anafe')} "
        f"(count: {region.get('anafe_count') or 0})\n"
    )
    user_blocks = [
        {
            "type": "text",
            "text": f"METADATA DE LA REGIÓN:\n{meta_txt}",
        },
        {
            "type": "text",
            "text": ranking_txt,
        },
    ]
    if brief_text and brief_text.strip():
        user_blocks.append({
            "type": "text",
            "text": f"CONTEXTO DEL OPERADOR:\n{brief_text.strip()[:400]}",
        })
    user_blocks.append({
        "type": "text",
        "text": "Devolvé SOLO JSON con largo_m/ancho_m de esta región.",
    })

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=800,
                system=_REGION_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(crop_bytes).decode(),
                            },
                        },
                        *user_blocks,
                    ],
                }],
            ),
            timeout=REGION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {"error": "region_timeout", "region_id": region.get("id")}
    except Exception as e:
        return {"error": f"region_api_error: {e}", "region_id": region.get("id")}

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {"error": "region_parse_failed", "region_id": region.get("id"), "_raw": text[:300]}
        try:
            parsed = json.loads(m.group())
        except json.JSONDecodeError:
            return {"error": "region_parse_failed", "region_id": region.get("id"), "_raw": text[:300]}

    parsed["region_id"] = region.get("id")
    parsed["_local_cotas_count"] = len(local_cotas)
    parsed["_cotas_mode"] = cotas_mode
    parsed["_cota_ranking"] = ranking  # expuesto al log [region-detail]

    # PR 2b — Guardrails post-LLM apoyados en el RANKING determinístico
    # (no en el reasoning del VLM que puede sonar convincente y ser falso).
    # PR 2b.1 — además, cap duro de confidence cuando cotas_mode=expanded.
    parsed = _apply_guardrails(parsed, ranking, cotas_mode=cotas_mode)

    # Cuando caímos a fallback expanded, el resultado NUNCA es CONFIRMADO
    # aunque los números sean plausibles — el operador tiene que revisar
    # porque el anchoring no fue estricto.
    if cotas_mode == "expanded":
        _susp = list(parsed.get("suspicious_reasons") or [])
        _susp.append("medida tomada con pool de cotas expandido (no estricto a esta región)")
        parsed["suspicious_reasons"] = _susp

    # Fallback silencioso típico: el modelo devuelve L==A cuando no puede
    # elegir → usualmente agarra 0.60 (el ancho estándar) dos veces.
    largo = parsed.get("largo_m")
    ancho = parsed.get("ancho_m")
    if (
        isinstance(largo, (int, float))
        and isinstance(ancho, (int, float))
        and abs(float(largo) - float(ancho)) < 0.01
    ):
        _susp = list(parsed.get("suspicious_reasons") or [])
        _susp.append(f"largo == ancho ({largo}m) — probable fallback silencioso del VLM")
        parsed["suspicious_reasons"] = _susp

    return parsed


# ─────────────────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────────────────

def _field(valor: Optional[float], status: str = "CONFIRMADO") -> dict:
    return {"opus": None, "sonnet": None, "valor": valor, "status": status}


def _classify_region(region: dict) -> str:
    """Deriva el sector desde las features de la región.

    Reglas de derivación (sin depender del LLM para etiquetar):
    - `touches_wall=False` + (stools_adjacent=True o aislada del perímetro) → isla.
    - `touches_wall=True` → cocina (lados de U / L / recta contra pared).
    - `non_counter_upper=True` → no es mesada, se filtra upstream.
    - Default (sin info): cocina.

    El schema legacy seguía con field `sector` ("cocina"|"isla"|...) — si
    viene seteado se respeta para retrocompat; sino se deriva de features.
    """
    # Retrocompat con el schema viejo
    legacy_sector = (region.get("sector") or "").lower()
    if legacy_sector in ("isla", "cocina", "baño", "lavadero"):
        return legacy_sector
    features = region.get("features") or {}
    if features.get("non_counter_upper"):
        return "descarte"  # upstream debe filtrar
    touches = features.get("touches_wall")
    stools = features.get("stools_adjacent")
    if touches is False or stools is True:
        return "isla"
    return "cocina"


def _derive_description(region: dict) -> str:
    """Construye una descripción humana corta desde las features. Puramente
    descriptiva (sin inventar artefactos que el LLM no vio)."""
    features = region.get("features") or {}
    bits: list[str] = []
    if features.get("cooktop_groups"):
        n = int(features["cooktop_groups"])
        bits.append(f"{n} anafe{'s' if n > 1 else ''}")
    if features.get("sink_double"):
        bits.append("pileta doble")
    elif features.get("sink_simple"):
        bits.append("pileta")
    if features.get("stools_adjacent"):
        bits.append("banquetas")
    base = "Mesada"
    if bits:
        return f"{base} (con {', '.join(bits)})"
    return base


# ─────────────────────────────────────────────────────────────────────────────
# PR 2c — Brief vs features cross-check (mínimo)
#
# Detecta contradicciones obvias entre lo que clasificó el topology LLM y
# lo que dice el brief del operador. Alcance inicial: SOLO isla + anafe
# no confirmado por brief. Atacar otros tipos de contradicción en PRs
# separados si hace falta.
#
# Principio: NO mutamos las features del topology — respetamos el output
# del VLM. Solo HACEMOS VISIBLE la duda vía ambigüedad en el sector +
# sufijo "a confirmar" en la descripción del tramo.
# ─────────────────────────────────────────────────────────────────────────────

_BRIEF_MENTIONS_ANAFE = re.compile(
    r"\b(anafes?|hornallas?|cooktop)\b",
    re.IGNORECASE,
)
_BRIEF_ANAFE_IN_ISLA = re.compile(
    r"\b(anafes?|hornallas?|cooktop).{0,30}isla|"
    r"isla.{0,30}(anafes?|hornallas?|cooktop)",
    re.IGNORECASE | re.DOTALL,
)
# Amplía a cooktop / hornallas, no solo "anafe" — el operador puede usar
# cualquiera de las tres palabras para negarlo.
_BRIEF_ANAFE_NEGATED = re.compile(
    r"\b(sin\s+(anafes?|hornallas?|cooktop)|"
    r"no\s+(lleva|tiene|va|hay)\s+(anafes?|hornallas?|cooktop))\b",
    re.IGNORECASE,
)


def _detect_region_brief_contradictions(region: dict, brief_text: str) -> list[str]:
    """Detecta contradicciones entre features del topology y brief.

    Alcance mínimo (PR 2c): isla con anafe no confirmada por el brief.

    Orden de evaluación (importante):
    1. `brief_places_in_isla` — si el brief asocia anafe con isla explícito,
       NO hay contradicción aunque haya cooktop_groups. Se chequea PRIMERO
       para evitar caer en rama genérica cuando el brief sí asocia los dos.
    2. `brief_negates_anafe` — brief dice "sin anafe" / "sin hornallas":
       topology se equivocó, contradicción fuerte.
    3. `brief_has_anafe` pero NO en isla — topology ubica en isla pero
       brief no asocia isla con anafe: ambiguo.
    4. Brief no menciona anafe — contradicción suave, confirmar.

    Retorna lista de strings (puede ser vacía). NO muta `region`.
    """
    contradictions: list[str] = []
    features = region.get("features") or {}
    touches_wall = features.get("touches_wall")
    cooktop = features.get("cooktop_groups") or 0

    if not (touches_wall is False and cooktop > 0):
        return contradictions  # no hay escenario isla+anafe para chequear

    brief = brief_text or ""
    brief_places_in_isla = bool(_BRIEF_ANAFE_IN_ISLA.search(brief))
    if brief_places_in_isla:
        return contradictions  # brief confirma isla+anafe, sin contradicción

    brief_negates_anafe = bool(_BRIEF_ANAFE_NEGATED.search(brief))
    if brief_negates_anafe:
        contradictions.append(
            "topology detectó anafe en isla pero el brief dice explícitamente "
            "que NO lleva anafe — revisar"
        )
        return contradictions

    brief_has_anafe = bool(_BRIEF_MENTIONS_ANAFE.search(brief))
    if brief_has_anafe:
        contradictions.append(
            "topology ubica anafe en isla pero el brief no asocia anafe "
            "con isla — revisar si va en isla o en cocina"
        )
    else:
        contradictions.append(
            "topology detectó anafe en isla pero el brief no lo menciona "
            "— puede ser confusión visual (símbolo en cocina contigua), "
            "confirmar con el operador"
        )
    return contradictions


def _aggregate(
    topology: dict,
    region_results: list[dict],
    brief_text: str = "",
) -> dict:
    """Combina topología global + medidas por región en el schema dual_read.

    PR 2c: `brief_text` se usa para detectar contradicciones obvias entre
    features del topology y lo que dice el operador (ej: topology marca
    anafe en isla pero brief no lo confirma). La contradicción se agrega
    como ambigüedad del sector + sufijo "a confirmar" en la descripción
    del tramo. NO se muta `region.features` — el output del VLM se respeta.
    """
    # Agrupar regiones por sector derivado de features (o legacy `sector`).
    # Regiones clasificadas como "descarte" (alacenas superiores) se filtran.
    by_sector: dict[str, list[dict]] = {}
    for region in topology.get("regions") or []:
        sec = _classify_region(region)
        if sec == "descarte":
            continue
        by_sector.setdefault(sec, []).append(region)

    sectores: list[dict] = []
    all_ambiguedades: list[dict] = []

    # index results by region_id
    results_by_id = {r.get("region_id"): r for r in region_results if isinstance(r, dict)}

    for sec_name, regions in by_sector.items():
        tramos = []
        for region in regions:
            rid = region.get("id")
            r_result = results_by_id.get(rid) or {}
            largo = r_result.get("largo_m")
            ancho = r_result.get("ancho_m")
            m2 = round(float(largo) * float(ancho), 2) if (
                isinstance(largo, (int, float)) and isinstance(ancho, (int, float))
            ) else None

            # status: DUDOSO si hubo error, medida sospechosa, o faltan valores.
            # CONFIRMADO solo si la medición se ancló a las cotas locales y no
            # hay señales de fallback silencioso.
            error = r_result.get("error")
            suspicious = r_result.get("suspicious_reasons") or []
            if error or suspicious or largo is None or ancho is None:
                status = "DUDOSO"
            else:
                status = "CONFIRMADO"

            # PR 2c: contradicciones brief vs features (no mutamos features).
            contradictions = _detect_region_brief_contradictions(region, brief_text)

            # Descripción: deriva de `features` de la región (contrato PR E).
            # No inventamos artefactos — solo los que están en features.
            base_desc = _derive_description(region)
            n = len(tramos) + 1
            if base_desc == "Mesada":
                desc = f"Mesada {n}"
            else:
                desc = base_desc
            # Sufijo "— revisar" por status no-CONFIRMADO (preexistente).
            if status != "CONFIRMADO":
                desc = f"{desc} — revisar"
            # PR 2c: sufijo "— a confirmar" por contradicción brief/features.
            # Si ya dice "— revisar", no duplicamos; si no, lo agregamos.
            if contradictions and "a confirmar" not in desc and "revisar" not in desc:
                desc = f"{desc} — a confirmar"

            tramo = {
                "id": rid or f"t{n}",
                "descripcion": desc,
                "largo_m": _field(largo, status),
                "ancho_m": _field(ancho, status),
                "m2": _field(m2, status),
                "zocalos": [],
                "frentin": [],
                "regrueso": [],
                "features": region.get("features") or {},
            }
            if contradictions:
                tramo["_contradictions"] = contradictions
            tramos.append(tramo)

            if error:
                all_ambiguedades.append({
                    "tipo": "REVISION",
                    "texto": f"Región {rid}: no se pudo medir ({error}) — completá manual",
                })
            elif suspicious:
                all_ambiguedades.append({
                    "tipo": "REVISION",
                    "texto": f"Región {rid}: medida dudosa ({'; '.join(suspicious)[:120]})",
                })

            # PR 2c: cada contradicción va como bullet REVISION independiente
            for c_text in contradictions:
                all_ambiguedades.append({
                    "tipo": "REVISION",
                    "texto": f"Región {rid}: {c_text}",
                })

        sectores.append({
            "id": f"sector_{sec_name}",
            "tipo": sec_name,
            "tramos": tramos,
            # Propagamos las ambigüedades del aggregator al primer sector
            # (el frontend las rendera como "Revisar en plano" + bullets).
            "ambiguedades": list(all_ambiguedades) if sec_name == next(iter(by_sector)) else [],
        })

    if not sectores:
        # Edge case: global topology devolvió 0 regiones. Fallback implícito
        # a un sector vacío que el frontend renderiza igual, operador puede
        # agregar tramos manual.
        sectores.append({
            "id": "sector_cocina",
            "tipo": "cocina",
            "tramos": [],
            "ambiguedades": [{"tipo": "REVISION", "texto": "No se detectaron regiones de mesada"}],
        })

    return {
        "sectores": sectores,
        "requires_human_review": bool(all_ambiguedades) or len(sectores[0]["tramos"]) == 0,
        "conflict_fields": [],
        "source": "MULTI_CROP",
        "view_type": topology.get("view_type", "planta"),
        "view_type_reason": "multi-crop global topology",
        "m2_warning": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Plan B — Cache global por plan_hash + retry condicional + instability
# ─────────────────────────────────────────────────────────────────────────────

# Regex reusadas del detector de PR 2c.
_BRIEF_NEGATES_ANAFE = _BRIEF_ANAFE_NEGATED  # alias, ya está arriba en este módulo
_BRIEF_DOUBLE_SINK = re.compile(
    r"\b(doble\s+(bacha|pileta)|2\s+bachas|pileta\s+doble)\b",
    re.IGNORECASE,
)


def detect_strong_contradictions(topology: dict, brief_text: str) -> list[str]:
    """Contradicciones FUERTES topology vs brief. Solo estas disparan
    retry/bypass. Señales débiles quedan como ambigüedades (no pagan
    tokens extra).

    Reglas:
    - Count mismatch: brief sugiere N explícito Y topology devolvió < N.
    - Brief niega anafe/hornallas/cooktop, topology tiene cooktop_groups>0.
    - Brief dice pileta doble, topology no detectó sink_double en ninguna.
    """
    strong: list[str] = []
    brief = brief_text or ""
    regions = topology.get("regions") or []
    n_regions = len(regions)

    # Regla A — count mismatch
    expected = _infer_expected_region_count(brief)
    if expected and n_regions < expected["count"]:
        strong.append(
            f"count_mismatch: brief sugiere {expected['count']} tramos "
            f"({expected['description']}), topology devolvió {n_regions}"
        )

    # Regla B — brief niega anafe explícito pero topology afirma
    if _BRIEF_NEGATES_ANAFE.search(brief):
        for r in regions:
            features = r.get("features") or {}
            if (features.get("cooktop_groups") or 0) > 0:
                strong.append(
                    f"brief_negates_anafe_but_topology_has_cooktop: "
                    f"region {r.get('id')} cooktop_groups="
                    f"{features.get('cooktop_groups')}"
                )
                break

    # Regla C — brief dice pileta doble, topology no la tiene en ninguna
    if _BRIEF_DOUBLE_SINK.search(brief):
        has_double = any(
            (r.get("features") or {}).get("sink_double") for r in regions
        )
        if not has_double:
            strong.append(
                "brief_mentions_double_sink_but_topology_has_none"
            )

    return strong


def _iou_bbox_rel(bb1: dict, bb2: dict) -> float:
    """IoU (intersection over union) de dos bbox_rel {x,y,w,h} normalizados
    en 0..1. Retorna 0 si alguno está vacío."""
    if not bb1 or not bb2:
        return 0.0
    x1, y1 = bb1.get("x", 0), bb1.get("y", 0)
    w1, h1 = bb1.get("w", 0), bb1.get("h", 0)
    x2, y2 = bb2.get("x", 0), bb2.get("y", 0)
    w2, h2 = bb2.get("w", 0), bb2.get("h", 0)
    # Intersection
    ix = max(0.0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0.0, min(y1 + h1, y2 + h2) - max(y1, y2))
    intersection = ix * iy
    if intersection <= 0:
        return 0.0
    union = (w1 * h1) + (w2 * h2) - intersection
    return intersection / union if union > 0 else 0.0


def _topologies_diverge(
    t1: dict, t2: dict, iou_threshold: float = 0.5,
) -> bool:
    """True si dos topologies del mismo plan_hash difieren materialmente.

    Sin pairing semántico — orden importa. Si el orden cambia, también
    cuenta como divergencia (útil señal de ruido del VLM)."""
    r1 = t1.get("regions") or []
    r2 = t2.get("regions") or []
    if len(r1) != len(r2):
        return True
    for a, b in zip(r1, r2):
        if _iou_bbox_rel(a.get("bbox_rel") or {}, b.get("bbox_rel") or {}) < iou_threshold:
            return True
    return False


async def _get_or_build_topology(
    db,
    plan_hash: str | None,
    quote_id: str | None,
    image_bytes: bytes,
    brief_text: str,
    model: str,
) -> tuple[dict, dict]:
    """Entry point del cache+retry. Devuelve `(topology, meta)` donde:
    - topology: el dict a usar para la fase de medición.
    - meta: info para loggear / persistir en quote_breakdown.topology_cache_meta
      (from_cache, cache_source_quote_id, replaced_cache, retry_failed,
       stability_status al terminar).

    Si `db` o `plan_hash` no están disponibles → se saltea cache por
    completo (fallback a comportamiento previo, una sola llamada).

    Si el cache existente ya está marcado como `unstable`, NO intentamos
    bypass/retry (evita loop caro). Usamos cache + marcamos review.
    """
    from app.models.plan_topology_cache import PlanTopologyCache
    from sqlalchemy import select as sql_select

    meta: dict = {
        "plan_hash": plan_hash,
        "from_cache": False,
        "cache_source_quote_id": None,
        "replaced_cache": False,
        "retry_failed": False,
        "stability_status": "stable",
    }

    if not (plan_hash and db):
        topology = await _call_global_topology(image_bytes, model, brief_text)
        meta["note"] = "skipped_cache_missing_hash_or_db"
        return topology, meta

    # ── Lookup cache ────────────────────────────────────────────────
    cached_row: PlanTopologyCache | None = None
    try:
        r = await db.execute(
            sql_select(PlanTopologyCache).where(
                PlanTopologyCache.plan_hash == plan_hash
            )
        )
        cached_row = r.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"[topology-cache] lookup failed: {e}, proceding without cache")
        cached_row = None

    if cached_row is not None:
        cached_topology = dict(cached_row.topology_json or {})
        cached_status = cached_row.stability_status or "stable"
        meta["from_cache"] = True
        meta["cache_source_quote_id"] = cached_row.source_quote_id
        meta["stability_status"] = cached_status
        logger.info(
            f"[topology-cache] HIT plan_hash={plan_hash} "
            f"source_quote_id={cached_row.source_quote_id} "
            f"status={cached_status} n_regions={cached_row.n_regions}"
        )

        # Si el hash ya está marcado como unstable, NO reintentamos —
        # usamos cache + marcamos review. Evita loop de retry en planos
        # que ya demostraron ser problemáticos.
        if cached_status == "unstable":
            logger.info(
                f"[topology-cache] hash marked unstable — using cache "
                "as-is, review flag will be set"
            )
            return cached_topology, meta

        # Si el cache contradice fuerte el brief, intentamos un fresh retry.
        contradictions = detect_strong_contradictions(cached_topology, brief_text)
        if not contradictions:
            return cached_topology, meta

        logger.info(
            f"[topology-cache] hit but contradicts brief "
            f"({len(contradictions)} issues) — bypass cache for fresh retry: "
            f"{contradictions[0][:80]}"
        )
        retry_hint = (
            "Tu respuesta cacheada anterior contradijo el brief del operador: "
            + "; ".join(contradictions[:2])
            + ". Revisá la segmentación teniendo eso en cuenta."
        )
        try:
            fresh = await _call_global_topology(
                image_bytes, model, brief_text, extra_user_text=retry_hint,
            )
        except Exception as e:
            logger.warning(f"[topology-cache] fresh retry raised: {e}")
            fresh = {"error": f"retry_exception: {e}"}

        if fresh.get("error"):
            # Retry falló — usar cache pero marcar explícito.
            meta["retry_failed"] = True
            logger.warning(
                f"[topology-cache] retry_failed=true reason={fresh['error']} "
                f"fallback_to=cache"
            )
            return cached_topology, meta

        # Evaluar cuál es mejor: el que tiene menos contradicciones fuertes.
        contradictions_fresh = detect_strong_contradictions(fresh, brief_text)
        if len(contradictions_fresh) >= len(contradictions):
            logger.info(
                f"[topology-cache] fresh retry also contradicts "
                f"({len(contradictions_fresh)} vs {len(contradictions)}) "
                "— keep cache"
            )
            meta["retry_failed"] = False  # funcionó técnicamente, solo no mejoró
            return cached_topology, meta

        # Fresh gana. Actualizar cache global (posible marcar unstable si
        # divergió materialmente del cached).
        meta["replaced_cache"] = True
        diverges = _topologies_diverge(cached_topology, fresh)
        new_status = "unstable" if diverges else "stable"
        meta["stability_status"] = new_status
        await _persist_cache(
            db, plan_hash, fresh, quote_id or cached_row.source_quote_id,
            diverged=diverges, prev_row=cached_row,
        )
        # Incluir metadata al snapshot perdedor en quote_breakdown (caller)
        meta["alternate_topology_loser"] = cached_topology
        return fresh, meta

    # ── Cache miss: fresh call + persistir ───────────────────────────
    logger.info(f"[topology-cache] MISS plan_hash={plan_hash} — fresh call")
    fresh = await _call_global_topology(image_bytes, model, brief_text)
    if fresh.get("error"):
        return fresh, meta

    meta["from_cache"] = False
    # Persistir nuevo cache (stable por default cuando no había anterior)
    if quote_id:
        await _persist_cache(
            db, plan_hash, fresh, quote_id, diverged=False, prev_row=None,
        )
    return fresh, meta


async def _persist_cache(
    db,
    plan_hash: str,
    topology: dict,
    source_quote_id: str,
    *,
    diverged: bool,
    prev_row,
) -> None:
    """Upsert del cache. Si prev_row existe, actualiza in-place. Si diverged,
    marca stability_status=unstable y bump divergence_count."""
    from app.models.plan_topology_cache import PlanTopologyCache
    from sqlalchemy import update as sql_update
    n_regions = len(topology.get("regions") or [])
    try:
        if prev_row is None:
            new_row = PlanTopologyCache(
                plan_hash=plan_hash,
                topology_json=topology,
                stability_status="stable",
                n_regions=n_regions,
                divergence_count=0,
                source_quote_id=source_quote_id,
            )
            db.add(new_row)
            await db.commit()
            logger.info(
                f"[topology-cache] persisted new plan_hash={plan_hash} "
                f"source_quote_id={source_quote_id} n_regions={n_regions}"
            )
            return
        # Update existing row
        new_status = "unstable" if diverged else prev_row.stability_status
        new_divergence = (prev_row.divergence_count or 0) + (1 if diverged else 0)
        await db.execute(
            sql_update(PlanTopologyCache)
            .where(PlanTopologyCache.plan_hash == plan_hash)
            .values(
                topology_json=topology,
                stability_status=new_status,
                n_regions=n_regions,
                divergence_count=new_divergence,
                source_quote_id=source_quote_id,
            )
        )
        await db.commit()
        logger.info(
            f"[topology-cache] updated plan_hash={plan_hash} "
            f"status={new_status} divergence_count={new_divergence}"
        )
    except Exception as e:
        logger.warning(f"[topology-cache] persist failed: {e}, non-blocking")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def read_plan_multi_crop(
    image_bytes: bytes,
    cotas: list[Cota],
    brief_text: str = "",
    model: str = None,
    *,
    plan_hash: str | None = None,
    quote_id: str | None = None,
    db=None,
) -> dict:
    """Drop-in replacement de `dual_read_crop` con pipeline multi-crop.

    PR Plan B: si `plan_hash` + `db` están presentes, usa cache global
    (tabla `plan_topology_cache`) para reusar topology entre quotes.
    Sin esos params funciona como antes (sin cache).

    Retorna el mismo shape JSON + `topology_cache_meta` para que el caller
    lo guarde en `quote_breakdown` como traza.
    """
    _model = model or settings.ANTHROPIC_MODEL

    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img_size = img.size
    except Exception as e:
        logger.error(f"[multi-crop] image open failed: {e}")
        return {"error": f"image_open_failed: {e}"}

    logger.info(f"[multi-crop] starting — image {img_size}, {len(cotas)} cotas")

    # Fase 1: topología (con cache/retry de Plan B)
    topology, topology_meta = await _get_or_build_topology(
        db, plan_hash, quote_id, image_bytes, brief_text, _model,
    )
    if topology.get("error"):
        logger.warning(f"[multi-crop] global topology failed: {topology['error']}")
        return {"error": topology["error"]}

    regions = topology.get("regions") or []
    logger.info(f"[multi-crop] global topology detected {len(regions)} regions")

    # Diagnostic log: full topology response structurado. Crítico para
    # debuggear casos donde la clasificación sale mal (ej: plano Bernardi
    # abril 2026 — topology detectó 2 regiones en vez de 3, clasificó "isla
    # con anafe" a lo que es un tramo de la L). Sin esto tenemos que
    # reproducir el caso pidiéndole al operador que lo vuelva a subir.
    try:
        _topology_summary = {
            "view_type": topology.get("view_type"),
            "n_regions": len(regions),
            "regions": [
                {
                    "id": r.get("id"),
                    "bbox_rel": r.get("bbox_rel"),
                    "features": r.get("features"),
                    "evidence": (r.get("evidence") or "")[:120],
                    "legacy_sector": r.get("sector"),
                }
                for r in regions
            ],
            "brief_len": len(brief_text or ""),
            "brief_preview": (brief_text or "")[:200],
            "cotas_count": len(cotas),
            "cotas_values": sorted({round(c.value, 2) for c in cotas}),
        }
        logger.info(f"[multi-crop/topology-detail] {json.dumps(_topology_summary, ensure_ascii=False)}")
    except Exception as _e_log:
        logger.warning(f"[multi-crop] topology detail log failed: {_e_log}")

    if not regions:
        return {"error": "no_regions_detected"}

    # Fase 2: mediciones en paralelo
    tasks = [
        _measure_region(image_bytes, img_size, r, cotas, _model, brief_text)
        for r in regions
    ]
    region_results = await asyncio.gather(*tasks, return_exceptions=True)
    # Mapear excepciones → error dict
    region_results = [
        (r if isinstance(r, dict) else {"error": f"exception: {r}", "region_id": None})
        for r in region_results
    ]
    ok_count = sum(1 for r in region_results if not r.get("error"))
    logger.info(f"[multi-crop] {ok_count}/{len(regions)} regions measured successfully")

    # Diagnostic log: resumen por región de lo que devolvió el LLM (o el
    # error). Útil para ver en prod qué cota eligió cada región — si eligió
    # una cota swappeada de otro sector, es señal de que el topology puso
    # el bbox mal. Pareado con el log [topology-detail] de arriba tenemos
    # el pipeline completo en los logs sin tener que reproducir el caso.
    try:
        _region_summary = []
        for r in region_results:
            _ranking = r.get("_cota_ranking") or {}
            _region_summary.append({
                "region_id": r.get("region_id"),
                "error": r.get("error"),
                "largo_m": r.get("largo_m"),
                "ancho_m": r.get("ancho_m"),
                "cotas_mode": r.get("_cotas_mode"),
                "local_cotas": r.get("_local_cotas_count"),
                "expanded_cotas": r.get("expanded_cotas_count"),
                "confidence": r.get("confidence"),
                "suspicious": r.get("suspicious_reasons"),
                "rejected": [
                    {"v": c.get("value"), "why": (c.get("reason") or "")[:60]}
                    for c in (r.get("rejected_candidates") or [])[:3]
                ],
                # PR 2b.1 — ranking determinístico completo, para diagnóstico.
                # Sin esto estamos ciegos: no sabemos si falla el filtro, el
                # scoring o el guardrail.
                "ranking": {
                    "orientation": _ranking.get("orientation"),
                    "scale_px_per_m": _ranking.get("scale_px_per_m"),
                    "length_top": [
                        {"v": e["value"], "s": e["score"], "b": e["bucket"]}
                        for e in (_ranking.get("length") or [])[:4]
                    ],
                    "depth_top": [
                        {"v": e["value"], "s": e["score"], "b": e["bucket"]}
                        for e in (_ranking.get("depth") or [])[:4]
                    ],
                    "excluded_hard": [
                        {"v": h["value"], "why": (h.get("reason") or "")[:60]}
                        for h in (_ranking.get("excluded_hard") or [])
                    ],
                } if _ranking else None,
            })
        logger.info(f"[multi-crop/region-detail] {json.dumps(_region_summary, ensure_ascii=False)}")
    except Exception as _e_log:
        logger.warning(f"[multi-crop] region detail log failed: {_e_log}")

    result = _aggregate(topology, region_results, brief_text=brief_text)

    # Plan B — anexar topology_cache_meta + flags de review si aplica
    if result and not result.get("error"):
        result["topology_cache_meta"] = topology_meta
        # Promote requires_human_review si retry falló o el cache es unstable.
        if topology_meta.get("retry_failed") or topology_meta.get("stability_status") == "unstable":
            result["requires_human_review"] = True
            # Inject ambiguedad explícita en primer sector para que la UI
            # la muestre como bullet "Revisar en plano" (patrón ya existente).
            sectores = result.get("sectores") or []
            if sectores:
                amb_list = list(sectores[0].get("ambiguedades") or [])
                if topology_meta.get("retry_failed"):
                    amb_list.append({
                        "tipo": "REVISION",
                        "texto": (
                            "No se pudo validar el topology contra el brief "
                            "(retry LLM falló) — revisá las medidas con cuidado."
                        ),
                    })
                if topology_meta.get("stability_status") == "unstable":
                    amb_list.append({
                        "tipo": "REVISION",
                        "texto": (
                            "Topology inestable — dos lecturas del mismo "
                            "plano divergieron. Revisá medidas con cuidado."
                        ),
                    })
                sectores[0]["ambiguedades"] = amb_list

    return result
