"""Qué piezas del despiece el operador tiene que verificar sí o sí.

La IA a veces inventa medidas al leer planos. En vez de mostrar todo igual de
"seguro", el código marca lo que no tiene respaldo:
- UNANCHORED: la medida no figura entre las cotas escritas en el plano.
- CONFLICTO / DUDOSO: las dos lecturas no coinciden o la IA no estaba segura.
Y a nivel plano: si el plano no tenía texto (foto o PDF escaneado) ninguna medida
pudo contrastarse con cotas, y se avisa.
Función pura: sin DB ni LLM.
"""
from __future__ import annotations

_REASONS = {
    "CONFLICTO": "Las dos lecturas del plano no coinciden",
    "DUDOSO": "La IA no estaba segura de esta medida",
}

NO_TEXT_WARNING = (
    "El plano no tiene texto legible (foto o PDF escaneado): las medidas las leyó "
    "solo la IA y no se pudieron contrastar con cotas. Verificá cada una contra el plano."
)


def _field_reason(field) -> str | None:
    if not isinstance(field, dict):
        return None
    status = field.get("status")
    if status == "UNANCHORED":
        return field.get("unanchored_reason") or "La medida no figura en las cotas del plano"
    return _REASONS.get(status or "")


def tramo_review_reason(tramo: dict) -> str | None:
    """Motivo para verificar un tramo, o None. Si el operador ya lo editó a mano
    (no viene del brief) se da por verificado."""
    if tramo.get("_manual") and not tramo.get("_from_text"):
        return None
    for key in ("largo_m", "ancho_m"):
        reason = _field_reason(tramo.get(key))
        if reason:
            return reason
    return None


def zocalo_review_reason(zocalo: dict) -> str | None:
    if zocalo.get("status") == "UNANCHORED":
        return zocalo.get("unanchored_reason") or "La medida no figura en las cotas del plano"
    return _REASONS.get(zocalo.get("status") or "")


def plan_warnings(dual_read: dict | None) -> list[str]:
    return [NO_TEXT_WARNING] if (dual_read or {}).get("sin_texto_en_plano") else []
