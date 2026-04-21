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
from app.core.company_config import get as _cfg


def _default_zocalo_alto() -> float:
    """PR #57 — leer alto zócalo default desde catalog/config.json en vez
    de hardcodear. Permite que el operador lo edite desde el panel de
    Configuración web sin redeploy."""
    return _cfg("measurements.default_zocalo_height", 0.07)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# System prompt — same for both models (comparison limpia)
# ═══════════════════════════════════════════════════════

# PR #26 — prompt cargado desde rules/plan-reader-v1.md para que los dos
# modelos (Opus + Sonnet) usen la misma fuente de verdad que el agente
# principal. Antes estaba hardcoded acá → cada cambio requería update en
# 2 lugares y el dual reader se quedaba con versiones viejas.
def _load_plan_reader_prompt() -> str:
    """Read the canonical plan-reader prompt from rules/plan-reader-v1.md."""
    import pathlib
    _here = pathlib.Path(__file__).resolve()
    # Go up from api/app/modules/quote_engine/ to api/, then rules/
    _rules_dir = _here.parent.parent.parent.parent / "rules"
    _path = _rules_dir / "plan-reader-v1.md"
    try:
        return _path.read_text(encoding="utf-8")
    except Exception as _e:
        logging.error(
            "[dual-read] Could not load plan-reader-v1.md (%s). "
            "Falling back to minimal prompt.", _e,
        )
        return (
            "Sos un lector experto de planos de marmolería. "
            "Identificá mesadas y zócalos desde las cotas dibujadas. "
            "Devolvé JSON con sectores/tramos/zocalos."
        )


PLAN_READER_SYSTEM_PROMPT = _load_plan_reader_prompt()


VALID_LADOS = {"izquierdo", "derecho", "trasero", "frontal", "lateral"}

# Reconciliation thresholds
DELTA_PERCENT_ALERTA = 0.05   # 5%
CONFIDENCE_THRESHOLD = 0.7
SONNET_CONFIDENCE_SKIP_OPUS = 0.9
OPUS_TIMEOUT_SECONDS = 60


# ═══════════════════════════════════════════════════════
# Vision API call
# ═══════════════════════════════════════════════════════

