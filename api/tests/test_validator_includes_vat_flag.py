"""Tests para PR #415 — validator skipea check IVA cuando mo_item
tiene `price_includes_vat: true`.

**Bug observado:** PR #414 hizo que `catalog_lookup` respete el flag
y devuelva `price_ars = price_ars_base` (mismo valor) cuando el JSON
dice `price_includes_vat: true`. Eso es correcto.

Pero el validador (`validation_tool._check_iva_mo`) seguía exigiendo
`unit_price == round(base × 1.21)`. Para el flete de Piñero
(base=100000, unit=100000) el validador fallaba con:

    IVA MO inconsistente en 'Flete + toma medidas Piñero':
    base=100000.0 × 1.21 → esperado=121000, actual=100000.0

Eso bloqueaba `generate_documents` y Sonnet caía a recalcular
cambiando "Piñero" por "Rosario" como "solución" (alucinación).

**Fix (3 cambios en cadena):**
  1. `catalog_lookup` propaga `price_includes_vat: true` al output.
  2. `calculator` copia el flag al `mo_item` cuando arma el flete.
  3. `validator` reconoce el flag: si está, exige `unit == base`
     (no `unit == base × 1.21`).

Tests cubren los 3 niveles:
  - catalog_lookup output incluye el flag.
  - calculator agrega flag al mo_item del flete.
  - validator pasa cuando flag está, sigue chequeando cuando no.
"""
from __future__ import annotations

import pytest

from app.modules.agent.tools.catalog_tool import catalog_lookup
from app.modules.agent.tools.validation_tool import _check_iva_mo
from app.modules.quote_engine.calculator import calculate_quote


# ═══════════════════════════════════════════════════════════════════════
# catalog_lookup propaga el flag
# ═══════════════════════════════════════════════════════════════════════


class TestCatalogLookupPropagatesFlag:
    def test_pinero_includes_flag_in_output(self):
        result = catalog_lookup("delivery-zones", "ENVPIÑERO")
        assert result.get("found") is True
        assert result.get("price_includes_vat") is True

    def test_canada_includes_flag(self):
        result = catalog_lookup("delivery-zones", "FLETE CAÑADA")
        assert result.get("found") is True
        assert result.get("price_includes_vat") is True

    def test_rosario_does_not_include_flag(self):
        """Items SIN el flag en JSON no deben tener `price_includes_vat`
        en el output (o tener False)."""
        result = catalog_lookup("delivery-zones", "ENVIOROS")
        assert result.get("found") is True
        # El field puede no estar (preferido) o estar como False.
        assert not result.get("price_includes_vat", False)


# ═══════════════════════════════════════════════════════════════════════
# Validador respeta el flag
# ═══════════════════════════════════════════════════════════════════════


class TestValidatorRespectsFlag:
    def test_pinero_flete_passes_validation(self):
        """Item de flete Piñero (base=100000, unit=100000, flag=true)
        debe pasar validación. Pre-#415 fallaba con 'IVA MO inconsistente'."""
        qdata = {
            "mo_items": [
                {
                    "description": "Flete + toma medidas Piñero",
                    "quantity": 3,
                    "unit_price": 100000,
                    "base_price": 100000,
                    "total": 300000,
                    "price_includes_vat": True,
                },
            ],
        }
        errors, warnings = _check_iva_mo(qdata)
        assert errors == [], (
            f"Esperaba sin errores cuando price_includes_vat=true. "
            f"Got errors={errors}"
        )

    def test_normal_flete_still_validated(self):
        """Item sin flag (Rosario, etc): validador sigue exigiendo
        unit == round(base × 1.21). Regression guard."""
        qdata = {
            "mo_items": [
                {
                    "description": "Flete + toma medidas Rosario",
                    "quantity": 1,
                    "unit_price": 52000,    # final con IVA
                    "base_price": 42975,    # sin IVA → × 1.21 ≈ 51999.75
                    "total": 52000,
                    # NO flag — debe validar.
                },
            ],
        }
        errors, warnings = _check_iva_mo(qdata)
        # 52000 ≈ round(42975 × 1.21) = round(51999.75) = 52000 ✓
        assert errors == []

    def test_normal_flete_with_wrong_unit_fails(self):
        """Si un item normal tiene unit_price mal calculado, sigue
        fallando (drift guard)."""
        qdata = {
            "mo_items": [
                {
                    "description": "MO Test",
                    "quantity": 1,
                    "unit_price": 1000,     # mal: debería ser ~1210
                    "base_price": 1000,
                    "total": 1000,
                    # NO flag.
                },
            ],
        }
        errors, warnings = _check_iva_mo(qdata)
        assert any("IVA MO inconsistente" in e for e in errors)

    def test_flag_true_with_unit_diff_from_base_fails(self):
        """Drift guard: si flag=true pero unit ≠ base, eso es bug del
        calculator/catalog_lookup → debe fallar."""
        qdata = {
            "mo_items": [
                {
                    "description": "Flete bug",
                    "quantity": 1,
                    "unit_price": 121000,   # mal: con flag=true debería ser igual al base
                    "base_price": 100000,
                    "total": 121000,
                    "price_includes_vat": True,
                },
            ],
        }
        errors, warnings = _check_iva_mo(qdata)
        assert any("price_includes_vat=true esperaba unit==base" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════
# End-to-end — calculator inyecta flag y validador lo respeta
# ═══════════════════════════════════════════════════════════════════════


class TestEndToEndPineroPasses:
    def test_pinero_quote_validates_clean(self):
        """Quote real con flete Piñero: el flujo completo (calculator
        agrega flete con flag → validador lo respeta) no debe generar
        `_validation_errors`. Regression del caso DYSCON post-#414."""
        result = calculate_quote({
            "client_name": "DYSCON Test",
            "project": "Test",
            "material": "Granito Negro Brasil",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Piñero",
            "plazo": "30 días",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "flete_qty": 3,
        })
        assert result["ok"] is True
        # El item del flete Piñero debe estar y tener el flag.
        flete_items = [
            m for m in result["mo_items"] if "piñero" in m["description"].lower()
        ]
        assert len(flete_items) == 1
        flete = flete_items[0]
        assert flete.get("price_includes_vat") is True
        assert flete["unit_price"] == 100000
        assert flete["total"] == 300000

        # Y NO debe haber errores de validación de IVA en el flete.
        validation_errors = result.get("_validation_errors") or []
        flete_errors = [e for e in validation_errors if "Piñero" in e or "piñero" in e]
        assert flete_errors == [], (
            f"Regresión PR #415: validador sigue fallando con flete Piñero. "
            f"Errors: {flete_errors}"
        )
