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

# PR #392 — frentín (faldón) y regrueso.
#
# Regla de skip (criterio del operador, 2026-04-24):
#   "skip solo cuando ya podés poblar tramo.frentin[] / tramo.regrueso[]
#    sin inventar nada. Si falta alto o lados, preguntar."
#
# Por eso _FRENTIN_ALTO matchea cuando hay un **valor numérico explícito**
# (ej: "frentín de 5cm", "faldón 10 cm"). Mención vaga ("con frentín") NO
# matchea → el operador igual tiene que confirmar alto en la card.
# _FRENTIN_NO matchea "sin frentín" / "no lleva frentín" → skip directo,
# el despiece queda sin items de frentín.
_FRENTIN_ALTO = re.compile(
    r"\b(?:frent[ií]n|fald[oó]n)\s+(?:de\s+)?(\d+)\s*cm",
    re.IGNORECASE,
)
_FRENTIN_NO = re.compile(
    r"\bsin\s+(?:frent[ií]n|fald[oó]n)|no\s+(?:lleva|va)\s+(?:frent[ií]n|fald[oó]n)",
    re.IGNORECASE,
)
_REGRUESO_ALTO = re.compile(
    r"\bregrueso\s+(?:de\s+)?(\d+)\s*cm",
    re.IGNORECASE,
)
_REGRUESO_NO = re.compile(
    r"\bsin\s+regrueso|no\s+(?:lleva|va)\s+regrueso",
    re.IGNORECASE,
)


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


def _detect_isla_profundidad_question(
    brief: str, dual_result: dict, *, force: bool = False,
) -> dict | None:
    """Isla → SIEMPRE preguntar profundidad (nunca asumir). Dispara si
    dual_read detectó isla, brief la menciona, o `force=True` (cuando la
    pregunta de presencia fire y necesitamos el detalle pre-emitido).

    Skip solo si el brief da el valor explícito (ej: "isla de 0.80",
    "profundidad isla X").
    """
    has_isla = (
        force
        or _has_sector_type(dual_result, "isla")
        or _brief_mentions_isla(brief)
    )
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


def _detect_isla_patas_question(
    brief: str, dual_result: dict, *, force: bool = False,
) -> dict | None:
    """Isla → preguntar si lleva patas (frontal + ambos laterales) y alto.
    Siempre preguntar — no hay default razonable y afecta la cotización.
    Dispara si dual_read detectó isla, brief la menciona, o `force=True`."""
    has_isla = (
        force
        or _has_sector_type(dual_result, "isla")
        or _brief_mentions_isla(brief)
    )
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


def _detect_isla_patas_alto_question(
    brief: str, dual_result: dict, *, force: bool = False,
) -> dict | None:
    """Isla con patas → preguntar el alto (piso a mesada). Default 0.90m es
    razonable pero NO silencioso — el operador lo confirma. Skip si brief ya
    da el valor explícito (raro).

    Frontend oculta esta pregunta cuando la respuesta a `isla_patas` es "no"
    (cascada isla_presence → isla_patas → isla_patas_alto).
    """
    has_isla = (
        force
        or _has_sector_type(dual_result, "isla")
        or _brief_mentions_isla(brief)
    )
    if not has_isla:
        return None
    if brief:
        if re.search(r"\balto\s+(de\s+)?patas?\s*[=:]?\s*\d", brief, re.IGNORECASE):
            return None
        if re.search(r"\bpatas?\s+(de\s+)?\d+[,.]\d\s*m\b", brief, re.IGNORECASE):
            return None
    return {
        "id": "isla_patas_alto",
        "label": "Alto de las patas",
        "question": (
            "¿De qué alto son las patas? Es la distancia del piso al borde "
            "inferior de la mesada."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "0.90", "label": "0.90 m (estándar — piso a mesada)"},
            {"value": "0.85", "label": "0.85 m"},
            {"value": "0.80", "label": "0.80 m"},
            {"value": "custom", "label": "Otra medida (detallar)"},
        ],
        "detail_placeholder": "Ej: 0.75",
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


def _has_non_isla_sector(dual_result: dict) -> bool:
    """True si el despiece tiene al menos un sector que NO es isla.
    La alzada solo tiene sentido en sectores apoyados contra pared
    (cocina, baño, lavadero) — la isla es central sin pared de fondo.
    """
    for s in dual_result.get("sectores") or []:
        tipo = (s.get("tipo") or "").lower()
        if tipo and tipo != "isla":
            return True
    return False


