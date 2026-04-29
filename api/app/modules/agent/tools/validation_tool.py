"""Post-despiece deterministic validation.

Pure functions that verify business rules on the qdata dict
returned by calculate_quote(). No I/O, no async.
"""

import math
import logging
from dataclasses import dataclass, field

from app.core.company_config import get as _cfg

_IVA = _cfg("iva.multiplier", 1.21)
_SINTETICOS = set(
    _cfg("materials.sinteticos", ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto"])
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Public entry point ──────────────────────────────────────────────────────


def validate_despiece(qdata: dict) -> ValidationResult:
    """Run all sub-validators on a calculate_quote result dict."""
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for check in (
        _check_iva_material,
        _check_iva_mo,
        _check_material_total,
        _check_merma_rules,
        _check_pegadopileta,
        _check_piece_m2,
        _check_mo_item_totals,
        _check_colocacion_qty,
        _check_regrueso_consistency,  # PR #419 — detecta double-count
        _check_products_only_consistency,  # PR #424 — modo solo producto
    ):
        try:
            errors, warnings = check(qdata)
            all_errors.extend(errors)
            all_warnings.extend(warnings)
        except Exception as exc:
            logging.warning(f"Validation check {check.__name__} crashed: {exc}")
            all_warnings.append(f"Check {check.__name__} no pudo ejecutarse: {exc}")

    return ValidationResult(
        ok=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings,
    )


# ── Sub-validators ──────────────────────────────────────────────────────────


def _check_iva_material(qdata: dict) -> tuple[list[str], list[str]]:
    """Verify material_price_unit = f(material_price_base * IVA)."""
    errors, warnings = [], []
    base = qdata.get("material_price_base")
    unit = qdata.get("material_price_unit")
    currency = qdata.get("material_currency", "").upper()

    if base is None or unit is None:
        if base is None and unit is not None:
            warnings.append("Falta material_price_base — no se puede verificar IVA del material")
        return errors, warnings

    if currency == "USD":
        expected = math.floor(base * _IVA)
    else:
        expected = round(base * _IVA)

    if unit != expected:
        errors.append(
            f"IVA material inconsistente: price_base={base} × {_IVA} → "
            f"esperado={expected}, actual={unit} ({currency})"
        )
    return errors, warnings


def _check_iva_mo(qdata: dict) -> tuple[list[str], list[str]]:
    """Verify each MO item: unit_price = round(base_price * IVA). MO is always ARS.

    Edificio items have an additional ÷1.05 discount applied after IVA, so:
      unit_price = round(base × IVA / 1.05)
    The item flag `edificio_discount: True` signals this and the expected
    value is adjusted accordingly.
    """
    errors, warnings = [], []
    for mo in qdata.get("mo_items", []):
        bp = mo.get("base_price")
        up = mo.get("unit_price")
        desc = mo.get("description", "?")
        has_edif_disc = bool(mo.get("edificio_discount"))
        # PR #415 — items con `price_includes_vat: true` (caso flete
        # Piñero/Cañada/Alvear): el JSON ya tiene el precio final con
        # IVA, así que `unit_price == base_price`. La fórmula
        # `unit == round(base × 1.21)` NO aplica para estos. Sin este
        # skip el validador bloqueaba generate_documents y Sonnet
        # caía a recalcular cambiando localidad → flete viejo + render
        # incorrecto (caso DYSCON post-#414).
        price_includes_vat = bool(mo.get("price_includes_vat"))

        if bp is None:
            continue  # Old data without base_price — skip silently
        if up is None:
            warnings.append(f"MO '{desc}' sin unit_price")
            continue

        if price_includes_vat:
            # Cuando el catálogo ya trae el precio con IVA, el "base"
            # es igual al "with_iva". Validar igualdad estricta —
            # cualquier divergencia es bug del calculator/catalog_lookup.
            if abs(up - bp) > 1:
                errors.append(
                    f"MO '{desc}' con price_includes_vat=true esperaba "
                    f"unit==base ({bp}), actual={up}"
                )
            continue

        if has_edif_disc:
            expected = round(bp * _IVA / 1.05)
        else:
            expected = round(bp * _IVA)
        if abs(up - expected) > 1:
            errors.append(
                f"IVA MO inconsistente en '{desc}': base={bp} × {_IVA}"
                f"{' ÷ 1.05' if has_edif_disc else ''} → "
                f"esperado={expected}, actual={up}"
            )
    return errors, warnings


def _check_material_total(qdata: dict) -> tuple[list[str], list[str]]:
    """Verify material_total = round(m2 * price_unit) - discount_amount."""
    errors, warnings = [], []
    m2 = qdata.get("material_m2")
    price_unit = qdata.get("material_price_unit")
    total = qdata.get("material_total")
    discount = qdata.get("discount_amount", 0) or 0

    if m2 is None or price_unit is None or total is None:
        return errors, warnings

    gross = round(m2 * price_unit)
    expected_net = gross - discount

    if abs(total - expected_net) > 1:
        errors.append(
            f"Total material inconsistente: {m2} m² × {price_unit} = {gross}, "
            f"descuento={discount} → esperado={expected_net}, actual={total}"
        )
    return errors, warnings


def _check_merma_rules(qdata: dict) -> tuple[list[str], list[str]]:
    """Negro Brasil NEVER merma. Synthetics SHOULD have merma."""
    errors, warnings = [], []
    mat = (qdata.get("material_name") or "").lower()
    merma = qdata.get("merma") or {}

    # Negro Brasil + merma = ERROR (upgraded from warning)
    if "negro brasil" in mat and merma.get("aplica"):
        errors.append("Negro Brasil NUNCA lleva merma — merma.aplica debe ser False")

    # Synthetic without merma = warning (might be valid if desperdicio < 1.0 m²)
    mat_type = (qdata.get("material_type") or "").lower()
    is_synthetic = mat_type in _SINTETICOS or any(s in mat for s in _SINTETICOS)
    if is_synthetic and not merma.get("aplica"):
        desperdicio = merma.get("desperdicio", 0)
        if desperdicio >= 1.0:
            warnings.append(
                f"Material sintético ({qdata.get('material_name')}) con desperdicio={desperdicio} m² "
                f"debería llevar merma (umbral: 1.0 m²)"
            )

    # Natural stone with merma = warning
    if not is_synthetic and "negro brasil" not in mat and merma.get("aplica"):
        warnings.append(f"Piedra natural ({qdata.get('material_name')}) con merma — verificar")

    return errors, warnings


def _check_pegadopileta(qdata: dict) -> tuple[list[str], list[str]]:
    """If pileta is empotrada, exactly 1 pileta MO item should exist."""
    errors, warnings = [], []
    pileta = qdata.get("pileta") or ""

    if pileta not in ("empotrada_johnson", "empotrada_cliente"):
        return errors, warnings

    pileta_mo_count = 0
    for mo in qdata.get("mo_items", []):
        desc = (mo.get("description") or "").lower()
        if "pileta" in desc or "pegado" in desc:
            pileta_mo_count += 1

    if pileta_mo_count == 0:
        errors.append(
            f"Pileta '{pileta}' solicitada pero no hay ítem MO de pileta/pegado"
        )
    elif pileta_mo_count > 1:
        warnings.append(
            f"Hay {pileta_mo_count} ítems MO de pileta — debería ser 1 por presupuesto"
        )

    return errors, warnings


def _check_piece_m2(qdata: dict) -> tuple[list[str], list[str]]:
    """Verify piece m2 calculations and total material_m2."""
    errors, warnings = [], []
    pieces = qdata.get("piece_details")
    if not pieces:
        return errors, warnings

    total_m2 = 0.0
    for p in pieces:
        largo = p.get("largo", 0)
        dim2 = p.get("dim2", 0)
        m2 = p.get("m2", 0)
        qty = p.get("quantity", 1)

        # Skip largo×dim2 consistency check when:
        # - override=True (Planilla de Cómputo del comitente: m² incluye
        #   zócalo/frente, NO se recalcula desde largo×prof). DINALE
        #   15/04/2026 fallaba cada vez aquí.
        # - _is_frentin=True (PR #164: faldón/frentín tiene m²=0
        #   intencional, contribuye solo a MO).
        if not p.get("override") and not p.get("_is_frentin"):
            expected_m2 = largo * dim2
            if abs(m2 - expected_m2) > 0.01:
                errors.append(
                    f"Pieza '{p.get('description', '?')}': m2={m2} pero "
                    f"largo={largo} × dim2={dim2} = {expected_m2:.4f}"
                )
        total_m2 += m2 * qty

    declared_m2 = qdata.get("material_m2")
    if declared_m2 is not None:
        expected_total = round(total_m2, 2)

        # PR #418 — observabilidad: log estructurado SIEMPRE, no solo
        # cuando hay error. Así tenemos traza del happy path también
        # (sirve para diagnosticar regresiones por comparación).
        # MISMATCH se loguea adentro del helper si delta > 0.01.
        try:
            from app.modules.quote_engine.audit import log_m2_audit
            log_m2_audit(
                quote_id=qdata.get("quote_id"),
                source="validator",
                material_m2=declared_m2,
                piece_details=pieces,
                recomputed_total=expected_total,
            )
        except Exception:
            # Observabilidad nunca rompe la validación. El error de
            # mismatch igual se sigue acumulando abajo si corresponde.
            pass

        if abs(declared_m2 - expected_total) > 0.01:
            errors.append(
                f"material_m2={declared_m2} no coincide con suma de piezas={expected_total}"
            )

    return errors, warnings


def _check_mo_item_totals(qdata: dict) -> tuple[list[str], list[str]]:
    """Verify each MO item: total ≈ quantity × unit_price.

    Tolerancia dinámica: con qty alto el redondeo de unit_price se acumula
    (qty=19 puede divergir ~10 ARS sin que haya bug). Ignoramos diferencias
    pequeñas en términos absolutos Y proporcionales — solo flaguamos cuando
    la diferencia es >$50 o >0.1% del total. El warning es informativo
    (no afecta al PDF/Excel del cliente).
    """
    errors, warnings = [], []
    for mo in qdata.get("mo_items", []):
        qty = mo.get("quantity", 0)
        up = mo.get("unit_price", 0)
        total = mo.get("total")
        desc = mo.get("description", "?")

        if total is None:
            continue

        expected = round(qty * up)
        diff = abs(total - expected)
        # Tolerancia: max($50, 0.1% del total) — absorbe rounding cosmético.
        tolerance = max(50, abs(total) * 0.001)
        if diff > tolerance:
            # Mensaje en español, orientado al operador, sin jerga técnica.
            warnings.append(
                f"Diferencia menor de redondeo en '{desc}': "
                f"${diff:,.0f} sobre ${abs(total):,.0f}. "
                f"No afecta al presupuesto del cliente."
                .replace(",", ".")
            )

    return errors, warnings


def _check_colocacion_qty(qdata: dict) -> tuple[list[str], list[str]]:
    """If colocacion=True, colocacion MO qty should be max(material_m2, 1.0)."""
    errors, warnings = [], []
    if not qdata.get("colocacion"):
        return errors, warnings

    m2 = qdata.get("material_m2", 0)
    expected_qty = max(m2, 1.0)

    for mo in qdata.get("mo_items", []):
        desc = (mo.get("description") or "").lower()
        if "colocaci" in desc:
            actual_qty = mo.get("quantity", 0)
            if abs(actual_qty - expected_qty) > 0.01:
                warnings.append(
                    f"Colocación qty={actual_qty} pero material_m2={m2} → "
                    f"esperado max({m2}, 1.0) = {expected_qty}"
                )
            return errors, warnings

    warnings.append("Colocación=True pero no se encontró ítem MO de colocación")
    return errors, warnings


# Tolerancia para el check de consistencia regrueso. 5 cm² = 0.05 m².
# Calibrada para regrueso_ml >= 30 (típico DYSCON-scale: ~60 ml → ~3 m²
# expected → 1.7% slack relativo, $$ ruido <$15K).
#
# TOLERANCIA: 0.05 m² absoluto. Calibrado para regrueso_ml >= 30.
# Proyectos chicos (regrueso_ml=10 → expected 0.5 m²) tienen 10% slack
# relativo, pero riesgo monetario absoluto bajo (~$9K máx).
# Si aparece caso de undercount en proyecto chico, migrar a
# `max(0.05, 0.02 * expected)` (relativo o absoluto, lo que sea mayor).
# YAGNI hasta que aparezca el caso.
_REGRUESO_CONSISTENCY_TOLERANCE_M2 = 0.05


def _check_regrueso_consistency(qdata: dict) -> tuple[list[str], list[str]]:
    """Verifica consistencia entre `regrueso_ml` y suma de m² de las
    piezas regrueso en `piece_details`.

    **Por qué es ruidoso (errors, no warnings):** caso espejo del
    DYSCON post-#417 — operador declara `regrueso_ml=60.68` pero
    incluye solo 5 de 7 piezas regrueso en el despiece (suman 2.17 m²
    vs expected 3.034 m²). Si fuera silencioso (skip cuantitativo),
    el cliente termina subfacturado ~$193K sin que nadie se entere
    en 3 semanas. Errores ruidosos > undercount silencioso.

    Lógica:

    1. Si no hay `regrueso=True` o `regrueso_ml<=0` → no aplica.
    2. Si `pieces_regrueso_m2 < 0.001` → caso #417 original (regrueso
       declarado SIN piezas) → calculator ya sumó `regrueso_ml × 0.05`
       al total. NO chequeamos consistencia (no hay nada que comparar).
    3. Si hay piezas regrueso en piece_details:
       - Comparar `sum(piece.m2 × qty for piece regrueso)` vs
         `regrueso_ml × 0.05`.
       - Si delta supera la tolerancia (0.05 m²) → error ruidoso.
       - Si dentro de tolerancia → ok, calculator no double-counteó.

    Tolerancia documentada arriba (`_REGRUESO_CONSISTENCY_TOLERANCE_M2`).
    """
    errors, warnings = [], []
    if not qdata.get("regrueso"):
        return errors, warnings
    regrueso_ml = qdata.get("regrueso_ml") or 0
    try:
        regrueso_ml = float(regrueso_ml)
    except (TypeError, ValueError):
        return errors, warnings
    if regrueso_ml <= 0:
        return errors, warnings

    # Import local para no acoplar el módulo a quote_engine en import
    # time. El validator ya importa otras cosas de quote_engine si fuera
    # necesario; esta es la única vez que toca regrueso_detect.
    try:
        from app.modules.quote_engine.regrueso_detect import sum_regrueso_pieces_m2
    except Exception as exc:
        warnings.append(
            f"_check_regrueso_consistency: no se pudo cargar regrueso_detect: {exc}"
        )
        return errors, warnings

    pieces = qdata.get("piece_details") or []
    pieces_regrueso_m2 = sum_regrueso_pieces_m2(pieces)

    if pieces_regrueso_m2 < 0.001:
        # Caso #417 baseline: regrueso declarado sin piezas en despiece.
        # Calculator ya sumó `regrueso_ml × 0.05` al total. No tenemos
        # contra qué comparar — confiamos en el declarado.
        return errors, warnings

    expected_m2 = round(regrueso_ml * 0.05, 4)
    # Redondeo a 4 decimales del delta antes de comparar — sin esto el
    # boundary `delta == 0.05` es indeterminado por float imprecision
    # (`abs(0.25 - 0.2)` da 0.04999999999999998 en Python). Con round
    # el comparador `>` es estable y un cambio futuro a `>=` se
    # detecta en los tests de boundary.
    delta = round(abs(pieces_regrueso_m2 - expected_m2), 4)
    if delta > _REGRUESO_CONSISTENCY_TOLERANCE_M2:
        # Error ruidoso — bloquea generate_documents. El operador
        # tiene que decidir: o declaró mal el despiece (faltan piezas
        # regrueso) o regrueso_ml está mal. NO elegimos por él.
        errors.append(
            f"Inconsistencia regrueso: piezas con 'regrueso' en "
            f"description suman {pieces_regrueso_m2:.4f} m² pero "
            f"regrueso_ml={regrueso_ml} × 0.05 = {expected_m2:.4f} m². "
            f"Delta {delta:.4f} m² supera tolerancia "
            f"{_REGRUESO_CONSISTENCY_TOLERANCE_M2}. "
            f"O faltan piezas regrueso en el despiece, o regrueso_ml "
            f"está mal. Confirmar con operador."
        )
    return errors, warnings


# Tolerancia para el sanity check del total ARS (modo products_only).
# 1 peso absoluto. Float arithmetic + rounding pueden dejar 0.5-1 peso
# de drift; mayor que eso indica fórmula rota.
_PRODUCTS_ONLY_TOTAL_TOLERANCE_ARS = 1.0


def _check_products_only_consistency(qdata: dict) -> tuple[list[str], list[str]]:
    """Verifica que un breakdown en modo `products_only` sea coherente.

    **Por qué existe** (PR #424, caso DYSCON 29/04/2026):

    El operador pidió 32 piletas Johnson "solo producto, sin MO". Sonnet
    armó un payload con `material vacío + sinks + mo_items inventados +
    total_ars que no incluía las piletas` → cliente cobrado de menos.
    El nuevo modo `products_only` lo emite limpio, pero un Sonnet
    futuro podría intentar mezclar quote normal + products_only y
    pasar data inconsistente. Este check lo agarra ruidosamente.

    Solo dispara si `_quote_mode == "products_only"`. Verifica:

    1. **`material_m2` debe ser 0.** El modo NO usa material — si
       llegara con material_m2>0, alguien (Sonnet/refactor futuro)
       mezcló modos.
    2. **`mo_items` debe estar vacío.** El modo NO inyecta MO de
       pileta — el operador lo pidió "sin MO" explícito.
    3. **`sinks` no puede estar vacío.** Si está vacío, no hay nada
       que cotizar — error.
    4. **`total_ars` debe coincidir con `sum(sinks) - discount_amount`.**
       Drift guard del bug DYSCON: el total NO coincidía con la suma
       de productos visibles.

    Errores ruidosos (`errors`, no `warnings`) → bloquea
    `generate_documents` y fuerza al operador a revisar antes de
    generar PDF con números inconsistentes.
    """
    errors, warnings = [], []
    if qdata.get("_quote_mode") != "products_only":
        return errors, warnings

    # 1. material_m2 debe ser 0
    mat_m2 = qdata.get("material_m2") or 0
    if mat_m2 > 0:
        errors.append(
            f"products_only inválido: material_m2={mat_m2} (debe ser 0). "
            f"El modo solo-producto no cotiza material."
        )

    # 2. mo_items debe estar vacío
    mo_items = qdata.get("mo_items") or []
    if mo_items:
        descs = [m.get("description", "?") for m in mo_items[:3]]
        errors.append(
            f"products_only inválido: mo_items no vacío "
            f"({len(mo_items)} ítems: {descs}). El operador pidió "
            f"'sin MO' al activar este modo."
        )

    # 3. sinks no puede estar vacío
    sinks = qdata.get("sinks") or []
    if not sinks:
        errors.append(
            "products_only inválido: sinks vacío. Sin productos no hay "
            "nada que cotizar — revisar el input."
        )
        return errors, warnings  # sin sinks no podemos validar el total

    # 4. total_ars == sum(sinks) - discount_amount
    sinks_subtotal = sum(
        (s.get("unit_price") or 0) * (s.get("quantity") or 0)
        for s in sinks
    )
    discount_amount = qdata.get("discount_amount") or 0
    expected_total = sinks_subtotal - discount_amount
    actual_total = qdata.get("total_ars") or 0
    delta = abs(actual_total - expected_total)
    if delta > _PRODUCTS_ONLY_TOTAL_TOLERANCE_ARS:
        errors.append(
            f"products_only inválido: total_ars={actual_total} ≠ "
            f"sum(sinks)-descuento = {sinks_subtotal}-{discount_amount} "
            f"= {expected_total}. Delta {delta:.0f} ARS supera "
            f"tolerancia {_PRODUCTS_ONLY_TOTAL_TOLERANCE_ARS}. "
            f"Sin este check el cliente se cobraría mal (caso DYSCON 29/04/2026)."
        )

    return errors, warnings
