"""Post-hoc validator for dual_reader output.

Rechaza (marca UNANCHORED) cualquier valor numérico emitido por el LLM que
no esté presente en las cotas extraídas del text layer del PDF. Esto
apaga la clase de bugs donde el VLM inventa medidas geométricamente
plausibles pero ausentes del plano (caso Bernardi: "1.75", "2.35"
como ancho de isla).

No rechaza hard — baja el status del field a UNANCHORED y lo flaguea en
ambiguedades. El operador ve que ese valor no está anclado y lo corrige
con doble-click (PR #282) o borra/agrega el tramo con los botones ± ya
existentes.
"""
from __future__ import annotations

from typing import Iterable


TOLERANCE = 0.01  # metros — 1cm. Apretado desde 2cm tras caso real donde
# Valentina leyó 2.15m en vez de 2.05m en un plano con cota explícita de 2.05:
# con tol=0.02 la diferencia de 10cm igual se detectaba (|2.15-2.05|=0.10 > 0.02),
# pero nunca llegó acá porque el reconciliador Opus/Sonnet (±5%) aceptó ambos
# modelos coincidiendo en 2.15. Bajar a 1cm reduce falsos positivos en cotas
# cercanas como 0.60/0.62 y fuerza el anchor real contra el text layer.


_FP_EPSILON = 1e-6  # evita falsos UNANCHORED por ruido de floating point


def _matches_any(value: float, reference: Iterable[float], tol: float = TOLERANCE) -> bool:
    """True si `value` está dentro de `tol` metros de algún valor de referencia.
    Agrega epsilon chico para evitar que `abs(2.94 - 2.95) = 0.01000...231` sea
    rechazado por un tol="0.01" exacto."""
    if value is None:
        return True  # valores null no se validan (el frontend los renderiza como edit inputs)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True
    return any(abs(v - float(r)) <= tol + _FP_EPSILON for r in reference if r is not None)


def annotate_anchoring(result: dict, extracted_values: list[float]) -> dict:
    """Marca fields del output de dual_read como UNANCHORED cuando su `valor`
    no aparece en la lista de cotas extraídas del text layer.

    Muta (y devuelve) `result` in-place para conservar todos los campos del
    schema. Si `extracted_values` está vacío (ej: PDF escaneado sin text
    layer), no hace nada — el validator queda en modo "no-op" y no empeora
    el flujo existente.
    """
    if not extracted_values:
        return result

    unanchored_count = 0
    warnings: list[str] = []

    for sector in result.get("sectores") or []:
        for tramo in sector.get("tramos") or []:
            # largo / ancho
            for field_name in ("largo_m", "ancho_m"):
                fv = tramo.get(field_name)
                if not isinstance(fv, dict):
                    continue
                val = fv.get("valor")
                if not _matches_any(val, extracted_values):
                    fv["status"] = "UNANCHORED"
                    fv["unanchored_reason"] = (
                        f"{val}m no está en las cotas del plano"
                    )
                    unanchored_count += 1
            # zócalos ml
            for z in tramo.get("zocalos") or []:
                ml = z.get("ml")
                if ml is not None and not _matches_any(ml, extracted_values):
                    z["status"] = "UNANCHORED"
                    z["unanchored_reason"] = (
                        f"{ml}ml no está en las cotas del plano"
                    )
                    unanchored_count += 1

        if unanchored_count > 0 and warnings == []:
            existing = list(sector.get("ambiguedades") or [])
            existing.append({
                "tipo": "REVISION",
                "texto": (
                    f"{unanchored_count} medida(s) no coinciden con cotas "
                    "leídas del PDF — verificá doble-click en el despiece."
                ),
            })
            sector["ambiguedades"] = existing
            warnings.append(sector.get("id", "?"))

    if unanchored_count > 0:
        result["requires_human_review"] = True

    return result
