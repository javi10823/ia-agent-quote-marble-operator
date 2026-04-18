"""Pending questions — infra para "preguntar antes de asumir".

Principio rector del operador D'Angelo: Valentina nunca asume datos que no
están en el brief ni en el plano. En vez de rellenar defaults silenciosos,
emite una `pending_question` que bloquea el Confirmar de la card hasta que
el operador responda (o marque "no aplica").

Este módulo define:
- El shape del objeto PendingQuestion.
- Detectores (funciones puras que toman contexto y devuelven preguntas).
- Un aplicador que toma las respuestas del operador y las materializa en el
  JSON de medidas verificadas (ej: "Sí, trasero 7cm" → agrega zócalos).

Arranca con UN detector: zócalos cuando el brief no los menciona. Siguientes
PRs agregan más (profundidad de isla, patas, anafe count, etc.) sobre la
misma infra.
"""
from __future__ import annotations

import re
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Brief matchers (keyword detection sobre el texto libre del operador)
# ─────────────────────────────────────────────────────────────────────────────

_ZOCALO_WITH = re.compile(
    r"\b(con\s+z[oó]c|lleva(n)?\s+z[oó]c|z[oó]calos?\s*s[ií]|"
    r"z[oó]c\s*[=:]\s*\d)",
    re.IGNORECASE,
)
_ZOCALO_WITHOUT = re.compile(
    r"\b(sin\s+z[oó]c|no\s+(lleva|van)\s+z[oó]c|z[oó]calos?\s*no|"
    r"no\s+z[oó]c)",
    re.IGNORECASE,
)

_JOHNSON = re.compile(r"\bjohnson\b", re.IGNORECASE)
_PILETA_DOBLE = re.compile(r"\b(doble\s+bacha|bacha\s+doble|pileta\s+doble|doble\s+pileta|2\s+bachas)\b", re.IGNORECASE)
_PILETA_SIMPLE = re.compile(r"\b(simple\s+bacha|bacha\s+simple|pileta\s+simple|1\s+bacha)\b", re.IGNORECASE)
_APOYO_EXPLICIT = re.compile(r"\b(pileta|bacha)\s+(de\s+)?apoyo\b", re.IGNORECASE)

_COLOCACION_WITH = re.compile(r"\b(con\s+colocaci[oó]n|incluye\s+colocaci[oó]n|colocaci[oó]n\s*s[ií])\b", re.IGNORECASE)
_COLOCACION_WITHOUT = re.compile(r"\b(sin\s+colocaci[oó]n|no\s+(incluye\s+)?colocaci[oó]n|colocaci[oó]n\s*no)\b", re.IGNORECASE)

_ANAFE_COUNT_EXPLICIT = re.compile(r"\b(1|un|uno|2|dos|3|tres)\s+anafes?\b", re.IGNORECASE)
_ANAFE_DUAL = re.compile(r"\b(anafe\s+(a\s+)?gas.*(anafe\s+)?(el[eé]ctrico|vitro)|2\s+anafes)\b", re.IGNORECASE)

_PILETA_NO = re.compile(r"\bsin\s+(pileta|bacha)|no\s+(lleva|va)\s+(pileta|bacha)", re.IGNORECASE)
_ANAFE_NO = re.compile(r"\bsin\s+anafe|no\s+(lleva|va)\s+anafe", re.IGNORECASE)
_ISLA = re.compile(r"\bisla\b", re.IGNORECASE)
_ISLA_NO = re.compile(r"\bsin\s+isla|no\s+(lleva|va)\s+isla|cocina\s+(recta|en\s+l)\b", re.IGNORECASE)
_ALZADA = re.compile(r"\b(con|lleva)\s+alzada|alzada\s+(de|=)\s*\d", re.IGNORECASE)
_ALZADA_NO = re.compile(r"\bsin\s+alzada|no\s+(lleva|va)\s+alzada", re.IGNORECASE)


def brief_mentions_zocalos(brief: str) -> str | None:
    """Devuelve 'yes' si el brief pide zócalos, 'no' si los excluye, None si
    no los menciona (→ hay que preguntar)."""
    if not brief:
        return None
    if _ZOCALO_WITHOUT.search(brief):
        return "no"
    if _ZOCALO_WITH.search(brief):
        return "yes"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Question detectors
# ─────────────────────────────────────────────────────────────────────────────

