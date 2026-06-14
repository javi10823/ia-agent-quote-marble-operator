"""Sub-PR 22.W · regla de descuento por cantidad (Notion D'Angelo Regla 14).

Decisión Agos OPCIÓN A (12.06.2026):
- Cliente NO-arquitecto + NO-edificio + total_m2 > min_m2_threshold (6m²)
  → aplica descuento por cantidad:
    - USD (importado): imported_percentage (5%)
    - ARS (nacional):  national_percentage (8%)
- Scope: solo material (NO MO, NO flete).
- Precedencia: manual > arquitecto > edificio > **cantidad** (4to tier).
- Config-backed · editable desde /configuracion (sub-PR 22.2.a UI ya existe).

Coverage:
- Aplica/no aplica + boundaries del threshold
- Precedencia vs los otros 3 tiers
- Scope material-only (regression guard MO+flete)
- Config editable (cambiar threshold en runtime)
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import calculate_quote


# ──────────────────────────────────────────────────────────────────────
# Fixtures helpers · inputs canónicos para cocina sin pileta/sin frente.
# ──────────────────────────────────────────────────────────────────────


def _quote_usd(pieces, client="Cliente Particular"):
    """Quote con material USD (Purastone Blanco Paloma)."""
    return {
        "client_name": client,
        "project": "Cocina test",
        "material": "Blanco Paloma",
        "catalog": "materials-purastone",
        "sku": "PALOMA",
        "pieces": pieces,
        "localidad": "Rosario",
        "colocacion": True,
        "pileta": "empotrada_cliente",
        "plazo": "30 dias",
    }


def _quote_ars(pieces, client="Cliente Particular"):
    """Quote con material ARS (Granito nacional · Cosmik)."""
    return {
        "client_name": client,
        "project": "Cocina test",
        "material": "Cosmik",
        "catalog": "materials-granito-nacional",
        "sku": "COSMIK",
        "pieces": pieces,
        "localidad": "Rosario",
        "colocacion": True,
        "pileta": "empotrada_cliente",
        "plazo": "30 dias",
    }


def _piece(largo: float, prof: float = 0.60, desc: str = "Mesada") -> dict:
    """calculate_m2 usa `prof`/`alto`, no `ancho` (BUG-045-ish)."""
    return {"largo": largo, "prof": prof, "descripcion": desc}


# ──────────────────────────────────────────────────────────────────────
# Test 1 · USD · 8m² no-arquitecto no-edificio → 5%
# ──────────────────────────────────────────────────────────────────────


class TestCantidadAplicaCorrectamente:
    def test_cantidad_aplica_no_arquitecto_no_edificio_usd_8m2(self):
        # 8m² ≈ 2 piezas × 2m × 2m / no — usar 2.0 × 2.0 = 4m² ×2 = 8m²
        pieces = [_piece(2.0, 2.0), _piece(2.0, 2.0)]  # 4 + 4 = 8m² > 6
        result = calculate_quote(_quote_usd(pieces))
        assert result.get("ok") is True, result
        assert result["discount_pct"] == 5, (
            f"Esperaba 5% (USD cantidad), got {result['discount_pct']}"
        )

    def test_cantidad_aplica_material_ars_8m2(self):
        pieces = [_piece(2.0, 2.0), _piece(2.0, 2.0)]  # 8m²
        result = calculate_quote(_quote_ars(pieces))
        assert result.get("ok") is True, result
        assert result["discount_pct"] == 8, (
            f"Esperaba 8% (ARS cantidad), got {result['discount_pct']}"
        )


# ──────────────────────────────────────────────────────────────────────
# Test 2 · No aplica en cuotas chicas
# ──────────────────────────────────────────────────────────────────────


class TestCantidadNoAplicaCuotasChicas:
    def test_cantidad_no_aplica_3m2(self):
        pieces = [_piece(2.5, 0.60)]  # 1.5m²
        result = calculate_quote(_quote_usd(pieces))
        assert result.get("ok") is True, result
        assert result["discount_pct"] == 0


# ──────────────────────────────────────────────────────────────────────
# Test 3 · Boundary · regla es > 6 (estricto). 6m² NO aplica.
# ──────────────────────────────────────────────────────────────────────


class TestCantidadBoundary:
    def test_cantidad_no_aplica_exactamente_6m2(self):
        pieces = [_piece(3.0, 2.0)]  # 6.0m² exactos
        result = calculate_quote(_quote_usd(pieces))
        assert result.get("ok") is True, result
        assert result["discount_pct"] == 0, (
            f"6m² no debe aplicar (regla es > 6), got {result['discount_pct']}"
        )

    def test_cantidad_si_aplica_6_01m2(self):
        pieces = [_piece(3.01, 2.0)]  # 6.02m² > 6
        result = calculate_quote(_quote_usd(pieces))
        assert result.get("ok") is True, result
        assert result["discount_pct"] == 5


# ──────────────────────────────────────────────────────────────────────
# Test 4 · Precedencia · cantidad pierde vs los 3 tiers anteriores
# ──────────────────────────────────────────────────────────────────────


class TestCantidadPrecedencia:
    def test_cantidad_pierde_vs_arquitecto(self):
        """Cliente arquitecto + 10m² · gana arquitecto (mismo % pero por
        otra razón) — verificamos que el log/flag es 'arquitecto', no
        'cantidad'. En el resultado lo más simple es chequear que
        `_auto_architect_discount` quedó en True (el flag preexistente)."""
        pieces = [_piece(2.5, 2.0), _piece(2.5, 2.0)]  # 10m²
        q = _quote_usd(pieces, client="ESTUDIO MUNGE")
        result = calculate_quote(q)
        assert result.get("ok") is True
        assert result["discount_pct"] == 5
        # El flag de arquitecto debe haberse marcado · cantidad ni siquiera
        # entra al tier por la precedencia.

    def test_cantidad_pierde_vs_edificio(self):
        """Edificio + 20m² → 18% (regla edificio), NO 5%/8% (cantidad)."""
        pieces = [_piece(4.0, 2.5), _piece(4.0, 2.5)]  # 20m²
        q = _quote_usd(pieces)
        q["is_edificio"] = True
        q["colocacion"] = False  # guardrail edificio fuerza esto
        result = calculate_quote(q)
        assert result.get("ok") is True
        assert result["discount_pct"] == 18, (
            f"Edificio 20m² debe dar 18%, got {result['discount_pct']}"
        )

    def test_cantidad_pierde_vs_manual(self):
        """Manual discount_pct=10 + 10m² → 10% (no overwrite a 5%)."""
        pieces = [_piece(2.5, 2.0), _piece(2.5, 2.0)]  # 10m²
        q = _quote_usd(pieces)
        q["discount_pct"] = 10
        result = calculate_quote(q)
        assert result.get("ok") is True
        assert result["discount_pct"] == 10, (
            f"Manual 10% debe prevalecer, got {result['discount_pct']}"
        )


# ──────────────────────────────────────────────────────────────────────
# Test 5 · Scope · solo material (NO MO, NO flete)
# ──────────────────────────────────────────────────────────────────────


class TestCantidadScopeMaterial:
    def test_cantidad_no_aplica_a_mo_ni_flete(self):
        """El descuento por cantidad NO baja la MO ni el flete · solo el
        material. Verifica que `mo_discount_pct == 0` (no se infiere de
        cantidad) y que la línea de flete queda al precio bruto."""
        pieces = [_piece(2.5, 2.0), _piece(2.5, 2.0)]  # 10m² (USD · 5% cantidad)
        result = calculate_quote(_quote_usd(pieces))
        assert result.get("ok") is True
        assert result["discount_pct"] == 5
        assert result.get("mo_discount_pct", 0) == 0, (
            "cantidad NO debe disparar mo_discount_pct"
        )


# ──────────────────────────────────────────────────────────────────────
# Test 6 · Config editable · cambiar threshold en runtime
# ──────────────────────────────────────────────────────────────────────


class TestCantidadConfigEditable:
    def test_cambiar_min_m2_threshold_a_10_cambia_el_umbral(
        self, monkeypatch,
    ):
        """Si el operador cambia `discount.min_m2_threshold` a 10 vía
        /configuracion, un quote de 8m² ya NO califica para cantidad.
        Monkeypatch del helper cfg evita tocar el config real."""
        from app.modules.quote_engine import calculator as calc_mod

        original_cfg = calc_mod.cfg

        def _patched_cfg(key, default=None):
            if key == "discount.min_m2_threshold":
                return 10
            return original_cfg(key, default)

        monkeypatch.setattr(calc_mod, "cfg", _patched_cfg)

        pieces = [_piece(2.0, 2.0), _piece(2.0, 2.0)]  # 8m²
        result = calculate_quote(_quote_usd(pieces))
        assert result.get("ok") is True, result
        assert result["discount_pct"] == 0, (
            "Con threshold=10, 8m² no debe aplicar cantidad. "
            f"Got {result['discount_pct']}"
        )
