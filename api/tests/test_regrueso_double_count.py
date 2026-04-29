"""Tests para PR #419 — fix double-count del regrueso (regression #417).

**Contexto del bug** (caso DYSCON observado en logs `9da51080-...`):

El #417 sumaba `regrueso_ml × 0.05` al `total_m2` siempre que `regrueso=True`.
Pero cuando el operador declaraba las piezas "frente regrueso" en el
despiece (con `prof=0.05`), `calculate_m2` ya las contabilizaba.
Resultado: double-count de 3.034 m² × $224.825 = **$675K cobrados de
más al cliente**.

**El caso espejo (peor)**: si fixeáramos con `any(regrueso in piece) →
skip` (binario), un operador que declara 5 de 7 piezas regrueso
generaría undercount silencioso (~0.86 m² faltantes = ~$193K menos
cobrados) que nadie detecta hasta que el cliente compara ml vs m²
facturados.

**Estrategia (review feedback):**

1. Calculator (`regrueso_detect.is_regrueso_piece` + branch en
   `calculate_quote`): si HAY piezas regrueso → no sumar extra (ya
   están). Si NO hay → sumar `regrueso_ml × 0.05` (caso #417 original).
2. Validator (`_check_regrueso_consistency`): chequea cuantitativamente
   que `sum(regrueso pieces m²) ≈ regrueso_ml × 0.05` con tolerancia
   0.05 m². Si difiere → error RUIDOSO que bloquea generate_documents.

**Tests cubren:**

1. DYSCON exact (caso real del log) → no double-count, validator verde.
2. Subfacturación silenciosa (5 de 7 pieces) → ERROR ruidoso.
3. False positive "Frente sin regrueso" → no matchea, calc suma extra.
4. Boundary delta=0.05 exacto → pasa (no error).
5. Boundary delta=0.0501 → error.
6. Caso #417 baseline (regrueso_ml SIN pieces regrueso) → suma extra.
7. regrueso_ml=0 + pieces regrueso → no aplica check, pieces normal.
8. regrueso=False + regrueso_ml positivo → no aplica nada.
9. Drift guard de la API pública (importable + signature estable).

**Nota crítica para futuros refactores:**

Si tocás este archivo y removés cualquier test, **leé primero el bug
DYSCON original**. El test #2 (subfacturación silenciosa) NO ES
OPCIONAL — sin él, una implementación binaria del fix se cuela y
abre el caso espejo del bug original.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import calculate_quote
from app.modules.quote_engine.regrueso_detect import (
    is_regrueso_piece,
    sum_regrueso_pieces_m2,
)
from app.modules.agent.tools.validation_tool import (
    _check_regrueso_consistency,
    validate_despiece,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers — armar el qdata mínimo para el validator sin pasar por
# calculate_quote (más rápido y aísla la lógica del check).
# ═══════════════════════════════════════════════════════════════════════


def _qdata(regrueso=True, regrueso_ml=60.68, pieces=None) -> dict:
    """qdata mínimo para invocar `_check_regrueso_consistency` directo."""
    return {
        "regrueso": regrueso,
        "regrueso_ml": regrueso_ml,
        "piece_details": pieces or [],
    }


def _piece(desc: str, m2: float, qty: int = 1, **extra) -> dict:
    """Pieza mínima de piece_details."""
    return {
        "description": desc,
        "m2": m2,
        "quantity": qty,
        "largo": 1.0,
        "dim2": m2,  # placeholder, no validamos largo×dim2 acá
        **extra,
    }


# ═══════════════════════════════════════════════════════════════════════
# is_regrueso_piece — word boundary + negación
# ═══════════════════════════════════════════════════════════════════════


class TestIsRegruesoPiece:
    @pytest.mark.parametrize("desc", [
        "Frente regrueso",
        "M1 frente regrueso",
        "REGRUESO",
        "regrueso del frente h:5cm",
        "M3 frente regrueso (Office 12)",
    ])
    def test_positive(self, desc):
        assert is_regrueso_piece({"description": desc}) is True

    @pytest.mark.parametrize("desc", [
        "Frente sin regrueso",
        "Mesada sin regrueso",
        "no incluye regrueso",
        "no lleva regrueso",
        "no tiene regrueso",
        "no va regrueso",
    ])
    def test_negation_wins(self, desc):
        """'sin regrueso', 'no incluye regrueso' etc. → NO matchea como pieza."""
        assert is_regrueso_piece({"description": desc}) is False

    @pytest.mark.parametrize("desc", [
        "Mesada",
        "Zócalo lateral",
        "Pileta empotrada",
        "regruesoadicional",  # word boundary: NO matchea sin espacio
        "",
    ])
    def test_negative(self, desc):
        assert is_regrueso_piece({"description": desc}) is False

    def test_no_description(self):
        assert is_regrueso_piece({}) is False
        assert is_regrueso_piece({"description": None}) is False

    def test_not_a_dict(self):
        """Defensive — no rompe con shape inesperado."""
        assert is_regrueso_piece(None) is False
        assert is_regrueso_piece("not-a-dict") is False


# ═══════════════════════════════════════════════════════════════════════
# sum_regrueso_pieces_m2 — helper compartido calc + validator
# ═══════════════════════════════════════════════════════════════════════


class TestSumRegruesoPiecesM2:
    def test_dyscon_exact(self):
        """Caso real DYSCON: 7 piezas regrueso, sum_total ≈ 3.034 m²."""
        pieces = [
            _piece("M1 frente regrueso", m2=0.10, qty=24),  # 2.40
            _piece("M2 frente regrueso", m2=0.085, qty=1),  # 0.085
            _piece("M3 frente regrueso", m2=0.125, qty=1),  # 0.125
            _piece("M4 frente regrueso", m2=0.125, qty=1),  # 0.125
            _piece("M5 frente regrueso", m2=0.09, qty=1),   # 0.09
            _piece("M6 frente regrueso", m2=0.08, qty=2),   # 0.16
            _piece("M7 frente regrueso", m2=0.08, qty=2),   # 0.16
        ]
        # 2.40 + 0.085 + 0.125 + 0.125 + 0.09 + 0.16 + 0.16 = 3.145
        # (los m2 redondeados a 2 decimales del log real dan ~3.145).
        result = sum_regrueso_pieces_m2(pieces)
        assert 3.0 <= result <= 3.2, f"esperaba ~3.1, vi {result}"

    def test_skips_non_regrueso(self):
        pieces = [
            _piece("Mesada", m2=2.0, qty=1),
            _piece("Frente regrueso", m2=0.5, qty=2),
            _piece("Zócalo", m2=0.3, qty=1),
        ]
        assert sum_regrueso_pieces_m2(pieces) == 1.0  # solo 0.5 × 2

    def test_skips_negation(self):
        """'Frente sin regrueso' NO se cuenta."""
        pieces = [
            _piece("Frente sin regrueso", m2=0.5, qty=1),
            _piece("Frente regrueso", m2=0.3, qty=1),
        ]
        assert sum_regrueso_pieces_m2(pieces) == 0.3

    def test_empty(self):
        assert sum_regrueso_pieces_m2([]) == 0.0
        assert sum_regrueso_pieces_m2(None) == 0.0


# ═══════════════════════════════════════════════════════════════════════
# _check_regrueso_consistency — validator ruidoso
# ═══════════════════════════════════════════════════════════════════════


class TestRegruesoConsistencyCheck:
    # ── 1. DYSCON exact ──────────────────────────────────────────────
    def test_dyscon_exact_passes(self):
        """Caso real: regrueso_ml=60.68, pieces ~3.034 m². Dentro de
        tolerancia → no error."""
        # Construyo pieces que sumen exacto regrueso_ml × 0.05 = 3.034.
        # 7 pieces con largos del DYSCON real.
        pieces = [
            _piece("M1 frente regrueso", m2=1.92 * 0.05, qty=24),  # 2.304
            _piece("M2 frente regrueso", m2=1.7 * 0.05, qty=1),    # 0.085
            _piece("M3 frente regrueso", m2=2.5 * 0.05, qty=1),    # 0.125
            _piece("M4 frente regrueso", m2=2.5 * 0.05, qty=1),    # 0.125
            _piece("M5 frente regrueso", m2=1.8 * 0.05, qty=1),    # 0.09
            _piece("M6 frente regrueso", m2=1.55 * 0.05, qty=2),   # 0.155
            _piece("M7 frente regrueso", m2=1.5 * 0.05, qty=2),    # 0.15
        ]
        # Suma = 2.304 + 0.085 + 0.125 + 0.125 + 0.09 + 0.155 + 0.15 = 3.034
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=60.68, pieces=pieces,
        ))
        assert errors == [], f"esperaba sin errores, vi {errors}"

    # ── 2. Subfacturación silenciosa (CRÍTICO — no borrar este test) ──
    def test_undercount_emits_loud_error(self):
        """Operador declara 5 de 7 piezas regrueso + regrueso_ml=60.68.
        Pieces suman ~2.17 m² vs expected 3.034 m². Delta 0.86 supera
        tolerancia 0.05 → ERROR RUIDOSO. Si este test pasa con un fix
        que silencia la inconsistencia, el bug del caso espejo está
        abierto y un cliente pagaría ~$193K menos."""
        pieces = [
            _piece("M1 frente regrueso", m2=1.92 * 0.05, qty=24),  # 2.304
            _piece("M2 frente regrueso", m2=1.7 * 0.05, qty=1),    # 0.085
            # M3, M4, M5 OMITIDOS — operador se olvidó.
            _piece("M6 frente regrueso", m2=1.55 * 0.05, qty=2),   # 0.155
            _piece("M7 frente regrueso", m2=1.5 * 0.05, qty=2),    # 0.15
        ]
        # Suma ~2.694, expected 3.034, delta ~0.34 → error.
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=60.68, pieces=pieces,
        ))
        assert len(errors) == 1, f"esperaba 1 error, vi {errors}"
        assert "Inconsistencia regrueso" in errors[0]
        assert "Confirmar con operador" in errors[0]

    # ── 3. False positive "sin regrueso" ─────────────────────────────
    def test_false_positive_sin_regrueso(self):
        """Pieza con 'sin regrueso' en description NO debe contar como
        pieza regrueso. Si el operador declara `regrueso_ml=60.68` y
        las piezas son "Frente sin regrueso", el calculator debe sumar
        el extra normal — no skipearlo por false positive."""
        pieces = [
            _piece("Mesada principal", m2=1.0, qty=1),
            _piece("Frente sin regrueso", m2=0.5, qty=1),
        ]
        # pieces_regrueso_m2 = 0 → caso baseline #417. No error.
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=60.68, pieces=pieces,
        ))
        assert errors == []

    # ── 4. Boundary delta = 0.05 exacto → pasa ──────────────────────
    def test_boundary_delta_exact_005_passes(self):
        """`delta == 0.05` con check `> 0.05` debe pasar (no error).
        Si alguien cambia `>` por `>=` en 6 meses, este test lo agarra."""
        # regrueso_ml=20 → expected = 1.0
        # pieces suman 1.05 → delta = 0.05 exacto.
        pieces = [_piece("Frente regrueso", m2=1.05, qty=1)]
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=20.0, pieces=pieces,
        ))
        assert errors == [], f"delta=0.05 exacto debería pasar, vi {errors}"

    # ── 5. Boundary delta = 0.0501 → error ─────────────────────────
    def test_boundary_delta_above_005_fails(self):
        """`delta > 0.05` (apenas) debe disparar error."""
        # regrueso_ml=20 → expected = 1.0
        # pieces suman 1.0501 → delta = 0.0501 > tolerancia 0.05.
        pieces = [_piece("Frente regrueso", m2=1.0501, qty=1)]
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=20.0, pieces=pieces,
        ))
        assert len(errors) == 1, \
            f"delta=0.0501 debería fallar, vi {errors}"

    # ── 6. Caso #417 baseline ──────────────────────────────────────
    def test_417_baseline_no_pieces_regrueso(self):
        """regrueso_ml declarado SIN piezas regrueso en despiece →
        no error (no hay nada que comparar). El calculator suma el
        extra al total. Comportamiento original del #417."""
        pieces = [
            _piece("Mesada", m2=2.5, qty=1),
            _piece("Zócalo", m2=0.5, qty=1),
        ]
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=60.68, pieces=pieces,
        ))
        assert errors == []

    # ── 7. regrueso_ml=0 con pieces regrueso ────────────────────────
    def test_regrueso_ml_zero_skips_check(self):
        """`regrueso_ml=0` → check no aplica aunque haya pieces regrueso.
        El operador no declaró el ml total — no hay contra qué comparar."""
        pieces = [_piece("Frente regrueso", m2=2.0, qty=1)]
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=True, regrueso_ml=0, pieces=pieces,
        ))
        assert errors == []

    # ── 8. regrueso=False + regrueso_ml positivo ───────────────────
    def test_regrueso_flag_false_skips_check(self):
        """`regrueso=False` → check no aplica, sin importar regrueso_ml
        o pieces."""
        pieces = [_piece("Frente regrueso", m2=2.0, qty=1)]
        errors, _ = _check_regrueso_consistency(_qdata(
            regrueso=False, regrueso_ml=60.68, pieces=pieces,
        ))
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════
# Calculator — no double-count cuando hay pieces regrueso
# ═══════════════════════════════════════════════════════════════════════