def _has_sector_type(dual_result: dict, tipo: str) -> bool:
    return any(
        (s.get("tipo") or "").lower() == tipo
        for s in (dual_result.get("sectores") or [])
    )


# "cocina-like": cualquier sector que NO sea baño/lavadero/isla cuenta como
# cocina a fines de disparar preguntas (pileta, anafe, alzada). Cubre los
# casos donde el LLM tipa el sector como "l", "u", "recta", "cocina_l", etc.
_NON_COCINA_TIPOS = {"baño", "banio", "baño_principal", "toilet", "lavadero", "isla"}


def _is_cocina_work(dual_result: dict, brief: str = "") -> bool:
    """True si el trabajo tiene un sector tipo cocina (amplio) o si el brief
    menciona cocina explícitamente (aunque el dual_read haya fallado)."""
    for s in (dual_result.get("sectores") or []):
        tipo = (s.get("tipo") or "").lower()
        if tipo and tipo not in _NON_COCINA_TIPOS:
            # "cocina", "l", "u", "recta", "cocina_isla", etc.
            return True
    if brief and re.search(r"\bcocina\b", brief, re.IGNORECASE):
        return True
    # Si NO hay baño ni lavadero explícito, asumimos cocina por default
    has_non_cocina = any(
        (s.get("tipo") or "").lower() in _NON_COCINA_TIPOS
        for s in (dual_result.get("sectores") or [])
    )
    return not has_non_cocina and bool(dual_result.get("sectores"))


def _brief_mentions_isla(brief: str) -> bool:
    return bool(brief and re.search(r"\bisla\b", brief, re.IGNORECASE) and
                not re.search(r"\bsin\s+isla|no\s+(lleva|va)\s+isla", brief, re.IGNORECASE))


def _has_pileta_in_card(dual_result: dict) -> bool:
    """True si algún tramo tiene marca de pileta (feature o metadata)."""
    for s in dual_result.get("sectores") or []:
        for t in s.get("tramos") or []:
            features = t.get("features") or {}
            if features.get("has_pileta") or features.get("sink_double"):
                return True
            notes = (t.get("descripcion") or "").lower()
            if "pileta" in notes or "bacha" in notes:
                return True
    return False


def _detect_pileta_question(brief: str, dual_result: dict) -> dict | None:
    """Pregunta unificada de pileta para cocina: existe + tipo simple/doble.

    En cocina, si la pileta existe va siempre empotrada (regla D'Angelo,
    nunca apoyo). Entonces solo variamos: existe + si existe, simple o
    doble.

    Skip si brief es explícito ("sin pileta" / "pileta doble" / etc.) o si
    la card tiene sink_double como feature con valor definido.
    """
    if not _is_cocina_work(dual_result, brief or ""):
        return None
    brief = brief or ""

    # Skip si brief niega explícito
    if _PILETA_NO.search(brief):
        return None
    # Skip si brief ya dice simple o doble
    if _PILETA_DOBLE.search(brief) or _PILETA_SIMPLE.search(brief):
        return None
    # Skip si la card ya tiene sink_double con valor concluyente
    for s in dual_result.get("sectores") or []:
        for t in s.get("tramos") or []:
            features = t.get("features") or {}
            if features.get("sink_double") is not None:
                return None

    return {
        "id": "pileta_simple_doble",
        "label": "Pileta",
        "question": (
            "¿Lleva pileta? En cocina siempre va empotrada (regla D'Angelo — "
            "nunca apoyo). Si lleva, ¿es simple o doble?"
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "simple", "label": "Sí — simple (1 bacha)"},
            {"value": "doble", "label": "Sí — doble (2 bachas)"},
            {"value": "no", "label": "No lleva pileta"},
        ],
    }


def _detect_isla_profundidad_question(brief: str, dual_result: dict) -> dict | None:
    """Isla → SIEMPRE preguntar profundidad (nunca asumir). Dispara si
    dual_read detectó isla O si brief la menciona (aunque multi-crop falló).

    Skip solo si el brief da el valor explícito (ej: "isla de 0.80",
    "profundidad isla X").
    """
    has_isla = _has_sector_type(dual_result, "isla") or _brief_mentions_isla(brief)
    if not has_isla:
        return None
    if brief:
        if re.search(r"isla\s+(de\s+)?\d+[,.]\d", brief, re.IGNORECASE):
            return None
        if re.search(r"profundidad\s+isla\s*[=:]?\s*\d", brief, re.IGNORECASE):
            return None
    return {
        "id": "isla_profundidad",
        "label": "Profundidad de la isla",
        "question": (
            "¿Cuál es la profundidad (ancho) de la isla? En general el plano "
            "no la muestra explícitamente — preferimos no asumir."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "0.60", "label": "0.60 m (estándar residencial)"},
            {"value": "0.70", "label": "0.70 m"},
            {"value": "0.80", "label": "0.80 m"},
            {"value": "custom", "label": "Otra medida (detallar)"},
        ],
        "detail_placeholder": "Ej: 0.75",
    }


