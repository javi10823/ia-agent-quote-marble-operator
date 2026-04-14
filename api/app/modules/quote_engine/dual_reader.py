"""Dual vision reader for marble workshop plans.

Sends the same cropped plan image to Claude Sonnet (fast) first.
If Sonnet reports high confidence (≥0.9), uses that result directly.
If Sonnet is unsure, also sends to Claude Opus and reconciles.

All measurement extraction is via structured JSON with strict enum
for zócalo sides — no fuzzy matching needed in reconciliation.

Flag: dual_read_enabled (config.json ai_engine section)
  - true  → Sonnet first, Opus on demand, reconciliation
  - false → Sonnet only, direct result, no reconciliation
"""
import asyncio
import base64
import json
import logging
import re
from typing import Optional

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# System prompt — same for both models (comparison limpia)
# ═══════════════════════════════════════════════════════

PLAN_READER_SYSTEM_PROMPT = """# SYSTEM PROMPT — LECTOR DE PLANOS DE MARMOLERÍA
## Versión 1.0 | DevLabs

Sos un lector experto de planos de marmolería con criterio de arquitecto.
Antes de cualquier cálculo, RENDERIZÁ cada sector individualmente a 300 DPI con crop.
Nunca confíes en la vista general del plano. Sin excepción.

## PROTOCOLO DE LECTURA — 4 PASADAS OBLIGATORIAS

**Pasada 1 — Inventario**
Identificá todos los sectores presentes (cocina, baño, lavadero, etc.)

**Pasada 2 — Geometría por sector**
Determiná el tipo de mesada:
- RECTA     : 1 tramo. Tomá largo × ancho del rectángulo total.
- EN L      : 2 tramos COMPLEMENTARIOS. Verificá: prof_tramo1 + largo_tramo2 ≈ dim exterior. NO sumes piezas completas — se solaparían.
- EN U      : 3 tramos complementarios. Mismo criterio.
- ISLA      : rectángulo total. Recortes internos son merma — NO reducen m².

**Pasada 3 — Cotas**
- VISTA EN PLANTA    : largo (eje horizontal) × ancho (profundidad)
- VISTA EN ELEVACIÓN : dimensión SOBRE línea de mesada = zócalo | dimensión BAJO = frentin/faldón
- Z antes de número  = longitud de zócalo en cm

**Pasada 4 — Validación**
Verificá consistencia entre vistas. Si hay contradicción → anotá en ambiguedades.

## REGLA CRÍTICA — DIMENSIÓN DE PLACA vs. ML DE ZÓCALO

Son dos medidas DISTINTAS. NUNCA las confundas.
- **Placa (tramo):** dimensión del mármol. Define el rectángulo de la pieza. Usala para calcular m².
- **Zócalo (ml):** longitud de la pared donde va el zócalo. Puede ser MAYOR que la placa. Usala para m² de zócalo.

## REGLA — ZÓCALOS: SOLO POR COTA EXPLÍCITA

NUNCA derives zócalos de los lados de la pieza. Un zócalo existe SOLO si el plano muestra:
- Cota etiquetada como Z, ZOC, ZÓCALO o similar
- Dimensión explícita con altura (ej: 1.74 ML × 0.07)
- Indicación textual en tabla de características
Si no hay cota → ese lado no tiene zócalo. No inferir.
Altura default: 0.07m si se indica "zócalos 7 cm".

## REGLA — FRENTIN / FALDÓN: SOLO POR EVIDENCIA EXPLÍCITA

Frentin/faldón SOLO si el plano muestra vista de elevación con cota debajo de la línea de mesada.
Si no hay vista de elevación → frentin = [].

## REGLA — REGRUESO

Regrueso = terminación lateral del zócalo en receptáculos de ducha.
Si no hay duchas → regrueso = 0. SIMPLE por default.

## REGLAS DE COGNICIÓN VISUAL Y OCR

1. Escaneá rótulo/notas en márgenes para unidades, espesores, materiales.
2. LÍNEAS DE CONTORNO (gruesas) ≠ LÍNEAS DE COTA (finas con flechas).
3. Textos rotados: leé paralelo a su línea de cota.
4. Cuidado OCR: 5 vs S, 6 vs 8, 1 vs 7.
5. Si cota < 10 y otra > 50 → normalizar a metros.
6. Validar proporciones visuales: si 60 y 120, el segundo debe verse el doble.

## OTRAS REGLAS FIJAS

- Mesada > 3m → "SE REALIZA EN 2 TRAMOS"
- m² redondeados a 2 decimales
- Signo ambiguo → NO interpretes, anotar en ambiguedades
- NUNCA asumir simetría
- Johnson (pileta) → PEGADOPILETA

## REGLA DE ESQUINAS — SIN SUPERFICIE DOBLE

EN L: Un tramo FULL (con esquina), otro NETO (empieza donde termina el full).
EN U: Laterales FULL, medio NETO (restar depth de ambos laterales).
Verificar: depth_full + largo_neto = dim exterior total.

## FORMATO DE SALIDA — SOLO JSON

Lado de zócalos DEBE ser uno de: "izquierdo", "derecho", "trasero", "frontal", "lateral"

```json
{
  "sectores": [
    {
      "id": "cocina",
      "tipo": "recta | recta_2_tramos | L | U | isla",
      "tramos": [
        {
          "id": "tramo_1",
          "descripcion": "Mesada cocina tramo 1",
          "largo_m": 1.55,
          "ancho_m": 0.60,
          "m2": 0.93,
          "zocalos": [
            { "lado": "frontal", "ml": 1.55, "alto_m": 0.07 }
          ],
          "frentin": [],
          "regrueso": [],
          "notas": []
        }
      ],
      "m2_placas": 0.93,
      "m2_zocalos": 0.11,
      "m2_total": 1.04,
      "ambiguedades": [],
      "confident": 0.95
    }
  ]
}
```

confident: 0.0 a 1.0 por sector. Ambiguedades → confident < 0.8.
"""

