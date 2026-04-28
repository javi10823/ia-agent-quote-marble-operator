"""Tests para PR #407 — `pileta_qty` derivado de mesadas en edificios
cuando la pileta fue auto-inyectada por el guardrail mo-list-authority.

**Bug:** caso DYSCON (32 mesadas con quantities mixtas) cobraba
"Agujero y pegado pileta" qty=1, debería ser qty=32. La causa: el
auto-count del edificio guardrail (calculator.py:946) solo busca
keywords ["pileta", "bacha", "lavatorio", "kitchenette", ...] en las
descripciones; las descripciones DYSCON ("M1 mesada", "M2 mesada
(Office 32)") no las tienen. Y aun si las tuviera, contaba 1 por
línea ignorando `p.quantity`.

Fix con dos cambios:

1. **Bug A:** el sum del auto-count usa `quantity` en vez de 1. Si una
   pieza con keyword tiene `quantity=10`, cuenta 10, no 1.

2. **Bug B (acotado por origen):** si la pileta fue **auto-inyectada
   por el guardrail mo-list-authority** (`agent.py:5469`, marcado con
   `_pileta_inferred_by_guardrail=True`) y NO hay match por keyword,
   asumir que cada mesada lleva pileta — `pileta_qty = sum(mesadas
   .quantity)`. Excluye zócalos / frentín / regrueso / alzada / faldón.

**Precedencia (de mayor a menor):**
  1. `pileta_qty > 1` explícito del operador → respeta.
  2. Auto-count por keywords → respeta.
  3. Fallback "todas las mesadas" — solo si flag de origen está.
  4. Default `pileta_qty=1`.

**Lo que NO toca:**
  - Cálculo del material o del regrueso (intactos).
  - Path Dual Read del plano (sin quantity por diseño).
  - Residencial simple (no es_edificio → no entra al guardrail).
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import calculate_quote


def _input(**overrides) -> dict:
    base = {
        "client_name": "Test Pileta",
        "project": "Edificio",
        "material": "Granito Gris Mara",
        "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        "localidad": "Rosario",
        "plazo": "30 días",
    }
    base.update(overrides)
    return base


def _qty_of(item_desc: str, mo_items: list) -> int | float:
    """Devuelve la quantity del primer mo_item cuya descripción matchea."""
    for m in mo_items:
        if item_desc.lower() in m["description"].lower():
            return m["quantity"]
    return 0


# ═══════════════════════════════════════════════════════════════════════
# Caso DYSCON — pileta auto-inyectada + 14 mesadas con quantities mixtas
# ═══════════════════════════════════════════════════════════════════════


class TestDysconPiletaQtyFromMesadas:
    def test_dyscon_pileta_qty_equals_32(self):
        """Caso del bug: edificio con pileta auto-inyectada por
        mo-list-authority + 14 piezas con quantities mixtas → debe
        cobrar 32 piletas (suma de mesadas físicas)."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            _pileta_inferred_by_guardrail=True,  # flag del guardrail
            colocacion=False,
            pieces=[
                {"description": "M1 mesada", "largo": 1.92, "prof": 0.6, "quantity": 24},
                {"description": "M1 zócalo atrás", "largo": 1.92, "prof": 0.1, "quantity": 24},
                {"description": "M2 mesada (Office 32)", "largo": 1.7, "prof": 0.6, "quantity": 1},
                {"description": "M2 zócalo atrás", "largo": 1.7, "prof": 0.1, "quantity": 1},
                {"description": "M3 mesada (Office 12)", "largo": 2.5, "prof": 0.6, "quantity": 1},
                {"description": "M3 zócalo atrás", "largo": 2.5, "prof": 0.1, "quantity": 1},
                {"description": "M4 mesada (Office 27)", "largo": 2.5, "prof": 0.6, "quantity": 1},
                {"description": "M4 zócalo atrás", "largo": 2.5, "prof": 0.1, "quantity": 1},
                {"description": "M5 mesada (Office 53)", "largo": 1.8, "prof": 0.6, "quantity": 1},
                {"description": "M5 zócalo atrás", "largo": 1.8, "prof": 0.1, "quantity": 1},
                {"description": "M6 mesada (Office 80/83)", "largo": 1.55, "prof": 0.6, "quantity": 2},
                {"description": "M6 zócalo atrás", "largo": 1.55, "prof": 0.1, "quantity": 2},
                {"description": "M7 mesada (Office 87/90)", "largo": 1.5, "prof": 0.6, "quantity": 2},
                {"description": "M7 zócalo atrás", "largo": 1.5, "prof": 0.1, "quantity": 2},
            ],
        ))
        assert result["ok"] is True
        # Suma de mesadas: 24 + 1 + 1 + 1 + 1 + 2 + 2 = 32.
        assert result["pileta_qty"] == 32, (
            f"Caso DYSCON regresión: pileta_qty={result['pileta_qty']} "
            f"esperaba 32 (suma de mesada quantities)"
        )
        assert _qty_of("agujero y pegado pileta", result["mo_items"]) == 32


