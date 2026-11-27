"""`is_edificio` lo decide el operador, no el LLM.

Con is_edificio=True el calculador cambia el precio: sin colocación, MO ÷1.05,
18 % de descuento (≥15 m²), otra merma y otros fletes. Un True inventado
corrompe el presupuesto, y la vista del operador todavía no muestra cálculos de
edificio. Se acepta solo si el operador lo dijo o ya estaba marcado así en el
cálculo guardado. Función pura.
"""
from __future__ import annotations

import re

# Señales fuertes. A propósito NO están "planos", "cocinas" ni "unidades":
# aparecen en cualquier brief de una cocina particular.
_STRONG = re.compile(
    r"\b(?:edificios?|torres?|departamentos?|consorcios?|constructora|fideicomiso|"
    r"obra\s+nueva|tipolog[ií]as?|building)\b",
    re.IGNORECASE,
)
_EXPLICIT = re.compile(
    r"\b(?:es\s+(?:un\s+)?edificio|es\s+(?:una\s+)?obra|obra\s+padre|modo\s+(?:edificio|obra)|"
    r"trat[aá]lo\s+como\s+(?:edificio|obra))\b",
    re.IGNORECASE,
)
_NOT_EDIFICIO = re.compile(
    r"\b(?:no\s+es\s+(?:un\s+)?edificio|particular|casa\s+de\s+familia|vivienda\s+particular)\b",
    re.IGNORECASE,
)


def operator_says_edificio(text: str) -> bool:
    return bool(_STRONG.search(text or "") or _EXPLICIT.search(text or ""))


def authorize_is_edificio(
    llm_value, operator_text: str, persisted: bool
) -> tuple[bool, str | None]:
    """Devuelve (valor a usar, aviso). El LLM no promueve a edificio solo."""
    if not llm_value:
        # Promoción solo con una orden explícita del operador.
        if _EXPLICIT.search(operator_text or "") and not _NOT_EDIFICIO.search(operator_text or ""):
            return True, None
        return False, None
    if persisted or operator_says_edificio(operator_text):
        if _NOT_EDIFICIO.search(operator_text or "") and not persisted and not _EXPLICIT.search(operator_text or ""):
            # Dice "edificio" pero también "particular": ambiguo → no promover.
            return False, (
                "Se cotizó como obra particular: el pedido menciona edificio y particular a la vez. "
                "Si es un edificio, decilo explícito (\"es edificio\")."
            )
        return True, None
    return False, (
        "Se cotizó como obra particular: nada en el pedido indica que sea un edificio. "
        "Si lo es, decilo explícito (\"es edificio\")."
    )