def _detect_alzada_question(brief: str, dual_result: dict) -> dict | None:
    """Alzada: típicamente el operador la olvida o no está en el plano.

    PR #388 — se pregunta para cualquier trabajo con al menos un sector
    NO-isla (cocina, baño, lavadero). Antes el gate era `_is_cocina_work`
    que dejaba afuera baños y lavaderos puros — se omitía la pregunta
    aunque pudieran llevar alzada.

    Skip cuando:
    - El único sector detectado es isla (no tiene pared de fondo).
    - El dual_read está vacío y el brief no menciona cocina (fallback
      conservador — no preguntar a ciegas).
    - El brief ya menciona alzada explícitamente (con/sin/alto).
    """
    b = brief or ""
    has_non_isla = _has_non_isla_sector(dual_result)
    # Si no hay sectores detectados, caer al legacy gate (brief cocina o
    # sectores vacíos sin evidencia de baño/lavadero).
    if not has_non_isla and not _is_cocina_work(dual_result, b):
        return None
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


# ─────────────────────────────────────────────────────────────────────
# PR #392 — Frentín / faldón y regrueso: preguntas + apply
# ─────────────────────────────────────────────────────────────────────
#
# Antes no existían en el flow de contexto. El brief_analyzer solo
# capturaba boolean `frentin_mentioned` / `regrueso_mentioned` y el
# context_analyzer los volcaba como assumption "Mencionado" sin
# dimensiones. Resultado: Claude tenía que inventar alto y lados en
# Paso 2, o directamente omitirlos si el brief no los mencionaba.
#
# Este PR cierra el loop:
#   - Pregunta siempre que haya al menos un tramo de mesada en el
#     dual_read, salvo que el brief traiga valor operativo (ver regla
#     de skip arriba en los regex).
#   - Apply answer llena `tramo.frentin[]` / `tramo.regrueso[]` con
#     shape `{lado, ml, alto_m}`. Usa `ml = tramo.largo_m.valor` y
#     `lado = "frente"` (D1/D2 del plan). Custom vía detail parseable.
#   - Skip tramos `_derived:true` (patas de isla, alzada) — esos no
#     llevan frentín/regrueso propios, ya son piezas derivadas.
#   - Consumer: `build_verified_context` (post-#387) ya renderiza los
#     items bajo `SECTOR: X`. Claude los ve con alto exacto y no
#     inventa.


def _has_any_tramo(dual_result: dict) -> bool:
    """True si hay al menos un tramo de mesada (no-derivado) en el
    dual_read. Gate de las preguntas de frentín/regrueso — si no hay
    despiece sobre el cual aplicarlos, no preguntamos."""
    for s in dual_result.get("sectores") or []:
        for t in s.get("tramos") or []:
            if not t.get("_derived"):
                return True
    return False


def _detect_frentin_question(brief: str, dual_result: dict) -> dict | None:
    """Frentín / faldón: pieza vertical que baja por el frente de la mesada.

    Skip (brief con valor operativo):
      - "sin frentín" / "sin faldón" / "no lleva frentín" → `_FRENTIN_NO`.
      - "frentín de 5 cm" / "faldón 10cm" → `_FRENTIN_ALTO`.

    Mención vaga ("con frentín" sin cm) → igual se pregunta para que el
    operador confirme alto/lados.

    Skip también cuando no hay ningún tramo en el dual_read (no hay
    mesada sobre la cual aplicar).
    """
    b = brief or ""
    if _FRENTIN_NO.search(b):
        return None
    if _FRENTIN_ALTO.search(b):
        return None
    if not _has_any_tramo(dual_result):
        return None
    return {
        "id": "frentin",
        "label": "Frentín / Faldón",
        "question": (
            "¿Lleva frentín o faldón? (tira vertical que baja por el "
            "frente de la mesada)"
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "no", "label": "No lleva"},
            {"value": "3", "label": "Sí — 3 cm frente"},
            {"value": "5", "label": "Sí — 5 cm frente"},
            {"value": "10", "label": "Sí — 10 cm frente"},
            {"value": "custom", "label": "Sí — otro alto o lados (detallar)"},
        ],
        "detail_placeholder": "Ej: 7 cm, frente y lateral izq",
    }