class TestCalculatorDoubleCountFix:
    def test_dyscon_real_input_no_double_count(self):
        """Reproduce el input real del log DYSCON post-#417. El bug
        original mostraba `material_m2=48.584 vs sum_pieces=45.55`
        (delta 3.034). Post-fix: deben coincidir dentro de 0.01."""
        result = calculate_quote({
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "client_name": "DYSCON S.A.",
            "project": "Unidad Penal N°8 — Piñero",
            "plazo": "30 días",
            "localidad": "Piñero",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "pileta_qty": 32,
            "regrueso": True,
            "regrueso_ml": 60.68,
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "prof": 0.1, "quantity": 24},
                {"description": "M1 frente regrueso", "largo": 1.92, "prof": 0.05, "quantity": 24},
                {"description": "M2 mesada", "largo": 1.7, "prof": 0.6, "quantity": 1},
                {"description": "M2 zócalo atrás", "largo": 1.7, "prof": 0.1, "quantity": 1},
                {"description": "M2 frente regrueso", "largo": 1.7, "prof": 0.05, "quantity": 1},
                {"description": "M3 mesada", "largo": 2.5, "prof": 0.6, "quantity": 1},
                {"description": "M3 zócalo atrás", "largo": 2.5, "prof": 0.1, "quantity": 1},
                {"description": "M3 frente regrueso", "largo": 2.5, "prof": 0.05, "quantity": 1},
                {"description": "M4 mesada", "largo": 2.5, "prof": 0.6, "quantity": 1},
                {"description": "M4 zócalo atrás", "largo": 2.5, "prof": 0.1, "quantity": 1},
                {"description": "M4 frente regrueso", "largo": 2.5, "prof": 0.05, "quantity": 1},
                {"description": "M5 mesada", "largo": 1.8, "prof": 0.6, "quantity": 1},
                {"description": "M5 zócalo atrás", "largo": 1.8, "prof": 0.1, "quantity": 1},
                {"description": "M5 frente regrueso", "largo": 1.8, "prof": 0.05, "quantity": 1},
                {"description": "M6 mesada", "largo": 1.55, "prof": 0.6, "quantity": 2},
                {"description": "M6 zócalo atrás", "largo": 1.55, "prof": 0.1, "quantity": 2},
                {"description": "M6 frente regrueso", "largo": 1.55, "prof": 0.05, "quantity": 2},
                {"description": "M7 mesada", "largo": 1.5, "prof": 0.6, "quantity": 2},
                {"description": "M7 zócalo atrás", "largo": 1.5, "prof": 0.1, "quantity": 2},
                {"description": "M7 frente regrueso", "largo": 1.5, "prof": 0.05, "quantity": 2},
            ],
        })
        assert result.get("ok") is True, f"calc falló: {result.get('error')}"
        material_m2 = result["material_m2"]
        # Suma manual de pieces (m2 × qty para cada uno).
        sum_pieces = sum(
            (p["m2"] or 0) * (p["quantity"] or 1)
            for p in result["piece_details"]
        )
        delta = abs(material_m2 - sum_pieces)
        # Pre-fix: delta ≈ 3.034 (double-count del regrueso).
        # Post-fix: delta ≤ 0.01 (solo rounding cosmético).
        assert delta < 0.01, (
            f"material_m2={material_m2} vs sum_pieces={sum_pieces:.4f} "
            f"delta={delta:.4f} > 0.01 — double-count regression"
        )

    def test_417_baseline_still_works(self):
        """regrueso_ml declarado SIN pieces regrueso → calculator debe
        seguir sumando `regrueso_ml × 0.05` al total (comportamiento
        del #417 original que arregló el subfacturado)."""
        result = calculate_quote({
            "client_name": "Test Cliente",
            "project": "Test Proyecto",
            "plazo": "30 días",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "regrueso": True,
            "regrueso_ml": 10.0,  # 10 ml × 0.05 = 0.5 m² extra
            "pieces": [
                # Sin piezas "regrueso" — solo mesada.
                {"description": "Mesada", "largo": 2.0, "prof": 0.6, "quantity": 1},
            ],
        })
        assert result.get("ok") is True, f"calc falló: {result.get('error')}"
        # mesada = 2.0 × 0.6 = 1.20 m². + regrueso 0.5 = 1.70 m² total.
        assert abs(result["material_m2"] - 1.70) < 0.01, (
            f"material_m2={result['material_m2']}, esperaba ~1.70 "
            f"(1.20 mesada + 0.50 regrueso extra)"
        )