async def _call_vision(
    crop_bytes: bytes,
    model: str,
    timeout: float = OPUS_TIMEOUT_SECONDS,
    cotas_text: str | None = None,
    brief_text: str | None = None,
) -> dict:
    """Call Claude Vision API with plan reader prompt. Returns parsed JSON.

    If cotas_text is provided, it's injected BEFORE the extraction instruction
    so the model uses those pre-extracted cotas instead of reading numbers
    from the image. The model still sees the image for geometric interpretation.

    PR #68 — brief_text: texto que mandó el operador junto al plano (ej:
    "con zócalos", "granito negro boreal", "rosario", "natalia"). Se inyecta
    como contexto para que los modelos de visión puedan desambiguar
    decisiones (material, zócalos presentes, localidad, etc.) en vez de
    flaguear falso positivos como "confirmar con cliente".
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    user_text_blocks = []
    if brief_text and brief_text.strip():
        user_text_blocks.append({
            "type": "text",
            "text": (
                "CONTEXTO DEL OPERADOR (texto que acompañó al plano):\n"
                f"```\n{brief_text.strip()}\n```\n\n"
                "Usá esta información para desambiguar lectura:\n"
                "- Si menciona material (granito, silestone, etc.) → no flaguees "
                "\"material no indicado\".\n"
                "- Si dice \"con zócalos\" o \"lleva zócalos\" → considerá que sí los "
                "tiene aunque el render no los dibuje explícito. NO flaguees "
                "\"zócalos no visibles\" como razón para descartarlos.\n"
                "- Si menciona localidad, cliente, obra → incluilo en los campos "
                "`client_name` / `proyecto` / `localidad` del JSON si el schema los tiene.\n"
                "- Si dice \"bacha comprada\" / \"cliente provee pileta\" → `pileta = "
                "empotrada_cliente`, sin sku Johnson.\n"
                "- Aclaraciones del operador MANDAN sobre lo que se vea en la imagen."
            ),
        })
    if cotas_text:
        user_text_blocks.append({
            "type": "text",
            "text": (
                cotas_text
                + "\n\n"
                + "⚠️ REGLA CRÍTICA (sin excepciones): TODO valor numérico que "
                + "devuelvas en el JSON (largo_m, ancho_m, zócalos) DEBE coincidir "
                + "EXACTAMENTE con uno de los valores numéricos listados arriba.\n"
                + "- Si una medida del plano no aparece en esta lista, NO la uses. "
                + "Marcala con `status: \"DUDOSO\"` y dejá `valor: null`, en vez de "
                + "estimar visualmente.\n"
                + "- NO redondees, NO promedies, NO infieras desde el dibujo sin cota. "
                + "Mejor un `null` honesto que un número inventado.\n"
                + "- Si ves varias cotas candidatas para el mismo rol (ej. pared-a-pared "
                + "vs muro-a-muro), elegí la INTERNA (pared-a-pared) y anotá tu elección "
                + "en `ambiguedades`.\n"
                + "Tu tarea es ASIGNAR cada cota listada a su rol geométrico usando la "
                + "posición (x, y) — no generar números nuevos."
            ),
        })
    user_text_blocks.append({
        "type": "text",
        "text": "Extraé las medidas de este plano de marmolería. Devolvé SOLO JSON según el schema indicado.",
    })

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
                        *user_text_blocks,
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

# ═══════════════════════════════════════════════════════
# Ambigüedades — dedup, filtro de obsoletas, categorización
# ═══════════════════════════════════════════════════════
#
# Los modelos Opus y Sonnet a veces escriben el mismo warning con palabras
# distintas (ej. "altura de zócalo asumida 0.07m" vs "se asume 0.07 m por
# convención estándar (7 cm)"). Un `set()` no las dedupea porque las strings
# difieren. Además, a veces un modelo levanta una ambigüedad que el otro
# modelo resolvió, y después de reconciliar queda como warning "huérfano"
# que contradice el resultado final (ej. "solo 1 zócalo" cuando Opus
# encontró los otros dos).
#
# Solución: agrupar por "bucket" temático basado en keywords, filtrar las
# que contradicen el reconciliado, y categorizar como DEFAULT / INFO /
# REVISION para que la UI pueda darles jerarquía.

_AMBIG_BUCKETS: list[tuple[str, list[list[str]]]] = [
    # (bucket_id, list of keyword groups — all keywords in a group must match)
    ("altura_zocalo_default", [
        ["altura", "zócal", "asum"],
        ["altura", "zocal", "asum"],
        ["altura", "zócal", "default"],
        ["altura", "zocal", "default"],
        ["altura", "zócal", "convenci"],
        ["altura", "zocal", "convenci"],
        ["altura", "zócal", "7 cm"],
        ["altura", "zocal", "7 cm"],
        ["altura", "zócal", "7cm"],
        ["altura", "zocal", "7cm"],
    ]),
    ("pileta_sin_modelo", [
        ["pileta", "modelo"],
        ["pileta", "marca"],
    ]),
    ("forma_l_sin_indicacion", [
        ["forma", "l", "no"],
        ["unión", "tramos"],
        ["union", "tramos"],
        ["inglete"],
        ["solape"],
        ["tramos", "independientes"],
    ]),
    ("conteo_zocalos", [
        ["solo", "zócal", "identific"],
        ["solo", "zocal", "identific"],
        ["no muestra", "zócal"],
        ["no muestra", "zocal"],
    ]),
]


def _normalize_text(s: str) -> str:
    """Lowercase, collapse whitespace, strip accents lightly."""
    t = s.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _bucket_of(warning: str) -> str:
    """Return bucket id if matches any known group, else the normalized text itself."""
    t = _normalize_text(warning)
    for bucket_id, groups in _AMBIG_BUCKETS:
        for group in groups:
            if all(kw in t for kw in group):
                return bucket_id
    # Fallback: fingerprint from content words (ignore numbers + stopwords)
    stopwords = {
        "de","el","la","los","las","en","por","un","una","no","se","con",
        "al","del","para","que","y","o","a","es","esta","está","pese","ni",
        "su","sus","lo","le","ya","ha","se","hay","sin","solo","explícito",
    }
    clean = re.sub(r"\d+[.,]?\d*\s*(m|cm|ml|mm)?", " ", t)
    clean = re.sub(r"[^\w\sáéíóúñ]", " ", clean)
    words = sorted({w for w in clean.split() if len(w) > 3 and w not in stopwords})
    return "fp:" + " ".join(words)


def _is_obsolete(warning: str, rec_tramos: list[dict]) -> bool:
    """True if the warning contradicts the reconciled sector state."""
    t = _normalize_text(warning)

    # "solo se identifica N zócalo(s)" vs actual reconciled count
    m = re.search(r"solo se identific\w*\s*(\d+)\s*z[oó]cal", t)
    if m:
        reported = int(m.group(1))
        actual = sum(
            1
            for tr in rec_tramos
            for z in tr.get("zocalos", [])
            if (z.get("ml") or 0) > 0
        )
        if actual > reported:
            return True

    # "tramo X no muestra zócalos..." but that tramo now has zócalos
    m = re.search(r"tramo[_\s]*([a-z0-9_]+).*(no muestra|sin z[oó]cal)", t)
    if m:
        key = m.group(1).strip("_ ")
        for tr in rec_tramos:
            tid = (tr.get("id") or "").lower()
            desc = (tr.get("descripcion") or "").lower()
            if key and (key in tid or key in desc):
                has = any((z.get("ml") or 0) > 0 for z in tr.get("zocalos", []))
                if has:
                    return True

    # "calculado X vs declarado Y [diff N%]" (o al revés: declarado Y ... calculado X)
    # → el modelo comparó su estimado (típicamente mesadas sola) con la planilla.
    # Si el total reconciliado de la UI (mesadas + zócalos) ya coincide con el
    # declarado, este warning es obsoleto: describe un estado intermedio que el
    # reconciliador resolvió al agregar zócalos que un modelo vio y el otro no.
    _reported_decl = None
    _m1 = re.search(
        r"calculad\w*\s*(\d+(?:[.,]\d+)?).{0,30}?declarad\w*[^\d]{0,10}(\d+(?:[.,]\d+)?)",
        t,
    )
    _m2 = re.search(
        r"declarad\w*[^\d]{0,10}(\d+(?:[.,]\d+)?).{0,30}?calculad\w*\s*(\d+(?:[.,]\d+)?)",
        t,
    )
    if _m1:
        try:
            _reported_decl = float(_m1.group(2).replace(",", "."))
        except ValueError:
            pass
    elif _m2:
        try:
            _reported_decl = float(_m2.group(1).replace(",", "."))
        except ValueError:
            pass

    if _reported_decl is not None and _reported_decl > 0:
        try:
            actual = 0.0
            for tr in rec_tramos:
                m2 = tr.get("m2", {})
                actual += m2.get("valor", 0) if isinstance(m2, dict) else (m2 or 0)
                for z in tr.get("zocalos", []):
                    ml = z.get("ml", 0) or 0
                    alto = z.get("alto_m", 0) or 0
                    if ml > 0:
                        actual += ml * alto
            if abs(actual - _reported_decl) / _reported_decl < 0.015:
                return True
        except ZeroDivisionError:
            pass

    return False


def _categorize(warning: str) -> str:
    """Classify warning as DEFAULT (info-only), INFO (falta dato externo), REVISION (necesita vista al plano)."""
    t = _normalize_text(warning)
    if any(k in t for k in ("asum", "default", "convenci")) and ("altura" in t or "7 cm" in t or "7cm" in t):
        return "DEFAULT"
    if "pileta" in t and any(k in t for k in ("modelo", "marca", "no indicad")):
        return "INFO"
    if any(
        k in t
        for k in (
            "solo se identific",
            "no muestra",
            "no hay texto",
            "no hay indicación",
            "no hay indicacion",
            "pese a",
            "dudos",
            "conflict",
            "tramos independientes",
            "inglete",
            "solape",
        )
    ):
        return "REVISION"
    return "REVISION"


_CATEGORY_ORDER = {"REVISION": 0, "INFO": 1, "DEFAULT": 2}


def _clean_ambiguedades(raw: list[str], rec_tramos: list[dict]) -> list[dict]:
    """Dedup (by bucket), filter obsoletas, categorize, sort by priority."""
    seen: set[str] = set()
    out: list[dict] = []
    for w in raw:
        if not isinstance(w, str) or not w.strip():
            continue
        if _is_obsolete(w, rec_tramos):
            continue
        key = _bucket_of(w)
        if key in seen:
            continue
        seen.add(key)
        out.append({"tipo": _categorize(w), "texto": w.strip()})
    out.sort(key=lambda d: _CATEGORY_ORDER.get(d["tipo"], 99))
    return out


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
        _alto_default = _default_zocalo_alto()
        if za and zb:
            status, ml = _compare_float(za.get("ml", 0), zb.get("ml", 0))
            result.append({
                "lado": lado,
                "opus_ml": za.get("ml", 0),
                "sonnet_ml": zb.get("ml", 0),
                "ml": ml if ml is not None else za.get("ml", 0),
                "alto_m": za.get("alto_m", _alto_default),
                "status": status,
            })
        elif za:
            result.append({
                "lado": lado, "opus_ml": za.get("ml", 0), "sonnet_ml": None,
                "ml": za.get("ml", 0), "alto_m": za.get("alto_m", _alto_default),
                "status": "SOLO_OPUS",
            })
        elif zb:
            result.append({
                "lado": lado, "opus_ml": None, "sonnet_ml": zb.get("ml", 0),
                "ml": zb.get("ml", 0), "alto_m": zb.get("alto_m", _alto_default),
                "status": "SOLO_SONNET",
            })
    return result


def reconcile(opus: dict, sonnet: dict) -> dict:
    """Reconcile results from two models. Returns reconciled data with status per field."""
    opus_sectores = opus.get("sectores", [])
    sonnet_sectores = sonnet.get("sectores", [])

    # PR #69 — sector dedup: si Opus devuelve 1 sector y Sonnet devuelve 1
    # sector pero con IDs distintos (caso común: Opus="cocina", Sonnet=
    # "lavadero" para la misma mesada en L), son EL MISMO sector con
    # labeling diferente. Mergear al id de Opus (usualmente más conservador)
    # para que la reconciliación de tramos se haga entre los dos modelos
    # en vez de mostrarlos como sectores duplicados separados.
    if len(opus_sectores) == 1 and len(sonnet_sectores) == 1:
        o_id = opus_sectores[0].get("id", "sector")
        s_id = sonnet_sectores[0].get("id", "sector")
        if o_id != s_id:
            logger.info(
                f"[dual-read] sector dedup: Opus id='{o_id}' vs Sonnet id='{s_id}' "
                f"→ unificando ambos como '{o_id}'."
            )
            sonnet_sectores = [dict(sonnet_sectores[0], id=o_id)]

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

        # PR #69 — tramo dedup análogo al de sectores: si ambos modelos
        # reportan la misma cantidad de tramos pero con IDs distintos
        # (caso común: Opus="tramo_largo"+"retorno", Sonnet="principal"+
        # "retorno"), tratarlos como los mismos tramos por posición.
        _opus_tramos_raw = os.get("tramos", []) or []
        _sonnet_tramos_raw = ss.get("tramos", []) or []
        if (
            len(_opus_tramos_raw) > 0
            and len(_opus_tramos_raw) == len(_sonnet_tramos_raw)
        ):
            _sonnet_tramos_norm = []
            for _idx, _st_raw in enumerate(_sonnet_tramos_raw):
                _opus_id = _opus_tramos_raw[_idx].get("id") if _idx < len(_opus_tramos_raw) else None
                _sonnet_id = _st_raw.get("id")
                if _opus_id and _sonnet_id and _opus_id != _sonnet_id:
                    logger.info(
                        f"[dual-read] tramo dedup [{sid}]: Opus id='{_opus_id}' "
                        f"vs Sonnet id='{_sonnet_id}' → unificando como '{_opus_id}'."
                    )
                    _sonnet_tramos_norm.append(dict(_st_raw, id=_opus_id))
                else:
                    _sonnet_tramos_norm.append(_st_raw)
            _sonnet_tramos_raw = _sonnet_tramos_norm

        # Match tramos by id
        o_tramos = {t.get("id", f"t{i}"): t for i, t in enumerate(_opus_tramos_raw)}
        s_tramos = {t.get("id", f"t{i}"): t for i, t in enumerate(_sonnet_tramos_raw)}
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

            # PR #28 — convención: largo ≥ ancho. Si Opus y Sonnet están
            # "swapped" (uno dice 0.6×1.55 y el otro 1.55×0.6), preferir la
            # variante con largo ≥ ancho. Evita que la UI muestre el
            # retorno al revés cuando los modelos invierten ejes.
            ov_l, sv_l = ot.get("largo_m", 0) or 0, st.get("largo_m", 0) or 0
            ov_a, sv_a = ot.get("ancho_m", 0) or 0, st.get("ancho_m", 0) or 0
            _swapped = (
                abs(ov_l - sv_a) < 0.02 and abs(ov_a - sv_l) < 0.02
                and ov_l > 0 and sv_l > 0
                and (ov_l != sv_l)
            )
            if _swapped:
                # Prefer the variant with largo >= ancho
                opus_ok = ov_l >= ov_a
                sonnet_ok = sv_l >= sv_a
                _pick_largo, _pick_ancho = None, None
                if opus_ok and not sonnet_ok:
                    _pick_largo, _pick_ancho = ov_l, ov_a
                elif sonnet_ok and not opus_ok:
                    _pick_largo, _pick_ancho = sv_l, sv_a
                elif opus_ok and sonnet_ok:
                    _pick_largo, _pick_ancho = max(ov_l, sv_l), min(ov_a, sv_a)
                if _pick_largo is not None:
                    logger.info(
                        f"[dual-read] tramo {tid}: dims swapped (opus={ov_l}×{ov_a} "
                        f"vs sonnet={sv_l}×{sv_a}) → normalizando a "
                        f"{_pick_largo}×{_pick_ancho} (largo≥ancho)"
                    )
                    fields["largo_m"]["valor"] = _pick_largo
                    fields["largo_m"]["status"] = "OK"
                    fields["ancho_m"]["valor"] = _pick_ancho
                    fields["ancho_m"]["status"] = "OK"
                    # Clear the conflict flag we added earlier for this tramo
                    _marker_l = f"{sid}.{tid}.largo_m"
                    _marker_a = f"{sid}.{tid}.ancho_m"
                    conflict_fields = [
                        c for c in conflict_fields if c not in (_marker_l, _marker_a)
                    ]

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
            "ambiguedades": _clean_ambiguedades(
                list(os.get("ambiguedades", [])) + list(ss.get("ambiguedades", [])),
                rec_tramos,
            ),
        })

    # PR #71 — propagar view_type del modelo con mayor confianza (o del
    # que lo reportó). Si ambos coinciden → perfecto. Si difieren →
    # mergeamos hacia la clasificación más restrictiva (render_3d gana
    # sobre planta porque requiere reglas más conservadoras).
    _o_vt = opus.get("view_type", "unknown")
    _s_vt = sonnet.get("view_type", "unknown")
    if _o_vt == _s_vt:
        _merged_vt = _o_vt
        _merged_reason = opus.get("view_type_reason") or sonnet.get("view_type_reason") or ""
    elif _o_vt in ("unknown", "") and _s_vt not in ("unknown", ""):
        _merged_vt = _s_vt
        _merged_reason = sonnet.get("view_type_reason", "")
    elif _s_vt in ("unknown", "") and _o_vt not in ("unknown", ""):
        _merged_vt = _o_vt
        _merged_reason = opus.get("view_type_reason", "")
    else:
        # Conflict — prefer render_3d / mixed / elevation over planta
        _priority = {"render_3d": 3, "mixed": 2, "elevation": 2, "planta": 1, "unknown": 0}
        _merged_vt = _o_vt if _priority.get(_o_vt, 0) >= _priority.get(_s_vt, 0) else _s_vt
        _merged_reason = f"Opus: {_o_vt}; Sonnet: {_s_vt}. Se eligió {_merged_vt} por prioridad."
        logger.info(f"[dual-read] view_type conflict: Opus={_o_vt} vs Sonnet={_s_vt} → merged={_merged_vt}")

    return {
        "sectores": reconciled_sectores,
        "requires_human_review": requires_review,
        "conflict_fields": conflict_fields,
        "source": "DUAL",
        "view_type": _merged_vt,
        "view_type_reason": _merged_reason,
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
            "ambiguedades": _clean_ambiguedades(list(s.get("ambiguedades", [])), tramos),
        })
    return {
        "sectores": sectores,
        "requires_human_review": False,
        "conflict_fields": [],
        "source": source,
        # PR #71 — clasificación de tipo de vista propagada del modelo.
        "view_type": data.get("view_type", "unknown"),
        "view_type_reason": data.get("view_type_reason", ""),
    }


# ═══════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════

async def dual_read_crop(
    crop_bytes: bytes,
    crop_label: str = "cocina",
    planilla_m2: Optional[float] = None,
    dual_enabled: bool = True,
    cotas_text: Optional[str] = None,
    brief_text: Optional[str] = None,
) -> dict:
    """Read a crop with Sonnet first, Opus on demand. Reconcile results.

    Flag semantics (dual_read_enabled in config.json):
      True  → Sonnet first, if confident < 0.9 → also Opus, then reconcile
      False → Sonnet ONLY, direct result, NO Opus call, NO reconciliation

    NOTE: This flag is INDEPENDENT of use_opus_for_plans (which controls the
    main agent loop model). dual_read_enabled controls only this dual vision
    reader module. Both can be true/false independently.

    cotas_text: optional pre-extracted cotas (from cotas_extractor) to inject
    into the vision prompt. When provided, the model uses those exact numbers
    and only does geometric interpretation.
    """
    sonnet_model = settings.ANTHROPIC_MODEL  # claude-sonnet-4-5-20250514
    # Opus model from config (not hardcoded) — allows changing without code deploy
    from app.modules.agent.tools.catalog_tool import get_ai_config
    _ai = get_ai_config()
    opus_model = _ai.get("opus_model", "claude-opus-4-6")

    # Step 1: Always call Sonnet (fast, ~3-5s)
    if cotas_text:
        logger.info(f"[dual-read] Calling Sonnet for '{crop_label}' with {len(cotas_text)} chars of pre-extracted cotas...")
    else:
        logger.info(f"[dual-read] Calling Sonnet for '{crop_label}' (no cotas_text)...")
    sonnet_result = await _call_vision(crop_bytes, sonnet_model, timeout=30, cotas_text=cotas_text, brief_text=brief_text)

    if sonnet_result.get("error"):
        logger.error(f"[dual-read] Sonnet failed: {sonnet_result['error']}")
        if dual_enabled:
            # Fallback to Opus
            logger.info(f"[dual-read] Falling back to Opus...")
            opus_result = await _call_vision(crop_bytes, opus_model, timeout=OPUS_TIMEOUT_SECONDS, cotas_text=cotas_text, brief_text=brief_text)
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

    # Check M2 mismatch with planilla BEFORE deciding to skip Opus
    _sonnet_preview = _build_single_result(sonnet_result, "SOLO_SONNET")
    _m2_mismatch = _check_m2(_sonnet_preview, planilla_m2)

    if min_confidence >= SONNET_CONFIDENCE_SKIP_OPUS and not _m2_mismatch:
        # Sonnet is confident AND m2 matches planilla → skip Opus, save cost
        logger.info(f"[dual-read] Sonnet confident ≥{SONNET_CONFIDENCE_SKIP_OPUS} + m2 OK → skipping Opus")
        _sonnet_preview["m2_warning"] = None
        _sonnet_preview["_sonnet_raw"] = sonnet_result  # preserve for operator retry
        return _sonnet_preview

    if _m2_mismatch:
        logger.warning(f"[dual-read] M2 mismatch with planilla → forcing Opus call: {_m2_mismatch}")

    # Step 3: Sonnet unsure → call Opus with timeout
    logger.info(f"[dual-read] Sonnet unsure ({min_confidence:.2f}) → calling Opus (timeout={OPUS_TIMEOUT_SECONDS}s)...")
    opus_result = await _call_vision(crop_bytes, opus_model, timeout=OPUS_TIMEOUT_SECONDS, cotas_text=cotas_text, brief_text=brief_text)

    if opus_result.get("error"):
        # Opus failed/timed out → use Sonnet alone
        logger.warning(f"[dual-read] Opus failed: {opus_result['error']} → using Sonnet only")
        result = _build_single_result(sonnet_result, "SOLO_SONNET")
        result["m2_warning"] = _check_m2(result, planilla_m2)
        result["_sonnet_raw"] = sonnet_result
        return result

    # Step 4: Both succeeded → reconcile
    logger.info(f"[dual-read] Both models responded → reconciling...")
    reconciled = reconcile(opus_result, sonnet_result)
    reconciled["m2_warning"] = _check_m2(reconciled, planilla_m2)
    reconciled["_sonnet_raw"] = sonnet_result
    return reconciled


def _check_m2(result: dict, planilla_m2: Optional[float]) -> Optional[str]:
    """Check if calculated m2 (mesadas + zócalos) matches planilla m2.

    IMPORTANT: el total se calcula sumando m2 de cada tramo + área de los
    zócalos (ml × alto_m), igual que lo que muestra la UI. Antes usaba
    sector.m2_total que reportan los modelos (típicamente solo mesadas),
    lo que hacía que el warning no coincidiera con lo que el operador
    ve en la card y escondía casos de piezas faltantes.

    Threshold: 2%. Una diff de 2% suele indicar un zócalo no detectado
    (ej: 0.05 m² = ~0.75 ml × 0.07 m). Con threshold más alto se perdía
    esa señal.
    """
    if planilla_m2 is None or planilla_m2 <= 0:
        return None

    total = 0.0
    for s in result.get("sectores", []):
        for t in s.get("tramos", []):
            m2 = t.get("m2", {})
            total += (m2.get("valor", 0) if isinstance(m2, dict) else (m2 or 0))
            for z in t.get("zocalos", []):
                ml = z.get("ml", 0) or 0
                alto = z.get("alto_m", 0) or 0
                if ml > 0:
                    total += ml * alto

    if total == 0:
        return None
    diff_pct = abs(total - planilla_m2) / planilla_m2
    if diff_pct >= 0.015:
        falta = planilla_m2 - total
        sign = "faltan" if falta > 0 else "sobran"
        return (
            f"M² detectado ({total:.2f}) no coincide con planilla ({planilla_m2:.2f}) · "
            f"{sign} {abs(falta):.2f} m² — revisá si falta un zócalo o pieza en el plano."
        )
    return None


# ═══════════════════════════════════════════════════════
# Context injection
# ═══════════════════════════════════════════════════════

def build_verified_context(
    confirmed_data: dict,
    commercial_attrs: dict | None = None,
    derived_pieces: list[dict] | None = None,
) -> str:
    """Build injection text from operator-confirmed measurements + commercial
    attributes with authority/precedence annotations.

    PR #80: el despiece confirmado es INMUTABLE desde el punto de vista
    de Valentina.

    PR #374: atributos comerciales (anafe_count, pileta_simple_doble, etc.)
    también se inyectan con su source y wording escalonado. Esto impide
    que el LLM re-lea la imagen post-confirmación y sobreafirme hechos
    (ej: "2 anafes confirmados" cuando el dual_read detectó 1). Si vos
    eres el LLM leyendo esto: **usá estos valores. NO re-contés desde
    la imagen.** El wording que uses en el resumen debe respetar el
    source: "confirmado" solo si source=operator_answer.

    `commercial_attrs` shape esperado:
        {
          "anafe_count": {"value": int, "source": str},
          "pileta_simple_doble": {"value": str, "source": str},
          "isla_presence": {"value": bool, "source": str},
          "operator_answers": [{"id": str, "value": str, "label": str}],
          "divergences": [{"field": str, "brief_value": ..., "dual_read_value": ...}]
        }
    Todos los campos son opcionales — solo se emite lo que venga.

    Precedencia (autoridad) canónica:
        operator_answer > brief > dual_read > default
    """
    lines = [
        "[MEDIDAS VERIFICADAS POR DOBLE LECTURA + OPERADOR — FUENTE DE VERDAD]",
        "⛔ Estos valores son definitivos. NO leas la imagen. Usá estos valores exactos.",
        "⛔ NO preguntar al operador sobre el despiece (ya confirmado). Si detecta",
        "   un error y te lo menciona, el sistema automáticamente reabre Paso 1.",
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
                ml = z.get("ml", 0) or 0
                alto = z.get("alto_m", _default_zocalo_alto())
                lado = z.get("lado", "?")
                if ml > 0:
                    lines.append(f"  Zócalo {lado}: {ml}ml × {alto}m")
                # ml=0 → ignorado (operador lo descartó intencionalmente)
        lines.append("")

    # ── Atributos comerciales con precedencia explícita ──────────────
    if commercial_attrs:
        lines.extend(_format_commercial_attrs_block(commercial_attrs))

    # ── Piezas derivadas determinísticamente (PR #377) ───────────────
    # Separadas de los atributos — el LLM copia literal estas piezas en
    # el Paso 1. Backend arma las dimensiones; el LLM no las calcula.
    if derived_pieces:
        lines.extend(_format_derived_pieces_block(derived_pieces))

    return "\n".join(lines)


def _format_derived_pieces_block(pieces: list[dict]) -> list[str]:
    """Bloque imperativo con piezas ya calculadas desde respuestas del
    operador. El LLM debe copiarlas literal en el Paso 1.

    PR #377 — resuelve bug Bernardi 22/04/2026 donde el LLM calculaba
    mal patas laterales de isla (emitía 0.90×0.90 en vez de 0.60×0.90)
    porque el prompt le pasaba los atributos del operador como etiquetas
    planas sin instrucción de combinar dimensiones.

    Ahora el backend calcula las piezas (Pata lateral = prof×alto,
    Pata frontal = largo×alto) y se las pasa ya listas al LLM.
    """
    lines: list[str] = [
        "[PIEZAS DERIVADAS DE RESPUESTAS DEL OPERADOR — DETERMINÍSTICAS]",
        "⛔ Estas piezas están CALCULADAS por el backend desde los datos",
        "   confirmados por el operador. Copialas LITERAL en el Paso 1.",
        "⛔ NO recalcular dimensiones. NO cambiar el orden. NO omitir.",
        "⛔ Si pensás que hay un error, volvé al operador — no las editues.",
        "",
    ]
    for p in pieces:
        desc = p.get("description", "?")
        largo = p.get("largo")
        prof = p.get("prof")
        m2 = p.get("m2")
        lines.append(
            f"  {desc}: {largo} × {prof} = {m2} m²"
        )
    lines.append("")
    return lines


# Wording según source — determinístico, no dejarlo al LLM.
# Precedencia: operator_answer > brief > dual_read > default.
_SOURCE_WORDING = {
    "operator_answer": "confirmado por operador",
    "operator": "confirmado por operador",  # alias
    "brief": "del brief",
    "dual_read": "detectado en plano",
    "default": "asumido (revisar)",
}


def _source_wording(source: str | None) -> str:
    """Mapea un source a un fragmento de texto con certeza apropiada.

    Regla central del PR: "confirmado" solo cuando source=operator_answer.
    Si el LLM en el resumen quiere decir "X confirmado", tiene que venir
    de acá. Para otros sources el wording degrada a "del brief" /
    "detectado en plano" / "asumido (revisar)".
    """
    if not source:
        return "asumido (revisar)"
    return _SOURCE_WORDING.get(source, "asumido (revisar)")


def _format_commercial_attrs_block(attrs: dict) -> list[str]:
    """Construye las líneas del bloque "ATRIBUTOS COMERCIALES" del
    verified_context. Cada campo lleva su source explícito. El LLM debe
    respetar esos sources al generar el resumen — no usar wording de
    certeza ("confirmado") salvo cuando source=operator_answer.
    """
    lines: list[str] = [
        "[ATRIBUTOS COMERCIALES — FUENTE DE VERDAD POR CAMPO]",
        "⛔ USÁ SOLO ESTOS VALORES. NO re-cuentes desde la imagen.",
        "⛔ Wording del resumen: 'confirmado' SOLO si source=operator_answer.",
        "   brief → 'del brief'. dual_read → 'detectado en plano'.",
        "   default → 'asumido (revisar)'. Si no está listado → 'pendiente'.",
        "",
    ]
    had_any = False

    def _emit(field: str, value, source: str | None) -> None:
        nonlocal had_any
        wording = _source_wording(source)
        lines.append(f"  {field}: {value}  [source={source or 'default'} — {wording}]")
        had_any = True

    anafe = attrs.get("anafe_count")
    if anafe and anafe.get("value") is not None:
        _emit("anafe_count", anafe["value"], anafe.get("source"))

    pileta = attrs.get("pileta_simple_doble")
    if pileta and pileta.get("value") is not None:
        _emit("pileta_simple_doble", pileta["value"], pileta.get("source"))

    isla = attrs.get("isla_presence")
    if isla and isla.get("value") is not None:
        _emit("isla_presence", "sí" if isla["value"] else "no", isla.get("source"))

    # Respuestas del operador a pending_questions (profundidad isla,
    # patas, alto patas, alzada, etc). Son autoridad máxima: el operador
    # las respondió explícitamente.
    op_answers = attrs.get("operator_answers") or []
    if op_answers:
        lines.append("")
        lines.append("  Respuestas del operador (source=operator_answer — CONFIRMADAS):")
        for a in op_answers:
            qid = a.get("id", "?")
            val = a.get("label") or a.get("value") or "?"
            lines.append(f"    - {qid}: {val}")
        had_any = True

    # Divergencias explícitas — para que el LLM NO las esconda.
    divs = attrs.get("divergences") or []
    if divs:
        lines.append("")
        lines.append("  ⚠ DIVERGENCIAS entre fuentes (flag 'revisar' en el resumen):")
        for d in divs:
            field = d.get("field", "?")
            bv = d.get("brief_value")
            dv = d.get("dual_read_value")
            lines.append(f"    - {field}: brief={bv} vs plano={dv}")
        had_any = True

    lines.append("")
    if not had_any:
        # No hubo ningún atributo estructurado — bloque vacío pero aún así
        # emitido para que el LLM vea que "no hay nada confirmado" y
        # evite inventar.
        lines.append("  (ningún atributo comercial con valor estructurado — pedí al operador)")
        lines.append("")
    return lines


def _parse_float_answer(a: dict | None) -> float | None:
    """Convierte una operator_answer del tipo radio-with-detail a float.

    La UI guarda los values como strings ("0.60", "0.90"). Cuando el
    operador elige "custom" puede haber un detail con el número en texto.
    Devuelve None si no parsea — señal de "dato faltante" río abajo.
    """
    if not a:
        return None
    for key in ("value", "detail"):
        raw = a.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (int, float)):
                f = float(raw)
                if f > 0:
                    return f
                continue
            s = str(raw).strip().replace(",", ".")
            # remueve sufijo "m" si está
            s = re.sub(r"m\s*$", "", s, flags=re.IGNORECASE).strip()
            f = float(s)
            if f > 0:
                return f
        except (TypeError, ValueError):
            continue
    return None


# Mapeo explícito de `isla_patas.value` → lista de lados activos. Centralizado
# para que si el schema de la pregunta cambia (ver pending_questions.py), el
# helper siga alineado. Si el value no está acá → no se emite nada (fallback
# seguro, no inventar).
_ISLA_PATAS_SIDES = {
    "frontal_y_ambos_laterales": ["frontal", "lateral_izq", "lateral_der"],
    # alias histórico más corto que apareció en algunas cards
    "frontal_y_laterales": ["frontal", "lateral_izq", "lateral_der"],
    "solo_frontal": ["frontal"],
    "solo_laterales": ["lateral_izq", "lateral_der"],
    "no": [],
    # "custom" → sin mapping determinístico; el LLM debe preguntar al
    # operador cuáles lados. NO emitir piezas automáticas.
}


def build_derived_isla_pieces(
    operator_answers: list | None,
    verified_measurements: dict | None,
) -> tuple[list[dict], list[str]]:
    """Expande las respuestas confirmadas del operador sobre patas de isla
    a piezas físicas ya calculadas. Scope SOLO patas de isla (frontal /
    laterales) — no extrapola a frentines, zócalos ni otros derivados.

    Regla de dimensiones (alineada con quote-033 y la regla física):
      - Pata frontal  = `largo_isla × alto_patas`
      - Pata lateral  = `profundidad_isla × alto_patas`

    Datos base requeridos (TODOS). Si falta alguno → devolvemos
    lista vacía + warning. NO inventar dimensiones.
      - operator_answer `isla_patas` con value reconocido (distinto de
        "custom" y "no"-con-patas).
      - operator_answer `isla_patas_alto` con valor numérico parseable.
      - operator_answer `isla_profundidad` con valor numérico parseable.
      - `verified_measurements` con un sector tipo "isla" y largo > 0.

    Returns:
        (pieces, warnings)
        pieces: list[{description, largo, prof, m2, source}] determinísticas
        warnings: list de strings explicando por qué no se emitió (si aplica)
    """
    warnings: list[str] = []
    if not operator_answers:
        return [], []

    by_id: dict[str, dict] = {}
    for a in operator_answers:
        fid = a.get("id") if isinstance(a, dict) else None
        if fid:
            by_id[fid] = a

    patas_ans = by_id.get("isla_patas")
    if not patas_ans:
        # No se preguntó / no se respondió. No es error — simplemente no
        # hay derivadas que emitir.
        return [], []

    patas_value = patas_ans.get("value")
    sides = _ISLA_PATAS_SIDES.get(patas_value)
    if sides is None:
        # value="custom" u otro no mapeable. El LLM debe preguntar.
        warnings.append(
            f"isla_patas={patas_value!r} no se puede expandir automáticamente "
            f"(ej: 'custom'). No se emiten piezas derivadas."
        )
        return [], warnings
    if not sides:
        # "no" → no hay patas. Nada que emitir, sin warning.
        return [], []

    # Datos base — todos obligatorios para emitir piezas.
    alto = _parse_float_answer(by_id.get("isla_patas_alto"))
    prof = _parse_float_answer(by_id.get("isla_profundidad"))

    # largo_isla viene de las medidas verificadas (sector tipo="isla").
    largo_isla: float | None = None
    for sector in (verified_measurements or {}).get("sectores", []) or []:
        if (sector.get("tipo") or "").lower() != "isla":
            continue
        for tramo in sector.get("tramos", []) or []:
            largo_field = tramo.get("largo_m")
            if isinstance(largo_field, dict):
                v = largo_field.get("valor")
            else:
                v = largo_field
            try:
                if v is not None and float(v) > 0:
                    largo_isla = float(v)
                    break
            except (TypeError, ValueError):
                continue
        if largo_isla:
            break

    missing: list[str] = []
    if alto is None:
        missing.append("isla_patas_alto")
    if prof is None and any(s.startswith("lateral") for s in sides):
        missing.append("isla_profundidad")
    if largo_isla is None and "frontal" in sides:
        missing.append("largo_isla (de medidas verificadas)")
    if missing:
        warnings.append(
            f"No se emiten piezas derivadas de patas isla — faltan datos "
            f"base: {', '.join(missing)}. El LLM debe preguntar al operador "
            f"o resolver antes de listar patas."
        )
        return [], warnings

    def _mk_piece(desc: str, largo_v: float, prof_v: float) -> dict:
        return {
            "description": desc,
            "largo": round(float(largo_v), 2),
            "prof": round(float(prof_v), 2),
            "m2": round(float(largo_v) * float(prof_v), 2),
            "source": "derived_from_operator_answers",
        }

    pieces: list[dict] = []
    # Orden: frontal primero, luego laterales (izq, der). Match con cómo
    # lo escribe el LLM en ejemplos válidos (quote-033).
    if "frontal" in sides:
        pieces.append(_mk_piece(
            "Pata frontal isla", largo_isla, alto,
        ))
    if "lateral_izq" in sides:
        pieces.append(_mk_piece(
            "Pata lateral isla izq", prof, alto,
        ))
    if "lateral_der" in sides:
        pieces.append(_mk_piece(
            "Pata lateral isla der", prof, alto,
        ))

    return pieces, warnings


def build_commercial_attrs(
    analysis: dict | None,
    dual_result: dict | None,
    operator_answers: list | None = None,
) -> dict:
    """Orquesta la reconciliación de atributos comerciales para el
    verified_context. Usa la capa pura de reconcile_* de context_analyzer
    (no duplica lógica).

    Precedencia aplicada:
    - Si operator_answers incluye un answer para anafe_count / pileta_*,
      ese gana (source=operator_answer).
    - Sino, reconcile_* decide entre brief y dual_read.

    Devuelve dict compatible con `build_verified_context(commercial_attrs=)`.
    """
    # Lazy import para evitar dependencia circular dual_reader ↔ context_analyzer.
    from app.modules.quote_engine.context_analyzer import (
        reconcile_anafe_count,
        reconcile_pileta_simple_doble,
        _scan_features,
    )

    analysis = analysis or {}
    dual_result = dual_result or {}
    feats = _scan_features(dual_result)

    # Operator answers → índice por field id (los ids coinciden con el
    # campo canónico: "anafe_count", "pileta_simple_doble", etc.)
    op_by_field: dict[str, dict] = {}
    for a in operator_answers or []:
        fid = a.get("id")
        if fid:
            op_by_field[fid] = a

    out: dict = {}

    # anafe_count
    if "anafe_count" in op_by_field:
        a = op_by_field["anafe_count"]
        try:
            val = int(a.get("value"))
            out["anafe_count"] = {"value": val, "source": "operator_answer"}
        except (TypeError, ValueError):
            pass
    else:
        rec = reconcile_anafe_count(analysis, feats)
        if rec["final"] is not None:
            out["anafe_count"] = {"value": rec["final"], "source": rec["source"]}
        if rec["divergent"]:
            out.setdefault("divergences", []).append({
                "field": "anafe_count",
                "brief_value": rec["brief_value"],
                "dual_read_value": rec["dual_read_value"],
            })

    # pileta_simple_doble
    if "pileta_simple_doble" in op_by_field:
        a = op_by_field["pileta_simple_doble"]
        val = a.get("value")
        if val:
            out["pileta_simple_doble"] = {"value": val, "source": "operator_answer"}
    else:
        rec = reconcile_pileta_simple_doble(analysis, feats)
        if rec["final"] is not None:
            out["pileta_simple_doble"] = {
                "value": rec["final"], "source": rec["source"],
            }
        if rec["divergent"]:
            out.setdefault("divergences", []).append({
                "field": "pileta_simple_doble",
                "brief_value": rec["brief_value"],
                "dual_read_value": rec["dual_read_value"],
            })

    # isla_presence — derivable de feats/analysis.
    isla_brief = bool(analysis.get("isla_mentioned"))
    isla_dr = bool(feats.get("has_isla"))
    if "isla_presence" in op_by_field:
        val = op_by_field["isla_presence"].get("value")
        if val in ("yes", "no"):
            out["isla_presence"] = {"value": val == "yes", "source": "operator_answer"}
    elif isla_brief:
        out["isla_presence"] = {"value": True, "source": "brief"}
    elif isla_dr:
        out["isla_presence"] = {"value": True, "source": "dual_read"}

    # Todas las respuestas del operador, para que el LLM las vea como
    # "confirmadas" aunque no estén en los campos canónicos (ej:
    # isla_profundidad, isla_patas, alzada).
    if operator_answers:
        out["operator_answers"] = list(operator_answers)

    return out