VALID_LADOS = {"izquierdo", "derecho", "trasero", "frontal", "lateral"}

# Reconciliation thresholds
DELTA_PERCENT_ALERTA = 0.05   # 5%
CONFIDENCE_THRESHOLD = 0.7
SONNET_CONFIDENCE_SKIP_OPUS = 0.9
OPUS_TIMEOUT_SECONDS = 15


# ═══════════════════════════════════════════════════════
# Vision API call
# ═══════════════════════════════════════════════════════

async def _call_vision(crop_bytes: bytes, model: str, timeout: float = OPUS_TIMEOUT_SECONDS) -> dict:
    """Call Claude Vision API with plan reader prompt. Returns parsed JSON."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=3000,
                system=PLAN_READER_SYSTEM_PROMPT,
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
                        {
                            "type": "text",
                            "text": "Extraé las medidas de este plano de marmolería. Devolvé SOLO JSON según el schema indicado.",
                        },
                    ],
                }],
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[dual-read] {model} timed out after {timeout}s")
        return {"error": f"Timeout after {timeout}s", "model": model}
    except Exception as e:
        logger.error(f"[dual-read] {model} API error: {e}")
        return {"error": str(e), "model": model}

    # Extract text from response
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Parse JSON — strip markdown fences if present
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        result = json.loads(text)
        result["_model"] = model
        result["_raw_length"] = len(text)
        return result
    except json.JSONDecodeError as e:
        # Try to find JSON object in response
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                result = json.loads(match.group())
                result["_model"] = model
                return result
            except json.JSONDecodeError:
                pass
        logger.error(f"[dual-read] {model} JSON parse failed: {e}\nRaw: {text[:500]}")
        return {"error": f"JSON parse failed: {e}", "model": model, "_raw": text[:500]}


# ═══════════════════════════════════════════════════════
# Reconciliation
# ═══════════════════════════════════════════════════════

def _compare_float(a: float, b: float) -> tuple[str, float]:
    """Compare two float values, return (status, reconciled_value)."""
    if a == b:
        return "CONFIRMADO", a
    if a == 0 and b == 0:
        return "CONFIRMADO", 0
    avg = (a + b) / 2
    max_val = max(abs(a), abs(b))
    if max_val == 0:
        return "CONFIRMADO", 0
    delta_pct = abs(a - b) / max_val
    if delta_pct < DELTA_PERCENT_ALERTA:
        return "ALERTA", round(avg, 4)
    return "CONFLICTO", None  # Operator must choose


def _compare_zocalos(a_list: list, b_list: list) -> list[dict]:
    """Compare zócalo arrays by matching 'lado' field (strict ==)."""
    result = []
    a_by_lado = {z.get("lado", ""): z for z in a_list}
    b_by_lado = {z.get("lado", ""): z for z in b_list}
    all_lados = set(a_by_lado.keys()) | set(b_by_lado.keys())

    for lado in sorted(all_lados):
        za = a_by_lado.get(lado)
        zb = b_by_lado.get(lado)
        if za and zb:
            status, ml = _compare_float(za.get("ml", 0), zb.get("ml", 0))
            result.append({
                "lado": lado,
                "opus_ml": za.get("ml", 0),
                "sonnet_ml": zb.get("ml", 0),
                "ml": ml if ml is not None else za.get("ml", 0),
                "alto_m": za.get("alto_m", 0.07),
                "status": status,
            })
        elif za:
            result.append({
                "lado": lado, "opus_ml": za.get("ml", 0), "sonnet_ml": None,
                "ml": za.get("ml", 0), "alto_m": za.get("alto_m", 0.07),
                "status": "SOLO_OPUS",
            })
        elif zb:
            result.append({
                "lado": lado, "opus_ml": None, "sonnet_ml": zb.get("ml", 0),
                "ml": zb.get("ml", 0), "alto_m": zb.get("alto_m", 0.07),
                "status": "SOLO_SONNET",
            })
    return result


def reconcile(opus: dict, sonnet: dict) -> dict:
    """Reconcile results from two models. Returns reconciled data with status per field."""
    opus_sectores = opus.get("sectores", [])
    sonnet_sectores = sonnet.get("sectores", [])

    # Match sectors by id
    opus_by_id = {s.get("id", f"s{i}"): s for i, s in enumerate(opus_sectores)}
    sonnet_by_id = {s.get("id", f"s{i}"): s for i, s in enumerate(sonnet_sectores)}
    all_ids = list(dict.fromkeys(list(opus_by_id.keys()) + list(sonnet_by_id.keys())))

    reconciled_sectores = []
    requires_review = False
    conflict_fields = []

    for sid in all_ids:
        os = opus_by_id.get(sid, {})
        ss = sonnet_by_id.get(sid, {})

        # Match tramos by id
        o_tramos = {t.get("id", f"t{i}"): t for i, t in enumerate(os.get("tramos", []))}
        s_tramos = {t.get("id", f"t{i}"): t for i, t in enumerate(ss.get("tramos", []))}
        all_tramo_ids = list(dict.fromkeys(list(o_tramos.keys()) + list(s_tramos.keys())))

        rec_tramos = []
        for tid in all_tramo_ids:
            ot = o_tramos.get(tid, {})
            st = s_tramos.get(tid, {})

            # Compare numeric fields
            fields = {}
            for field in ["largo_m", "ancho_m", "m2"]:
                ov = ot.get(field, 0)
                sv = st.get(field, 0)
                status, val = _compare_float(ov, sv)

                # Check confidence
                o_conf = os.get("confident", 1.0)
                s_conf = ss.get("confident", 1.0)
                if min(o_conf, s_conf) < CONFIDENCE_THRESHOLD:
                    status = "DUDOSO"

                if status in ("CONFLICTO", "DUDOSO"):
                    requires_review = True
                    conflict_fields.append(f"{sid}.{tid}.{field}")

                fields[field] = {
                    "opus": ov, "sonnet": sv,
                    "valor": val if val is not None else ov,
                    "status": status,
                }

            # Compare zócalos
            o_zocs = ot.get("zocalos", [])
            s_zocs = st.get("zocalos", [])
            rec_zocs = _compare_zocalos(o_zocs, s_zocs)
            for z in rec_zocs:
                if z["status"] in ("CONFLICTO", "DUDOSO"):
                    requires_review = True
                    conflict_fields.append(f"{sid}.{tid}.zocalo_{z['lado']}")

            rec_tramos.append({
                "id": tid,
                "descripcion": ot.get("descripcion", st.get("descripcion", "")),
                **fields,
                "zocalos": rec_zocs,
                "frentin": ot.get("frentin", st.get("frentin", [])),
                "regrueso": ot.get("regrueso", st.get("regrueso", [])),
            })

        # Sector-level m2
        o_m2 = os.get("m2_total", 0)
        s_m2 = ss.get("m2_total", 0)
        m2_status, m2_val = _compare_float(o_m2, s_m2)

        reconciled_sectores.append({
            "id": sid,
            "tipo": os.get("tipo", ss.get("tipo", "")),
            "tramos": rec_tramos,
            "m2_total": {"opus": o_m2, "sonnet": s_m2, "valor": m2_val or o_m2, "status": m2_status},
            "ambiguedades": list(set(os.get("ambiguedades", []) + ss.get("ambiguedades", []))),
        })

    return {
        "sectores": reconciled_sectores,
        "requires_human_review": requires_review,
        "conflict_fields": conflict_fields,
        "source": "DUAL",
    }


def _build_single_result(data: dict, source: str) -> dict:
    """Wrap a single-model result as a reconciled result (all CONFIRMADO)."""
    sectores = []
    for s in data.get("sectores", []):
        tramos = []
        for t in s.get("tramos", []):
            tramos.append({
                "id": t.get("id", ""),
                "descripcion": t.get("descripcion", ""),
                "largo_m": {"opus": None, "sonnet": None, source.lower(): t.get("largo_m", 0),
                            "valor": t.get("largo_m", 0), "status": source},
                "ancho_m": {"opus": None, "sonnet": None, source.lower(): t.get("ancho_m", 0),
                            "valor": t.get("ancho_m", 0), "status": source},
                "m2": {"opus": None, "sonnet": None, source.lower(): t.get("m2", 0),
                       "valor": t.get("m2", 0), "status": source},
                "zocalos": [
                    {**z, "status": source, "opus_ml": None, "sonnet_ml": None}
                    for z in t.get("zocalos", [])
                ],
                "frentin": t.get("frentin", []),
                "regrueso": t.get("regrueso", []),
            })
        sectores.append({
            "id": s.get("id", ""),
            "tipo": s.get("tipo", ""),
            "tramos": tramos,
            "m2_total": {"valor": s.get("m2_total", 0), "status": source},
            "ambiguedades": s.get("ambiguedades", []),
        })
    return {
        "sectores": sectores,
        "requires_human_review": False,
        "conflict_fields": [],
        "source": source,
    }


# ═══════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════

async def dual_read_crop(
    crop_bytes: bytes,
    crop_label: str = "cocina",
    planilla_m2: Optional[float] = None,
    dual_enabled: bool = True,
) -> dict:
    """Read a crop with Sonnet first, Opus on demand. Reconcile results.

    Flag semantics (dual_read_enabled in config.json):
      True  → Sonnet first, if confident < 0.9 → also Opus, then reconcile
      False → Sonnet ONLY, direct result, NO Opus call, NO reconciliation

    NOTE: This flag is INDEPENDENT of use_opus_for_plans (which controls the
    main agent loop model). dual_read_enabled controls only this dual vision
    reader module. Both can be true/false independently.
    """
    sonnet_model = settings.ANTHROPIC_MODEL  # claude-sonnet-4-5-20250514
    # Opus model from config (not hardcoded) — allows changing without code deploy
    from app.modules.agent.tools.catalog_tool import get_ai_config
    _ai = get_ai_config()
    opus_model = _ai.get("opus_model", "claude-opus-4-6")

    # Step 1: Always call Sonnet (fast, ~3-5s)
    logger.info(f"[dual-read] Calling Sonnet for '{crop_label}'...")
    sonnet_result = await _call_vision(crop_bytes, sonnet_model, timeout=30)

    if sonnet_result.get("error"):
        logger.error(f"[dual-read] Sonnet failed: {sonnet_result['error']}")
        if dual_enabled:
            # Fallback to Opus
            logger.info(f"[dual-read] Falling back to Opus...")
            opus_result = await _call_vision(crop_bytes, opus_model, timeout=OPUS_TIMEOUT_SECONDS)
            if opus_result.get("error"):
                return {"error": "Both models failed", "sonnet_error": sonnet_result["error"], "opus_error": opus_result["error"]}
            return _build_single_result(opus_result, "SOLO_OPUS")
        return {"error": f"Sonnet failed: {sonnet_result['error']}"}

    # If dual_read_enabled=false → return Sonnet directly, no reconciliation
    if not dual_enabled:
        logger.info(f"[dual-read] dual_read_enabled=false → returning Sonnet directly")
        result = _build_single_result(sonnet_result, "SOLO_SONNET")
        result["m2_warning"] = _check_m2(result, planilla_m2)
        return result

    # Step 2: Check Sonnet confidence
    min_confidence = min(
        (s.get("confident", 1.0) for s in sonnet_result.get("sectores", [{"confident": 0}])),
        default=0,
    )
    logger.info(f"[dual-read] Sonnet confidence: {min_confidence:.2f}")

    if min_confidence >= SONNET_CONFIDENCE_SKIP_OPUS:
        # Sonnet is confident → skip Opus, save cost
        logger.info(f"[dual-read] Sonnet confident ≥{SONNET_CONFIDENCE_SKIP_OPUS} → skipping Opus")
        result = _build_single_result(sonnet_result, "SOLO_SONNET")
        result["m2_warning"] = _check_m2(result, planilla_m2)
        return result

    # Step 3: Sonnet unsure → call Opus with timeout
    logger.info(f"[dual-read] Sonnet unsure ({min_confidence:.2f}) → calling Opus (timeout={OPUS_TIMEOUT_SECONDS}s)...")
    opus_result = await _call_vision(crop_bytes, opus_model, timeout=OPUS_TIMEOUT_SECONDS)

    if opus_result.get("error"):
        # Opus failed/timed out → use Sonnet alone
        logger.warning(f"[dual-read] Opus failed: {opus_result['error']} → using Sonnet only")
        result = _build_single_result(sonnet_result, "SOLO_SONNET")
        result["m2_warning"] = _check_m2(result, planilla_m2)
        return result

    # Step 4: Both succeeded → reconcile
    logger.info(f"[dual-read] Both models responded → reconciling...")
    reconciled = reconcile(opus_result, sonnet_result)
    reconciled["m2_warning"] = _check_m2(reconciled, planilla_m2)
    return reconciled


def _check_m2(result: dict, planilla_m2: Optional[float]) -> Optional[str]:
    """Check if calculated m2 matches planilla m2."""
    if planilla_m2 is None:
        return None
    total = sum(
        s.get("m2_total", {}).get("valor", 0) if isinstance(s.get("m2_total"), dict) else s.get("m2_total", 0)
        for s in result.get("sectores", [])
    )
    if total == 0:
        return None
    diff_pct = abs(total - planilla_m2) / planilla_m2
    if diff_pct > 0.10:
        return f"⚠️ M² calculado ({total:.2f}) no coincide con planilla ({planilla_m2:.2f}). Diferencia: {diff_pct*100:.0f}%"
    return None


# ═══════════════════════════════════════════════════════
# Context injection
# ═══════════════════════════════════════════════════════

def build_verified_context(confirmed_data: dict) -> str:
    """Build injection text from operator-confirmed measurements."""
    lines = [
        "[MEDIDAS VERIFICADAS POR DOBLE LECTURA + OPERADOR — FUENTE DE VERDAD]",
        "⛔ Estos valores son definitivos. NO leas la imagen. Usá estos valores exactos.",
        "",
    ]

    for sector in confirmed_data.get("sectores", []):
        sid = sector.get("id", "sector")
        lines.append(f"SECTOR: {sid.upper()}")
        for tramo in sector.get("tramos", []):
            tid = tramo.get("id", "")
            desc = tramo.get("descripcion", tid)
            largo = tramo.get("largo_m", {})
            ancho = tramo.get("ancho_m", {})
            m2 = tramo.get("m2", {})
            largo_v = largo.get("valor", 0) if isinstance(largo, dict) else largo
            ancho_v = ancho.get("valor", 0) if isinstance(ancho, dict) else ancho
            m2_v = m2.get("valor", 0) if isinstance(m2, dict) else m2
            lines.append(f"  {desc}: {largo_v}m × {ancho_v}m = {m2_v} m²")
            for z in tramo.get("zocalos", []):
                ml = z.get("ml", 0)
                alto = z.get("alto_m", 0.07)
                lado = z.get("lado", "?")
                lines.append(f"  Zócalo {lado}: {ml}ml × {alto}m")
        lines.append("")

    return "\n".join(lines)