def _detect_regrueso_question(brief: str, dual_result: dict) -> dict | None:
    """Regrueso: refuerzo de espesor en el frente visible de la mesada.
    Mismo patrón de skip que frentín."""
    b = brief or ""
    if _REGRUESO_NO.search(b):
        return None
    if _REGRUESO_ALTO.search(b):
        return None
    if not _has_any_tramo(dual_result):
        return None
    return {
        "id": "regrueso",
        "label": "Regrueso",
        "question": (
            "¿Lleva regrueso? (refuerzo de espesor en los frentes "
            "visibles de la mesada)"
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "no", "label": "No lleva"},
            {"value": "2", "label": "Sí — 2 cm"},
            {"value": "3", "label": "Sí — 3 cm"},
            {"value": "5", "label": "Sí — 5 cm"},
            {"value": "custom", "label": "Sí — otro alto o lados (detallar)"},
        ],
        "detail_placeholder": "Ej: 4 cm, frente y lateral",
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

    # Bloque isla: si puede haber isla (detectada / mencionada en brief / no
    # negada), emitimos las 3 preguntas juntas. La UI oculta/relaja las
    # dependientes (profundidad + patas) cuando el operador responde "no"
    # a la pregunta de presencia.
    q_isla_presence = _detect_isla_presence_question(brief, dual_result)
    isla_possible = (
        _has_sector_type(dual_result, "isla")
        or _brief_mentions_isla(brief)
        or q_isla_presence is not None
    )
    if q_isla_presence:
        questions.append(q_isla_presence)
    if isla_possible:
        q_isla_prof = _detect_isla_profundidad_question(brief, dual_result, force=True)
        if q_isla_prof:
            questions.append(q_isla_prof)
        q_isla_patas = _detect_isla_patas_question(brief, dual_result, force=True)
        if q_isla_patas:
            questions.append(q_isla_patas)
        q_isla_patas_alto = _detect_isla_patas_alto_question(brief, dual_result, force=True)
        if q_isla_patas_alto:
            questions.append(q_isla_patas_alto)

    q_zoc = _detect_zocalos_question(brief, dual_result)
    if q_zoc:
        questions.append(q_zoc)
    q_alz = _detect_alzada_question(brief, dual_result)
    if q_alz:
        questions.append(q_alz)
    # PR #392 — frentín y regrueso, siempre con gate de brief explícito.
    # Aparecen después de alzada porque son trabajos menos frecuentes —
    # mantener alzada cerca de zócalos (decisiones core del despiece).
    q_frentin = _detect_frentin_question(brief, dual_result)
    if q_frentin:
        questions.append(q_frentin)
    q_regrueso = _detect_regrueso_question(brief, dual_result)
    if q_regrueso:
        questions.append(q_regrueso)
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
    """Setea ancho_m del tramo de isla con la profundidad elegida.

    Busca tramos de isla en 2 lugares (en este orden):
      1. Sectores con `tipo == "isla"` (caso canónico).
      2. Tramos cuya descripción contenga "isla" dentro de cualquier
         sector (común en cocinas L + isla donde el dual_read lumps
         todo en un solo sector tipo "L" / "cocina").

    Antes sólo miraba (1) — si el plano no tenía un sector isla
    separado, el 0.60 que respondía el operador no se aplicaba y el
    despiece quedaba con la medida original (1.20 u otro valor).
    """
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value in ("0.60", "0.70", "0.80", "0.90", "1.00"):
        prof = float(value)
    elif value == "custom":
        try:
            prof = float(answer.get("detail") or 0)
        except (TypeError, ValueError):
            return dual_result
    else:
        try:
            prof = float(value)  # last resort: si el value es un número crudo
        except (TypeError, ValueError):
            return dual_result
    if prof <= 0 or prof > 5:
        return dual_result

    def _update_tramo(tramo: dict) -> None:
        tramo.setdefault("ancho_m", {})
        tramo["ancho_m"]["valor"] = prof
        tramo["ancho_m"]["status"] = "CONFIRMADO"
        tramo["ancho_m"]["source"] = "brief_rule"
        largo = (tramo.get("largo_m") or {}).get("valor") or 0
        tramo.setdefault("m2", {})
        tramo["m2"]["valor"] = round(float(largo) * prof, 2)
        tramo["m2"]["status"] = "CONFIRMADO"

    updated_any = False
    for sector in dual_result.get("sectores") or []:
        if (sector.get("tipo") or "").lower() == "isla":
            for tramo in sector.get("tramos") or []:
                _update_tramo(tramo)
                updated_any = True

    # Fallback: buscar tramos "isla" en sectores non-isla (cocina L + isla
    # lumped juntos). Solo si no actualizamos nada en el loop anterior —
    # para no pisar dos veces si el plano tiene ambos formatos.
    if not updated_any:
        for sector in dual_result.get("sectores") or []:
            if (sector.get("tipo") or "").lower() == "isla":
                continue
            for tramo in sector.get("tramos") or []:
                desc = (tramo.get("descripcion") or "").lower()
                feats = tramo.get("features") or {}
                is_isla_tramo = (
                    "isla" in desc
                    or feats.get("is_island")
                    or feats.get("isla")
                )
                if is_isla_tramo:
                    _update_tramo(tramo)
                    updated_any = True

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


