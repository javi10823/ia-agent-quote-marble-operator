"""Brief analyzer — extracción robusta de contexto del brief del operador.

Soporta TODOS los tipos de trabajo (cocina / baño / lavadero / edificio) y
todos los campos del contrato required_fields.py. Usa Haiku (rápido y
barato) para parsing natural del texto; si falla, cae a regex fallback
que cubre los campos más comunes. Nunca crashea — siempre devuelve un
dict con shape válido.

Schema del output: ver `EMPTY_SCHEMA` abajo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

BRIEF_ANALYZER_MODEL = "claude-haiku-4-5-20251001"
BRIEF_ANALYZER_TIMEOUT_SECONDS = 20


# ─────────────────────────────────────────────────────────────────────────────
# Shape completa (contrato). Todas las keys presentes, valor null/false/[] si
# no se pudo extraer. Garantiza que el caller siempre tiene un shape estable.
# ─────────────────────────────────────────────────────────────────────────────

EMPTY_SCHEMA: dict = {
    # Globales
    "client_name": None,
    "project": None,
    "material": None,
    "localidad": None,
    "forma_pago": None,  # "contado" | "cuotas" | "transferencia" | "cheque" | null
    "demora_dias": None,  # int o string
    "es_edificio": False,
    "tipologias_count": None,  # int — relevant for edificios multi-tipo

    # Tipos de trabajo detectados (list: cocina, baño, lavadero, otro)
    "work_types": [],

    # Zócalos
    "zocalos": None,  # "yes" | "no" | null
    "zocalos_alto_cm": None,
    "zocalos_lados": None,  # list[str] | null

    # Alzada
    "alzada": None,
    "alzada_alto_cm": None,

    # Colocación
    "colocacion": None,  # "yes" | "no" | null

    # Pileta
    "pileta_mentioned": False,
    "pileta_type": None,  # "apoyo" | "empotrada" | "bajomesada" | null
    "pileta_count": None,
    "pileta_simple_doble": None,  # "simple" | "doble" | null (para cocina)
    "mentions_johnson": False,
    "johnson_sku": None,

    # Anafe
    "anafe_mentioned": False,
    "anafe_count": None,
    "anafe_gas_y_electrico": False,

    # Isla
    "isla_mentioned": False,
    "isla_profundidad_m": None,
    "isla_patas_lados": None,  # list[str] | null
    "isla_pata_alto_m": None,

    # Descuento
    "descuento_mentioned": False,
    "descuento_tipo": None,  # "arquitecta" | "cliente" | null
    "descuento_pct": None,

    # Frentin / regrueso / pulido
    "frentin_mentioned": False,
    "regrueso_mentioned": False,
    "pulido_mentioned": False,

    # Metadata
    "raw_notes": "",
    "extraction_method": "llm",  # "llm" | "regex_fallback" | "empty"
}


# ─────────────────────────────────────────────────────────────────────────────
# LLM prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Sos un extractor de contexto para presupuestos de
marmolería (D'Angelo). Recibís el brief/enunciado libre del operador y
devolvés JSON estructurado con TODOS los campos relevantes para el
trabajo, null/false/[] si no están presentes.

**Reglas críticas:**

1. NO inventes. Si no está en el brief, devolvé null / false / [] según
   corresponda al tipo.
2. `client_name`: SOLO el nombre, sin texto pegado. "Erica Bernardi" ✓;
   "Erica Bernardi SIN zocalos" ✗. Parar en mayúsculas all-caps, puntos,
   palabras funcionales (sin, con, en, de).
3. `material`: nombre limpio del material. Ej: "Puraprima Onix White
   Mate", "Silestone Blanco Norte", "Granito Negro Brasil". NO pegues
   "Cliente:" ni texto extra.
4. `localidad`: ciudad principal capitalizada. "Rosario", "Funes",
   "Puerto San Martín".
5. `work_types`: lista de sectores mencionados. Valores válidos:
   "cocina", "baño", "lavadero", "otro". Puede haber múltiples.
6. `zocalos`: "yes" si brief dice "con zócalos" / "lleva". "no" si
   "sin zócalos" / "no lleva". null si no menciona. Alto en cm si dice.
7. `pileta_type` (para baño): "apoyo" si dice "pileta de apoyo";
   "empotrada" si "empotrada" / "bajomesada"; null si ambigüo.
8. `pileta_simple_doble` (para cocina): "doble" si "pileta doble",
   "2 bachas"; "simple" si "1 bacha", "simple"; null si no aclara.
9. `anafe_count`: número explícito. "2 anafes", "anafe gas + eléctrico"
   → 2. "1 anafe" → 1. null si no dice. `anafe_gas_y_electrico` si
   menciona ambos explícitos.
10. `isla_mentioned`: true si el brief menciona isla explícitamente.
11. `descuento_tipo`: "arquitecta" si menciona arquitecta, "cliente"
    si descuento al cliente, null si no.
12. `es_edificio`: true si menciona "edificio", "unidades",
    "departamentos", "tipologías", edificio X, etc.
13. `mentions_johnson` + `johnson_sku`: true/string si menciona Johnson
    (ej "Johnson LUXOR S171" → johnson_sku="LUXOR S171").
14. `frentin_mentioned`, `regrueso_mentioned`, `pulido_mentioned`:
    true si el brief menciona estos trabajos extra.
15. `raw_notes`: copia de frases sueltas que no categorizas (ej
    aclaraciones específicas del cliente).

**Schema exacto (todas las keys presentes siempre):**

```json
{
  "client_name": string | null,
  "project": string | null,
  "material": string | null,
  "localidad": string | null,
  "forma_pago": "contado"|"cuotas"|"transferencia"|"cheque"|null,
  "demora_dias": int|string|null,
  "es_edificio": bool,
  "tipologias_count": int|null,
  "work_types": ["cocina"|"baño"|"lavadero"|"otro", ...],
  "zocalos": "yes"|"no"|null,
  "zocalos_alto_cm": int|null,
  "zocalos_lados": ["trasero"|"lateral_izq"|"lateral_der"|"frontal", ...]|null,
  "alzada": "yes"|"no"|null,
  "alzada_alto_cm": int|null,
  "colocacion": "yes"|"no"|null,
  "pileta_mentioned": bool,
  "pileta_type": "apoyo"|"empotrada"|"bajomesada"|null,
  "pileta_count": int|null,
  "pileta_simple_doble": "simple"|"doble"|null,
  "mentions_johnson": bool,
  "johnson_sku": string|null,
  "anafe_mentioned": bool,
  "anafe_count": int|null,
  "anafe_gas_y_electrico": bool,
  "isla_mentioned": bool,
  "isla_profundidad_m": float|null,
  "isla_patas_lados": ["frontal"|"lateral_izq"|"lateral_der", ...]|null,
  "isla_pata_alto_m": float|null,
  "descuento_mentioned": bool,
  "descuento_tipo": "arquitecta"|"cliente"|null,
  "descuento_pct": float|null,
  "frentin_mentioned": bool,
  "regrueso_mentioned": bool,
  "pulido_mentioned": bool,
  "raw_notes": string
}
```

Devolvé SOLO el JSON. Sin markdown, sin comentarios."""