# ═══════════════════════════════════════════════════════════════════════
# Precedencia — el override del operador siempre gana
# ═══════════════════════════════════════════════════════════════════════


class TestPrecedence:
    def test_operator_explicit_qty_1_respected(self):
        """Si el operador pasa `pileta_qty=1` explícito en un edificio
        grande con muchas mesadas (NO viene del guardrail), respetar
        esa decisión — no aplicar el fallback. Caso real: edificio
        con 1 sola pileta general en una sala común."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            pileta_qty=1,
            # IMPORTANTE: sin _pileta_inferred_by_guardrail flag → operador
            # declaró explícitamente.
            colocacion=False,
            pieces=[
                {"description": "M1 mesada", "largo": 2.0, "prof": 0.6, "quantity": 30},
            ],
        ))
        # NO debe escalar — operador dijo 1.
        assert result["pileta_qty"] == 1
        assert _qty_of("agujero y pegado pileta", result["mo_items"]) == 1

    def test_operator_explicit_qty_5_respected(self):
        """Override manual con qty>1 — respetar."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            pileta_qty=5,
            _pileta_inferred_by_guardrail=True,  # incluso con flag, qty>1 manda.
            colocacion=False,
            pieces=[
                {"description": "M1 mesada", "largo": 2.0, "prof": 0.6, "quantity": 30},
            ],
        ))
        assert result["pileta_qty"] == 5

    def test_keyword_match_takes_precedence_over_fallback(self):
        """Si hay piezas con keyword (lavatorio, kitchenette, etc.)
        + flag del guardrail, el auto-count keyword toma precedencia.
        El fallback NO se activa (tiene un `elif`).

        Nota sobre el filtro de keywords: el matcher es substring-based
        — `"pileta"` matchea cualquier descripción que contenga esa
        palabra, incluyendo casos como `"Mesada sin pileta"`. Ese es
        un bug latente del filtro original (pre-#407), no scope de
        este PR. Por eso el test usa descripciones sin la palabra
        "pileta" para aislar el comportamiento del fallback."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            _pileta_inferred_by_guardrail=True,
            colocacion=False,
            pieces=[
                {"description": "Lavatorio baño", "largo": 1.5, "prof": 0.6, "quantity": 10},
                # Mesadas adicionales SIN keyword (ni "pileta" ni "bacha"
                # ni "lavatorio" ni "kitchenette") — el filtro keyword
                # no las cuenta.
                {"description": "M1 mesada cocina", "largo": 2.0, "prof": 0.6, "quantity": 50},
            ],
        ))
        # Auto-count keyword: 10 (de lavatorio × quantity).
        # Fallback NO entra porque keyword devolvió >1.
        assert result["pileta_qty"] == 10, (
            f"Esperaba qty=10 (keyword match con quantity), got "
            f"{result['pileta_qty']}. Fallback no debería activarse cuando "
            f"keyword match resolvió."
        )


# ═══════════════════════════════════════════════════════════════════════
# Regression — residencial / sin pileta / sin flag
# ═══════════════════════════════════════════════════════════════════════


class TestNoRegression:
    def test_residential_simple_qty_1(self):
        """is_edificio=False → no entra al guardrail → respeta qty
        default. Cocina particular con 1 pileta."""
        result = calculate_quote(_input(
            is_edificio=False,
            pileta="empotrada_cliente",
            # Sin flag, sin quantity multipliers.
            pieces=[{"description": "Mesada cocina", "largo": 2.0, "prof": 0.6}],
        ))
        assert result["pileta_qty"] == 1
        assert _qty_of("agujero y pegado pileta", result["mo_items"]) == 1

    def test_no_pileta_no_item(self):
        """Sin pileta seteada → no aparece el mo_item."""
        result = calculate_quote(_input(
            is_edificio=True,
            # pileta=None
            colocacion=False,
            pieces=[{"description": "M1 mesada", "largo": 2.0, "prof": 0.6, "quantity": 10}],
        ))
        assert _qty_of("agujero y pegado pileta", result["mo_items"]) == 0

    def test_edificio_without_guardrail_flag_stays_at_1(self):
        """Edificio con pileta declarada por el operador (sin flag) +
        descripciones sin keyword + mesadas con quantity → respeta
        pileta_qty=1. El fallback solo se activa con el flag."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            # Sin _pileta_inferred_by_guardrail.
            colocacion=False,
            pieces=[
                {"description": "M1 mesada", "largo": 2.0, "prof": 0.6, "quantity": 10},
            ],
        ))
        # No keyword match + sin flag → no fallback → qty default 1.
        assert result["pileta_qty"] == 1, (
            f"Sin flag de guardrail, no debe activarse fallback. "
            f"Got qty={result['pileta_qty']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Bug A — el sum ahora respeta quantity (no cuenta 1 por línea)
# ═══════════════════════════════════════════════════════════════════════


class TestKeywordSumUsesQuantity:
    def test_keyword_sum_uses_quantity_not_lines(self):
        """1 línea con keyword 'lavatorio' y quantity=10 → pileta_qty=10
        (no 1 como antes del fix)."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            colocacion=False,
            pieces=[
                {"description": "Lavatorio baño tipo A", "largo": 1.5, "prof": 0.6, "quantity": 10},
            ],
        ))
        assert result["pileta_qty"] == 10

    def test_keyword_sum_multiple_lines(self):
        """Múltiples líneas con keywords y quantities mixtas → suma todas."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            colocacion=False,
            pieces=[
                {"description": "Lavatorio tipo A", "largo": 1.5, "prof": 0.6, "quantity": 10},
                {"description": "Lavatorio tipo B", "largo": 1.7, "prof": 0.6, "quantity": 5},
                {"description": "Kitchenette tipo C", "largo": 1.2, "prof": 0.6, "quantity": 3},
            ],
        ))
        # 10 + 5 + 3 = 18.
        assert result["pileta_qty"] == 18


