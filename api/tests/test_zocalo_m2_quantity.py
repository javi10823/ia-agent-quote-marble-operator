"""Tests para PR #408 — `m2` propio del zócalo y sufijo `(×N)` en `lado`.

**Bug:** PR #405 propagó `quantity` al zócalo como metadata pero:
  - El backend no calculó un campo `m2` propio del zócalo (solo lo
    hizo para el tramo).
  - El display del `lado` del zócalo no llevaba sufijo `(×N)`
    cuando quantity > 1 (a diferencia del tramo, que sí lo lleva).

Resultado: la card editable del frontend renderizaba el m² del
zócalo como `ml × alto_m` sin multiplicar por quantity → caso DYSCON
mostraba 37.71 m² en vez de 42.39 (faltaban los 4.68 m² de los
zócalos M1×24, M6×2 y M7×2).

Fix:
  1. Agregar `m2 = ml × alto × quantity` al zócalo (consistente con
     `tramo.m2.valor` ya multiplicado).
  2. Sufijo `(×N)` al `lado` cuando quantity > 1.
  3. Cuando se hereda quantity del tramo padre (tramo qty>1, zócalo
     qty=1 default), recomputar `m2` y agregar sufijo.
  4. `m2_total_valor` del sector ahora suma `z.m2` (fuente única).

Nota: el frontend (`DualReadResult.tsx`) también se modifica para
multiplicar `ml × alto × quantity` al renderizar — sin esto el bug
visual del despiece persiste aunque el backend tenga los números
correctos.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.text_parser import parsed_pieces_to_card


# ═══════════════════════════════════════════════════════════════════════
# Zócalo con quantity explícita del LLM
# ═══════════════════════════════════════════════════════════════════════


class TestZocaloM2WithExplicitQuantity:
    def test_zocalo_m2_field_multiplied(self):
        """Zócalo con quantity=24 debe llevar `m2 = ml × alto × 24`."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 24},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        zocalo = card["sectores"][0]["tramos"][0]["zocalos"][0]
        # 1.92 × 0.10 × 24 = 4.608 → round(2) = 4.61.
        assert zocalo["m2"] == 4.61, (
            f"Esperaba m² del zócalo = 4.61, got {zocalo['m2']}"
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
        # m² recomputed con la quantity heredada.
        assert zocalo["m2"] == 4.61
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

        # Sum esperado = mesadas (36.36) + zócalos multiplicados (6.04) ≈ 42.40.
        # Tolerancia por rounding floor del parser (0.10).
        assert 42.30 <= total <= 42.45, (
            f"Total sector regresión: {total} fuera del rango esperado "
            f"(42.30-42.45). Caso DYSCON debe sumar ~42.39."
        )

        # Verificar que los zócalos clave tienen m² correcto.
        # Tramos = solo mesadas (zócalos van como child). 7 mesadas:
        # M1[0], M2[1], M3[2], M4[3], M5[4], M6[5], M7[6].
        # M1: 1.92 × 0.10 × 24 = 4.608 → 4.61.
        # M6: 1.55 × 0.10 × 2 = 0.310 → 0.31.
        # M7: 1.50 × 0.10 × 2 = 0.300 → 0.30.
        m1_zocalo = sector["tramos"][0]["zocalos"][0]
        m6_zocalo = sector["tramos"][5]["zocalos"][0]
        m7_zocalo = sector["tramos"][6]["zocalos"][0]
        assert m1_zocalo["m2"] == 4.61
        assert m6_zocalo["m2"] == 0.31
        assert m7_zocalo["m2"] == 0.30