# ─────────────────────────────────────────────────────────────────────────────
# Regex fallback — cubre los campos más críticos cuando el LLM falla
# ─────────────────────────────────────────────────────────────────────────────

_CLIENT_RE = re.compile(
    r"cliente\s*[:=]?\s*"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3})",
)
_MATERIAL_KEYS = ("silestone", "dekton", "neolith", "puraprima", "pura prima",
                  "purastone", "laminatto", "granito", "mármol", "marmol",
                  "onix", "quartz")
_MATERIAL_STOP = re.compile(
    r"\b(cliente|cliente:|con\s+|sin\s+|en\s+|obra|proyecto|presupuesto|"
    r"rosario|funes|roldan|roldán|localidad|,)",
    re.IGNORECASE,
)
_LOCALIDAD_RE = re.compile(
    r"\b(rosario|echesortu|funes|rold[aá]n|puerto\s+san\s+mart[ií]n|"
    r"granadero\s+baigorria|pueblo\s+esther|capit[aá]n\s+bermudez|"
    r"villa\s+gobernador\s+g[aá]lvez|arroyo\s+seco|san\s+lorenzo|"
    r"san\s+nicol[aá]s|pergamino|rafaela|fisherton)\b",
    re.IGNORECASE,
)
_ZOCALO_YES = re.compile(r"\b(con\s+z[oó]c|lleva(n)?\s+z[oó]c|z[oó]calos?\s*s[ií])", re.IGNORECASE)
_ZOCALO_NO = re.compile(r"\b(sin\s+z[oó]c|no\s+(lleva|van)\s+z[oó]c|z[oó]calos?\s*no)", re.IGNORECASE)
_COLOC_YES = re.compile(r"\b(con\s+colocaci[oó]n|incluye\s+colocaci[oó]n)", re.IGNORECASE)
_COLOC_NO = re.compile(r"\b(sin\s+colocaci[oó]n|no\s+(incluye\s+)?colocaci[oó]n)", re.IGNORECASE)
_PILETA = re.compile(r"\b(pileta|bacha)\b", re.IGNORECASE)
_PILETA_DOBLE = re.compile(r"\b(doble\s+bacha|bacha\s+doble|pileta\s+doble|2\s+bachas)", re.IGNORECASE)
_PILETA_APOYO = re.compile(r"\bpileta\s+(de\s+)?apoyo", re.IGNORECASE)
_PILETA_EMPOTRADA = re.compile(r"\b(empotrada|bajomesada|bajo\s+mesada)\b", re.IGNORECASE)
_JOHNSON = re.compile(r"\bjohnson\s+([A-Z0-9\s]+?)(?=\s+en\s|\s+con\s|\s+cliente|\s*[,;.]|$)", re.IGNORECASE)
_ANAFE = re.compile(r"\banafe", re.IGNORECASE)
_ANAFE_DUAL = re.compile(r"anafe\s+(a\s+)?gas.*el[eé]ctrico|2\s+anafes", re.IGNORECASE)
_ANAFE_COUNT = re.compile(r"(\d+)\s+anafes?\b", re.IGNORECASE)
_ISLA = re.compile(r"\bisla\b", re.IGNORECASE)
_BANIO = re.compile(r"\b(ba[ñn]o|vanitory)\b", re.IGNORECASE)
_COCINA = re.compile(r"\bcocina\b", re.IGNORECASE)
_LAVADERO = re.compile(r"\blavadero\b", re.IGNORECASE)
_EDIFICIO = re.compile(r"\b(edificio|tipolog[ií]a|unidades|departamentos?|dptos?)\b", re.IGNORECASE)
_DESCUENTO_ARQ = re.compile(r"\barquitect[oa]\b", re.IGNORECASE)
_DESCUENTO_PCT = re.compile(r"(\d+)\s*%", re.IGNORECASE)
_FRENTIN = re.compile(r"\bfrent[ií]n\b", re.IGNORECASE)
_REGRUESO = re.compile(r"\bregrueso\b", re.IGNORECASE)
_PULIDO = re.compile(r"\bpulido\b", re.IGNORECASE)


