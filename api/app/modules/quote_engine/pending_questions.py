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

def detect_pending_questions(brief: str, dual_result: dict) -> list[dict]:
    """Devuelve la lista de preguntas pendientes. Vacía si todos los datos
    detectables están presentes.

    Cada detector corre independiente — si uno falla o no aplica, los otros
    siguen. Orden de la lista = orden de presentación en la UI (primero lo
    más crítico).
    """
    questions: list[dict] = []
    q_zoc = _detect_zocalos_question(brief, dual_result)
    if q_zoc:
        questions.append(q_zoc)
    q_pileta = _detect_pileta_type_question(brief, dual_result)
    if q_pileta:
        questions.append(q_pileta)
    # Futuros detectores (PR D):
    # - profundidad isla si no hay cota
    # - patas isla (frontal + laterales)
    # - colocación
    # - anafe count
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


def apply_answers(dual_result: dict, answers: list[dict]) -> dict:
    """Aplica todas las respuestas del operador al card. Extensible por
    question_id. Hoy: `zocalos` + `pileta_simple_doble`."""
    for ans in answers or []:
        qid = ans.get("id")
        if qid == "zocalos":
            apply_zocalos_answer(dual_result, ans)
        elif qid == "pileta_simple_doble":
            apply_pileta_type_answer(dual_result, ans)
    return dual_result
