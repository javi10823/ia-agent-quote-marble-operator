"""Tests para PR #414 — `catalog_lookup` respeta `price_includes_vat: true`.

**Bug observado:** Caso DYSCON cobraba el flete de Piñero a $121.000
cuando el catálogo dice $100.000 (con IVA ya incluido). Mismo bug
para Cañada de Gómez ($272.250 vs $225.000) y Alvear ($36.300 vs
$30.000).

Causa raíz: `catalog_tool.py:catalog_lookup` aplicaba `round(price_ars
× 1.21)` SIEMPRE, ignorando el flag `price_includes_vat: true` del
item. Cuando ese flag está, el precio del JSON YA es el final con
IVA y NO debe re-multiplicarse.

Items afectados hoy (todos en `delivery-zones.json`):
  - ENVPIÑERO    — $100.000
  - FLETE CAÑADA — $225.000
  - ENVALV       — $30.000

Fix: chequear `item.get("price_includes_vat")` antes de aplicar IVA.
Si es `True`, devolver `price_ars` / `price_usd` tal cual del JSON.
"""
from __future__ import annotations

import pytest

from app.modules.agent.tools.catalog_tool import catalog_lookup


# ═══════════════════════════════════════════════════════════════════════
# Items con price_includes_vat: true — NO se multiplica
# ═══════════════════════════════════════════════════════════════════════


class TestPriceIncludesVatRespected:
    def test_pinero_returns_100000_not_121000(self):
        """Piñero: precio JSON $100.000 (con IVA). NO multiplicar."""
        result = catalog_lookup("delivery-zones", "ENVPIÑERO")
        assert result.get("found") is True
        assert result["price_ars"] == 100000, (
            f"Esperaba $100.000 (IVA incluido). Got ${result['price_ars']}. "
            f"Si dice $121.000, el flag price_includes_vat se está ignorando."
        )
        # Base = mismo valor (consistencia: cuando includes_vat, no hay
        # diferencia entre base y final).
        assert result["price_ars_base"] == 100000

    def test_canada_returns_225000_not_272250(self):
        """Cañada de Gómez: precio JSON $225.000 (con IVA)."""
        result = catalog_lookup("delivery-zones", "FLETE CAÑADA")
        assert result.get("found") is True
        assert result["price_ars"] == 225000

    def test_alvear_returns_30000_not_36300(self):
        """Alvear: precio JSON $30.000 (con IVA)."""
        result = catalog_lookup("delivery-zones", "ENVALV")
        assert result.get("found") is True
        assert result["price_ars"] == 30000


# ═══════════════════════════════════════════════════════════════════════
# Items SIN price_includes_vat — siguen con IVA aplicado (regression)
# ═══════════════════════════════════════════════════════════════════════


class TestNoFlagStillAppliesIva:
    def test_rosario_still_applies_iva(self):
        """Rosario NO tiene `price_includes_vat: true` (precio sin IVA
        en JSON). Debe seguir aplicando ×1.21."""
        result = catalog_lookup("delivery-zones", "ENVIOROS")
        assert result.get("found") is True
        # `price_ars_base` es el del JSON; `price_ars` aplicó IVA.
        assert result["price_ars"] > result["price_ars_base"], (
            f"Rosario debe seguir aplicando IVA: base={result['price_ars_base']} "
            f"vs final={result['price_ars']}. Si son iguales, alguien rompió "
            f"el path SIN price_includes_vat."
        )

    def test_labor_pegadopileta_applies_iva(self):
        """Labor SKUs no tienen el flag (todos sin IVA en el catálogo).
        Deben seguir aplicando IVA."""
        result = catalog_lookup("labor", "PEGADOPILETA")
        assert result.get("found") is True
        assert result["price_ars"] > result["price_ars_base"]

    def test_material_silestone_applies_iva(self):
        """Materiales: USD precio sin IVA, debe aplicar floor(× 1.21)."""
        result = catalog_lookup("materials-silestone", "SILESTONENORTE")
        assert result.get("found") is True
        # USD aplica `floor(× 1.21)` — final >= base.
        assert result["price_usd"] >= result["price_usd_base"]


# ═══════════════════════════════════════════════════════════════════════
# Drift guard — bytes y semántica del flag
# ═══════════════════════════════════════════════════════════════════════


class TestFlagSemantics:
    def test_only_true_skips_iva(self):
        """`price_includes_vat: false` (explícito) debe aplicar IVA igual
        que cuando el flag está ausente."""
        # Mock un item con flag False explícito y verificar que aplica IVA.
        # Como no podemos mockear catalog_lookup fácil sin DB, usamos un
        # SKU real que tenga flag false (la mayoría de delivery zones).
        result = catalog_lookup("delivery-zones", "ENVFUNES")
        assert result.get("found") is True
        # Funes tiene `price_includes_vat: false` — debe aplicar IVA.
        assert result["price_ars"] > result["price_ars_base"]