# ═══════════════════════════════════════════════════════════════════════
# Bug B — el fallback excluye zócalos / frentín / regrueso / alzada
# ═══════════════════════════════════════════════════════════════════════


class TestFallbackExcludesNonMesadaPieces:
    def test_fallback_excludes_zocalos(self):
        """El fallback solo cuenta mesadas; zócalos no llevan pileta."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            _pileta_inferred_by_guardrail=True,
            colocacion=False,
            pieces=[
                {"description": "M1 mesada", "largo": 2.0, "prof": 0.6, "quantity": 10},
                # Zócalos NO deben contarse aunque tengan "mesada" en la descripción.
                {"description": "M1 zócalo atrás", "largo": 2.0, "prof": 0.1, "quantity": 10},
            ],
        ))
        # Solo cuenta la mesada (10), no el zócalo.
        assert result["pileta_qty"] == 10

    def test_fallback_excludes_frentin_regrueso_alzada(self):
        """Frentín, regrueso, alzada y faldón también se excluyen del
        fallback aunque su descripción contenga 'mesada' por algún motivo."""
        result = calculate_quote(_input(
            is_edificio=True,
            pileta="empotrada_cliente",
            _pileta_inferred_by_guardrail=True,
            colocacion=False,
            pieces=[
                {"description": "M1 mesada", "largo": 2.0, "prof": 0.6, "quantity": 5},
                {"description": "M1 mesada frentín", "largo": 2.0, "alto": 0.05, "quantity": 5},
                {"description": "M1 mesada regrueso", "largo": 2.0, "alto": 0.03, "quantity": 5},
                {"description": "Alzada cocina mesada", "largo": 2.0, "alto": 0.1, "quantity": 5},
            ],
        ))
        # Solo cuenta la mesada principal — 5.
        assert result["pileta_qty"] == 5