def _detect_isla_patas_question(brief: str, dual_result: dict) -> dict | None:
    """Isla → preguntar si lleva patas (frontal + ambos laterales) y alto.
    Siempre preguntar — no hay default razonable y afecta la cotización.
    Dispara si dual_read detectó isla O brief la menciona."""
    has_isla = _has_sector_type(dual_result, "isla") or _brief_mentions_isla(brief)
    if not has_isla:
        return None
    return {
        "id": "isla_patas",
        "label": "Patas de la isla",
        "question": (
            "¿La isla lleva patas (frente y/o laterales)? El alto suele ser del "
            "piso a la mesada. El plano no deja esto explícito."
        ),
        "type": "radio_with_detail",
        "options": [
            {
                "value": "frontal_y_ambos_laterales",
                "label": "Sí — frontal + ambos laterales",
                "apply": {"sides": ["frontal", "lateral_izq", "lateral_der"]},
            },
            {
                "value": "solo_frontal",
                "label": "Solo frontal",
                "apply": {"sides": ["frontal"]},
            },
            {
                "value": "solo_laterales",
                "label": "Solo ambos laterales",
                "apply": {"sides": ["lateral_izq", "lateral_der"]},
            },
            {
                "value": "custom",
                "label": "Otra combinación (detallar lados y alto)",
                "apply": {"sides": "custom"},
            },
            {"value": "no", "label": "No lleva patas"},
        ],
        "detail_placeholder": "Ej: 'solo lateral_izq, alto 0.80m'",
    }


def _detect_colocacion_question(brief: str, dual_result: dict) -> dict | None:
    """Colocación: si el brief no menciona, preguntar. Default comercial suele
    ser 'con colocación' pero no lo asumimos silencioso."""
    b = brief or ""
    if _COLOCACION_WITH.search(b) or _COLOCACION_WITHOUT.search(b):
        return None
    return {
        "id": "colocacion",
        "label": "Colocación",
        "question": "¿El presupuesto incluye colocación (mano de obra de instalación)?",
        "type": "radio_with_detail",
        "options": [
            {"value": "si", "label": "Sí, incluye colocación"},
            {"value": "no", "label": "No, solo corte y pulido"},
        ],
    }


def _detect_anafe_count_question(brief: str, dual_result: dict) -> dict | None:
    """Pregunta unificada de anafe: existe + cuántos. Siempre en cocina
    salvo que el brief lo confirme explícito (count o 'sin anafe').
    """
    if not _is_cocina_work(dual_result, brief or ""):
        return None
    b = brief or ""
    # Skip si brief dice count explícito o niega anafe
    if _ANAFE_COUNT_EXPLICIT.search(b):
        return None
    if _ANAFE_NO.search(b):
        return None

    return {
        "id": "anafe_count",
        "label": "Anafe",
        "question": (
            "¿Lleva anafe? Si sí, ¿cuántos? Cada anafe empotrado suma MO "
            "(gas y eléctrico suelen ir separados = 2 agujeros)."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "1", "label": "Sí — 1 anafe"},
            {"value": "2", "label": "Sí — 2 anafes (ej: gas + eléctrico)"},
            {"value": "3", "label": "Sí — 3+ anafes (detallar)"},
            {"value": "0", "label": "No lleva anafe"},
        ],
        "detail_placeholder": "Si son 3+: cuántos",
    }