# Map de flags que el LLM puede marcar como `true` y que validamos
# contra el brief literal con word-boundary. PR #425 — fix
# alucinación del LLM Haiku que confundía "frente regrueso" con
# "frentín". Ver `_validate_llm_word_mentions` abajo.
_LLM_WORD_VALIDATIONS = (
    ("frentin_mentioned", _FRENTIN, "frent[ií]n"),
    ("regrueso_mentioned", _REGRUESO, "regrueso"),
    ("pulido_mentioned", _PULIDO, "pulido"),
)


def _validate_llm_word_mentions(brief: str, result: dict) -> None:
    """Override flags ruidosos del LLM cuando la palabra literal NO
    aparece word-boundary en el brief.

    **Por qué existe (PR #425, caso DYSCON 29/04/2026):**

    El LLM Haiku marcaba `frentin_mentioned: true` para briefs que
    contenían "frente regrueso" (interpretaba "frente" como frentín,
    aunque son dos conceptos distintos en marmolería: frentín =
    pieza vertical pegada al borde frontal, MO con SKU FALDON;
    frente regrueso = pieza horizontal que aumenta espesor visual
    del frente, MO con SKU REGRUESO).

    Endurecer el system prompt es frágil (review feedback: "el
    system prompt es demasiado frágil en conversaciones largas").
    Garantía dura: post-process con los mismos regex word-boundary
    que ya usa el fallback. Si el LLM dice `true` pero la palabra
    literal NO está en el brief, override a `False` con log.

    **Edge case conocido**: "sin frentín" → `frentin_mentioned: true`
    porque la palabra literal aparece. Es técnicamente correcto a
    nivel del analyzer (la mención está). Sonnet maneja la negación
    contextualmente. No es responsabilidad de este filtro detectar
    negación — anotado en Issue follow-up.

    Muta `result` in-place. NO tira excepciones — la observabilidad
    nunca rompe el flow (warning log + continúa).
    """
    for flag_key, regex, word_label in _LLM_WORD_VALIDATIONS:
        if not result.get(flag_key):
            continue
        if regex.search(brief):
            continue  # LLM y regex coinciden — OK
        # LLM dijo true pero la palabra literal no está → alucinación.
        logger.warning(
            f"[brief-analyzer] LLM hallucination override: "
            f"{flag_key}=true sin literal '{word_label}' en brief. "
            f"Override → False. Brief snippet: {brief[:150]!r}"
        )
        result[flag_key] = False


