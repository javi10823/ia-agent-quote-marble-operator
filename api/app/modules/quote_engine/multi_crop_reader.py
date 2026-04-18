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
- Cuántas regiones de mesada hay.
- Dónde está cada una (bbox en coordenadas relativas 0-1 respecto a la imagen).
- Qué artefactos tiene cada una (pileta, anafe, horno, isla, etc).

**Señal visual dominante:** las mesadas se dibujan como **regiones rellenas
en gris oscuro**. Todo lo que NO está relleno en gris oscuro (alacenas,
módulos superiores, electrodomésticos free-standing, paredes) NO es mesada.

**No tenés que medir nada en esta pasada.** Solo identificá regiones.

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
  superior (heladera/horno/despensa como módulo alto), NO mesada. En ese
  caso NO debería estar en la lista — pero si hay duda, marcalo true para
  que el aggregator lo filtre.
- U + isla = 4 regiones (3 lados + 1 isla). L = 2. Recta = 1.
- bbox_rel: (x,y) top-left + (w,h) relativos a la imagen.
- NO etiquetes "isla" ni "cocina" — eso sale de combinar features.
- NO inventes regiones que no ves.
"""


async def _call_global_topology(
    image_bytes: bytes,
    model: str,
    brief_text: str = "",
) -> dict:
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_blocks = []
    if brief_text and brief_text.strip():
        user_blocks.append({
            "type": "text",
            "text": (
                "CONTEXTO DEL OPERADOR:\n"
                f"```\n{brief_text.strip()}\n```\n\n"
                "Usalo para desambiguar si corresponde."
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

    # Filtrar cotas candidatas ANTES de croppear: si no hay evidencia
    # suficiente para elegir largo + ancho, cortamos acá sin gastar la
    # llamada al LLM. Menos latencia + menos tokens + menos chance de
    # que el modelo fabrique un 0.60×0.60 silencioso.
    local_cotas: list[Cota] = []
    for c in candidate_cotas:
        if x <= c.x <= x2 and y <= c.y <= y2:
            local_cotas.append(c)

    MIN_LOCAL_COTAS = 2
    if candidate_cotas and len(local_cotas) < MIN_LOCAL_COTAS:
        logger.info(
            f"[multi-crop] region {region.get('id')} has only {len(local_cotas)} "
            f"local cotas (<{MIN_LOCAL_COTAS}) — skip LLM, return DUDOSO"
        )
        return {
            "error": "insufficient_local_cotas",
            "region_id": region.get("id"),
            "local_cotas_count": len(local_cotas),
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
    cotas_txt = format_cotas_for_prompt(local_cotas) if local_cotas else "(sin cotas extraídas en esta región)"
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
            "text": f"COTAS CANDIDATAS (del text layer del PDF):\n{cotas_txt}",
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

    # Sanity checks post-LLM: marcamos suspicious_reasons para que el
    # aggregator emita DUDOSO en vez de CONFIRMADO. Regla: no aceptar
    # output del VLM con "cara de confiado" cuando la evidencia no cierra.
    largo = parsed.get("largo_m")
    ancho = parsed.get("ancho_m")
    suspicious: list[str] = []
    cota_values = [c.value for c in local_cotas]

    def _anchored(v) -> bool:
        if v is None or not isinstance(v, (int, float)):
            return False
        return any(abs(float(v) - cv) <= 0.02 for cv in cota_values)

    if local_cotas:
        if largo is not None and not _anchored(largo):
            suspicious.append(f"largo {largo}m no está en las cotas locales de la región")
        if ancho is not None and not _anchored(ancho):
            suspicious.append(f"ancho {ancho}m no está en las cotas locales de la región")

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

    return _aggregate(topology, region_results)
