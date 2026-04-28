"""Tests para PR #408 + #409 — `m2` del zócalo con regla
round-unit-then-multiply usando `_round_half_up`.

**Bug original (#408):** PR #405 propagó `quantity` al zócalo como
metadata pero no calculó un campo `m2` propio. La card editable
mostraba `ml × alto_m` sin multiplicar — caso DYSCON: total 37.71
en vez de 42.39.

**Bug de redondeo (#409):** PR #408 usó `round(ml × alto × qty, 2)`
(multiply-then-round) → M1 ×24 daba 4.61 cuando el operador esperaba
4.56. Política unificada del operador, alineada con calculator:

    m²/u  = round_half_up(base, 2)
    m²    = round_half_up(m²/u × quantity, 2)

Casos esperados (DYSCON):
  - M1: 1.92 × 0.10 = 0.192 → round_half_up=0.19 → × 24 = 4.56
  - M6: 1.55 × 0.10 = 0.155 → round_half_up=0.16 → × 2  = 0.32
  - M7: 1.50 × 0.10 = 0.150 → round_half_up=0.15 → × 2  = 0.30
  - Total sector ≈ 42.39 m²

Garantías post-#409:
  - Backend (text_parser) usa `_round_half_up` (importado de
    calculator).
  - Frontend (DualReadResult.tsx) usa `roundHalfUp` JS espejo.
  - Ambos producen los mismos números que `calculate_m2:717-719`.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.text_parser import parsed_pieces_to_card


# ═══════════════════════════════════════════════════════════════════════
# Zócalo con quantity explícita del LLM
# ═══════════════════════════════════════════════════════════════════════


class TestZocaloM2WithExplicitQuantity:
    def test_zocalo_m2_field_multiplied_round_half_up(self):
        """PR #409: M1 zócalo con quantity=24 debe usar
        round-unit-then-multiply: 0.19/u × 24 = 4.56 (no 4.61
        de multiply-then-round que tenía #408)."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 24},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        zocalo = card["sectores"][0]["tramos"][0]["zocalos"][0]
        # 1.92 × 0.10 = 0.192 → round_half_up=0.19 → × 24 = 4.56.
        assert zocalo["m2"] == 4.56, (
            f"PR #409 regresión: m² del zócalo M1 = {zocalo['m2']}, "
            f"esperaba 4.56 (round-unit-then-multiply con _round_half_up)"
        )
        assert zocalo["quantity"] == 24
        # Sufijo (×24) en el lado.
        assert "(×24)" in zocalo["lado"], (
            f"Falta sufijo (×24) en lado: {zocalo['lado']!r}"
        )

    def test_zocalo_quantity_1_no_suffix(self):
        """Zócalo con quantity=1 (default) → m² sin multiplicar y sin
        sufijo. Caso residencial simple."""
        parsed = {
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo trasero", "largo": 2.0, "alto": 0.05},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        zocalo = card["sectores"][0]["tramos"][0]["zocalos"][0]
        # 2.0 × 0.05 × 1 = 0.10.
        assert zocalo["m2"] == 0.10
        assert zocalo["quantity"] == 1
        assert "(×" not in zocalo["lado"], (
            f"No debe haber sufijo (×N) cuando quantity=1: {zocalo['lado']!r}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Zócalo que hereda quantity del tramo padre
# ═══════════════════════════════════════════════════════════════════════


class TestZocaloInheritedQuantity:
    def test_zocalo_inherits_and_recomputes_m2(self):
        """Mesada con quantity=24 + zócalo SIN quantity explícita →
        zócalo hereda 24, m² se recomputa con la quantity heredada."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                # Zócalo SIN quantity → debe heredar 24 del tramo.
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        zocalo = card["sectores"][0]["tramos"][0]["zocalos"][0]
        assert zocalo["quantity"] == 24
        # PR #409: m² recomputed con round-unit-then-multiply.
        # 0.19/u × 24 = 4.56 (no 4.61).
        assert zocalo["m2"] == 4.56
        # Sufijo agregado en herencia.
        assert "(×24)" in zocalo["lado"]


# ═══════════════════════════════════════════════════════════════════════
# Caso DYSCON exacto — total visible 42.39
# ═══════════════════════════════════════════════════════════════════════


class TestDysconTotalMatchesBackend:
    def test_dyscon_zocalos_contribute_full_m2(self):
        """Caso real DYSCON. Si los zócalos M1×24, M6×2, M7×2 se
        renderizaran con m²/u (bug pre-#408), el total del sector
        sería 37.71. Con el fix, suma 42.39."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.60, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 24},
                {"description": "M2 mesada (Office 32)", "largo": 1.70, "prof": 0.60, "quantity": 1},
                {"description": "M2 zócalo atrás", "largo": 1.70, "alto": 0.10, "quantity": 1},
                {"description": "M3 mesada (Office 12)", "largo": 2.50, "prof": 0.60, "quantity": 1},
                {"description": "M3 zócalo atrás", "largo": 2.50, "alto": 0.10, "quantity": 1},
                {"description": "M4 mesada (Office 27)", "largo": 2.50, "prof": 0.60, "quantity": 1},
                {"description": "M4 zócalo atrás", "largo": 2.50, "alto": 0.10, "quantity": 1},
                {"description": "M5 mesada (Office 53)", "largo": 1.80, "prof": 0.60, "quantity": 1},
                {"description": "M5 zócalo atrás", "largo": 1.80, "alto": 0.10, "quantity": 1},
                {"description": "M6 mesada (Office 80/83)", "largo": 1.55, "prof": 0.60, "quantity": 2},
                {"description": "M6 zócalo atrás", "largo": 1.55, "alto": 0.10, "quantity": 2},
                {"description": "M7 mesada (Office 87/90)", "largo": 1.50, "prof": 0.60, "quantity": 2},
                {"description": "M7 zócalo atrás", "largo": 1.50, "alto": 0.10, "quantity": 2},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        sector = card["sectores"][0]
        total = sector["m2_total"]["valor"]

        # PR #409 — Total esperado exacto del operador: 42.39 m².
        # Round-unit-then-multiply con _round_half_up es la regla.
        assert total == 42.39, (
            f"PR #409 regresión: total sector = {total}, esperaba 42.39 "
            f"(suma exacta del operador con round_half_up unitario)"
        )

        # Verificar que los zócalos clave tienen m² correcto.
        # Tramos = solo mesadas (zócalos van como child). 7 mesadas:
        # M1[0], M2[1], M3[2], M4[3], M5[4], M6[5], M7[6].
        # PR #409 — round-unit-then-multiply con _round_half_up:
        # M1: round_half_up(1.92×0.10, 2)=0.19 × 24 = 4.56.
        # M6: round_half_up(1.55×0.10, 2)=0.16 × 2  = 0.32.
        # M7: round_half_up(1.50×0.10, 2)=0.15 × 2  = 0.30.
        m1_zocalo = sector["tramos"][0]["zocalos"][0]
        m6_zocalo = sector["tramos"][5]["zocalos"][0]
        m7_zocalo = sector["tramos"][6]["zocalos"][0]
        assert m1_zocalo["m2"] == 4.56, f"M1 zócalo = {m1_zocalo['m2']}, esperaba 4.56"
        assert m6_zocalo["m2"] == 0.32, f"M6 zócalo = {m6_zocalo['m2']}, esperaba 0.32 (half-up)"
        assert m7_zocalo["m2"] == 0.30, f"M7 zócalo = {m7_zocalo['m2']}, esperaba 0.30"


# ═══════════════════════════════════════════════════════════════════════
# PR #409 — política unificada round_half_up unitario primero
# ═══════════════════════════════════════════════════════════════════════


class TestRoundHalfUpPolicy:
    def test_half_up_breaks_python_banker_rounding(self):
        """Caso clave: M6 zócalo. `round(0.155, 2)` con banker's de
        Python da 0.15 (no 0.16). El operador requiere half-up = 0.16."""
        parsed = {
            "pieces": [
                {"description": "M6 mesada", "largo": 1.55, "prof": 0.6, "quantity": 2},
                {"description": "M6 zócalo atrás", "largo": 1.55, "alto": 0.10, "quantity": 2},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        zocalo = card["sectores"][0]["tramos"][0]["zocalos"][0]
        # round_half_up(0.155, 2) = 0.16. × 2 = 0.32.
        # Si esto rompe a 0.30, alguien volvió a `round()` (banker's).
        assert zocalo["m2"] == 0.32, (
            f"M6 zócalo m² = {zocalo['m2']}, esperaba 0.32. "
            f"Si volvió a 0.30, regresión: alguien revertió `_round_half_up` "
            f"a `round()` (banker's de Python). El operador requiere "
            f"half-up: 0.155 → 0.16 (no 0.15)."
        )

    def test_mesada_uses_round_half_up_too(self):
        """Mesada también usa round-unit-then-multiply para mantener
        consistencia con zócalos y calculator."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        # 1.92 × 0.60 = 1.152 → round_half_up=1.15 → × 24 = 27.60.
        assert tramo["m2"]["valor"] == 27.60, (
            f"M1 mesada m² = {tramo['m2']['valor']}, esperaba 27.60"
        )
