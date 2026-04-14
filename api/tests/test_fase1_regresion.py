"""Regresión Fase 1 — 4 casos que deben seguir andando bien.

Casos:
1. Texto solo — presupuesto estándar (material + MO + descuento)
2. Plano simple (baño) — 1 página, visión nativa
3. Planilla Estudio Munge (2 piezas independientes, Purastone)
4. Edificio ESH — caso tabular multitipología

Los 4 casos disparan calculate_quote() con inputs representativos.
Este archivo NO prueba el pipeline visual completo (eso es Fase 2).
"""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret-1234567890")
os.environ.setdefault("APP_ENV", "test")

from app.modules.quote_engine.calculator import calculate_quote


# ══════════════════════════════════════════════════════════════════
# CASO 1 — Texto solo: presupuesto estándar residencial
# ══════════════════════════════════════════════════════════════════

class TestFase1TextoSolo:
    """Operador pasa despiece por texto, Valentina calcula."""

    def test_caso1_residencial_con_descuento_arquitecta(self):
        """Arquitecta MUNGE → descuento 5% automático."""
        result = calculate_quote({
            "client_name": "ESTUDIO MUNGE",
            "project": "Cocina casa particular",
            "material": "Blanco Paloma",
            "catalog": "materials-purastone",
            "sku": "PALOMA",
            "pieces": [
                {"description": "Mesada cocina tramo 1", "largo": 1.55, "prof": 0.60},
                {"description": "Mesada cocina tramo 2", "largo": 1.72, "prof": 0.75},
                {"description": "Zócalo fondo tramo 1", "largo": 1.74, "alto": 0.07},
                {"description": "Zócalo fondo tramo 2", "largo": 1.55, "alto": 0.07},
                {"description": "Zócalo lateral derecho", "largo": 0.75, "alto": 0.07},
            ],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"] is True
        # Arquitecta detectada automáticamente → 5% USD
        assert result["discount_pct"] == 5, f"Expected 5% architect discount, got {result['discount_pct']}"
        assert result["material_currency"] == "USD"
        # m² debe estar cerca de 2.50
        assert abs(result["material_m2"] - 2.50) < 0.1, f"m² off: {result['material_m2']}"


# ══════════════════════════════════════════════════════════════════
# CASO 2 — Plano simple (baño, 1 página)
# ══════════════════════════════════════════════════════════════════

class TestFase1PlanoBano:
    """Baño simple: 1 vanitory + zócalo. calculate_quote con los pieces
    que Valentina extrae del plano."""

    def test_caso2_bano_simple(self):
        result = calculate_quote({
            "client_name": "Test Baño",
            "project": "Baño principal",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Vanitory", "largo": 1.20, "prof": 0.50},
                {"description": "Zócalo vanitory", "largo": 1.20, "alto": 0.05},
            ],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"] is True
        # 1.20 × 0.50 = 0.60 + 1.20 × 0.05 = 0.06 → 0.66 m²
        assert 0.6 < result["material_m2"] < 0.7, f"m² off: {result['material_m2']}"
        # Sin descuento (no es arquitecta, <6m²)
        assert result["discount_pct"] == 0


# ══════════════════════════════════════════════════════════════════
# CASO 3 — Planilla Estudio Munge (piezas independientes, Purastone)
# ══════════════════════════════════════════════════════════════════

class TestFase1EstudioMunge:
    """Planilla con 2 mesadas + 3 zócalos, Purastone Blanco Paloma.
    Verifica que el descuento de arquitecta aplique automáticamente
    y que las piezas no se asuman como L."""

    def test_caso3_munge_purastone_paloma(self):
        result = calculate_quote({
            "client_name": "ESTUDIO MUNGE",
            "project": "A1335",
            "material": "Purastone Blanco Paloma",
            "catalog": "materials-purastone",
            "sku": "PALOMA",
            "pieces": [
                # Dos mesadas INDEPENDIENTES (no L)
                {"description": "Mesada cocina A", "largo": 1.55, "prof": 0.60},
                {"description": "Mesada cocina B", "largo": 1.72, "prof": 0.75},
                {"description": "Zócalo A fondo", "largo": 1.55, "alto": 0.07},
                {"description": "Zócalo B fondo", "largo": 1.74, "alto": 0.07},
                {"description": "Zócalo B lateral", "largo": 0.75, "alto": 0.07},
            ],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_johnson",
            "pileta_sku": "LUXOR171",
            "plazo": "30 dias",
        })
        assert result["ok"] is True
        # Arquitecta → descuento 5% USD automático
        assert result["discount_pct"] == 5
        # Pileta Johnson LUXOR S171 se aplica
        sinks = result.get("sinks", [])
        assert sinks, "Expected sink product for empotrada_johnson"
        assert "LUXOR" in sinks[0]["name"].upper()
        # MO tiene PEGADOPILETA
        mo_descs = [m["description"].lower() for m in result["mo_items"]]
        assert any("pileta" in d for d in mo_descs), f"Missing PEGADOPILETA: {mo_descs}"


# ══════════════════════════════════════════════════════════════════
# CASO 4 — Edificio ESH (multitipología)
# ══════════════════════════════════════════════════════════════════

class TestFase1EdificioESH:
    """Edificio con múltiples tipologías DC-XX. Sin merma, sin colocación,
    flete por tipologías, descuento 18%."""

    def test_caso4_edificio_multi_tipologia(self):
        result = calculate_quote({
            "client_name": "Estudio 72 - Fideicomiso Ventus",
            "project": "Edificio",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "DC-02 mesada", "largo": 3.00, "prof": 1.00, "quantity": 2},
                {"description": "DC-03 mesada", "largo": 2.96, "prof": 1.00, "quantity": 6},
                {"description": "DC-04 mesada", "largo": 2.87, "prof": 1.00, "quantity": 8},
                {"description": "DC-05 mesada", "largo": 1.17, "prof": 1.00, "quantity": 1},
                {"description": "DC-06 mesada", "largo": 1.12, "prof": 1.00, "quantity": 1},
                {"description": "DC-07 mesada", "largo": 2.60, "prof": 1.00, "quantity": 6},
                {"description": "DC-08 mesada", "largo": 1.79, "prof": 1.00, "quantity": 1},
            ],
            "localidad": "Rosario",
            "colocacion": False,  # edificio sin colocación
            "pileta": "empotrada_cliente",
            "pileta_qty": 25,
            "is_edificio": True,
            "plazo": "120 dias",
            "discount_pct": 18,
        })
        assert result["ok"] is True
        # Edificio → no merma
        assert result["merma"]["aplica"] is False, f"Edificio NO debe tener merma: {result['merma']}"
        # 18% descuento material
        assert result["discount_pct"] == 18
        # Flete: 25 piezas / 6 per trip = 5 fletes
        flete_item = next((m for m in result["mo_items"] if "flete" in m["description"].lower()), None)
        assert flete_item is not None
        assert flete_item["quantity"] == 5, f"Flete debe ser 5, got {flete_item['quantity']}"
        # La leyenda "SE REALIZA EN 2 TRAMOS" NO debe aparecer
        labels = result["sectors"][0]["pieces"]
        assert not any("2 TRAMOS" in l for l in labels), (
            f"Edificio no debe tener '2 TRAMOS': {labels}"
        )


# ══════════════════════════════════════════════════════════════════
# MO commercial discount + flete excluded from all discounts
# ══════════════════════════════════════════════════════════════════

class TestMoDiscountAndFleteRules:
    """Regla comercial: descuento % sobre MO (excluye flete) + flete nunca
    recibe ningún descuento (ni ÷1.05 ni mo_discount)."""

    def test_mo_discount_excludes_flete(self):
        """Descuento 5% sobre MO aplica a pegado/anafe pero NO al flete."""
        result = calculate_quote({
            "client_name": "Edificio Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "DC-A mesada", "largo": 2.00, "prof": 0.60, "quantity": 4},
            ],
            "localidad": "Rosario",
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "pileta_qty": 4,
            "anafe": True,
            "is_edificio": True,
            "plazo": "120 dias",
            "discount_pct": 18,
            "mo_discount_pct": 5,
        })
        assert result["ok"] is True
        # mo_discount_amount reported
        assert result["mo_discount_pct"] == 5
        assert result["mo_discount_amount"] > 0
        # Flete NOT discounted — its total is still the raw catalog price.
        flete_item = next((m for m in result["mo_items"] if "flete" in m["description"].lower()), None)
        assert flete_item is not None
        # Flete no debe tener edificio_discount flag
        assert not flete_item.get("edificio_discount"), "Flete no debe tener ÷1.05"
        # Flete unit_price sigue siendo el del catálogo (no reducido)
        assert flete_item["unit_price"] == flete_item["total"] / flete_item["quantity"]

    def test_mo_discount_scope_invariant_dinale(self):
        """SCOPE INVARIANTE: el descuento MO SIEMPRE aplica a todo MO menos
        flete, sin importar cómo lo enuncie el brief.

        Caso DINALE 14/04/2026: brief dice 'Descuento 5% solo sobre PEGADOPILETA'
        + MO incluye PEGADOPILETA + FALDON + Flete. El descuento debe calcularse
        sobre PEGADOPILETA + FALDON (todo lo que no es flete), NO solo sobre
        PEGADOPILETA. Ver rules/quote-process-buildings.md → "Descuento
        comercial sobre MO" → SCOPE INVARIANTE.
        """
        result = calculate_quote({
            "client_name": "DINALE",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.00, "prof": 0.60, "quantity": 10},
            ],
            "localidad": "Rosario",
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "pileta_qty": 19,
            "frentin": True,
            "frentin_ml": 2.90,
            "is_edificio": True,
            "plazo": "4 meses",
            "mo_discount_pct": 5,
        })
        assert result["ok"] is True
        mo = result["mo_items"]
        descs = {m["description"].lower() for m in mo}
        # Debe haber al menos pegado + faldon + flete
        assert any("pegado" in d or "pileta" in d for d in descs), descs
        assert any(
            "faldon" in d or "faldón" in d or "frentin" in d or "frentín" in d
            for d in descs
        ), descs
        assert any("flete" in d for d in descs), descs

        # Suma esperada del descuento: 5% sobre (todo MO excepto flete)
        subtotal_excl_flete = sum(
            m["total"] for m in mo if "flete" not in m["description"].lower()
        )
        expected_disc = round(subtotal_excl_flete * 0.05)
        assert result["mo_discount_amount"] == expected_disc, (
            f"Scope invariant violated: discount should be 5% of ALL MO "
            f"except flete (={subtotal_excl_flete}) = {expected_disc}, "
            f"got {result['mo_discount_amount']}"
        )
        # Sanity: flete NO recibe descuento
        flete = next(m for m in mo if "flete" in m["description"].lower())
        assert not flete.get("edificio_discount")

    def test_no_mo_discount_when_zero(self):
        """Sin mo_discount_pct, mo_discount_amount = 0."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"] is True
        assert result.get("mo_discount_pct", 0) == 0
        assert result.get("mo_discount_amount", 0) == 0

    def test_edificio_paso2_shows_divide_105_column(self):
        """build_deterministic_paso2 para edificio muestra columna ÷1.05 y desc MO."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Edificio Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "DC-A mesada", "largo": 2.00, "prof": 0.60, "quantity": 4},
            ],
            "localidad": "Rosario",
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "pileta_qty": 4,
            "anafe": True,
            "is_edificio": True,
            "plazo": "120 dias",
            "discount_pct": 18,
            "mo_discount_pct": 5,
        })
        rendered = build_deterministic_paso2(result)
        assert "÷1.05" in rendered, "edificio paso2 debe mostrar columna ÷1.05"
        assert "Base s/IVA" in rendered, "edificio paso2 debe mostrar columna Base s/IVA"
        assert "Descuento 5% sobre MO" in rendered, (
            "edificio paso2 debe mostrar línea de descuento MO"
        )
        assert "excluye flete" in rendered.lower()


