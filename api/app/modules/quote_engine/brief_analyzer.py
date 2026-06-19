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
    # Contacto del cliente. Extraído del bloque "Contacto:" del brief o de
    # las palabras-ancla típicas ("Tel:", "Email:", etc.). Sub-PR
    # `brief-analyzer-deuda-cleanup` cerró el wire de mirroreo a las
    # columnas `Quote.client_phone` / `Quote.client_email` vía lazy denorm
    # en `agent/router.py::get_quote` (pareja del `client_name` denorm).
    "phone": None,   # string | null  · ej "3464696027"
    "email": None,   # string | null  · ej "x@y.com"
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

    # Frentin / regrueso / pulido — Bug 5 fix · PR #485.
    # Migrados de `*_mentioned: bool` a ternary `"yes"|"no"|null` para
    # distinguir "Brief dice 'Frentín: No' explícito" (= "no") vs "Brief
    # no menciona frentín en absoluto" (= null). Antes ambos colapsaban
    # a `False` y el sistema perdía la información del operador. Patrón
    # replicado de `colocacion`/`zocalos`/`alzada`. Activa el Issue
    # follow-up del PR #425.
    "frentin": None,   # "yes" | "no" | null
    "regrueso": None,  # "yes" | "no" | null
    "pulido": None,    # "yes" | "no" | null

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
3. `phone` / `email`: extraé del bloque "Contacto:" del brief o cuando
   se declaren explícitamente con palabras-ancla: "Tel:", "Cel:",
   "Teléfono:", "WhatsApp:", "Móvil:" para phone · "Email:", "Mail:"
   para email. SOLO si están ancladas a esas palabras — NO extraigas
   IDs (ej "DA-1781136799652-KVZU"), DNI ("12345678"), CUITs
   ("20-12345678-9") ni números de orden sueltos. Phone: devolvé solo
   los dígitos sin espacios/guiones (ej "3464696027" no
   "3464-696027"). Email: formato estándar. null si no se mencionan.
4. `material`: nombre limpio del material. Ej: "Puraprima Onix White
   Mate", "Silestone Blanco Norte", "Granito Negro Brasil". NO pegues
   "Cliente:" ni texto extra.
5. `localidad`: ciudad principal capitalizada. "Rosario", "Funes",
   "Puerto San Martín".
6. `work_types`: lista de sectores mencionados. Valores válidos:
   "cocina", "baño", "lavadero", "otro". Puede haber múltiples.
7. `zocalos`: "yes" si brief dice "con zócalos" / "lleva". "no" si
   "sin zócalos" / "no lleva". null si no menciona. Alto en cm si dice.
8. `pileta_type` (para baño): "apoyo" si dice "pileta de apoyo";
   "empotrada" si "empotrada" / "bajomesada"; null si ambigüo.
9. `pileta_simple_doble` (para cocina): "doble" si "pileta doble",
   "2 bachas"; "simple" si "1 bacha", "simple"; null si no aclara.
10. `anafe_count`: número explícito. "2 anafes", "anafe gas + eléctrico"
    → 2. "1 anafe" → 1. null si no dice. `anafe_gas_y_electrico` si
    menciona ambos explícitos.
11. `isla_mentioned`: true si el brief menciona isla explícitamente.
12. `descuento_tipo`: "arquitecta" si menciona arquitecta, "cliente"
    si descuento al cliente, null si no.
13. `es_edificio`: true si menciona "edificio", "unidades",
    "departamentos", "tipologías", edificio X, etc.
14. `mentions_johnson` + `johnson_sku`: true/string si menciona Johnson
    (ej "Johnson LUXOR S171" → johnson_sku="LUXOR S171").
15. `frentin`, `regrueso`, `pulido`: ternary "yes"|"no"|null.
    - "yes" si brief dice "con frentín" / "lleva frentín" / "Frentín: Sí".
    - "no" si brief dice "sin frentín" / "Frentín: No" / "no lleva frentín".
    - null si NO se menciona en absoluto.
    Idem para regrueso y pulido. Importante: distinguir "No" explícito
    del operador de "no mencionado" — son operativamente distintos
    (el primero es decisión, el segundo es ausencia de información).
16. `raw_notes`: copia de frases sueltas que no categorizas (ej
    aclaraciones específicas del cliente).

**Schema exacto (todas las keys presentes siempre):**

```json
{
  "client_name": string | null,
  "phone": string | null,
  "email": string | null,
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
  "frentin": "yes"|"no"|null,
  "regrueso": "yes"|"no"|null,
  "pulido": "yes"|"no"|null,
  "raw_notes": string
}
```