def apply_isla_patas_alto_answer(dual_result: dict, answer: dict) -> dict:
    """Setea el alto de las patas de la isla. Convive con apply_isla_patas_answer:
    patas sets sides+default alto, este pisa alto con el valor real.

    Idempotente — si la sección `patas` no existía (patas=no), no hace nada."""
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value in ("0.90", "0.85", "0.80"):
        alto = float(value)
    elif value == "custom":
        try:
            alto = float(answer.get("detail") or 0)
        except (TypeError, ValueError):
            return dual_result
    else:
        return dual_result
    if alto <= 0 or alto > 5:
        return dual_result
    for sector in dual_result.get("sectores") or []:
        if (sector.get("tipo") or "").lower() != "isla":
            continue
        patas = sector.get("patas")
        if not patas or not patas.get("sides"):
            continue  # no lleva patas → alto no aplica
        patas["alto_m"] = alto
        patas["alto_source"] = "operator"
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


# ─────────────────────────────────────────────────────────────────────
# PR #392 — apply frentín / regrueso
# ─────────────────────────────────────────────────────────────────────
#
# Shape estable (coherente con zócalos, consumido por
# `build_verified_context` post-#387):
#     tramo["frentin"] = [{"lado": "frente", "ml": <float>, "alto_m": <float>}]
#     tramo["regrueso"] = [...]
#
# Default de lados = "frente" para presets (D1/D2 acordados con operador).
# Custom permite que el detail especifique lados extra — parsing simple
# por keywords; si el parse falla, cae a solo "frente" con el alto
# detectado.
#
# Idempotencia: cada apply REEMPLAZA la lista (no append). Si el
# operador reconfirma, no duplica items.
#
# Skip tramos `_derived:true` — las patas de isla y alzadas ya son
# piezas verticales por su propia cuenta, no llevan frentín propio.


_CUSTOM_ALTO_CM = re.compile(r"(\d+(?:[.,]\d+)?)\s*cm", re.IGNORECASE)
_CUSTOM_LADOS_MAP = {
    "frente":       "frente",
    "frontal":      "frente",
    "adelante":     "frente",
    "lateral izq":  "lateral_izq",
    "lateral izquierdo": "lateral_izq",
    "lado izq":     "lateral_izq",
    "izquierdo":    "lateral_izq",
    "izq":          "lateral_izq",
    "lateral der":  "lateral_der",
    "lateral derecho": "lateral_der",
    "lado der":     "lateral_der",
    "derecho":      "lateral_der",
    "der":          "lateral_der",
    "trasero":      "trasero",
    "atras":        "trasero",
    "atrás":        "trasero",
}


def _parse_custom_frentin_regrueso(detail: str) -> tuple[float | None, list[str]]:
    """Parsea `detail` de custom respuesta → (alto_m, lados).

    Reconoce:
      - alto numérico "N cm" / "N.N cm" → alto_m.
      - keywords de lados: "frente", "lateral izq", "trasero", etc.

    Si no detecta ningún lado → ["frente"] (default consistente con
    los presets). Si no detecta alto → alto_m None (caller maneja).
    """
    alto_m: float | None = None
    d = (detail or "").lower()
    m = _CUSTOM_ALTO_CM.search(d)
    if m:
        try:
            alto_m = float(m.group(1).replace(",", ".")) / 100.0
        except ValueError:
            alto_m = None

    lados: list[str] = []
    for kw, lado in _CUSTOM_LADOS_MAP.items():
        if kw in d and lado not in lados:
            lados.append(lado)
    if not lados:
        lados = ["frente"]
    return alto_m, lados