def _detect_isla_presence_question(brief: str, dual_result: dict) -> dict | None:
    """Si el dual_read no detectó isla pero el brief no la niega, preguntar
    explícitamente si va o no. Cubre el caso donde el multi-crop falla al
    detectar la isla (plano difícil) — evitamos perder la isla.
    """
    if _has_sector_type(dual_result, "isla"):
        return None  # ya detectada, otras preguntas cubren detalles
    b = brief or ""
    if _ISLA.search(b) and not _ISLA_NO.search(b):
        # Brief la menciona → no preguntar existencia, pero sí detalles
        # (se cubren por _detect_isla_profundidad_question y _isla_patas)
        return None
    if _ISLA_NO.search(b):
        return None  # brief explícito: no hay isla
    return {
        "id": "isla_presence",
        "label": "Isla",
        "question": (
            "¿El plano tiene isla central? Detectarla depende del render — "
            "confirmanos para no omitirla del presupuesto."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "yes", "label": "Sí, hay isla"},
            {"value": "no", "label": "No hay isla (cocina recta / L / U sin isla)"},
        ],
    }


def _detect_alzada_question(brief: str, dual_result: dict) -> dict | None:
    """Alzada: típicamente el operador la olvida o no está en el plano.
    Preguntar siempre en cocina salvo que brief sea explícito."""
    if not _is_cocina_work(dual_result, brief or ""):
        return None
    b = brief or ""
    if _ALZADA.search(b) or _ALZADA_NO.search(b):
        return None
    return {
        "id": "alzada",
        "label": "Alzada",
        "question": (
            "¿Lleva alzada? (la tira vertical que sube por detrás de la mesada)"
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "no", "label": "No lleva"},
            {"value": "5", "label": "Sí — 5 cm"},
            {"value": "10", "label": "Sí — 10 cm"},
            {"value": "custom", "label": "Sí — otro alto (detallar)"},
        ],
        "detail_placeholder": "Ej: 15 cm",
    }


