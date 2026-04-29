"""Observabilidad de m² — logs estructurados sin tocar lógica de negocio.

**Por qué existe este módulo (PR #418):**

Caso DYSCON post-#416/#417: el validador rechazó `generate_documents` con
`material_m2=48.584 no coincide con suma de piezas=45.55`. Para diagnosticar
el RC el camino tradicional era pedirle al operador un dump del
`quote_breakdown` desde Railway DB. Mal — la observabilidad es nuestra,
no del operador.

Este helper escribe el shape exacto que necesitamos para diagnosticar
divergencias entre `material_m2` (lo que persiste el calculator) y
`sum(piece.m2 × piece.quantity)` (lo que recomputa el validator).

**Diseño:**

- Cero side-effects fuera del logger.
- Try/except interno: si algo falla acá, NO rompe el flow del cálculo
  ni de la validación. La observabilidad nunca tira producción.
- Tag estable `[m2-audit:<quote_id>]` para que `grep m2-audit` filtre
  el ruido de Railway en un instante.

**Cuándo se llama:**

1. Desde `agent.py` post-`calculate_quote` (source="calculator") — captura
   lo que el calculator persiste a la DB. Una línea por pieza con todo el
   contexto que pediría un humano.
2. Desde `validation_tool._check_piece_m2` (source="validator") — captura
   lo que el validador ve y recomputa, ANTES de emitir el error. Si hay
   delta, dispara una línea fuerte `MISMATCH`.

**No reemplaza el fix.** Es la red para el próximo caso.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


# Campos por pieza que sí o sí queremos ver. El orden importa porque el
# operador (o yo) lee la línea del log de izquierda a derecha buscando el
# valor sospechoso. description primero — el shape del bug suele estar
# correlacionado con el tipo de pieza (regrueso, frentín, override, etc.).
_PIECE_FIELDS_PRIMARY = (
    "description", "largo", "dim2", "quantity", "m2",
    "override", "_is_frentin",
)
# Campos opcionales — solo se loguean si están presentes en la pieza.
# Evita ruido en quotes que no usan esas marcas.
_PIECE_FIELDS_OPTIONAL = (
    "_derived_kind", "_pileta_inferred_by_guardrail", "prof", "alto",
)


def _format_piece(idx: int, piece: dict) -> str:
    """Una línea por pieza. m2_unit y m2_total explícitos para no obligar
    al lector a multiplicar mentalmente.

    Si `piece` no es un dict (defensivo), devolvemos un placeholder en
    vez de tirar — el log es best-effort.
    """
    if not isinstance(piece, dict):
        return f"  piece[{idx}] <not-a-dict: {type(piece).__name__}>"

    parts = [f"  piece[{idx}]"]
    # Primary: siempre se loguean (con None si faltan). Sirve para detectar
    # piezas que vienen mal-formadas — un None acá ya es señal.
    for field in _PIECE_FIELDS_PRIMARY:
        val = piece.get(field)
        # description con repr para captar espacios/emojis pegados.
        if field == "description":
            parts.append(f"description={val!r}")
        else:
            parts.append(f"{field}={val}")

    # Optional: solo si están en el dict. No usamos default — la presencia
    # del campo es información en sí misma.
    for field in _PIECE_FIELDS_OPTIONAL:
        if field in piece:
            parts.append(f"{field}={piece[field]!r}")

    # m2_unit y m2_total derivados — para no obligar al lector a multiplicar.
    try:
        m2_unit = float(piece.get("m2") or 0)
        qty = int(piece.get("quantity") or 1)
        m2_total = round(m2_unit * qty, 4)
        parts.append(f"m2_unit={m2_unit}")
        parts.append(f"m2_total={m2_total}")
    except (TypeError, ValueError):
        parts.append("m2_unit=<unparseable>")
        parts.append("m2_total=<unparseable>")

    return " ".join(parts)


def _sum_piece_details(pieces: Iterable[dict]) -> float:
    """Suma `m2 × quantity` de cada pieza. Mismo cálculo que hace el
    validador en `_check_piece_m2`, replicado acá para que el log del
    calculator pueda mostrar la suma esperada SIN tener que correr el
    validador. Así un log solo del calculator ya delata el mismatch.

    Tolera piezas mal formadas (skip silencioso por pieza).
    """
    total = 0.0
    for p in pieces or []:
        if not isinstance(p, dict):
            continue
        try:
            m2 = float(p.get("m2") or 0)
            qty = int(p.get("quantity") or 1)
            total += m2 * qty
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def log_m2_audit(
    quote_id: str | None,
    source: str,
    material_m2: float | None,
    piece_details: list[dict] | None,
    recomputed_total: float | None = None,
) -> None:
    """Emite log estructurado para auditoría de `material_m2` vs piezas.

    Args:
        quote_id: identificador de la quote. Si None, se loguea como "?"
            (no rompemos por falta de tag).
        source: "calculator" cuando lo llama el caller del calc result,
            "validator" cuando lo llama `_check_piece_m2`. Determina el
            shape del header.
        material_m2: el valor persistido / declarado.
        piece_details: la lista de piezas tal como quedó en el breakdown.
        recomputed_total: solo para source="validator" — el total que
            recomputó el validador. Si delta > 0.01, se emite también
            la línea `MISMATCH`.

    Nunca tira excepción al caller. Errores internos se loguean en debug.
    """
    try:
        qid = quote_id or "?"
        pieces = list(piece_details or [])

        if source == "calculator":
            sum_pd = _sum_piece_details(pieces)
            header = (
                f"[m2-audit:{qid}] calculator material_m2={material_m2} "
                f"sum_piece_details={sum_pd} pieces={len(pieces)}"
            )
        elif source == "validator":
            delta = None
            if material_m2 is not None and recomputed_total is not None:
                delta = round(material_m2 - recomputed_total, 4)
            header = (
                f"[m2-audit:{qid}] validator material_m2={material_m2} "
                f"recomputed_total={recomputed_total} delta={delta} "
                f"pieces={len(pieces)}"
            )
        else:
            # Source desconocido — logueamos igual con shape genérico
            # para no perder la info. No esperamos llegar acá.
            header = (
                f"[m2-audit:{qid}] {source} material_m2={material_m2} "
                f"pieces={len(pieces)}"
            )

        # Construimos el bloque completo (header + piezas) y lo emitimos
        # como UNA línea de logger.info — Railway colapsa multi-línea en
        # el panel; mejor que sea un solo evento para que se lea junto.
        body_lines = [header]
        for i, p in enumerate(pieces):
            body_lines.append(_format_piece(i, p))
        logger.info("\n".join(body_lines))

        # MISMATCH alert — línea separada para que `grep MISMATCH` la encuentre.
        # Threshold 0.01 alineado con el tolerance del validator
        # (`abs(declared_m2 - expected_total) > 0.01`).
        if source == "calculator":
            sum_pd = _sum_piece_details(pieces)
            if material_m2 is not None and abs(material_m2 - sum_pd) > 0.01:
                logger.warning(
                    f"[m2-audit:{qid}] MISMATCH delta="
                    f"{round(material_m2 - sum_pd, 4)} "
                    f"source=calculator_vs_piece_details "
                    f"material_m2={material_m2} sum_piece_details={sum_pd}"
                )
        elif source == "validator":
            if (
                material_m2 is not None
                and recomputed_total is not None
                and abs(material_m2 - recomputed_total) > 0.01
            ):
                logger.warning(
                    f"[m2-audit:{qid}] MISMATCH delta="
                    f"{round(material_m2 - recomputed_total, 4)} "
                    f"source=stored_material_m2_vs_recomputed "
                    f"material_m2={material_m2} recomputed={recomputed_total}"
                )
    except Exception as e:
        # La observabilidad nunca rompe el flow. Si por algún motivo el
        # piece_details viene en un shape no-iterable o algo raro, solo
        # logueamos un debug y seguimos.
        logger.debug(f"[m2-audit] log helper failed: {e}")