Devolvé SOLO el JSON. Sin markdown, sin comentarios."""


# ─────────────────────────────────────────────────────────────────────────────
# Regex fallback — cubre los campos más críticos cuando el LLM falla
# ─────────────────────────────────────────────────────────────────────────────

_CLIENT_RE = re.compile(
    # Ancla "cliente" case-insensitive (`(?i:...)` inline) · captura sigue
    # case-sensitive para preservar Title Case del nombre. Dos defensas
    # contra contaminación del captura:
    #   1. Separador interno `[ \t]+` (no `\s+`) impide cruzar newlines · así
    #      "Cliente: Juan Pérez\nLocalidad:" captura solo "Juan Pérez".
    #   2. `_clean_client_match()` trunca palabras-ancla legítimas ("Tel",
    #      "Email") que también son Title Case válido y entran al match.
    r"(?i:cliente)\s*[:=]?[ \t]*"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:[ \t]+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3})",
)

_CLIENT_STOP_WORDS = {
    "tel", "cel", "teléfono", "telefono", "whatsapp",
    "móvil", "movil", "email", "mail",
    "en", "de", "con", "sin", "para",
}


def _clean_client_match(raw: str) -> str:
    """Trunca el nombre cuando aparece una stop-word (tel/email/preposición).

    Defensive safety net post-regex: el captura de `_CLIENT_RE` toma hasta
    4 Title-Case palabras consecutivas, y "Tel" cuenta como Title Case válido
    así que entra al match cuando el brief es "Cliente Juan Pérez Tel: 341...".
    Este helper trunca al primer match de stop-word (case-insensitive).
    """
    parts = raw.strip().split()
    out: list[str] = []
    for p in parts:
        if p.lower().rstrip(":,.;") in _CLIENT_STOP_WORDS:
            break
        out.append(p)
    return " ".join(out)
# Contacto · sub-PR sprint-4/contacto-extraction-fix.
# Phone requiere palabra-ancla cercana (Tel/Cel/Teléfono/WhatsApp/Móvil)
# para evitar falsos positivos: DNI (8 dígitos sueltos), CUIT (11 con
# dashes), IDs internos (ej "DA-1781136799652-KVZU" del brief Micaela),
# números de orden. Brief AR típico tiene formatos variados que
# normalizamos a solo dígitos al persistir: "3464696027" / "3464 696027"
# / "+54 9 3464 696027" / "(0346) 4-696027".
_PHONE_RE = re.compile(
    r"\b(?:tel|cel|tel[ée]fono|whats?app|m[oó]vil)\s*[:.\-=]?\s*"
    r"(\+?[\d(][\d\s\-().]{6,18}\d)",
    re.IGNORECASE,
)
_PHONE_CLEAN = re.compile(r"[\s\-().]")  # elimina espacios/guiones/paréntesis
# Email · regex estándar simple. No restringe TLD para no fallar con
# dominios largos (.com.ar, etc.).
_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
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
# Regex de presencia literal — usado por el validator anti-alucinación
# (PR #425) que chequea que la palabra esté en el brief. NO se usa para
# decidir yes/no (eso lo hacen _X_YES / _X_NO abajo).
_FRENTIN = re.compile(r"\bfrent[ií]n\b", re.IGNORECASE)
_REGRUESO = re.compile(r"\bregrueso\b", re.IGNORECASE)
_PULIDO = re.compile(r"\bpulido\b", re.IGNORECASE)

# Bug 5 fix · PR #485 — patrones espejo de zócalos para distinguir
# "Sí" / "No" / null en el regex fallback. Captura todos los formatos
# de brief estructurado típicos:
#   - "con frentín" / "lleva frentín" / "Frentín: Sí"
#   - "sin frentín" / "no lleva frentín" / "Frentín: No"
# Si el operador escribe formatos atípicos ("frentín? si"), el LLM
# Haiku ya lo captura con temperature=0. El regex es solo fallback.
_FRENTIN_YES = re.compile(
    r"\b(con\s+frent[ií]n|lleva(n)?\s+frent[ií]n|frent[ií]n\s*:?\s*s[ií])",
    re.IGNORECASE,
)
_FRENTIN_NO = re.compile(
    r"\b(sin\s+frent[ií]n|no\s+(lleva|van)\s+frent[ií]n|frent[ií]n\s*:?\s*no\b)",
    re.IGNORECASE,
)
_REGRUESO_YES = re.compile(
    r"\b(con\s+regrueso|lleva(n)?\s+regrueso|regrueso\s*:?\s*s[ií])",
    re.IGNORECASE,
)
_REGRUESO_NO = re.compile(
    r"\b(sin\s+regrueso|no\s+(lleva|van)\s+regrueso|regrueso\s*:?\s*no\b)",
    re.IGNORECASE,
)
_PULIDO_YES = re.compile(
    r"\b(con\s+pulido|lleva(n)?\s+pulido|pulido\s*:?\s*s[ií])",
    re.IGNORECASE,
)
_PULIDO_NO = re.compile(
    r"\b(sin\s+pulido|no\s+(lleva|van)\s+pulido|pulido\s*:?\s*no\b)",
    re.IGNORECASE,
)


# Map de flags ternary que el LLM puede setear y que validamos contra
# el brief literal con word-boundary. PR #425 — fix alucinación del LLM
# Haiku que confundía "frente regrueso" con "frentín". Post-Bug-5 (PR
# #485) los flags son ternary `"yes"|"no"|null` en vez de bool: si el
# LLM dijo "yes" o "no" pero la palabra literal NO aparece en el brief,
# override a `None` (no había nada que decidir).
_LLM_WORD_VALIDATIONS = (
    ("frentin", _FRENTIN, "frent[ií]n"),
    ("regrueso", _REGRUESO, "regrueso"),
    ("pulido", _PULIDO, "pulido"),
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
    que ya usa el fallback. Si el LLM setea un valor pero la palabra
    literal NO está en el brief, override a `None` con log.

    **Post Bug 5 (PR #485):** los flags son ternary `"yes"|"no"|null`.
    Si el LLM dijo `"yes"` o `"no"` (cualquier no-null) pero la
    palabra literal NO aparece en el brief → override a `None`. El
    caso "sin frentín" → "no" (la palabra SÍ aparece, el regex YES/NO
    decide la semántica) ya NO es deuda — el analyzer distingue
    explícitamente Sí/No/sin mencionar.

    Muta `result` in-place. NO tira excepciones — la observabilidad
    nunca rompe el flow (warning log + continúa).
    """
    for flag_key, regex, word_label in _LLM_WORD_VALIDATIONS:
        if result.get(flag_key) is None:
            continue  # LLM no decidió nada → no hay nada que validar
        if regex.search(brief):
            continue  # LLM y palabra literal coinciden — OK
        # LLM decidió yes/no pero la palabra literal no está → alucinación.
        logger.warning(
            f"[brief-analyzer] LLM hallucination override: "
            f"{flag_key}={result.get(flag_key)!r} sin literal "
            f"'{word_label}' en brief. Override → None. "
            f"Brief snippet: {brief[:150]!r}"
        )
        result[flag_key] = None


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
        cleaned = _clean_client_match(m.group(1))
        if cleaned:
            result["client_name"] = cleaned

    # Phone con palabra-ancla · sub-PR contacto-extraction. Limpiamos
    # formato (espacios/guiones/paréntesis) y validamos rango 8-16
    # dígitos. 8 dígitos legítimos (ej "Tel: 12345678") quedan — la
    # ancla es el filtro contra DNI/CUIT sueltos.
    m = _PHONE_RE.search(b)
    if m:
        cleaned = _PHONE_CLEAN.sub("", m.group(1))
        if 8 <= len(cleaned) <= 16:
            result["phone"] = cleaned

    m = _EMAIL_RE.search(b)
    if m:
        result["email"] = m.group(1)

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

    # Bug 5 fix · PR #485 — ternary "yes"/"no"/null replicando pattern
    # de zócalos. Prioridad: NO antes que YES (porque "sin frentín" no
    # debe matchear `_FRENTIN_YES` aunque contenga "frentín").
    if _FRENTIN_NO.search(b):
        result["frentin"] = "no"
    elif _FRENTIN_YES.search(b):
        result["frentin"] = "yes"
    if _REGRUESO_NO.search(b):
        result["regrueso"] = "no"
    elif _REGRUESO_YES.search(b):
        result["regrueso"] = "yes"
    if _PULIDO_NO.search(b):
        result["pulido"] = "no"
    elif _PULIDO_YES.search(b):
        result["pulido"] = "yes"

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
                # Bug 5 fix · PR #485 — temperature=0 elimina
                # variabilidad entre runs idénticos (Run1≠Run2 con
                # mismo brief). El SDK Anthropic default es 1.0, que
                # introduce stochasticidad inaceptable para extracción
                # estructurada user-facing. Ver lección #56.
                temperature=0,
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