def _extract_material_regex(brief: str) -> str | None:
    low = brief.lower()
    start_idx = -1
    for k in _MATERIAL_KEYS:
        idx = low.find(k)
        if idx != -1 and (start_idx == -1 or idx < start_idx):
            start_idx = idx
    if start_idx == -1:
        return None
    rest = brief[start_idx:]
    m = _MATERIAL_STOP.search(rest)
    if m:
        return rest[: m.start()].strip().rstrip(",.;").strip().title()
    # fallback: 60 chars
    return rest[:60].strip().rstrip(",.;").strip().title()


def _analyze_regex_fallback(brief: str) -> dict:
    """Extracción determinística — fallback si el LLM falla. Cubre los
    campos más usados. No es tan preciso como el LLM pero nunca falla."""
    b = brief or ""
    result = dict(EMPTY_SCHEMA)
    result["extraction_method"] = "regex_fallback"
    result["raw_notes"] = b.strip()[:500]

    m = _CLIENT_RE.search(b)
    if m:
        result["client_name"] = m.group(1).strip()

    mat = _extract_material_regex(b)
    if mat:
        result["material"] = mat

    m = _LOCALIDAD_RE.search(b)
    if m:
        result["localidad"] = m.group(0).title()

    if _ZOCALO_NO.search(b):
        result["zocalos"] = "no"
    elif _ZOCALO_YES.search(b):
        result["zocalos"] = "yes"

    if _COLOC_NO.search(b):
        result["colocacion"] = "no"
    elif _COLOC_YES.search(b):
        result["colocacion"] = "yes"

    if _PILETA.search(b):
        result["pileta_mentioned"] = True
    if _PILETA_DOBLE.search(b):
        result["pileta_simple_doble"] = "doble"
    if _PILETA_APOYO.search(b):
        result["pileta_type"] = "apoyo"
    elif _PILETA_EMPOTRADA.search(b):
        result["pileta_type"] = "empotrada"

    m = _JOHNSON.search(b)
    if m:
        result["mentions_johnson"] = True
        result["johnson_sku"] = m.group(1).strip()

    if _ANAFE.search(b):
        result["anafe_mentioned"] = True
    m = _ANAFE_COUNT.search(b)
    if m:
        try:
            result["anafe_count"] = int(m.group(1))
        except ValueError:
            pass
    if _ANAFE_DUAL.search(b):
        result["anafe_gas_y_electrico"] = True
        if not result["anafe_count"]:
            result["anafe_count"] = 2

    if _ISLA.search(b):
        result["isla_mentioned"] = True

    work = []
    if _COCINA.search(b):
        work.append("cocina")
    if _BANIO.search(b):
        work.append("baño")
    if _LAVADERO.search(b):
        work.append("lavadero")
    result["work_types"] = work

    if _EDIFICIO.search(b):
        result["es_edificio"] = True

    if _DESCUENTO_ARQ.search(b):
        result["descuento_mentioned"] = True
        result["descuento_tipo"] = "arquitecta"
    m = _DESCUENTO_PCT.search(b)
    if m:
        try:
            result["descuento_pct"] = float(m.group(1))
        except ValueError:
            pass

    if _FRENTIN.search(b):
        result["frentin_mentioned"] = True
    if _REGRUESO.search(b):
        result["regrueso_mentioned"] = True
    if _PULIDO.search(b):
        result["pulido_mentioned"] = True

    return result


