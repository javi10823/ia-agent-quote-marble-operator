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


def _detect_pileta_type_question(brief: str, dual_result: dict) -> dict | None:
    """En sector COCINA, pileta siempre es empotrada (regla D'Angelo).
    Lo único que puede variar es simple vs doble.

    Preguntamos SOLO si:
    - Hay sector cocina
    - Hay pileta detectada en la card o mencionada en el brief
    - El brief no dijo explícitamente simple ni doble
    - La card no tiene sink_double feature concluyente

    No se pregunta apoyo/empotrada nunca en cocina — es siempre empotrada."""
    if not _has_sector_type(dual_result, "cocina"):
        return None

    brief = brief or ""
    brief_mentions_pileta = bool(re.search(r"\b(pileta|bacha)\b", brief, re.IGNORECASE))
    has_pileta_card = _has_pileta_in_card(dual_result)
    if not (brief_mentions_pileta or has_pileta_card):
        return None

    # Si el operador ya especificó simple o doble, no preguntamos
    if _PILETA_DOBLE.search(brief) or _PILETA_SIMPLE.search(brief):
        return None

    # Si la card ya tiene sink_double definido con confianza, no preguntamos
    for s in dual_result.get("sectores") or []:
        for t in s.get("tramos") or []:
            features = t.get("features") or {}
            if features.get("sink_double") is not None:
                return None

    return {
        "id": "pileta_simple_doble",
        "label": "Tipo de pileta",
        "question": (
            "¿La pileta es simple o doble? En cocina siempre va empotrada "
            "(PEGADOPILETA), pero cambia el cálculo según la cantidad de bachas."
        ),
        "type": "radio_with_detail",
        "options": [
            {
                "value": "simple",
                "label": "Simple (1 bacha)",
                "apply": {"sink_type": {"basin_count": "simple", "mount_type": "abajo"}},
            },
            {
                "value": "doble",
                "label": "Doble (2 bachas contiguas)",
                "apply": {"sink_type": {"basin_count": "doble", "mount_type": "abajo"}},
            },
        ],
    }


def _detect_isla_profundidad_question(brief: str, dual_result: dict) -> dict | None:
    """Isla sin cota de profundidad → preguntar. Nunca asumir 0.60 silencioso.

    Dispara cuando:
    - Hay sector isla.
    - El tramo de isla tiene ancho_m con status DUDOSO/UNANCHORED o valor
      igual al largo (fallback silencioso del VLM).
    """
    if not _has_sector_type(dual_result, "isla"):
        return None
    for s in dual_result.get("sectores") or []:
        if (s.get("tipo") or "").lower() != "isla":
            continue
        for t in s.get("tramos") or []:
            ancho = t.get("ancho_m") or {}
            status = ancho.get("status", "")
            val = ancho.get("valor")
            largo = (t.get("largo_m") or {}).get("valor")
            if status in ("DUDOSO", "UNANCHORED") or (
                val is not None and largo is not None and abs(float(val) - float(largo)) < 0.01
            ):
                return {
                    "id": "isla_profundidad",
                    "label": "Profundidad de la isla",
                    "question": (
                        "¿Cuál es la profundidad (ancho) de la isla? El plano no la "
                        "muestra explícita — no queremos asumir."
                    ),
                    "type": "radio_with_detail",
                    "options": [
                        {"value": "0.60", "label": "0.60 m (estándar residencial)"},
                        {"value": "0.70", "label": "0.70 m"},
                        {"value": "custom", "label": "Otra medida (detallar)"},
                    ],
                    "detail_placeholder": "Ej: 0.80",
                }
    return None


def _detect_isla_patas_question(brief: str, dual_result: dict) -> dict | None:
    """Isla → preguntar si lleva patas (frontal + ambos laterales) y alto.
    Siempre preguntar — no hay default razonable y afecta la cotización."""
    if not _has_sector_type(dual_result, "isla"):
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
    """Si la card detectó múltiples anafes o el brief sugiere >1 pero no está
    claro, preguntar confirmación."""
    # Hay sector cocina con features.anafe_count >= 2 o multiple_anafe hint
    b = brief or ""
    if _ANAFE_COUNT_EXPLICIT.search(b):
        return None

    has_multi_hint = _ANAFE_DUAL.search(b) is not None
    card_count = 0
    for s in dual_result.get("sectores") or []:
        for t in s.get("tramos") or []:
            features = t.get("features") or {}
            card_count = max(card_count, int(features.get("cooktop_groups") or 0))

    if not (has_multi_hint or card_count >= 2):
        return None

    return {
        "id": "anafe_count",
        "label": "Cantidad de anafes",
        "question": (
            "¿Cuántos anafes lleva? Detectamos señales de más de uno "
            "(típicamente gas + eléctrico). Cada anafe empotrado suma MO."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "1", "label": "1 anafe"},
            {"value": "2", "label": "2 anafes (ej: gas + eléctrico)"},
            {"value": "3", "label": "3+ anafes (detallar)"},
            {"value": "0", "label": "No hay anafe empotrado"},
        ],
        "detail_placeholder": "Si son 3+: cuántos",
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
    # Son bloqueantes para cualquier cálculo — van primero.
    try:
        from app.modules.quote_engine.required_fields import detect_required_field_questions
        questions.extend(detect_required_field_questions(brief, quote, dual_result))
    except Exception:
        pass
    # Detectores específicos (PR B/C/D).
    q_anafe = _detect_anafe_count_question(brief, dual_result)
    if q_anafe:
        questions.append(q_anafe)
    q_pileta = _detect_pileta_type_question(brief, dual_result)
    if q_pileta:
        questions.append(q_pileta)
    q_isla_prof = _detect_isla_profundidad_question(brief, dual_result)
    if q_isla_prof:
        questions.append(q_isla_prof)
    q_isla_patas = _detect_isla_patas_question(brief, dual_result)
    if q_isla_patas:
        questions.append(q_isla_patas)
    q_zoc = _detect_zocalos_question(brief, dual_result)
    if q_zoc:
        questions.append(q_zoc)
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
    """Aplica la respuesta simple/doble al sector cocina. Siempre empotrada
    (regla D'Angelo). Si el brief menciona Johnson, usa empotrada_johnson;
    si no, empotrada_cliente.
    """
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    if value not in ("simple", "doble"):
        return dual_result

    # Guardamos la decisión en sector.pileta para que el calculator la use.
    for sector in dual_result.get("sectores") or []:
        if (sector.get("tipo") or "").lower() != "cocina":
            continue
        sector.setdefault("sink_type", {})
        sector["sink_type"]["basin_count"] = value
        sector["sink_type"].setdefault("mount_type", "abajo")
        # Hint para Valentina: pileta empotrada (nunca apoyo en cocina)
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
        elif qid == "isla_profundidad":
            apply_isla_profundidad_answer(dual_result, ans)
        elif qid == "isla_patas":
            apply_isla_patas_answer(dual_result, ans)
        elif qid == "colocacion":
            apply_colocacion_answer(dual_result, ans)
        elif qid == "anafe_count":
            apply_anafe_count_answer(dual_result, ans)
        elif qid == "material":
            apply_material_answer(dual_result, ans)
        elif qid == "localidad":
            apply_localidad_answer(dual_result, ans)
    return dual_result
