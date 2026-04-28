"""Tests para PR #405 — `quantity` en el parser textual.

Bug: cuando el operador pega un brief con piezas que declaran cantidad
multiplicada explícita ("× 24", "×2", etc.), el parser textual extraía
solo medidas por unidad y el dual_read mostraba `m² total = sum(m²/u)`
sin multiplicar. Caso real (DYSCON S.A. / Unidad Penal N°8 — Piñero,
quote 17052eac): operador declara 14 piezas con quantities `[24, 24,
1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2]` para total 42.39 m². El sistema
mostró 9.43 m² (suma de m²/u sin multiplicar).

Cobertura:
  - parsed_pieces_to_card respeta `quantity` del parser (default 1).
  - m2 del tramo = largo × prof × quantity.
  - Zócalo hereda quantity del tramo padre cuando el LLM no la pasa.
  - Zócalo respeta quantity propia si el LLM la pasó.
  - Total m² del sector = suma con quantities aplicadas.
  - Descripción del tramo lleva sufijo "(×N)" cuando quantity > 1.
  - Caso DYSCON exacto: 14 piezas → 42.39 m² total.
  - build_verified_context renderiza "× quantity = m² total" cuando >1.
  - Default (quantity=1 implícito): comportamiento idéntico a pre-#405.

NO se toca:
  - Calculator (ya respeta `quantity` cuando llega).
  - Path Dual Read del plano (sin quantity por diseño actual).
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.text_parser import parsed_pieces_to_card
from app.modules.quote_engine.dual_reader import build_verified_context


# ═══════════════════════════════════════════════════════════════════════
# parsed_pieces_to_card — propagación y multiplicación
# ═══════════════════════════════════════════════════════════════════════


class TestQuantityPropagation:
    def test_quantity_default_1_no_change(self):
        """Brief simple sin quantity → comportamiento idéntico a pre-#405.
        m2 = largo × prof; no aparece sufijo (×N) en descripción."""
        parsed = {
            "pieces": [
                {"description": "Mesada cocina", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo trasero", "largo": 2.0, "alto": 0.05},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        assert tramo["quantity"] == 1
        assert tramo["m2"]["valor"] == round(2.0 * 0.6, 2)  # 1.2
        assert "(×" not in tramo["descripcion"]
        # Zócalo hereda quantity=1.
        assert tramo["zocalos"][0]["quantity"] == 1

    def test_quantity_multiplies_m2(self):
        """quantity=24 → m2 = largo × prof × 24."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        assert tramo["quantity"] == 24
        # 1.92 × 0.60 = 1.152 → round 2 = 1.15. × 24 = 27.60.
        assert tramo["m2"]["valor"] == 27.6
        assert "(×24)" in tramo["descripcion"]
        # largo y ancho quedan POR UNIDAD (no multiplicados).
        assert tramo["largo_m"]["valor"] == 1.92
        assert tramo["ancho_m"]["valor"] == 0.6

    def test_zocalo_inherits_quantity_from_tramo(self):
        """Si el LLM extrajo quantity para la mesada pero no para el
        zócalo, el zócalo hereda la cantidad del tramo padre.
        Caso DYSCON: 24 mesadas → 24 zócalos."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                # zócalo SIN quantity → debe heredar 24.
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        assert tramo["quantity"] == 24
        assert len(tramo["zocalos"]) == 1
        assert tramo["zocalos"][0]["quantity"] == 24

    def test_zocalo_respects_explicit_quantity(self):
        """Si el LLM pasó quantity para el zócalo, respetarla (no
        sobrescribir con la del tramo padre)."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                # zócalo con quantity propia (raro pero posible).
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 12},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        tramo = card["sectores"][0]["tramos"][0]
        assert tramo["zocalos"][0]["quantity"] == 12

    def test_invalid_quantity_falls_back_to_1(self):
        """Si quantity viene como string, None, o número negativo →
        default 1 (no romper el flow)."""
        parsed = {
            "pieces": [
                {"description": "Mesada A", "largo": 2.0, "prof": 0.6, "quantity": "abc"},
                {"description": "Mesada B", "largo": 2.0, "prof": 0.6, "quantity": None},
                {"description": "Mesada C", "largo": 2.0, "prof": 0.6, "quantity": -5},
                {"description": "Mesada D", "largo": 2.0, "prof": 0.6, "quantity": 0},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        for tramo in card["sectores"][0]["tramos"]:
            assert tramo["quantity"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Total m² del sector — suma con quantities
# ═══════════════════════════════════════════════════════════════════════


class TestSectorTotal:
    def test_total_uses_multiplied_m2(self):
        """Total m² = sum(m² × quantity) tanto para mesadas como zócalos."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.0, "prof": 0.6, "quantity": 2},  # 0.60 × 2 = 1.20
                {"description": "M1 zócalo", "largo": 1.0, "alto": 0.10, "quantity": 2},  # 0.10 × 2 = 0.20
            ],
        }
        card = parsed_pieces_to_card(parsed)
        m2_total = card["sectores"][0]["m2_total"]["valor"]
        # 1.20 (mesada) + 0.20 (zócalo) = 1.40
        assert m2_total == 1.4

    def test_dyscon_full_case(self):
        """Caso real DYSCON — 14 piezas con quantities mixtas, total 42.39 m².
        Si esto rompe, el bug original volvió."""
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
        total = card["sectores"][0]["m2_total"]["valor"]
        # Esperado: 42.39 m² ± 0.02 (rounding floor en parser).
        # Cálculo del operador:
        #   Mesadas: 27.60 + 1.02 + 1.50 + 1.50 + 1.08 + 1.86 + 1.80 = 36.36
        #   Zócalos: 4.56 + 0.17 + 0.25 + 0.25 + 0.18 + 0.32 + 0.30 = 6.03
        #   Total: 42.39
        assert abs(total - 42.39) < 0.05, (
            f"Caso DYSCON regresión: total {total} vs esperado 42.39 "
            f"(delta {abs(total - 42.39):.2f})"
        )

    def test_total_without_quantity_unchanged(self):
        """Brief sin quantities (cocina particular) → total idéntico
        a pre-#405. Regression guard."""
        parsed = {
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},  # 1.20
                {"description": "Zócalo", "largo": 2.0, "alto": 0.05},  # 0.10
            ],
        }
        card = parsed_pieces_to_card(parsed)
        # 1.20 + 0.10 = 1.30
        assert card["sectores"][0]["m2_total"]["valor"] == 1.3


# ═══════════════════════════════════════════════════════════════════════
# verified_context — render del quantity para que Claude lo lea
# ═══════════════════════════════════════════════════════════════════════


class TestVerifiedContextRender:
    def test_render_with_quantity_includes_multiplier(self):
        """Cuando un tramo tiene quantity > 1, el verified_context debe
        renderizar `× N = m²_total` para que Claude pase quantity al
        calculate_quote.pieces[].quantity (NO un m²_override)."""
        parsed = {
            "pieces": [
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 24},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        ctx = build_verified_context(card)
        # Mesada: "× 24 = 27.6" debe aparecer.
        assert "× 24" in ctx
        assert "27.6" in ctx
        # Zócalo: "× 24" también.
        assert ctx.count("× 24") >= 2

    def test_render_without_quantity_unchanged(self):
        """Tramos con quantity=1 (default) → render idéntico a pre-#405:
        `largo × ancho = m²` (sin × N)."""
        parsed = {
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo", "largo": 2.0, "alto": 0.05},
            ],
        }
        card = parsed_pieces_to_card(parsed)
        ctx = build_verified_context(card)
        # Forma esperada: "Mesada: 2.0m × 0.6m = 1.2 m²" (sin × N).
        assert "× 1 =" not in ctx
        assert "1.2 m²" in ctx