# ══════════════════════════════════════════════════════════════════
# End-to-end Ventus: quantity respected + anafe_qty + auto 18% edificio
# ══════════════════════════════════════════════════════════════════

class TestVentusEdificioEndToEnd:
    """Caso Ventus real: 25 tipologías DC, 25 anafes, 25 piletas,
    debe dar 66.57 m², descuento 18% auto, 5 fletes, anafe × 25."""

    def _ventus_input(self, **overrides):
        base = {
            "client_name": "Estudio 72",
            "project": "Fideicomiso Ventus",
            "material": "Silestone Blanco Norte",
            "pieces": [
                # 14 tipologías con quantity explícito
                {"description": "Mesada DC-02 fondo",        "largo": 1.43, "prof": 0.62, "quantity": 2},
                {"description": "Mesada DC-02 izquierdo",    "largo": 0.94, "prof": 0.62, "quantity": 2},
                {"description": "Mesada DC-02 derecho",      "largo": 1.86, "prof": 0.62, "quantity": 2},
                {"description": "Mesada DC-03 fondo",        "largo": 1.37, "prof": 0.62, "quantity": 6},
                {"description": "Mesada DC-03 izquierdo",    "largo": 0.94, "prof": 0.62, "quantity": 6},
                {"description": "Mesada DC-03 derecho",      "largo": 1.86, "prof": 0.62, "quantity": 6},
                {"description": "Mesada DC-04 recta 1",      "largo": 2.03, "prof": 0.62, "quantity": 8},
                {"description": "Mesada DC-04 recta 2",      "largo": 1.17, "prof": 0.78, "quantity": 8},
                {"description": "Mesada DC-05 único",        "largo": 1.88, "prof": 0.62, "quantity": 1},
                {"description": "Mesada DC-06 único",        "largo": 1.80, "prof": 0.62, "quantity": 1},
                {"description": "Mesada DC-07 izquierdo",    "largo": 1.96, "prof": 0.62, "quantity": 6},
                {"description": "Mesada DC-07 fondo",        "largo": 1.50, "prof": 0.62, "quantity": 6},
                {"description": "Mesada DC-07 derecho",      "largo": 0.96, "prof": 0.62, "quantity": 6},
                {"description": "Mesada DC-08 único",        "largo": 2.99, "prof": 0.60, "quantity": 1},
                # Zócalos
                {"description": "Zócalo DC-02", "largo": 5.47, "alto": 0.075, "quantity": 2},
                {"description": "Zócalo DC-03", "largo": 5.41, "alto": 0.075, "quantity": 6},
                {"description": "Zócalo DC-04", "largo": 3.98, "alto": 0.075, "quantity": 8},
                {"description": "Zócalo DC-05", "largo": 1.88, "alto": 0.075, "quantity": 1},
                {"description": "Zócalo DC-06", "largo": 1.80, "alto": 0.075, "quantity": 1},
                {"description": "Zócalo DC-07", "largo": 3.70, "alto": 0.075, "quantity": 6},
                {"description": "Zócalo DC-08", "largo": 3.59, "alto": 0.075, "quantity": 1},
            ],
            "localidad": "Rosario",
            "colocacion": False,
            "is_edificio": True,
            "pileta": "empotrada_cliente",
            "pileta_qty": 25,
            "anafe": True,
            "anafe_qty": 25,
            "plazo": "120 dias",
            "mo_discount_pct": 5,
        }
        base.update(overrides)
        return base

    def test_total_m2_respects_quantity(self):
        """Total m² debe ser 66.57 (no 16.13)."""
        result = calculate_quote(self._ventus_input())
        assert result["ok"] is True
        # Tolerance 0.5 m² para redondeos internos
        assert abs(result["material_m2"] - 66.57) < 0.5, (
            f"Expected ~66.57, got {result['material_m2']}"
        )

    def test_discount_edificio_auto_18(self):
        """Sin pasar discount_pct, edificio con ≥15 m² debe aplicar 18%."""
        result = calculate_quote(self._ventus_input())
        assert result["ok"] is True
        assert result["discount_pct"] == 18, (
            f"Auto edificio discount expected 18%, got {result['discount_pct']}"
        )

    def test_anafe_qty_25(self):
        """anafe_qty=25 debe producir MO item con quantity 25."""
        result = calculate_quote(self._ventus_input())
        anafe_item = next((m for m in result["mo_items"]
                           if "anafe" in m["description"].lower()), None)
        assert anafe_item is not None
        assert anafe_item["quantity"] == 25

    def test_flete_5_for_25_pieces(self):
        """25 piezas físicas / 6 per trip = ceil(25/6) = 5 fletes."""
        # NOTE: physical pieces for flete exclude zócalos. With qty:
        # 2+2+2+6+6+6+8+8+1+1+6+6+6+1 = 61 mesadas físicas → ceil(61/6)=11
        # The operator said 5 fletes in the message, but that was HIS estimate.
        # The calculator now counts 61 pieces correctly.
        result = calculate_quote(self._ventus_input())
        flete_item = next((m for m in result["mo_items"]
                           if "flete" in m["description"].lower()), None)
        assert flete_item is not None
        # 61 mesadas / 6 = ceil 11 fletes (correcto con quantity)
        import math
        expected = math.ceil(61 / 6)
        assert flete_item["quantity"] == expected, (
            f"Expected ceil(61/6)={expected}, got {flete_item['quantity']}"
        )

    def test_flete_not_discounted(self):
        """Flete NUNCA lleva ÷1.05 ni mo_discount."""
        result = calculate_quote(self._ventus_input())
        flete_item = next((m for m in result["mo_items"]
                           if "flete" in m["description"].lower()), None)
        assert not flete_item.get("edificio_discount"), (
            "Flete debe mantener precio sin ÷1.05"
        )
        # unit_price × qty debe dar total exacto
        assert flete_item["total"] == flete_item["unit_price"] * flete_item["quantity"]

    def test_flete_qty_operator_override(self):
        """Si el operador declara flete_qty, el calculator usa ese valor."""
        result = calculate_quote(self._ventus_input(flete_qty=5))
        flete_item = next((m for m in result["mo_items"]
                           if "flete" in m["description"].lower()), None)
        assert flete_item["quantity"] == 5, (
            f"Override flete_qty=5 ignorado, got {flete_item['quantity']}"
        )

    def test_flete_qty_override_zero_ignored(self):
        """flete_qty=0 o None NO debe usarse como override — usa cálculo automático."""
        result = calculate_quote(self._ventus_input(flete_qty=0))
        flete_item = next((m for m in result["mo_items"]
                           if "flete" in m["description"].lower()), None)
        # Cálculo automático: 61 piezas / 6 = ceil 11
        import math
        assert flete_item["quantity"] == math.ceil(61 / 6)

    def test_empotrada_johnson_without_sku_does_not_add_sink(self):
        """Si pileta=empotrada_johnson pero no hay pileta_sku, NO debe agregar
        QUADRA Q71A default (el bug Ventus)."""
        result = calculate_quote({
            "client_name": "Test sin producto",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_johnson",  # Johnson but NO sku → no product
            "plazo": "30 dias",
        })
        assert result["ok"] is True
        sinks = result.get("sinks", [])
        assert sinks == [], f"No sink product expected, got: {sinks}"

    def test_empotrada_cliente_never_adds_sink(self):
        """pileta=empotrada_cliente jamás agrega producto pileta."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"] is True
        assert result.get("sinks", []) == []

    def test_flete_qty_override_residential(self):
        """Override también funciona en residencial (no solo edificio)."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
            "flete_qty": 3,
        })
        flete_item = next((m for m in result["mo_items"]
                           if "flete" in m["description"].lower()), None)
        assert flete_item["quantity"] == 3