# ─────────────────────────────────────────────────────────────────────────────
# LLM entry point — con fallback a regex
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_brief(brief: str) -> dict:
    """Extrae contexto estructurado del brief. Nunca crashea.

    Flow:
    1. Intenta LLM (Haiku, 20s timeout).
    2. Si falla / timeout → regex fallback.
    3. Si el brief está vacío → shape vacía.

    El output siempre tiene `extraction_method` marcando cuál se usó.
    """
    if not brief or not brief.strip():
        result = dict(EMPTY_SCHEMA)
        result["extraction_method"] = "empty"
        return result

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await asyncio.wait_for(
            client.messages.create(
                model=BRIEF_ANALYZER_MODEL,
                max_tokens=900,
                system=_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Brief:\n```\n{brief.strip()}\n```",
                }],
            ),
            timeout=BRIEF_ANALYZER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[brief-analyzer] LLM timeout → regex fallback")
        return _analyze_regex_fallback(brief)
    except Exception as e:
        logger.warning(f"[brief-analyzer] LLM error ({e}) → regex fallback")
        return _analyze_regex_fallback(brief)

    # Parse LLM response
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                parsed = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    if not isinstance(parsed, dict):
        logger.warning(f"[brief-analyzer] JSON parse failed → regex fallback")
        return _analyze_regex_fallback(brief)

    # Merge con shape vacío — todos los campos siempre presentes
    result = dict(EMPTY_SCHEMA)
    for k in EMPTY_SCHEMA:
        if k in parsed:
            result[k] = parsed[k]
    result["extraction_method"] = "llm"
    # preservar raw_notes si no viene del LLM
    if not result.get("raw_notes"):
        result["raw_notes"] = brief.strip()[:500]

    logger.info(
        f"[brief-analyzer] LLM extracted: client={result['client_name']}, "
        f"material={result['material']}, localidad={result['localidad']}, "
        f"work_types={result['work_types']}, pileta={result['pileta_type']}/"
        f"{result['pileta_simple_doble']}, anafe_count={result['anafe_count']}, "
        f"isla={result['isla_mentioned']}, es_edificio={result['es_edificio']}"
    )

    # PR #425 — post-process anti-alucinación. Mismas regex word-boundary
    # que el fallback regex; se ejecuta SOLO en la rama LLM porque el
    # fallback ya usa los regex como única fuente y no produce false
    # positives por construcción.
    _validate_llm_word_mentions(brief, result)

    return result
