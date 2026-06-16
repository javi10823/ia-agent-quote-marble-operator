"""sprint-4/zocalo-config-unification · regresión del bug del zócalo 7cm.

Bug (FASE 1): el agent leía `default_zocalo_height` del bloque `ai_engine.*`
del config (vía get_ai_config) en vez de `measurements.*` → la key no existía
ahí → caía SIEMPRE al fallback hardcodeado 0.07 (7cm). El default master
D'Angelo es 0.05 (5cm). Sobre-cobro ~40% en m² de zócalo (material + MO).

Fix: agent.py:571/2925 + dual_reader.py:31 leen `_cfg("measurements.
default_zocalo_height", 0.05)`.

Estos tests cubren los DOS consumidores del valor:
  1. `dual_reader._default_zocalo_alto()` (fallback corregido 0.07→0.05).
  2. `context_analyzer._build_assumptions()` (consume el `config_defaults`
     que el agent ahora arma con measurements.default_zocalo_height).
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine import dual_reader
from app.modules.quote_engine.context_analyzer import _build_assumptions


def _zocalo_assumption(assumptions: list[dict]) -> dict | None:
    return next((a for a in assumptions if "Trasero por tramo" in str(a.get("value", ""))), None)


# ── dual_reader._default_zocalo_alto · fallback corregido ──────────────────

class TestDualReaderDefaultZocalo:
    def test_usa_valor_de_config(self, monkeypatch):
        monkeypatch.setattr(
            dual_reader, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        assert dual_reader._default_zocalo_alto() == 0.05

    def test_respeta_config_editable_distinto(self, monkeypatch):
        monkeypatch.setattr(
            dual_reader, "_cfg",
            lambda key, default=None: 0.08 if key == "measurements.default_zocalo_height" else default,
        )
        assert dual_reader._default_zocalo_alto() == 0.08

    def test_fallback_es_005_no_007(self, monkeypatch):
        # Config sin la key (null/ausente) → devuelve el default que pasa la
        # función. Verifica que ese default ahora es 0.05 (no el viejo 0.07).
        monkeypatch.setattr(dual_reader, "_cfg", lambda key, default=None: default)
        assert dual_reader._default_zocalo_alto() == 0.05


# ── context_analyzer · consumer del config_defaults del agent ──────────────

class TestContextAssumptionsZocalo:
    def test_sin_alto_brief_usa_default_005(self):
        """Brief pide zócalo pero no especifica alto · config=0.05 → 5cm."""
        out = _build_assumptions(
            analysis={"zocalos": "yes"},
            quote=None,
            dual_result={},
            config_defaults={"default_zocalo_height": 0.05},
        )
        z = _zocalo_assumption(out)
        assert z is not None, out
        assert "5 cm" in z["value"]
        assert "7 cm" not in z["value"]

    def test_sin_alto_brief_respeta_config_editable_008(self):
        """Operador editó measurements a 0.08 en /configuracion → 8cm."""
        out = _build_assumptions(
            analysis={"zocalos": "yes"},
            quote=None,
            dual_result={},
            config_defaults={"default_zocalo_height": 0.08},
        )
        z = _zocalo_assumption(out)
        assert z is not None and "8 cm" in z["value"]

    def test_alto_explicito_en_brief_ignora_config(self):
        """Brief dice 'zócalo 6cm' → respeta el brief, ignora el default."""
        out = _build_assumptions(
            analysis={"zocalos": "yes", "zocalos_alto_cm": 6},
            quote=None,
            dual_result={},
            config_defaults={"default_zocalo_height": 0.05},
        )
        z = _zocalo_assumption(out)
        assert z is not None and "6 cm" in z["value"]
