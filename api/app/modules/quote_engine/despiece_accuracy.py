"""Precisión del despiece: lo que leyó la IA contra lo que confirmó el operador.

Cada presupuesto real con plano produce una muestra gratis: la lectura original
de la IA (`dual_read_ai_original`) y el despiece que el operador confirmó. Se
comparan tramo por tramo y se guarda el resultado en el presupuesto. Así el
"90 % hecho por la IA" se mide con datos reales en vez de a ojo.

Categorías por tramo de la IA:
- acertada: el operador la dejó igual (largo y ancho dentro de TOL_M).
- corregida: existe un tramo confirmado parecido pero con otra medida.
- inventada: la IA la puso y el operador la sacó.
Y por el lado del operador:
- faltante: el operador agregó un tramo que la IA no leyó.

Función pura: sin DB ni LLM.
"""
from __future__ import annotations

TOL_M = 0.01  # 1 cm: misma tolerancia que plan_anchor_validator


def _val(field) -> float | None:
    if isinstance(field, dict):
        field = field.get("valor")
    try:
        return None if field is None else float(field)
    except (TypeError, ValueError):
        return None


def _tramos(dual: dict | None) -> list[dict]:
    out = []
    for sector in (dual or {}).get("sectores") or []:
        for t in sector.get("tramos") or []:
            if t.get("_derived"):
                continue  # los derivados (patas de isla, alzadas) los arma el código
            largo, ancho = _val(t.get("largo_m")), _val(t.get("ancho_m"))
            if largo is None or ancho is None:
                continue
            out.append({
                "largo": largo,
                "ancho": ancho,
                "qty": int(t.get("quantity") or 1),
                "label": str(t.get("descripcion") or ""),
                "unanchored": any(
                    isinstance(t.get(k), dict) and t[k].get("status") == "UNANCHORED"
                    for k in ("largo_m", "ancho_m")
                ),
            })
    return out


def _same(a: dict, b: dict) -> bool:
    return abs(a["largo"] - b["largo"]) <= TOL_M and abs(a["ancho"] - b["ancho"]) <= TOL_M


def _close(a: dict, b: dict) -> bool:
    """Mismo tramo pero medido distinto: una dimensión coincide."""
    return (abs(a["largo"] - b["largo"]) <= TOL_M) or (abs(a["ancho"] - b["ancho"]) <= TOL_M)


def compute_accuracy(ai_original: dict | None, confirmed: dict | None) -> dict | None:
    """None si no hay lectura original de la IA para comparar."""
    ai = _tramos(ai_original)
    if not ai_original or not ai:
        return None
    real = _tramos(confirmed)
    pending = list(real)

    acertadas = corregidas = inventadas = 0
    # 1) coincidencias exactas primero, para que una corrección no robe el lugar.
    rest = []
    for t in ai:
        match = next((r for r in pending if _same(t, r)), None)
        if match:
            pending.remove(match)
            acertadas += 1
        else:
            rest.append(t)
    # 2) lo que queda: ¿se corrigió una medida o directamente se sacó?
    for t in rest:
        match = next((r for r in pending if _close(t, r)), None)
        if match:
            pending.remove(match)
            corregidas += 1
        else:
            inventadas += 1
    faltantes = len(pending)

    total_ai = len(ai)
    return {
        "tramos_ia": total_ai,
        "tramos_confirmados": len(real),
        "acertadas": acertadas,
        "corregidas": corregidas,
        "inventadas": inventadas,
        "faltantes": faltantes,
        "pct_acierto": round(100 * acertadas / total_ai, 1),
        # ¿las marcas "no coincide con el plano" avisaban de los errores?
        "marcadas_sin_anclar": sum(1 for t in ai if t["unanchored"]),
    }
