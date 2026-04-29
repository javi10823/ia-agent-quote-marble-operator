"""Detector de claims de cambio sin tool de mutación.

**Por qué este módulo (PR #441, P3.1):**

Issue #422 + caso DYSCON 29/04/2026: Sonnet a veces responde
"cambié la demora" / "modificado" / "ya actualicé" sin haber
llamado ninguna tool en ese turno. El operador lee la respuesta,
asume que el cambio se aplicó, y se queda con la información
vieja sin saberlo.

Los PRs anteriores cubrieron piezas concretas:
- PR #423 (retry counter): protege contra tool failures repetidos.
- PR #436 (`update_quote` reject ruidoso): protege silent drops
  en ese handler.

Pero **ninguno cubre la alucinación pura** — Sonnet inventa un
estado de cambio sin haber tocado nada. Este módulo detecta
ese patrón observable post-hoc analizando:

1. El texto que emitió el assistant en el turno.
2. Las tools que se llamaron en el turno.

Si el texto contiene un claim de cambio (verbos en pasado primera
persona singular: "cambié", "modifiqué", etc.) Y ninguna tool de
mutación fue llamada → señal de alucinación.

**Limitaciones conocidas (documentadas, no se cubren acá):**

- Solo detecta claims en **español** rioplatense. El sistema es
  monolingüe español; agregar inglés requiere expandir patterns
  (YAGNI hasta que aparezca el caso).
- No detecta claims en futuro / condicional ("voy a cambiar",
  "te lo cambio") — esos son válidos antes del próximo turno.
- No detecta claims de "consulta sin tool" (ej. "el catálogo
  dice X" sin llamar `catalog_lookup`) — sería otro detector.
- Falsos positivos posibles: "cambié de opinión", "modifiqué mi
  recomendación" como giro de respuesta. El threshold
  conservador (verbos directos solamente, no "ya está"/"listo")
  minimiza estos casos.

**Acción:** log warning con prefijo `[hallucination-detector:<qid>]`.
NO bloquea el turno ni notifica al frontend. Solo observabilidad
para diagnosticar la frecuencia del problema. Si en producción
aparece seguido, P3.2 (futuro) escalaría a notificación visible
al operador.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# ─────────────────────────────────────────────────────────────────────
# Tools que mutan estado del quote (escriben DB columnas, JSON
# breakdown, archivos PDF/Excel, columnas de URLs, status, etc.).
# Si Sonnet llama AL MENOS UNA de estas en el turno, NO consideramos
# alucinación aunque el texto tenga claims de cambio — el cambio
# está respaldado por la tool.
#
# Read-only tools (catalog_lookup, catalog_batch_lookup,
# check_architect, check_stock, read_plan, list_pieces): NO están
# acá. Son consulta pura desde la perspectiva del operador (pueden
# persistir cosas internas como `_paso1_rendered` para el LLM, pero
# no cambian el "estado visible" del quote).
# ─────────────────────────────────────────────────────────────────────
MUTATION_TOOLS: frozenset[str] = frozenset({
    "update_quote",        # cambia columnas + breakdown
    "calculate_quote",     # recota + persiste breakdown
    "patch_quote_mo",      # modifica MO
    "generate_documents",  # genera PDF/Excel + URLs
})


def is_mutation_tool(name: str) -> bool:
    """¿Esta tool muta estado visible del quote?"""
    return name in MUTATION_TOOLS


# ─────────────────────────────────────────────────────────────────────
# Patrones de claim de cambio
#
# Solo verbos DIRECTOS de primera persona singular ("cambié",
# "modifiqué") o pasivos ("cambiado", "modificada"). NO incluye:
# - Frases ambiguas ("ya está", "listo", "hecho") → false positives.
# - Futuro / condicional ("voy a cambiar", "te lo cambio") → no
#   son claims de un cambio realizado.
# - Verbos genéricos sin objeto ("hecho", "OK") → ruido.
#
# Cada patrón tiene `\b` word-boundary para no matchear como
# substring (ej: "intercambiar" no debe matchear "cambiar").
# ─────────────────────────────────────────────────────────────────────
_CHANGE_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    # cambié / cambiado / cambiada (también: cambié-lo, cambiémoslo).
    re.compile(r"\bcambi(?:é|ado|ada|ados|adas)\b", re.IGNORECASE),
    # modifiqué / modificado / modificada.
    re.compile(r"\bmodifiqu[ée]\b|\bmodificad(?:o|a|os|as)\b", re.IGNORECASE),
    # actualicé / actualizado / actualizada.
    re.compile(r"\bactualic[ée]\b|\bactualizad(?:o|a|os|as)\b", re.IGNORECASE),
    # agregué / agregado / agregada.
    re.compile(r"\bagregu[ée]\b|\bagregad(?:o|a|os|as)\b", re.IGNORECASE),
    # añadí / añadido / añadida.
    re.compile(r"\bañad[íi]\b|\bañadid(?:o|a|os|as)\b", re.IGNORECASE),
    # saqué / sacado / sacada.
    re.compile(r"\bsaqu[ée]\b|\bsacad(?:o|a|os|as)\b", re.IGNORECASE),
    # removí / removido / removida.
    re.compile(r"\bremov[íi]\b|\bremovid(?:o|a|os|as)\b", re.IGNORECASE),
    # eliminé / eliminado / eliminada.
    re.compile(r"\belimin[ée]\b|\beliminad(?:o|a|os|as)\b", re.IGNORECASE),
    # borré / borrado / borrada.
    re.compile(r"\bborr[ée]\b|\bborrad(?:o|a|os|as)\b", re.IGNORECASE),
    # quité / quitado / quitada.
    re.compile(r"\bquit[ée]\b|\bquitad(?:o|a|os|as)\b", re.IGNORECASE),
    # puse / puesto / puesta (cuidado con "puede", "pude" — \b cubre).
    re.compile(r"\bpuse\b|\bpuest(?:o|a|os|as)\b", re.IGNORECASE),
    # guardé / guardado / guardada.
    re.compile(r"\bguard[ée]\b|\bguardad(?:o|a|os|as)\b", re.IGNORECASE),
    # corregí / corregido / corregida.
    re.compile(r"\bcorreg[íi]\b|\bcorregid(?:o|a|os|as)\b", re.IGNORECASE),
    # ajusté / ajustado / ajustada.
    re.compile(r"\bajust[ée]\b|\bajustad(?:o|a|os|as)\b", re.IGNORECASE),
)


def detect_unsupported_change_claim(
    assistant_text: str,
    tools_called: Iterable[str],
) -> Optional[str]:
    """Devuelve un mensaje de warning si el texto del assistant
    contiene un claim de cambio pero NO se llamó ninguna mutation
    tool en este turno. Caso contrario devuelve None.

    Args:
        assistant_text: el texto que emitió el LLM al operador
            en este turno (concatenación de todos los text blocks).
        tools_called: nombres de las tools que se llamaron en este
            turno (set/list/iterable). Pueden ser todas las tools
            (mutation + read-only); el detector filtra.

    Returns:
        - None si no hay claim, o si hubo al menos una mutation tool.
        - str con descripción del match si dispara la alerta.
    """
    if not assistant_text:
        return None

    # Si AL MENOS UNA mutation tool fue llamada en el turno, el
    # claim está respaldado y NO es alucinación.
    tools_set = set(tools_called or [])
    if any(is_mutation_tool(t) for t in tools_set):
        return None

    # Buscar claim de cambio en el texto.
    for pattern in _CHANGE_CLAIM_PATTERNS:
        match = pattern.search(assistant_text)
        if match:
            matched_word = match.group(0)
            return (
                f"Posible alucinación: assistant dijo '{matched_word}' "
                f"pero NO se llamó ninguna mutation tool en este turno. "
                f"tools_called={sorted(tools_set) or '[]'}. "
                f"Verificar si el cambio se aplicó realmente."
            )
    return None
