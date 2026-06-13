"""Sub-PR 22.3 · Regla determinística alzada (Notion D'Angelo Regla 11).

- Si brief NO especifica alto alzada → default 60cm aplicado
  (`measurements.default_alzada_height` del config).
- Si brief NO especifica largo alzada → largo = perímetro del sector
  (cubre frente de la mesada · ya existente, regression guard).
- Si brief especifica alto → respetar brief (regression guard).

Patrón: invocar `merge_alzada_tramos_into_dual_read` con distintos
`alto_m` y verificar que los tramos `_derived_kind="alzada"` queden
con los valores esperados.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.dual_reader import merge_alzada_tramos_into_dual_read


# ──────────────────────────────────────────────────────────────────────
# Fixture · dual_read mínimo con un sector cocina y un tramo de mesada
# ──────────────────────────────────────────────────────────────────────


def _dual_read_cocina_simple() -> dict:
    return {
        "sectores": [
            {
                "id": "S1",
                "tipo": "cocina",
                "tramos": [
                    {
                        "id": "T1",
                        "descripcion": "M1 mesada",
                        "largo_m": {"valor": 2.0, "status": "CONFIRMADO"},
                        "ancho_m": {"valor": 0.6, "status": "CONFIRMADO"},
                        "m2": {"valor": 1.2, "status": "CONFIRMADO"},
                        "zocalos": [],
                    },
                ],
            },
        ],
    }


def _find_alzada_tramo(dual_read: dict) -> dict | None:
    for s in dual_read.get("sectores") or []:
        for t in s.get("tramos") or []:
            if t.get("_derived") and t.get("_derived_kind") == "alzada":
                return t
    return None


# ──────────────────────────────────────────────────────────────────────
# Test 6 · default alto aplicado cuando brief no especifica
# ──────────────────────────────────────────────────────────────────────


class TestAlzadaDefaultAltoAplicado:
    def test_alzada_active_sin_alto_aplica_default_60cm(self):
        """Si alzada está activa pero `alto_m=None` → default 0.60 del
        config aplica · flag `_alzada_default_applied=True` set."""
        dr = _dual_read_cocina_simple()
        out = merge_alzada_tramos_into_dual_read(dr, alto_m=None, active=True)

        assert out.get("_alzada_default_applied") is True
        assert out.get("alzada_alto_m") == pytest.approx(0.60, abs=0.001)
        alzada = _find_alzada_tramo(out)
        assert alzada is not None
        assert alzada["ancho_m"]["valor"] == pytest.approx(0.60, abs=0.001)

    def test_alzada_active_alto_cero_aplica_default(self):
        """`alto_m=0` también dispara el default (cubre input numérico
        accidental sin valor)."""
        dr = _dual_read_cocina_simple()
        out = merge_alzada_tramos_into_dual_read(dr, alto_m=0, active=True)

        assert out.get("_alzada_default_applied") is True
        alzada = _find_alzada_tramo(out)
        assert alzada is not None


# ──────────────────────────────────────────────────────────────────────
# Test 7 · default largo = perímetro del sector
# ──────────────────────────────────────────────────────────────────────


class TestAlzadaDefaultLargoAplicado:
    def test_largo_alzada_equivale_a_perimetro_visible_del_sector(self):
        """El largo de la alzada se deriva del `_sector_visible_perimeter`
        — para un sector con un tramo de 2m, el largo de la alzada = 2m."""
        dr = _dual_read_cocina_simple()
        out = merge_alzada_tramos_into_dual_read(dr, alto_m=None, active=True)

        alzada = _find_alzada_tramo(out)
        assert alzada is not None
        assert alzada["largo_m"]["valor"] == pytest.approx(2.0, abs=0.001)
        # m² = largo × alto = 2.0 × 0.60 = 1.20
        assert alzada["m2"]["valor"] == pytest.approx(1.20, abs=0.001)


# ──────────────────────────────────────────────────────────────────────
# Test 8 · brief override alto (respeta valor explícito)
# ──────────────────────────────────────────────────────────────────────


class TestAlzadaBriefOverrideAlto:
    def test_alto_explicito_no_pisa_con_default(self):
        """Si pasamos `alto_m=0.10` → usa 0.10, NO el default 0.60. Y el
        flag `_alzada_default_applied=False`."""
        dr = _dual_read_cocina_simple()
        out = merge_alzada_tramos_into_dual_read(dr, alto_m=0.10, active=True)

        assert out.get("_alzada_default_applied") is False
        alzada = _find_alzada_tramo(out)
        assert alzada is not None
        assert alzada["ancho_m"]["valor"] == pytest.approx(0.10, abs=0.001)
        # m² = 2.0 × 0.10 = 0.20
        assert alzada["m2"]["valor"] == pytest.approx(0.20, abs=0.001)


# ──────────────────────────────────────────────────────────────────────
# Test 9 · brief sin alzada (active=False) → no emite tramos
# ──────────────────────────────────────────────────────────────────────


class TestAlzadaBriefOverrideLargo:
    def test_active_false_no_emite_alzada_ni_aplica_default(self):
        """`active=False` (brief dice 'sin alzada') → NO emitir tramo
        alzada, NO marcar `_alzada_default_applied`. Regression guard."""
        dr = _dual_read_cocina_simple()
        out = merge_alzada_tramos_into_dual_read(dr, alto_m=None, active=False)

        assert out.get("_alzada_default_applied") is False
        assert _find_alzada_tramo(out) is None


# ──────────────────────────────────────────────────────────────────────
# Test 10 · determinismo · mismo input → mismo output (3 ejecuciones)
# ──────────────────────────────────────────────────────────────────────


class TestDeterminismoAlzada:
    def test_misma_invocacion_tres_veces_devuelve_outputs_identicos(self):
        """Determinismo · ejecutar `merge_alzada_tramos_into_dual_read`
        3 veces con mismo input debe devolver outputs estructuralmente
        idénticos. Si hay non-determinism (random, timestamp), este test
        rompe."""
        dr = _dual_read_cocina_simple()
        outs = [
            merge_alzada_tramos_into_dual_read(dr, alto_m=None, active=True)
            for _ in range(3)
        ]
        # Comparación por contenido del tramo derivado (los _derived ids
        # se derivan del nombre · son estables).
        alzadas = [_find_alzada_tramo(o) for o in outs]
        assert all(a is not None for a in alzadas)
        assert alzadas[0]["largo_m"]["valor"] == alzadas[1]["largo_m"]["valor"]
        assert alzadas[1]["largo_m"]["valor"] == alzadas[2]["largo_m"]["valor"]
        assert alzadas[0]["ancho_m"]["valor"] == alzadas[1]["ancho_m"]["valor"]
        assert alzadas[1]["ancho_m"]["valor"] == alzadas[2]["ancho_m"]["valor"]
        assert alzadas[0]["m2"]["valor"] == alzadas[1]["m2"]["valor"]
        assert alzadas[0]["id"] == alzadas[1]["id"] == alzadas[2]["id"]
