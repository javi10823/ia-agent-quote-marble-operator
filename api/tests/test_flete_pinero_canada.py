"""Tests para PR #411 — Piñero y Cañada de Gómez en delivery-zones.

**Bugs cerrados:**

1. **Encoding doble-UTF-8** en `delivery-zones.json`: los SKUs y
   locations con `Ñ` venían como `\\xc3\\x83\\xc2\\x91` (UTF-8 sobre
   UTF-8) en vez de `\\xc3\\x91`. Resultado: `ENVPIÑERO` aparecía
   como `ENVPIÃERO`, `FLETE CAÑADA` como `FLETE CAÃADA`. El matcher
   nunca los encontraba → fallback silencioso a Rosario.

2. **Aliases ausentes** en `config.json:zone_aliases`: `piñero` y
   `cañada de gomez` no estaban mapeados a sus SKUs. Cualquier
   quote con esas localidades caía al fallback Rosario.

3. **Precio desactualizado**: Piñero estaba a $90.000 (04/08/2025);
   actualizado a $100.000 (28/04/2026).

**Caso real DYSCON:** quote a "Piñero" cobraba flete Rosario
($52.000/flete) con label "Flete + toma medidas Piñero". Con 6
fletes, eso es $228.000 ARS de menos cobrados. Post-#411 cobra
$100.000/flete = $600.000 totales (correcto).
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import _find_flete


# ═══════════════════════════════════════════════════════════════════════
# Piñero — SKU correcto + precio actualizado
# ═══════════════════════════════════════════════════════════════════════


class TestPineroFlete:
    def test_pinero_with_tilde_resolves_to_envpinero(self):
        """`piñero` (con tilde) → SKU `ENVPIÑERO`, NO fallback Rosario."""
        result = _find_flete("Piñero")
        assert result.get("found") is True
        assert result.get("sku") == "ENVPIÑERO", (
            f"Esperaba SKU ENVPIÑERO, got {result.get('sku')!r}. "
            f"Si dice ENVIOROS, el alias o el catálogo están rotos."
        )

    def test_pinero_without_tilde_also_resolves(self):
        """`pinero` (sin tilde) — operador apurado tipea sin acentos."""
        result = _find_flete("Pinero")
        assert result.get("found") is True
        assert result.get("sku") == "ENVPIÑERO"

    def test_pinero_price_is_100000(self):
        """Precio actualizado: $100.000 ARS con IVA incluido (caso DYSCON)."""
        result = _find_flete("Piñero")
        # `price_includes_vat: true` en delivery-zones → catalog_lookup
        # devuelve `price_ars` ya con IVA × 1.21 aplicado. Pero como
        # el flag es true, el IVA ya estaba incluido en el base.
        # `price_ars_base` es el valor crudo del JSON.
        assert result.get("price_ars_base") == 100000.0, (
            f"Esperaba base $100.000, got ${result.get('price_ars_base')}"
        )

    def test_pinero_pulido_extra_true(self):
        """Piñero está cerca de Rosario pero NO es Rosario centro →
        cobra pulido extra (consistente con Pérez/Soldini/Villa)."""
        result = _find_flete("Piñero")
        assert result.get("pulido_extra") is True


# ═══════════════════════════════════════════════════════════════════════
# Cañada de Gómez — encoding fixeado + aliases
# ═══════════════════════════════════════════════════════════════════════


class TestCanadaFlete:
    def test_canada_with_tilde_resolves(self):
        """`cañada de gomez` → SKU `FLETE CAÑADA`."""
        result = _find_flete("Cañada de Gomez")
        assert result.get("found") is True
        assert result.get("sku") == "FLETE CAÑADA", (
            f"Esperaba SKU 'FLETE CAÑADA', got {result.get('sku')!r}"
        )

    def test_canada_short_alias_resolves(self):
        """`cañada` (sin "de gomez") también funciona."""
        result = _find_flete("Cañada")
        assert result.get("found") is True
        assert result.get("sku") == "FLETE CAÑADA"

    def test_canada_without_tilde_also_resolves(self):
        """`canada de gomez` (sin tilde)."""
        result = _find_flete("Canada de Gomez")
        assert result.get("found") is True
        assert result.get("sku") == "FLETE CAÑADA"


# ═══════════════════════════════════════════════════════════════════════
# Regression — zonas que ya funcionaban siguen funcionando
# ═══════════════════════════════════════════════════════════════════════


class TestNoRegression:
    def test_rosario_still_resolves(self):
        result = _find_flete("Rosario")
        assert result.get("found") is True
        assert result.get("sku") == "ENVIOROS"

    def test_perez_still_resolves(self):
        result = _find_flete("Perez")
        assert result.get("found") is True
        assert result.get("sku") == "ENVPEREZ"


# ═══════════════════════════════════════════════════════════════════════
# Mojibake guard — el archivo no debe re-introducir doble-UTF-8
# ═══════════════════════════════════════════════════════════════════════


class TestEncodingGuard:
    def test_no_mojibake_bytes_in_delivery_zones(self):
        """Drift guard: si alguien re-edita el catálogo y lo guarda
        con encoding mal (Latin-1 → UTF-8 doble), este test rompe."""
        from pathlib import Path
        p = Path(__file__).parent.parent / "catalog" / "delivery-zones.json"
        raw = p.read_bytes()
        # `\xc3\x83\xc2\x91` es la firma de Ñ doble-encodeada.
        # `\xc3\x83` solo es la firma de Ã (también señal de mojibake).
        assert b"\xc3\x83\xc2\x91" not in raw, (
            "Mojibake regresión: el archivo tiene 'Ñ' doble-encodeada "
            "(bytes \\xc3\\x83\\xc2\\x91). Probablemente alguien lo editó "
            "con un editor Latin-1 y guardó como UTF-8."
        )
        # Validar que es UTF-8 válido (sin caracteres extraños).
        decoded = raw.decode("utf-8")  # raise si hay bytes inválidos
        assert "Ã" not in decoded or "Ñ" in decoded, (
            "Si aparece 'Ã' debería ser parte de algo legítimo, no mojibake."
        )

    def test_no_mojibake_bytes_in_config(self):
        from pathlib import Path
        p = Path(__file__).parent.parent / "catalog" / "config.json"
        raw = p.read_bytes()
        assert b"\xc3\x83\xc2\x91" not in raw, (
            "Mojibake regresión en config.json. Re-guardar como UTF-8 puro."
        )
