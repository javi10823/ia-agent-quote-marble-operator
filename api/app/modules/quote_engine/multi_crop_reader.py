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
) -> dict:
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
    cotas_txt = format_cotas_for_prompt(cotas_for_llm) if cotas_for_llm else "(sin cotas extraídas)"
    cotas_header = {
        "local": "COTAS LOCALES (dentro del bbox de esta región):",
        "expanded": (
            "COTAS CERCANAS (dentro del bbox expandido — algunas pueden "
            "pertenecer a regiones vecinas, descartá las que no correspondan):"
        ),
    }[cotas_mode]
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
            "text": f"{cotas_header}\n{cotas_txt}",
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

    # Sanity checks post-LLM: marcamos suspicious_reasons para que el
    # aggregator emita DUDOSO en vez de CONFIRMADO. Regla: no aceptar
    # output del VLM con "cara de confiado" cuando la evidencia no cierra.
    largo = parsed.get("largo_m")
    ancho = parsed.get("ancho_m")
    suspicious: list[str] = []
    # Anclamos contra TODAS las cotas que le pasamos al LLM (no solo las
    # estrictamente locales): si usamos el pool expanded/global y el LLM
    # eligió una cota real, el valor está anclado — aceptable aunque no
    # sea "local". El nivel de confianza viene del flag cotas_mode, no
    # de si la cota vino del bbox estricto.
    cota_values = [c.value for c in cotas_for_llm]

    def _anchored(v) -> bool:
        if v is None or not isinstance(v, (int, float)):
            return False
        return any(abs(float(v) - cv) <= 0.02 for cv in cota_values)

    if cotas_for_llm:
        if largo is not None and not _anchored(largo):
            suspicious.append(f"largo {largo}m no está en las cotas candidatas ({cotas_mode})")
        if ancho is not None and not _anchored(ancho):
            suspicious.append(f"ancho {ancho}m no está en las cotas candidatas ({cotas_mode})")

    # Cuando caímos a fallback expanded o global, el resultado NUNCA es
    # CONFIRMADO aunque los números sean plausibles — el operador tiene
    # que revisar porque el anchoring no fue estricto. Esto es la línea
    # roja de "fail-loud": mostramos número (útil para arrancar), pero
    # con badge DUDOSO para que se revise.
    if cotas_mode == "expanded":
        suspicious.append(
            "medida tomada con pool de cotas expandido (no estricto a esta región)"
        )
    elif cotas_mode == "global_fallback":
        suspicious.append(
            "medida tomada con fallback global (no había cotas cercanas a esta región) — revisar"
        )

    # Fallback silencioso típico: el modelo devuelve L==A cuando no puede
    # elegir → usualmente agarra 0.60 (el ancho estándar) dos veces.
    if (
        isinstance(largo, (int, float))
        and isinstance(ancho, (int, float))
        and abs(float(largo) - float(ancho)) < 0.01
    ):
        suspicious.append(f"largo == ancho ({largo}m) — probable fallback silencioso del VLM")

    if suspicious:
        parsed["suspicious_reasons"] = suspicious

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


def _aggregate(topology: dict, region_results: list[dict]) -> dict:
    """Combina topología global + medidas por región en el schema dual_read."""
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

            # Descripción: deriva de `features` de la región (contrato PR E).
            # No inventamos artefactos — solo los que están en features.
            base_desc = _derive_description(region)
            n = len(tramos) + 1
            if base_desc == "Mesada":
                desc = f"Mesada {n}" + (" — revisar" if status != "CONFIRMADO" else "")
            else:
                desc = base_desc + (" — revisar" if status != "CONFIRMADO" else "")

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
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def read_plan_multi_crop(
    image_bytes: bytes,
    cotas: list[Cota],
    brief_text: str = "",
    model: str = None,
) -> dict:
    """Drop-in replacement de `dual_read_crop` con pipeline multi-crop.

    Retorna el mismo shape JSON. Si falla la fase global, devuelve
    `{"error": ...}` y el caller debería caer al pipeline legacy.
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

    # Fase 1: topología
    topology = await _call_global_topology(image_bytes, _model, brief_text)
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
            })
        logger.info(f"[multi-crop/region-detail] {json.dumps(_region_summary, ensure_ascii=False)}")
    except Exception as _e_log:
        logger.warning(f"[multi-crop] region detail log failed: {_e_log}")

    return _aggregate(topology, region_results)