def _tramo_largo(tramo: dict) -> float:
    """Extrae `largo_m.valor` (dict FieldValue) o `largo_m` crudo. 0 si falta."""
    largo = tramo.get("largo_m")
    if isinstance(largo, dict):
        v = largo.get("valor")
    else:
        v = largo
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _tramo_ancho(tramo: dict) -> float:
    """Extrae `ancho_m.valor` del tramo — usado como ml cuando el lado
    es lateral (los laterales corren por la profundidad de la mesada,
    no por el largo)."""
    ancho = tramo.get("ancho_m")
    if isinstance(ancho, dict):
        v = ancho.get("valor")
    else:
        v = ancho
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _ml_for_lado(tramo: dict, lado: str) -> float:
    """ML del item según el lado:
      - frente/trasero → corre por el largo de la mesada.
      - lateral_izq/der → corre por la profundidad (ancho).
    """
    if lado in ("lateral_izq", "lateral_der"):
        return _tramo_ancho(tramo)
    return _tramo_largo(tramo)


def _build_items_for_lados(tramo: dict, lados: list[str], alto_m: float) -> list[dict]:
    """Arma la lista de items `{lado, ml, alto_m}` para un tramo
    dado, descartando los que quedan con ml=0."""
    items: list[dict] = []
    for lado in lados:
        ml = _ml_for_lado(tramo, lado)
        if ml <= 0:
            continue
        items.append({
            "lado": lado,
            "ml": round(ml, 2),
            "alto_m": round(float(alto_m), 3),
        })
    return items


def _apply_extra_pieces_answer(
    dual_result: dict,
    answer: dict,
    *,
    field: str,
    preset_values: set[str],
) -> dict:
    """Helper común para frentín y regrueso. La diferencia entre ellos
    es solo el nombre del field (`frentin` / `regrueso`) y los valores
    preset aceptados — todo lo demás es idéntico."""
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")

    # "no" → limpiar el field en todos los tramos.
    if value == "no":
        for sector in dual_result.get("sectores") or []:
            for tramo in sector.get("tramos") or []:
                tramo[field] = []
        return dual_result

    # Determinar alto_m + lados.
    alto_m: float | None = None
    lados: list[str] = ["frente"]
    if value in preset_values:
        try:
            alto_m = int(value) / 100.0
        except (TypeError, ValueError):
            alto_m = None
    elif value == "custom":
        alto_m, lados = _parse_custom_frentin_regrueso(answer.get("detail") or "")
    else:
        # value desconocido → no aplicar, preservar estado actual.
        return dual_result

    if alto_m is None or alto_m <= 0:
        return dual_result

    # Aplicar a cada tramo no-derivado del dual_read. Reemplazo total
    # del field (idempotente: reconfirmar no duplica).
    for sector in dual_result.get("sectores") or []:
        for tramo in sector.get("tramos") or []:
            if tramo.get("_derived"):
                # Piezas derivadas (patas, alzadas) no llevan frentín/regrueso
                # propio — skipear y preservar lo que tengan.
                continue
            tramo[field] = _build_items_for_lados(tramo, lados, alto_m)
    return dual_result


def apply_frentin_answer(dual_result: dict, answer: dict) -> dict:
    """Aplica respuesta de `frentin` al dual_read. Escribe `tramo.frentin[]`
    en cada tramo no-derivado según los lados elegidos.

    `answer` shape:
        {
          "id": "frentin",
          "value": "no" | "3" | "5" | "10" | "custom",
          "detail": "texto libre (solo para custom)"
        }
    """
    return _apply_extra_pieces_answer(
        dual_result, answer,
        field="frentin",
        preset_values={"3", "5", "10"},
    )


def apply_regrueso_answer(dual_result: dict, answer: dict) -> dict:
    """Aplica respuesta de `regrueso` al dual_read. Shape idéntico a
    frentín con otros presets."""
    return _apply_extra_pieces_answer(
        dual_result, answer,
        field="regrueso",
        preset_values={"2", "3", "5"},
    )


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
        elif qid == "isla_patas_alto":
            apply_isla_patas_alto_answer(dual_result, ans)
        elif qid == "isla_patas":
            apply_isla_patas_answer(dual_result, ans)
        elif qid == "colocacion":
            apply_colocacion_answer(dual_result, ans)
        elif qid == "anafe_count":
            apply_anafe_count_answer(dual_result, ans)
        elif qid == "alzada":
            apply_alzada_answer(dual_result, ans)
        elif qid == "frentin":
            # PR #392
            apply_frentin_answer(dual_result, ans)
        elif qid == "regrueso":
            # PR #392
            apply_regrueso_answer(dual_result, ans)
        elif qid == "material":
            apply_material_answer(dual_result, ans)
        elif qid == "localidad":
            apply_localidad_answer(dual_result, ans)
    return dual_result
