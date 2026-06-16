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


# ── pending_questions (path INTERACTIVO) · fast-follow audit #501 ───────────
# El audit independiente de #501 detectó que el path interactivo seguía
# hardcodeando 7cm (pending_questions.py:585 opción default + :683 apply).
# Es probablemente el path MÁS frecuente (cualquier brief sin zócalo dispara
# la pregunta). Estos tests cierran ese gap.

from app.modules.quote_engine import pending_questions
from app.modules.quote_engine.pending_questions import (
    _detect_zocalos_question,
    apply_zocalos_answer,
)


def _dr_un_tramo() -> dict:
    """dual_result mínimo · 1 sector / 1 tramo / sin zócalos (dispara la pregunta)."""
    return {
        "sectores": [
            {
                "tipo": "cocina",
                "tramos": [
                    {"largo_m": {"valor": 2.05, "status": "CONFIRMADO"}, "zocalos": []},
                ],
            }
        ]
    }


class TestPendingQuestionInteractivo:
    def test_pregunta_default_usa_config_005_no_007(self, monkeypatch):
        monkeypatch.setattr(
            pending_questions, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        q = _detect_zocalos_question("", _dr_un_tramo())
        assert q is not None
        opt = next(o for o in q["options"] if o["value"] == "default_trasero")
        assert "5cm" in opt["label"] and "7cm" not in opt["label"]
        assert opt["apply"]["alto_m"] == 0.05

    def test_pregunta_default_respeta_config_editable_008(self, monkeypatch):
        monkeypatch.setattr(
            pending_questions, "_cfg",
            lambda key, default=None: 0.08 if key == "measurements.default_zocalo_height" else default,
        )
        q = _detect_zocalos_question("", _dr_un_tramo())
        opt = next(o for o in q["options"] if o["value"] == "default_trasero")
        assert "8cm" in opt["label"]
        assert opt["apply"]["alto_m"] == 0.08


class TestApplyZocalosAnswer:
    def test_sin_default_explicito_lee_config_005(self, monkeypatch):
        monkeypatch.setattr(
            pending_questions, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        dr = apply_zocalos_answer(_dr_un_tramo(), {"id": "zocalos", "value": "default_trasero"})
        z = dr["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["alto_m"] == 0.05

    def test_alto_m_explicito_en_answer_gana(self, monkeypatch):
        monkeypatch.setattr(
            pending_questions, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        dr = apply_zocalos_answer(
            _dr_un_tramo(), {"id": "zocalos", "value": "default_trasero", "alto_m": 0.10}
        )
        z = dr["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["alto_m"] == 0.10
