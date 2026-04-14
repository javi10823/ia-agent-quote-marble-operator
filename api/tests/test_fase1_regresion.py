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
