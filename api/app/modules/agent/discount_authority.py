"""Autoridad sobre los descuentos comerciales: los decide el operador, no el LLM.

El LLM puede pasar `discount_pct` / `mo_discount_pct` a calculate_quote, y un
valor pasado le gana a los descuentos automáticos (arquitecta, edificio,
cantidad). Sin control, un porcentaje inventado llega al precio final.

Regla: un descuento del LLM solo se acepta si ese porcentaje figura en lo que
escribió el operador (o ya estaba en el cálculo guardado). Si no, se descarta
y se avisa. Si el operador pide sacar el descuento, se anula y no se reinyecta.
Función pura: sin DB ni LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_PCT = 1
MAX_PCT = 50

_NUM = r"(\d{1,2}(?:[.,]\d+)?)"
# "descuento 10%", "desc. del 10 %", "dto 5%"
_SYM = r"(?:%|por\s*ciento)"
_PCT_AFTER = re.compile(
    rf"\b(?:descuento|desc|dto)\b\.?[^\n.%]{{0,40}}?{_NUM}\s*{_SYM}", re.IGNORECASE
)
# "10% de descuento", "5 % dto"
_PCT_BEFORE = re.compile(
    rf"{_NUM}\s*{_SYM}[^\n.%]{{0,40}}?\b(?:descuento|desc|dto)\b", re.IGNORECASE
)
_REMOVE = re.compile(
    r"\b(?:sin|quit[aá](?:r|le)?|sac[aá](?:r|le)?|elimin[aá](?:r|le)?|borr[aá](?:r|le)?|"
    r"cancel[aá](?:r)?|no\s+(?:hay|lleva|va|aplica|aplicar|corresponde))\s+"
    r"(?:el\s+|ning[uú]n\s+|m[aá]s\s+|ese\s+|este\s+)?(?:descuento|dto)\b",
    re.IGNORECASE,
)


def stated_percentages(text: str) -> set[float]:
    """Porcentajes que el operador asoció a la palabra descuento."""
    found: set[float] = set()
    for rx in (_PCT_AFTER, _PCT_BEFORE):
        for m in rx.finditer(text or ""):
            try:
                found.add(float(m.group(1).replace(",", ".")))
            except ValueError:
                continue
    return found


def wants_discount_removed(message: str) -> bool:
    return bool(_REMOVE.search(message or ""))


@dataclass
class DiscountDecision:
    discount_pct: float = 0
    mo_discount_pct: float = 0
    # (campo, valor, motivo): descuentos del LLM que NO se aplicaron.
    rejected: list[tuple[str, float, str]] = field(default_factory=list)
    removed: bool = False

    def warnings(self) -> list[str]:
        out = []
        for name, value, why in self.rejected:
            label = "descuento sobre material" if name == "discount_pct" else "descuento sobre MO"
            out.append(
                f"No se aplicó el {label} de {value:g}%: {why}. "
                "Si corresponde, indicá el porcentaje en el mensaje."
            )
        return out


def _clean(value) -> float:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def authorize_discounts(
    llm_discount_pct,
    llm_mo_discount_pct,
    operator_text: str,
    current_message: str,
    persisted: set[float] | None = None,
) -> DiscountDecision:
    """Decide qué descuentos del LLM se aceptan.

    `operator_text`: todo lo que escribió el operador en la conversación.
    `current_message`: su último mensaje (para detectar "sacá el descuento").
    `persisted`: porcentajes que ya estaban en el cálculo guardado.
    Un descuento no aceptado queda en 0: calculate_quote cae en las reglas
    automáticas (arquitecta, edificio, cantidad)."""
    decision = DiscountDecision()
    if wants_discount_removed(current_message):
        decision.removed = True
        return decision

    evidence = stated_percentages(operator_text) | set(persisted or ())
    for name, raw in (("discount_pct", llm_discount_pct), ("mo_discount_pct", llm_mo_discount_pct)):
        value = _clean(raw)
        if not value:
            continue
        if not (MIN_PCT <= value <= MAX_PCT):
            decision.rejected.append((name, value, f"fuera del rango {MIN_PCT}-{MAX_PCT}%"))
        elif value not in evidence:
            decision.rejected.append((name, value, "no figura en lo que pidió el operador"))
        else:
            setattr(decision, name, value)
    return decision