# ═══════════════════════════════════════════════════════════════════════
# Drift guard — API pública estable
# ═══════════════════════════════════════════════════════════════════════


class TestPublicAPIDriftGuard:
    def test_is_regrueso_piece_importable(self):
        """Si alguien renombra `is_regrueso_piece`, este test rompe y
        avisa que hay que actualizar callsites en calculator + validator."""
        from app.modules.quote_engine.regrueso_detect import is_regrueso_piece
        assert callable(is_regrueso_piece)

    def test_check_regrueso_in_validate_despiece_pipeline(self):
        """`_check_regrueso_consistency` debe estar registrado en el
        pipeline de `validate_despiece`. Si alguien lo saca, los errors
        de inconsistencia desaparecen silenciosamente — exactamente el
        anti-patrón que este PR resuelve."""
        # Construyo un qdata que SÍ debería emitir error de regrueso.
        # Si validate_despiece no incluye el check, no veríamos el error.
        qdata = {
            "regrueso": True,
            "regrueso_ml": 20.0,  # expected 1.0 m²
            "piece_details": [
                _piece("Frente regrueso", m2=2.0, qty=1),  # delta 1.0
            ],
            # Otros campos requeridos (mínimos para no romper otros checks).
            "material_currency": "ARS",
            "material_price_unit": None,
            "material_price_base": None,
        }
        result = validate_despiece(qdata)
        # Esperamos al menos un error con "Inconsistencia regrueso".
        regrueso_errors = [e for e in result.errors if "Inconsistencia regrueso" in e]
        assert len(regrueso_errors) == 1, (
            f"Esperaba 1 error de regrueso en pipeline, vi: {result.errors}"
        )