def _detect_zocalos_question(brief: str, dual_result: dict) -> dict | None:
    """Si el brief no menciona zócalos y la card tampoco los detectó, preguntar.

    No se pregunta cuando:
    - Brief dice "con zócalos" / "sin zócalos" (ya hay respuesta).
    - La card ya tiene zócalos con ml > 0 (el plan reader los vio).
    """
    mentioned = brief_mentions_zocalos(brief or "")
    if mentioned is not None:
        return None

    has_zocalos_in_card = any(
        (z.get("ml") or 0) > 0
        for s in (dual_result.get("sectores") or [])
        for t in (s.get("tramos") or [])
        for z in (t.get("zocalos") or [])
    )
    if has_zocalos_in_card:
        return None

    return {
        "id": "zocalos",
        "label": "Zócalos",
        "question": (
            "¿Lleva zócalos? El brief no los menciona y en el plano no se "
            "ven explícitamente. Si sí, ¿de qué alto y contra qué paredes?"
        ),
        "type": "radio_with_detail",
        "options": [
            {
                "value": "default_trasero",
                "label": "Sí — trasero por tramo, 7cm (default)",
                "apply": {"mode": "trasero_default", "alto_m": 0.07},
            },
            {
                "value": "custom",
                "label": "Sí — otro alto o qué lados (detallar)",
                "apply": {"mode": "custom"},
            },
            {
                "value": "no",
                "label": "No lleva zócalos",
                "apply": {"mode": "none"},
            },
        ],
        "detail_placeholder": (
            "Ej: 'trasero y lateral izq, 5cm' o '10cm solo trasero'"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point: detect all pending questions for this card
# ─────────────────────────────────────────────────────────────────────────────

def detect_pending_questions(
    brief: str,
    dual_result: dict,
    quote: dict | None = None,
) -> list[dict]:
    """Devuelve la lista de preguntas pendientes. Vacía si todos los datos
    detectables están presentes.

    Cada detector corre independiente — si uno falla o no aplica, los otros
    siguen. Orden de la lista = orden de presentación en la UI (primero lo
    más crítico para el cálculo).
    """
    questions: list[dict] = []
    # Campos obligatorios globales (PR F): material + localidad.
    try:
        from app.modules.quote_engine.required_fields import detect_required_field_questions
        questions.extend(detect_required_field_questions(brief, quote, dual_result))
    except Exception:
        pass
    # Presencia de componentes (orden de criticidad).
    q_pileta = _detect_pileta_question(brief, dual_result)
    if q_pileta:
        questions.append(q_pileta)
    q_anafe = _detect_anafe_count_question(brief, dual_result)
    if q_anafe:
        questions.append(q_anafe)
    q_isla_presence = _detect_isla_presence_question(brief, dual_result)
    if q_isla_presence:
        questions.append(q_isla_presence)
    q_isla_prof = _detect_isla_profundidad_question(brief, dual_result)
    if q_isla_prof:
        questions.append(q_isla_prof)
    q_isla_patas = _detect_isla_patas_question(brief, dual_result)
    if q_isla_patas:
        questions.append(q_isla_patas)
    q_zoc = _detect_zocalos_question(brief, dual_result)
    if q_zoc:
        questions.append(q_zoc)
    q_alz = _detect_alzada_question(brief, dual_result)
    if q_alz:
        questions.append(q_alz)
    q_coloc = _detect_colocacion_question(brief, dual_result)
    if q_coloc:
        questions.append(q_coloc)
    return questions


# ─────────────────────────────────────────────────────────────────────────────
# Answer applicator — materializa las respuestas del operador en el card
# ─────────────────────────────────────────────────────────────────────────────

def apply_zocalos_answer(dual_result: dict, answer: dict, default_alto_m: float = 0.07) -> dict:
    """Dada la respuesta del operador a la pregunta de zócalos, agrega
    los zócalos determinísticamente al card.

    `answer` formato (viene del frontend):
    {
      "id": "zocalos",
      "value": "default_trasero" | "custom" | "no",
      "detail": "texto libre si value == custom" (opcional),
      "alto_m": 0.07 (opcional, override del default),
    }

    Muta y devuelve dual_result in-place.
    """
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value == "no":
        # nada que agregar
        return dual_result

    alto = float(answer.get("alto_m") or default_alto_m)
    for sector in dual_result.get("sectores") or []:
        for tramo in sector.get("tramos") or []:
            largo = ((tramo.get("largo_m") or {}).get("valor")) or 0
            # Si el tramo ya tiene zócalos explícitos (de dual_read), no pisar
            has_existing = any(
                (z.get("ml") or 0) > 0 for z in (tramo.get("zocalos") or [])
            )
            if has_existing:
                continue
            if value == "default_trasero":
                tramo.setdefault("zocalos", []).append({
                    "lado": "trasero",
                    "ml": float(largo),
                    "alto_m": alto,
                    "status": "CONFIRMADO",
                    "opus_ml": None,
                    "sonnet_ml": None,
                    "source": "brief_rule",
                })
            elif value == "custom":
                # El detalle es texto libre — lo dejamos en metadata para
                # que Valentina o el operador lo lean post-confirm. No
                # inferimos lados automáticamente.
                tramo.setdefault("zocalos", []).append({
                    "lado": answer.get("detail", "trasero")[:50],
                    "ml": float(largo),
                    "alto_m": alto,
                    "status": "CONFIRMADO",
                    "opus_ml": None,
                    "sonnet_ml": None,
                    "source": "brief_rule_custom",
                    "detail_raw": answer.get("detail"),
                })
    return dual_result


def apply_pileta_type_answer(dual_result: dict, answer: dict) -> dict:
    """Aplica la respuesta del operador sobre pileta de cocina.

    Valores soportados:
    - "simple" / "doble" → cocina con pileta empotrada (regla D'Angelo,
      nunca apoyo), seteando basin_count.
    - "no" → sin pileta; seteamos flag para que el calculator no sume MO.
    """
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value not in ("simple", "doble", "no"):
        return dual_result

    for sector in dual_result.get("sectores") or []:
        if (sector.get("tipo") or "").lower() != "cocina":
            continue
        if value == "no":
            sector["pileta"] = None
            sector["pileta_type_hint"] = None
            sector["sink_type"] = None
        else:
            sector.setdefault("sink_type", {})
            sector["sink_type"]["basin_count"] = value
            sector["sink_type"].setdefault("mount_type", "abajo")
            sector["pileta_type_hint"] = "empotrada"
    return dual_result


def apply_isla_profundidad_answer(dual_result: dict, answer: dict) -> dict:
    """Setea ancho_m del tramo de isla con la profundidad elegida."""
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value in ("0.60", "0.70"):
        prof = float(value)
    elif value == "custom":
        try:
            prof = float(answer.get("detail") or 0)
        except (TypeError, ValueError):
            return dual_result
    else:
        return dual_result
    if prof <= 0 or prof > 5:
        return dual_result
    for sector in dual_result.get("sectores") or []:
        if (sector.get("tipo") or "").lower() != "isla":
            continue
        for tramo in sector.get("tramos") or []:
            tramo.setdefault("ancho_m", {})
            tramo["ancho_m"]["valor"] = prof
            tramo["ancho_m"]["status"] = "CONFIRMADO"
            tramo["ancho_m"]["source"] = "brief_rule"
            largo = (tramo.get("largo_m") or {}).get("valor") or 0
            tramo.setdefault("m2", {})
            tramo["m2"]["valor"] = round(float(largo) * prof, 2)
            tramo["m2"]["status"] = "CONFIRMADO"
    return dual_result


def apply_isla_patas_answer(dual_result: dict, answer: dict) -> dict:
    """Agrega metadata de patas al sector isla (frontal/laterales + alto)."""
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    side_map = {
        "frontal_y_ambos_laterales": ["frontal", "lateral_izq", "lateral_der"],
        "solo_frontal": ["frontal"],
        "solo_laterales": ["lateral_izq", "lateral_der"],
        "no": [],
    }
    sides: list[str]
    if value in side_map:
        sides = side_map[value]
    elif value == "custom":
        detail = str(answer.get("detail") or "")
        sides = [s.strip() for s in re.split(r"[,;/]", detail) if s.strip()]
    else:
        return dual_result
    try:
        alto = float(answer.get("alto_m") or 0.90)
    except (TypeError, ValueError):
        alto = 0.90
    for sector in dual_result.get("sectores") or []:
        if (sector.get("tipo") or "").lower() != "isla":
            continue
        sector["patas"] = {
            "sides": sides,
            "alto_m": alto,
            "source": "brief_rule",
            "detail_raw": answer.get("detail"),
        }
    return dual_result


def apply_colocacion_answer(dual_result: dict, answer: dict) -> dict:
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value not in ("si", "no"):
        return dual_result
    dual_result["colocacion"] = (value == "si")
    return dual_result


def apply_anafe_count_answer(dual_result: dict, answer: dict) -> dict:
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value == "0":
        count = 0
    elif value in ("1", "2"):
        count = int(value)
    elif value == "3":
        try:
            count = int(answer.get("detail") or 3)
        except (TypeError, ValueError):
            count = 3
    else:
        return dual_result
    dual_result["anafe"] = count > 0
    dual_result["anafe_qty"] = count
    return dual_result


def apply_isla_presence_answer(dual_result: dict, answer: dict) -> dict:
    """Si el operador dijo 'yes' → marcamos que hay isla (el calculator
    deberá pedir dimensiones en siguiente iteración). Si 'no' → removemos
    cualquier sector isla si existía."""
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value == "no":
        dual_result["sectores"] = [
            s for s in (dual_result.get("sectores") or [])
            if (s.get("tipo") or "").lower() != "isla"
        ]
        dual_result["isla_excluded_by_operator"] = True
    elif value == "yes":
        dual_result["isla_confirmed_by_operator"] = True
    return dual_result


def apply_alzada_answer(dual_result: dict, answer: dict) -> dict:
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value == "no":
        dual_result["alzada"] = False
        return dual_result
    try:
        alto_cm = int(value) if value in ("5", "10") else int(answer.get("detail") or 0)
    except (TypeError, ValueError):
        return dual_result
    if alto_cm <= 0:
        return dual_result
    dual_result["alzada"] = True
    dual_result["alzada_alto_m"] = alto_cm / 100.0
    return dual_result


def apply_answers(dual_result: dict, answers: list[dict]) -> dict:
    """Aplica todas las respuestas del operador al card. Dispatch por id."""
    # Import lazy para evitar ciclos
    from app.modules.quote_engine.required_fields import (
        apply_localidad_answer,
        apply_material_answer,
    )
    for ans in answers or []:
        qid = ans.get("id")
        if qid == "zocalos":
            apply_zocalos_answer(dual_result, ans)
        elif qid == "pileta_simple_doble":
            apply_pileta_type_answer(dual_result, ans)
        elif qid == "isla_presence":
            apply_isla_presence_answer(dual_result, ans)
        elif qid == "isla_profundidad":
            apply_isla_profundidad_answer(dual_result, ans)
        elif qid == "isla_patas":
            apply_isla_patas_answer(dual_result, ans)
        elif qid == "colocacion":
            apply_colocacion_answer(dual_result, ans)
        elif qid == "anafe_count":
            apply_anafe_count_answer(dual_result, ans)
        elif qid == "alzada":
            apply_alzada_answer(dual_result, ans)
        elif qid == "material":
            apply_material_answer(dual_result, ans)
        elif qid == "localidad":
            apply_localidad_answer(dual_result, ans)
    return dual_result
