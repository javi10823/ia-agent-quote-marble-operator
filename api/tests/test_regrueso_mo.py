"""Tests para PR #401 — M.O. de regrueso en el calculator.

Bug que arregla: PR #392 introdujo el detector + apply de respuestas
de regrueso en pending_questions, pero no agregó el bloque en
`calculate_quote` que convierte `regrueso_ml` → `mo_item` con SKU
REGRUESO. Resultado: cuando el operador pegaba un texto con
"M.O. REGRUESO frente 1x60,68ml" el regrueso quedaba registrado
en el dual_read pero **nunca aparecía como costo** en el Paso 2.

Cobertura:
  - regrueso=True + regrueso_ml=60.68 → mo_items contiene REGRUESO
    con qty=60.68 y unit_price del catálogo (13810.06).
  - Auto-detect: regrueso=True sin regrueso_ml + pieces con keyword
    "regrueso" → suma los largos.
  - Fallback: regrueso=True sin regrueso_ml ni keyword → 1 ml mínimo.
  - regrueso=False → no aparece en mo_items (regression guard).
  - regrueso preservado en el output snapshot (patch mode).
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import calculate_quote


# Helper — input mínimo válido para calculate_quote.
def _input(**overrides) -> dict:
    base = {
        "client_name": "Test Regrueso",
        "project": "Cocina",
        "material": "Silestone Blanco Norte",
        "pieces": [
            {"description": "Mesada", "largo": 2.0, "prof": 0.6},
        ],
        "localidad": "Rosario",
        "plazo": "30 días",
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════════
# Bloque principal — regrueso_ml → mo_item con SKU REGRUESO
# ═══════════════════════════════════════════════════════════════════════


class TestRegruesoMoItem:
    def test_regrueso_ml_explicit_creates_mo_item(self):
        """Caso del bug: 'M.O. REGRUESO frente 1x60,68ml' del texto fuente.
        El calculator debe convertirlo en un mo_item REGRUESO con qty=60.68
        y precio del catálogo (13810.06 ARS por ml)."""
        result = calculate_quote(_input(regrueso=True, regrueso_ml=60.68))
        assert result["ok"] is True

        regrueso_items = [
            m for m in result["mo_items"]
            if "regrueso" in m["description"].lower()
        ]
        assert len(regrueso_items) == 1, (
            f"Esperaba 1 mo_item de regrueso, encontré {len(regrueso_items)}: "
            f"{[m['description'] for m in result['mo_items']]}"
        )
        item = regrueso_items[0]
        # PR #403 — label canónico del repo (ver
        # `examples/quote-030-juan-carlos-negro-brasil.md:49`).
        # PR #401 había puesto "Regrueso frente" calcando mal del
        # frentín — el "frente" del brief era ubicación, no parte
        # del nombre. El operador lo señaló al revisar un quote.
        assert item["description"] == "Mano de obra regrueso x ml", (
            f"Label canónico distinto: {item['description']!r}. "
            f"Esperado: 'Mano de obra regrueso x ml' (ver ejemplo #030)."
        )
        assert item["quantity"] == 60.68
        # Precio del catálogo labor.json — 13810.06 ARS por ml (sin IVA).
        # El calculator aplica IVA ×1.21 → round(13810.06 * 1.21) = 16710
        # (regla de negocio CLAUDE.md: "ARS: round(price × 1.21)").
        # `base_price` queda como 13810.06 (sin IVA) para trazabilidad.
        assert item["unit_price"] == 16710, (
            f"Precio inesperado: {item['unit_price']}. "
            f"¿Se actualizó labor.json sin tocar el test? "
            f"(base ARS sin IVA esperado: 13810.06)"
        )
        assert item["base_price"] == 13810.06
        # total = round(unit_price * ml) = round(16710 * 60.68)
        assert item["total"] == round(16710 * 60.68)

    def test_regrueso_auto_detected_from_pieces(self):
        """Si `regrueso=True` pero `regrueso_ml` no se pasa, el calculator
        auto-detecta sumando largos de piezas con keyword 'regrueso'.
        Mismo patrón que el frentín."""
        result = calculate_quote(_input(
            regrueso=True,
            pieces=[
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Regrueso frente", "largo": 1.5, "prof": 0.05},
                {"description": "Regrueso lateral", "largo": 0.6, "prof": 0.05},
            ],
        ))
        assert result["ok"] is True
        regrueso_items = [
            m for m in result["mo_items"]
            if "regrueso" in m["description"].lower()
        ]
        assert len(regrueso_items) == 1
        # Suma de largos: 1.5 + 0.6 = 2.1 ml.
        assert regrueso_items[0]["quantity"] == 2.1

    def test_regrueso_fallback_minimum_1ml(self):
        """`regrueso=True` sin `regrueso_ml` y sin piezas marcadas →
        fallback de 1 ml. Para no perder silenciosamente la línea —
        el operador la ve en el Paso 2 y puede corregirla."""
        result = calculate_quote(_input(regrueso=True))
        regrueso_items = [
            m for m in result["mo_items"]
            if "regrueso" in m["description"].lower()
        ]
        assert len(regrueso_items) == 1
        assert regrueso_items[0]["quantity"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Regression guards
# ═══════════════════════════════════════════════════════════════════════


class TestRegruesoRegressionGuards:
    def test_no_regrueso_means_no_mo_item(self):
        """Sin regrueso, no aparece. Defensa contra que el bloque se
        active por accidente (ej: keyword 'regrueso' en una pieza pero
        sin flag explícita)."""
        result = calculate_quote(_input())
        regrueso_items = [
            m for m in result["mo_items"]
            if "regrueso" in m["description"].lower()
        ]
        assert regrueso_items == []

    def test_regrueso_false_with_ml_set_skips_item(self):
        """Si por alguna razón viene `regrueso=False` pero
        `regrueso_ml=10`, NO se debe agregar el mo_item — el flag
        manda. Esto previene que un patch parcial active un costo
        que el operador no pidió."""
        result = calculate_quote(_input(regrueso=False, regrueso_ml=10))
        regrueso_items = [
            m for m in result["mo_items"]
            if "regrueso" in m["description"].lower()
        ]
        assert regrueso_items == []

    def test_regrueso_persisted_in_output_snapshot(self):
        """El output del calculator debe incluir `regrueso` y `regrueso_ml`
        para que el patch mode (re-cálculo) los preserve. Sin esto, un
        derive_material perdería el regrueso del original."""
        result = calculate_quote(_input(regrueso=True, regrueso_ml=60.68))
        assert result["regrueso"] is True
        assert result["regrueso_ml"] == 60.68

    def test_regrueso_independent_from_frentin(self):
        """Regrueso y frentín son independientes — pedir uno no afecta
        al otro. Defense contra lógica copy-paste que confunde campos."""
        result = calculate_quote(_input(
            regrueso=True, regrueso_ml=2.0,
            frentin=False,
        ))
        descriptions = [m["description"].lower() for m in result["mo_items"]]
        assert any("regrueso" in d for d in descriptions)
        assert not any("armado frentín" in d or "armado frentin" in d for d in descriptions)

    def test_regrueso_suma_m2_al_material(self):
        """El regrueso consume material como un canto de 5cm de alto
        (análogo al zócalo). `material_m2` debe incluir `regrueso_ml × 0.05`
        — antes solo se cobraba la MO, el material quedaba subfacturado.

        Caso del bug: 42.39 m² de mesadas + 60.68 ml de regrueso →
        material_m2 esperado = 42.39 + 3.034 = 45.424."""
        base_pieces = [{"description": "Mesada", "largo": 7.065, "prof": 6.0, "quantity": 1}]

        sin = calculate_quote(_input(pieces=base_pieces))
        con = calculate_quote(_input(pieces=base_pieces, regrueso=True, regrueso_ml=60.68))

        assert sin["material_m2"] == 42.39
        assert con["material_m2"] == 45.424, (
            f"material_m2 debería sumar 60.68 × 0.05 = 3.034 al base. "
            f"Obtuve {con['material_m2']}, esperaba 45.424."
        )
        assert con["material_total"] > sin["material_total"], (
            "El total de material con regrueso debe ser mayor — el regrueso "
            "consume m² adicional que se multiplica por price_unit."
        )
