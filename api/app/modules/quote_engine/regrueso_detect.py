"""Detección de piezas regrueso en piece_details.

**Por qué este módulo existe (PR #419):**

El #417 introdujo un double-count del m² del regrueso cuando el operador
declaraba las piezas "frente regrueso" en el despiece (caso DYSCON):
`calculate_m2(pieces)` ya las incluía, y el #417 sumaba además
`regrueso_ml × 0.05` encima → cobraba ~3 m² × $224.825 = $675K de más.

El primer instinto fue `"regrueso" in description.lower()` — substring
match. Frágil de los dos lados:

- **False positive**: "Frente sin regrueso" → matchearía como pieza
  regrueso → calculator skipearía la suma del extra → undercount
  silencioso (peor que el sobrecount, que al menos lo agarra el
  validator de m²).
- **False negative**: "FR" abreviado → no matchea — fail loud vía
  validator (delta > 0.05) cuando aparezca el caso.

Por eso vive en su propio módulo — la lógica es lo bastante delicada
como para no inlineearla en calculator + validator. Y deja un único
lugar donde refactorizar cuando se migre a un campo estructurado
`is_regrueso: bool` en piece_details (deuda anotada como Issue A
en el PR #419).

**Convenciones de matching:**

- Word boundary (`\bregrueso\b`) — "regruesoadicional" no matchea por
  accidente, "regrueso" como palabra suelta sí.
- Negación previa: "sin regrueso", "no incluye regrueso",
  "no lleva regrueso", "no tiene regrueso", "no va regrueso" → NO match.

**Edge cases conocidos** (NO se manejan acá, fallan loud vía validator
o se documentan como deuda):

- "regrueso: no" / "regrueso=no" → matchea positivo (negación posterior,
  no antes). Probabilidad bajísima en lenguaje real de operador
  marmolería; si aparece, validator lo agarra como mismatch ruidoso.
- "sin frente regrueso" → matchea positivo (la negación califica al
  frente, no al regrueso). Ambiguo semánticamente — el operador
  tendría que aclarar.
- "FR", "Frente regr." y abreviaturas → NO matchean. Validator
  detectará el mismatch entre `regrueso_ml × 0.05` y la suma de
  pieces y emitirá error ruidoso.

Ninguno justifica complicar el regex. Si aparece un caso real, abrimos
issue específico — por ahora YAGNI.
"""
from __future__ import annotations

import re

# Word boundary para evitar matches accidentales como "regruesoX".
# IGNORECASE para que "REGRUESO" mayúscula también matchee.
_REGRUESO_RE = re.compile(r'\bregrueso\b', re.IGNORECASE)

# Negación previa: la palabra "regrueso" precedida por "sin" o "no
# (incluye|lleva|tiene|va)" cuenta como NEGATIVA. Solo aplica cuando
# la negación está INMEDIATAMENTE antes — construcciones invertidas
# tipo "regrueso: no" no se detectan acá (ver edge cases en docstring
# del módulo). Mantener simple — el validator atrapa lo que pase.
_NEG_REGRUESO_RE = re.compile(
    r'\b(sin|no(?:\s+(?:incluye|lleva|tiene|va))?)\s+regrueso\b',
    re.IGNORECASE,
)


def is_regrueso_piece(piece: dict) -> bool:
    """¿Esta pieza es un "frente regrueso" o equivalente?

    True si la description contiene "regrueso" como palabra entera
    SIN una negación inmediatamente antes.

    Args:
        piece: dict de piece_details con clave "description".

    Returns:
        True si es pieza regrueso, False si no o si la pieza no tiene
        description.

    Examples:
        >>> is_regrueso_piece({"description": "M1 frente regrueso"})
        True
        >>> is_regrueso_piece({"description": "Frente sin regrueso"})
        False
        >>> is_regrueso_piece({"description": "Mesada"})
        False
        >>> is_regrueso_piece({})
        False
    """
    if not isinstance(piece, dict):
        return False
    desc = piece.get("description") or ""
    if not isinstance(desc, str) or not desc:
        return False
    # Negación previa gana — chequear primero.
    if _NEG_REGRUESO_RE.search(desc):
        return False
    return bool(_REGRUESO_RE.search(desc))


def sum_regrueso_pieces_m2(piece_details: list[dict] | None) -> float:
    """Suma `m2 × quantity` de las piezas que matchean is_regrueso_piece.

    Helper único compartido entre calculator (decisión de double-count)
    y validator (check de consistencia ruidoso). Si la lógica de
    matching cambia, ambas partes la heredan en sincro.

    Tolera piece_details None / lista vacía / piezas mal-formadas
    (skip silencioso por pieza — la observabilidad es del audit log,
    no de este helper).

    Returns:
        Suma redondeada a 4 decimales. 0.0 si no hay piezas regrueso.
    """
    if not piece_details:
        return 0.0
    total = 0.0
    for p in piece_details:
        if not is_regrueso_piece(p):
            continue
        try:
            m2 = float(p.get("m2") or 0)
            qty = int(p.get("quantity") or 1)
            total += m2 * qty
        except (TypeError, ValueError):
            continue
    return round(total, 4)
