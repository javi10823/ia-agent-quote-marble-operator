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


# ── card_editor (path EDICIÓN MANUAL) · cierre saga · fast-follow audit #502 ─
# Cuarto y último sitio del bug 7cm: la op add_zocalo del editor manual de
# card (card_editor.py:238) defaulteaba a 0.07 hardcodeado e ignoraba el
# config. Detectado por el barrido amplio (grep del VALOR, no de la función).

from app.modules.agent import card_editor
from app.modules.agent.card_editor import apply_card_patch


def _card_un_tramo_sin_zocalo() -> dict:
    return {
        "sectores": [
            {"id": "cocina", "tipo": "L", "tramos": [
                {"id": "t1", "largo_m": {"valor": 1.61}, "zocalos": []},
            ]},
        ],
    }


def _add_zocalo_op(**extra) -> dict:
    return {"op": "add_zocalo", "sector_id": "cocina", "tramo_id": "t1",
            "lado": "trasero", "ml": 1.61, **extra}


class TestCardEditorAddZocalo:
    def test_sin_alto_m_usa_config_005(self, monkeypatch):
        monkeypatch.setattr(
            card_editor, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        patched, _applied, _errors = apply_card_patch(_card_un_tramo_sin_zocalo(), [_add_zocalo_op()])
        z = patched["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["alto_m"] == 0.05

    def test_alto_m_explicito_008_ignora_config(self, monkeypatch):
        monkeypatch.setattr(
            card_editor, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        patched, _a, _e = apply_card_patch(_card_un_tramo_sin_zocalo(), [_add_zocalo_op(alto_m=0.08)])
        z = patched["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["alto_m"] == 0.08

    def test_alto_m_cero_cae_al_config(self, monkeypatch):
        # Comportamiento documentado: un zócalo de 0cm de alto no es válido ·
        # 0 (falsy) se trata como "no especificado" → default del config.
        # Preserva la semántica `or` previa (antes 0 → 0.07; ahora 0 → config).
        monkeypatch.setattr(
            card_editor, "_cfg",
            lambda key, default=None: 0.05 if key == "measurements.default_zocalo_height" else default,
        )
        patched, _a, _e = apply_card_patch(_card_un_tramo_sin_zocalo(), [_add_zocalo_op(alto_m=0)])
        z = patched["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["alto_m"] == 0.05


# ── capa de INFERENCIA LLM (prompt del extractor) · CIERRE FINAL saga zócalo ─
# Quinto sitio (audit #503): el ejemplo de _EXTRACTOR_SYSTEM mostraba
# alto_m: 0.07 → sesgaba al LLM a emitir 0.07 explícito, que gana sobre el
# default config en apply_card_patch → bypassa el fix de #503. Este guard
# blinda el prompt contra regresión.

from app.modules.agent.card_editor import _EXTRACTOR_SYSTEM


class TestExtractorPromptNoZocalo007:
    def test_prompt_no_contiene_007(self):
        # Regresión: ningún 0.07 (ni el ejemplo) que sesgue al modelo.
        assert "0.07" not in _EXTRACTOR_SYSTEM

    def test_prompt_instruye_omitir_alto_si_no_especificado(self):
        # El prompt debe decirle al modelo que omita alto_m cuando el
        # operador no lo especifica (así gobierna el default del config).
        assert "alto_m" in _EXTRACTOR_SYSTEM
        assert "OMIT" in _EXTRACTOR_SYSTEM.upper()
