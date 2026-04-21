"""Tests de context_analyzer — construye la card de análisis previa al despiece.

Patcheamos `analyze_brief` (el LLM call) con el regex fallback determinístico
para que los tests corran sin pegar a Anthropic y sean reproducibles.
"""
import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.quote_engine.brief_analyzer import EMPTY_SCHEMA, _analyze_regex_fallback
from app.modules.quote_engine.context_analyzer import (
    _build_data_known,
    _detect_anafe,
    _detect_isla,
    _detect_pileta,
    _reconcile_work_types,
    build_context_analysis_sync as build_context_analysis,
)


@pytest.fixture(autouse=True)
def _mock_analyze_brief():
    """Reemplaza el LLM call por el regex fallback para tests deterministas."""
    async def _fake(brief: str) -> dict:
        return _analyze_regex_fallback(brief or "")
    with patch(
        "app.modules.quote_engine.context_analyzer.analyze_brief",
        new=_fake,
    ):
        yield


def _dual(has_cocina: bool = True) -> dict:
    sectores = []
    if has_cocina:
        sectores.append({
            "id": "s1",
            "tipo": "cocina",
            "tramos": [{
                "id": "t1",
                "descripcion": "Mesada",
                "largo_m": {"valor": 2.0, "status": "CONFIRMADO"},
                "ancho_m": {"valor": 0.6, "status": "CONFIRMADO"},
                "m2": {"valor": 1.2, "status": "CONFIRMADO"},
                "zocalos": [], "frentin": [], "regrueso": [],
            }],
            "ambiguedades": [],
        })
    return {"sectores": sectores, "source": "MULTI_CROP"}


class TestBuildContextAnalysis:
    def test_shape(self):
        out = build_context_analysis("brief", {"client_name": "Juan"}, _dual())
        assert "data_known" in out
        assert "assumptions" in out
        assert "pending_questions" in out
        assert "sector_summary" in out

    def test_client_from_quote(self):
        out = build_context_analysis("", {"client_name": "Juan"}, _dual())
        clientes = [r for r in out["data_known"] if r["field"] == "Cliente"]
        assert len(clientes) == 1
        assert clientes[0]["value"] == "Juan"
        assert clientes[0]["source"] == "quote"

    def test_material_from_brief(self):
        out = build_context_analysis("material silestone blanco norte", None, _dual())
        materiales = [r for r in out["data_known"] if r["field"] == "Material"]
        assert len(materiales) == 1
        assert "silestone" in materiales[0]["value"].lower()
        assert materiales[0]["source"] == "brief"

    def test_localidad_from_brief(self):
        out = build_context_analysis("cliente en rosario", None, _dual())
        assert any(r["field"] == "Localidad" for r in out["data_known"])

    def test_cocina_triggers_pileta_empotrada_rule(self):
        # La regla aplica cuando hay cocina Y pileta mencionada (evita
        # agregar la regla cuando el trabajo no tiene pileta).
        out = build_context_analysis("cocina con pileta", None, _dual(has_cocina=True))
        piletas = [a for a in out["assumptions"] if a["field"] == "Pileta (tipo de montaje)"]
        assert len(piletas) == 1
        assert "empotrada" in piletas[0]["value"].lower()
        assert piletas[0]["source"] == "rule"

    def test_cocina_without_pileta_mention_no_rule(self):
        """Sin pileta mencionada en brief ni detectada en card → no aplicamos
        la regla (el trabajo puede no tener pileta)."""
        out = build_context_analysis("", None, _dual(has_cocina=True))
        piletas = [a for a in out["assumptions"] if a["field"] == "Pileta (tipo de montaje)"]
        assert len(piletas) == 0

    def test_no_cocina_no_pileta_rule(self):
        out = build_context_analysis("", None, _dual(has_cocina=False))
        assert not any("Pileta" in a["field"] for a in out["assumptions"])

    def test_con_zocalos_triggers_assumption(self):
        out = build_context_analysis("cocina con zocalos en rosario", None, _dual())
        zoc = [a for a in out["assumptions"] if a["field"] == "Zócalos"]
        assert len(zoc) == 1
        assert "trasero" in zoc[0]["value"].lower()

    def test_con_colocacion_included(self):
        out = build_context_analysis("cocina con colocacion", None, _dual())
        coloc = [a for a in out["assumptions"] if a["field"] == "Colocación"]
        assert len(coloc) == 1
        assert "incluye" in coloc[0]["value"].lower()

    def test_defaults_always_included(self):
        out = build_context_analysis("", None, _dual())
        fields = [a["field"] for a in out["assumptions"]]
        assert "Forma de pago" in fields
        assert "Demora" in fields
        assert "Tipo" in fields

    def test_pending_questions_propagated(self):
        dual = _dual()
        dual["pending_questions"] = [{"id": "q1", "label": "X", "question": "¿?", "type": "radio_with_detail"}]
        out = build_context_analysis("", None, dual)
        assert len(out["pending_questions"]) == 1
        assert out["pending_questions"][0]["id"] == "q1"

    def test_sector_summary(self):
        out = build_context_analysis("", None, _dual())
        assert out["sector_summary"] is not None
        assert "cocina" in out["sector_summary"].lower()

    def test_empty_inputs_does_not_crash(self):
        """Brief vacío + dual vacío: no debería romper, devuelve shape mínima."""
        out = build_context_analysis("", None, {"sectores": []})
        assert "data_known" in out
        assert "assumptions" in out
        assert "tech_detections" in out
        assert out["pending_questions"] == []
        assert out["tech_detections"] == []


class TestTechDetections:
    """Separan lo que el plano/brief detectaron (verificable) de los defaults
    comerciales. Los campos con confidence >=0.60 aparecen aquí y suprimen la
    pending_question correspondiente."""

    def _dual_with_features(self, features: dict, tipo: str = "cocina", extra_sectores: list | None = None) -> dict:
        d = {
            "sectores": [{
                "id": "s1", "tipo": tipo,
                "tramos": [{
                    "id": "t1", "descripcion": "Mesada",
                    "largo_m": {"valor": 2.0, "status": "CONFIRMADO"},
                    "ancho_m": {"valor": 0.6, "status": "CONFIRMADO"},
                    "m2": {"valor": 1.2, "status": "CONFIRMADO"},
                    "zocalos": [], "frentin": [], "regrueso": [],
                    "features": features,
                }],
                "ambiguedades": [],
            }],
            "source": "MULTI_CROP",
        }
        if extra_sectores:
            d["sectores"].extend(extra_sectores)
        return d

    def test_sink_double_produces_verified_detection_from_brief(self):
        """Brief dice 'pileta doble' → detection con source=brief y verified."""
        out = build_context_analysis("cocina con pileta doble", None, self._dual_with_features({}))
        det = [d for d in out["tech_detections"] if d["field"] == "pileta_simple_doble"]
        assert len(det) == 1
        assert det[0]["value"] == "doble"
        assert det[0]["source"] == "brief"
        assert det[0]["status"] == "verified"

    def test_sink_double_from_plano_needs_confirmation(self):
        """Dual_read detecta sink_double → needs_confirmation (no brief)."""
        out = build_context_analysis("", None, self._dual_with_features({"sink_double": True}))
        det = [d for d in out["tech_detections"] if d["field"] == "pileta_simple_doble"]
        assert len(det) == 1
        assert det[0]["value"] == "doble"
        assert det[0]["source"] == "dual_read"
        assert det[0]["status"] == "needs_confirmation"

    def test_detection_suppresses_matching_pending_question(self):
        """Si hay tech_detection para pileta, no aparece en pending_questions."""
        dual = self._dual_with_features({"sink_double": True})
        dual["pending_questions"] = [
            {"id": "pileta_simple_doble", "label": "P", "question": "?", "type": "radio_with_detail"},
            {"id": "alzada", "label": "A", "question": "?", "type": "radio_with_detail"},
        ]
        out = build_context_analysis("", None, dual)
        ids = [q["id"] for q in out["pending_questions"]]
        assert "pileta_simple_doble" not in ids  # suprimida por detection
        assert "alzada" in ids  # otras preguntas intactas

    def test_isla_detected_when_sector_present(self):
        dual = self._dual_with_features({}, extra_sectores=[{
            "id": "s2", "tipo": "isla",
            "tramos": [{
                "id": "t_isla", "descripcion": "Isla",
                "largo_m": {"valor": 1.60, "status": "CONFIRMADO"},
                "ancho_m": {"valor": 0.60, "status": "DUDOSO"},
                "m2": {"valor": 0.96, "status": "DUDOSO"},
                "zocalos": [], "frentin": [], "regrueso": [],
            }], "ambiguedades": [],
        }])
        out = build_context_analysis("", None, dual)
        det = [d for d in out["tech_detections"] if d["field"] == "isla_presence"]
        assert len(det) == 1
        assert det[0]["value"] == "yes"
        assert det[0]["source"] == "dual_read"

    def test_anafe_count_from_brief_is_verified(self):
        out = build_context_analysis("cocina con 2 anafes", None, self._dual_with_features({}))
        det = [d for d in out["tech_detections"] if d["field"] == "anafe_count"]
        assert len(det) == 1
        assert det[0]["value"] == "2"
        assert det[0]["status"] == "verified"

    def test_has_pileta_only_no_detection_still_question(self):
        """has_pileta sin simple/doble → confidence 0.55 < 0.60, no se emite
        detection y el campo debería seguir como pending_question."""
        dual = self._dual_with_features({"has_pileta": True})
        dual["pending_questions"] = [
            {"id": "pileta_simple_doble", "label": "P", "question": "?", "type": "radio_with_detail"},
        ]
        out = build_context_analysis("", None, dual)
        assert not any(d["field"] == "pileta_simple_doble" for d in out["tech_detections"])
        assert any(q["id"] == "pileta_simple_doble" for q in out["pending_questions"])

    def test_detection_shape_has_required_keys(self):
        """Contrato: cada detection tiene field/label/value/display/options/source/confidence/status."""
        out = build_context_analysis("cocina con pileta doble", None, self._dual_with_features({}))
        d = next(x for x in out["tech_detections"] if x["field"] == "pileta_simple_doble")
        for key in ("field", "label", "value", "display", "options", "source", "confidence", "status"):
            assert key in d
        assert isinstance(d["options"], list)
        assert d["options"][0].keys() >= {"value", "label"}


# ── Round-trip: build context → apply answers → verify result ──────────────
# Simula el flow end-to-end de PR G sin DB ni LLM. Verifica que las
# respuestas del operador a pending_questions efectivamente modifican el
# dual_read_result via apply_answers del módulo pending_questions.


class TestContextConfirmationRoundTrip:
    def _dual_with_pending(self, pending: list[dict]) -> dict:
        d = _dual()
        d["pending_questions"] = pending
        return d

    def test_apply_answers_removes_pending_from_dual(self):
        """Handler [CONTEXT_CONFIRMED] aplica respuestas y limpia pending."""
        from app.modules.quote_engine.pending_questions import apply_answers

        pending = [{
            "id": "zocalos", "label": "Zócalos", "question": "?",
            "type": "radio_with_detail",
            "options": [{"value": "default_trasero", "label": "Sí"}],
        }]
        dual = self._dual_with_pending(pending)
        # Simulación del handler: aplica answers, limpia pending
        apply_answers(dual, [{"id": "zocalos", "value": "default_trasero"}])
        dual.pop("pending_questions", None)
        # Zócalos agregados al tramo con source=brief_rule
        assert len(dual["sectores"][0]["tramos"][0]["zocalos"]) == 1
        assert dual["sectores"][0]["tramos"][0]["zocalos"][0]["source"] == "brief_rule"
        assert "pending_questions" not in dual

    def test_pileta_simple_doble_applies_sink_type(self):
        from app.modules.quote_engine.pending_questions import apply_answers
        dual = _dual()
        dual["sectores"][0]["tramos"][0]["features"] = {"has_pileta": True}
        apply_answers(dual, [{"id": "pileta_simple_doble", "value": "doble"}])
        sector = dual["sectores"][0]
        assert sector["sink_type"]["basin_count"] == "doble"
        assert sector["pileta_type_hint"] == "empotrada"

    def test_multiple_answers_apply_in_one_pass(self):
        """Varios answers en un solo CONTEXT_CONFIRMED se aplican todos."""
        from app.modules.quote_engine.pending_questions import apply_answers
        dual = _dual()
        apply_answers(dual, [
            {"id": "zocalos", "value": "default_trasero"},
            {"id": "colocacion", "value": "si"},
            {"id": "anafe_count", "value": "2"},
        ])
        assert len(dual["sectores"][0]["tramos"][0]["zocalos"]) == 1
        assert dual["colocacion"] is True
        assert dual["anafe"] is True
        assert dual["anafe_qty"] == 2

    def test_full_flow_bernardi_like(self):
        """Caso Bernardi end-to-end (sin DB ni LLM):
        1. Construye context analysis desde brief + quote + dual_read
        2. Operador responde las preguntas bloqueantes
        3. apply_answers materializa todo en el dual_result
        4. pending_questions se limpia → card despiece queda lista.
        """
        from app.modules.quote_engine.pending_questions import apply_answers

        brief = "material pura prima onix white cliente erica bernardi con pileta doble con zocalos en rosario con colocacion"
        quote = None  # operador recién lo sube, sin datos previos en quote

        dual = _dual()
        # Agregar feature de pileta a un tramo de cocina para que la regla
        # pileta-empotrada se dispare (simula lo que detectaría la fase global)
        dual["sectores"][0]["tramos"][0]["features"] = {"has_pileta": True}
        dual["sectores"].append({
            "id": "s2", "tipo": "isla",
            "tramos": [{
                "id": "t_isla",
                "descripcion": "Mesada",
                "largo_m": {"valor": 1.60, "status": "CONFIRMADO"},
                "ancho_m": {"valor": 0.60, "status": "DUDOSO"},  # dispara pregunta
                "m2": {"valor": 0.96, "status": "DUDOSO"},
                "zocalos": [], "frentin": [], "regrueso": [],
            }],
            "ambiguedades": [],
        })
        # Agregar pending_questions típicos del caso
        dual["pending_questions"] = [
            {"id": "pileta_simple_doble", "label": "Pileta", "question": "?", "type": "radio_with_detail"},
            {"id": "isla_profundidad", "label": "Isla prof", "question": "?", "type": "radio_with_detail"},
            {"id": "isla_patas", "label": "Patas", "question": "?", "type": "radio_with_detail"},
        ]

        context = build_context_analysis(brief, quote, dual)
        assert any(r["field"] == "Material" for r in context["data_known"])
        assert any(r["field"] == "Localidad" for r in context["data_known"])
        assert any(a["field"] == "Pileta (tipo de montaje)" for a in context["assumptions"])
        assert any(a["field"] == "Zócalos" for a in context["assumptions"])
        assert any(a["field"] == "Colocación" for a in context["assumptions"])

        # Operador confirma respondiendo las 3 preguntas
        apply_answers(dual, [
            {"id": "pileta_simple_doble", "value": "doble"},
            {"id": "isla_profundidad", "value": "0.60"},
            {"id": "isla_patas", "value": "frontal_y_ambos_laterales", "alto_m": 0.90},
        ])
        dual.pop("pending_questions", None)

        # Verificamos el estado final listo para despiece:
        cocina = next(s for s in dual["sectores"] if s["tipo"] == "cocina")
        isla = next(s for s in dual["sectores"] if s["tipo"] == "isla")
        assert cocina["sink_type"]["basin_count"] == "doble"
        assert isla["tramos"][0]["ancho_m"]["valor"] == 0.60
        assert isla["patas"]["sides"] == ["frontal", "lateral_izq", "lateral_der"]
        assert "pending_questions" not in dual


# ─────────────────────────────────────────────────────────────────────────────
# PR #347 — Reconciliación brief ↔ dual_read + observabilidad + Tipo de trabajo
#
# Scope: inferir work_types desde dual_result.sectores cuando el brief no
# los trae, y loggear explícitamente la decisión de reconciliación por
# campo crítico (isla, anafe, pileta, work_types). Criterio: NO merge
# silencioso — cuando brief y dual_read divergen, `divergent=True` en
# el log.
# ─────────────────────────────────────────────────────────────────────────────


def _dual_with_sectores(tipos: list[str]) -> dict:
    """Build a dual_result con los tipos de sectores pedidos. Cada sector
    es un placeholder mínimo válido."""
    return {
        "sectores": [
            {
                "id": f"s{i}",
                "tipo": t,
                "tramos": [],
                "ambiguedades": [],
            }
            for i, t in enumerate(tipos, 1)
        ],
        "source": "MULTI_CROP",
    }


class TestReconcileWorkTypes:
    """_reconcile_work_types merge brief ↔ dual_result.sectores."""

    def test_brief_empty_falls_back_to_dual_read(self, caplog):
        """Caso Bernardi real: brief no menciona 'cocina'/'isla' → brief
        analysis devuelve work_types=[]. El dual_result sí tiene sectores
        cocina + isla. Merge debe devolver los del dual_read."""
        analysis = {"work_types": []}
        dual = _dual_with_sectores(["cocina", "isla"])
        with caplog.at_level(logging.INFO):
            out = _reconcile_work_types(analysis, dual)
        assert out["final"] == ["cocina", "isla"]
        assert out["source"] == "dual_read"
        assert out["divergent"] is False
        assert any("[context-reconcile]" in r.message and "field=work_types" in r.message
                   for r in caplog.records)

    def test_brief_wins_when_both_agree(self, caplog):
        analysis = {"work_types": ["cocina"]}
        dual = _dual_with_sectores(["cocina"])
        out = _reconcile_work_types(analysis, dual)
        assert out["final"] == ["cocina"]
        assert out["source"] == "brief"
        assert out["divergent"] is False

    def test_divergent_when_brief_and_dual_read_have_different_sets(self, caplog):
        """brief=['baño'] vs dual=['cocina'] → divergent=True, brief gana
        por precedencia pero el log deja constancia de la inconsistencia."""
        analysis = {"work_types": ["baño"]}
        dual = _dual_with_sectores(["cocina"])
        with caplog.at_level(logging.INFO):
            out = _reconcile_work_types(analysis, dual)
        assert out["final"] == ["baño"]
        assert out["source"] == "brief"
        assert out["divergent"] is True
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=work_types" in r.message)
        assert "divergent=True" in log

    def test_divergent_when_brief_subset_of_dual_read(self, caplog):
        """brief=['cocina'] vs dual=['cocina','isla'] → divergent=True,
        brief gana pero log lo muestra."""
        analysis = {"work_types": ["cocina"]}
        dual = _dual_with_sectores(["cocina", "isla"])
        out = _reconcile_work_types(analysis, dual)
        assert out["divergent"] is True
        assert out["source"] == "brief"

    def test_banio_and_bano_normalized_as_equal(self, caplog):
        """Brief usa 'baño' unicode, dual_result puede traer 'banio' (ASCII)
        — no son divergentes en canonical form."""
        analysis = {"work_types": ["baño"]}
        dual = _dual_with_sectores(["banio"])
        out = _reconcile_work_types(analysis, dual)
        assert out["divergent"] is False

    def test_both_empty_is_not_divergent(self, caplog):
        analysis = {"work_types": []}
        dual = _dual_with_sectores([])
        out = _reconcile_work_types(analysis, dual)
        assert out["final"] == []
        assert out["source"] == "default"
        assert out["divergent"] is False


class TestDetectIslaReconciliation:
    """_detect_isla ahora loguea [context-reconcile] siempre + marca
    divergent cuando brief y dual_read no coinciden y al menos uno es True."""

    def test_brief_true_dual_false_is_divergent(self, caplog):
        """Brief dice 'isla' pero plano no la detecta — divergencia real."""
        analysis = {"isla_mentioned": True}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            _detect_isla(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=isla_presence" in r.message)
        assert "divergent=True" in log
        assert "source=brief" in log

    def test_brief_false_dual_true_not_divergent(self, caplog):
        """Brief no menciona (isla_mentioned=False) pero plano detecta.
        NO es divergent: brief=False es "no mencionó", no "dijo que NO".
        Fallback natural al dual_read, consistente con anafe/pileta."""
        analysis = {"isla_mentioned": False}
        feats = {"has_isla": True, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            _detect_isla(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=isla_presence" in r.message)
        assert "divergent=False" in log
        assert "source=dual_read" in log

    def test_both_false_no_divergence(self, caplog):
        """Ni brief ni plano mencionan isla → no hay card, no divergent."""
        analysis = {"isla_mentioned": False}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            result = _detect_isla(analysis, feats)
        assert result is None
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=isla_presence" in r.message)
        assert "divergent=False" in log

    def test_both_true_no_divergence(self, caplog):
        analysis = {"isla_mentioned": True}
        feats = {"has_isla": True, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            _detect_isla(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=isla_presence" in r.message)
        assert "divergent=False" in log
        assert "source=brief" in log  # brief siempre gana cuando ambos true


class TestDetectAnafeReconciliation:
    def test_brief_count_differs_from_dual_is_divergent(self, caplog):
        """brief dice 2 anafes, plano detecta 1 → divergencia. Brief gana
        por precedencia, pero log deja constancia."""
        analysis = {"anafe_count": 2, "anafe_gas_y_electrico": True}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 1}
        with caplog.at_level(logging.INFO):
            result = _detect_anafe(analysis, feats)
        assert result["value"] == "2"
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=anafe_count" in r.message)
        assert "divergent=True" in log
        assert "source=brief" in log

    def test_brief_none_dual_positive_not_divergent(self, caplog):
        """Brief sin anafe_count (null), plano con cooktop_groups → fallback
        dual_read, NO divergent (brief no dijo nada)."""
        analysis = {"anafe_count": None}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 1}
        with caplog.at_level(logging.INFO):
            _detect_anafe(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=anafe_count" in r.message)
        assert "divergent=False" in log
        assert "source=dual_read" in log

    def test_brief_zero_dual_positive_is_divergent(self, caplog):
        """Brief explícito '0 anafes', plano detecta anafe → divergencia
        real (brief afirma que no hay, plano dice que sí)."""
        analysis = {"anafe_count": 0}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 1}
        with caplog.at_level(logging.INFO):
            _detect_anafe(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=anafe_count" in r.message)
        assert "divergent=True" in log
        assert "source=brief" in log

    def test_both_equal_not_divergent(self, caplog):
        analysis = {"anafe_count": 1}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 1}
        with caplog.at_level(logging.INFO):
            _detect_anafe(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=anafe_count" in r.message)
        assert "divergent=False" in log


class TestDetectPiletaReconciliation:
    def test_brief_simple_dual_double_is_divergent(self, caplog):
        analysis = {"pileta_simple_doble": "simple", "pileta_mentioned": True}
        feats = {"has_isla": False, "sink_double": True, "sink_simple": False,
                 "has_pileta": True, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            result = _detect_pileta(analysis, feats)
        assert result["value"] == "simple"  # brief gana
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=pileta_simple_doble" in r.message)
        assert "divergent=True" in log
        assert "source=brief" in log

    def test_brief_none_dual_simple_not_divergent(self, caplog):
        analysis = {"pileta_simple_doble": None, "pileta_mentioned": False,
                    "raw_notes": ""}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": True,
                 "has_pileta": True, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            result = _detect_pileta(analysis, feats)
        assert result["value"] == "simple"
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=pileta_simple_doble" in r.message)
        assert "divergent=False" in log
        assert "source=dual_read" in log

    def test_brief_explicit_no_vs_dual_detected_is_divergent(self, caplog):
        """Brief dice 'sin pileta' explícito Y plano detecta pileta → divergencia."""
        analysis = {"pileta_simple_doble": None, "pileta_mentioned": False,
                    "raw_notes": "sin pileta en la cocina"}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": True,
                 "has_pileta": True, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            result = _detect_pileta(analysis, feats)
        assert result["value"] == "no"  # brief gana
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=pileta_simple_doble" in r.message)
        assert "divergent=True" in log
        assert "source=brief" in log

    def test_brief_simple_dual_present_unknown_not_divergent(self, caplog):
        """Brief=simple + plano detecta presencia pero sin tipo → NO es
        divergent (el plano no contradice, solo es menos específico)."""
        analysis = {"pileta_simple_doble": "simple", "pileta_mentioned": True}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": True, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            _detect_pileta(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message and "field=pileta_simple_doble" in r.message)
        assert "divergent=False" in log


class TestBuildDataKnownTipoTrabajo:
    """_build_data_known debe agregar 'Tipo de trabajo' usando el merge
    brief ↔ dual_read (el bug visible de Bernardi real)."""

    def test_tipo_trabajo_from_dual_read_when_brief_empty(self):
        analysis = dict(EMPTY_SCHEMA)  # sin work_types
        dual = _dual_with_sectores(["cocina", "isla"])
        known = _build_data_known(analysis, quote=None, dual_result=dual)
        tipo_row = next((r for r in known if r["field"] == "Tipo de trabajo"), None)
        assert tipo_row is not None
        assert "Cocina" in tipo_row["value"]
        assert "Isla" in tipo_row["value"]
        assert tipo_row["source"] == "dual_read"

    def test_tipo_trabajo_from_brief_when_brief_has_types(self):
        analysis = dict(EMPTY_SCHEMA)
        analysis["work_types"] = ["cocina"]
        dual = _dual_with_sectores(["cocina"])
        known = _build_data_known(analysis, quote=None, dual_result=dual)
        tipo_row = next((r for r in known if r["field"] == "Tipo de trabajo"), None)
        assert tipo_row is not None
        assert tipo_row["source"] == "brief"

    def test_tipo_trabajo_marked_divergent_when_brief_and_dual_diverge(self):
        """Brief=cocina, dual=cocina+isla → source="brief+dual_read" para
        que la card refleje que hubo merge con divergencia."""
        analysis = dict(EMPTY_SCHEMA)
        analysis["work_types"] = ["cocina"]
        dual = _dual_with_sectores(["cocina", "isla"])
        known = _build_data_known(analysis, quote=None, dual_result=dual)
        tipo_row = next((r for r in known if r["field"] == "Tipo de trabajo"), None)
        assert tipo_row is not None
        assert tipo_row["source"] == "brief+dual_read"

    def test_no_tipo_trabajo_when_both_empty(self):
        analysis = dict(EMPTY_SCHEMA)
        dual = _dual_with_sectores([])
        known = _build_data_known(analysis, quote=None, dual_result=dual)
        tipo_row = next((r for r in known if r["field"] == "Tipo de trabajo"), None)
        assert tipo_row is None

    def test_backwards_compat_without_dual_result(self):
        """Caller legacy sin dual_result → comportamiento anterior (solo brief)."""
        analysis = dict(EMPTY_SCHEMA)
        analysis["work_types"] = ["cocina"]
        known = _build_data_known(analysis, quote=None)  # sin dual_result
        tipo_row = next((r for r in known if r["field"] == "Tipo de trabajo"), None)
        assert tipo_row is not None
        assert tipo_row["source"] == "brief"


class TestBernardiE2ELogging:
    """E2E con brief real de Bernardi + dual_result Bernardi-like.
    Valida que los 4 logs [context-reconcile] aparecen con los datos
    esperados — auditoría de que la observabilidad está completa."""

    def test_bernardi_brief_plus_dual_emits_four_reconcile_logs(self, caplog):
        brief = (
            "nuevo presupuesto material en pura prima onix white mate "
            "Cliente: Erica Bernardi SIN zocalos en rosario con colocacion"
        )
        # dual_result Bernardi-like: cocina con pileta simple + anafe,
        # más sector isla. R1 tiene cooktop + sink_simple.
        dual = {
            "sectores": [
                {
                    "id": "s_cocina",
                    "tipo": "cocina",
                    "tramos": [{
                        "id": "R1",
                        "descripcion": "Mesada",
                        "largo_m": {"valor": None, "status": "DUDOSO"},
                        "ancho_m": {"valor": 0.6, "status": "DUDOSO"},
                        "m2": {"valor": None, "status": "DUDOSO"},
                        "features": {
                            "sink_simple": True,
                            "sink_double": False,
                            "has_pileta": True,
                            "cooktop_groups": 1,
                        },
                        "zocalos": [], "frentin": [], "regrueso": [],
                    }],
                    "ambiguedades": [],
                },
                {
                    "id": "s_isla",
                    "tipo": "isla",
                    "tramos": [{
                        "id": "R3",
                        "descripcion": "Mesada",
                        "largo_m": {"valor": 2.05, "status": "CONFIRMADO"},
                        "ancho_m": {"valor": 0.6, "status": "CONFIRMADO"},
                        "m2": {"valor": 1.23, "status": "CONFIRMADO"},
                        "features": {},
                        "zocalos": [], "frentin": [], "regrueso": [],
                    }],
                    "ambiguedades": [],
                },
            ],
            "source": "MULTI_CROP",
        }
        with caplog.at_level(logging.INFO):
            out = build_context_analysis(brief, None, dual)

        # Verificamos que los 4 logs aparecen
        fields_logged = set()
        for r in caplog.records:
            if "[context-reconcile]" in r.message:
                for f in ("work_types", "isla_presence",
                          "pileta_simple_doble", "anafe_count"):
                    if f"field={f}" in r.message:
                        fields_logged.add(f)
        assert fields_logged == {
            "work_types", "isla_presence",
            "pileta_simple_doble", "anafe_count",
        }, f"Missing reconcile logs for: {{'work_types','isla_presence','pileta_simple_doble','anafe_count'}} - {fields_logged}"

        # Y el known tiene "Tipo de trabajo" con cocina + isla (source=dual_read,
        # brief vacío de work_types).
        tipo_row = next(
            (r for r in out["data_known"] if r["field"] == "Tipo de trabajo"),
            None,
        )
        assert tipo_row is not None
        assert "Cocina" in tipo_row["value"]
        assert "Isla" in tipo_row["value"]
        assert tipo_row["source"] == "dual_read"


class TestReconcileLogFormat:
    """Formato del log debe ser grep-friendly (key=value)."""

    def test_log_format_contains_all_expected_keys(self, caplog):
        analysis = {"isla_mentioned": True}
        feats = {"has_isla": False, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "cooktop_groups": 0}
        with caplog.at_level(logging.INFO):
            _detect_isla(analysis, feats)
        log = next(r.message for r in caplog.records
                   if "[context-reconcile]" in r.message)
        for key in ("field=", "brief_value=", "dual_read_value=", "final=",
                    "source=", "confidence=", "divergent="):
            assert key in log, f"Missing key '{key}' in log: {log}"


# ═══════════════════════════════════════════════════════
# PR #374 — Reconcile puros + assumptions con fallback brief→dual_read
# ═══════════════════════════════════════════════════════

from app.modules.quote_engine.context_analyzer import (  # noqa: E402
    reconcile_anafe_count,
    reconcile_pileta_simple_doble,
    _build_assumptions,
)


class TestReconcileAnafePure:
    """Helper puro exportable — no depende del schema de tech_detection.

    Bernardi real: brief sin mención de anafe + dual_read detectó 1 anafe
    (cooktop_groups=1). El reconcile debe devolver final=1 source=dual_read
    para que el assumptions layer pueda surface-ar el valor.
    """

    def test_bernardi_brief_silent_dual_read_detected(self):
        analysis = {"anafe_count": None}
        feats = {"cooktop_groups": 1, "sink_double": False, "sink_simple": True,
                 "has_pileta": True, "has_isla": True}
        rec = reconcile_anafe_count(analysis, feats)
        assert rec["final"] == 1
        assert rec["source"] == "dual_read"
        assert rec["divergent"] is False

    def test_brief_wins_over_dual_read(self):
        analysis = {"anafe_count": 2, "anafe_gas_y_electrico": True}
        feats = {"cooktop_groups": 1, "sink_double": False, "sink_simple": False,
                 "has_pileta": False, "has_isla": False}
        rec = reconcile_anafe_count(analysis, feats)
        assert rec["final"] == 2
        assert rec["source"] == "brief"
        assert rec["divergent"] is True

    def test_neither_returns_none(self):
        rec = reconcile_anafe_count({}, {"cooktop_groups": 0})
        assert rec["final"] is None
        assert rec["source"] == "default"


class TestReconcilePiletaPure:
    def test_bernardi_brief_silent_dual_read_simple(self):
        """Bernardi: brief sin mención de pileta tipo, dual_read detectó
        pileta simple → fallback a dual_read."""
        analysis = {"pileta_simple_doble": None, "pileta_mentioned": True}
        feats = {"cooktop_groups": 1, "sink_double": False, "sink_simple": True,
                 "has_pileta": True, "has_isla": True}
        rec = reconcile_pileta_simple_doble(analysis, feats)
        assert rec["final"] == "simple"
        assert rec["source"] == "dual_read"

    def test_bernardi_operator_corrects_to_doble(self):
        """Caso Javi: el operador respondió 'es 1 anafe y 1 pileta doble'
        contradiciendo el dual_read que dijo 'simple'. En el layer de
        `_build_assumptions` esto todavía no se ve (solo brief/dual_read);
        el operator_answer entra en build_commercial_attrs más arriba."""
        analysis = {"pileta_simple_doble": "doble", "pileta_mentioned": True}
        feats = {"cooktop_groups": 1, "sink_double": False, "sink_simple": True,
                 "has_pileta": True, "has_isla": True}
        rec = reconcile_pileta_simple_doble(analysis, feats)
        assert rec["final"] == "doble"
        assert rec["source"] == "brief"
        assert rec["divergent"] is True


class TestAssumptionsFallbackToDualRead:
    """Regresión Bernardi: brief silencioso + dual_read con anafe/pileta →
    assumption DEBE aparecer con source=dual_read. Antes desaparecía."""

    def _bernardi_dual(self):
        """Dual_read idéntico al log real de Bernardi: cocina con 1 anafe,
        pileta simple + isla sin artefactos."""
        return {
            "sectores": [
                {
                    "id": "cocina",
                    "tipo": "cocina",
                    "tramos": [{
                        "id": "t1",
                        "descripcion": "Mesada con pileta y anafe",
                        "largo_m": {"valor": 2.05, "status": "CONFIRMADO"},
                        "ancho_m": {"valor": 0.60, "status": "CONFIRMADO"},
                        "m2": {"valor": 1.23, "status": "CONFIRMADO"},
                        "zocalos": [],
                        "features": {
                            "cooktop_groups": 1,
                            "sink_simple": True,
                            "sink_double": False,
                            "has_pileta": True,
                            "has_isla": False,
                        },
                    }],
                },
                {
                    "id": "isla",
                    "tipo": "isla",
                    "tramos": [{
                        "id": "t2",
                        "descripcion": "Isla",
                        "largo_m": {"valor": 1.60, "status": "DUDOSO"},
                        "ancho_m": {"valor": 0.60, "status": "DUDOSO"},
                        "m2": {"valor": 0.96, "status": "DUDOSO"},
                        "zocalos": [],
                        "features": {},
                    }],
                },
            ],
        }

    def test_anafe_assumption_falls_back_to_dual_read_when_brief_silent(self):
        """Brief Bernardi: 'pura prima onix white mate Erica Bernardi SIN
        zocalos en rosario con colocacion' — NO menciona anafe. Dual read
        tiene cooktop_groups=1. Antes: assumption desaparecía → LLM
        re-contaba desde imagen y decía '2 anafes'. Ahora: assumption
        con source=dual_read.
        """
        analysis = {"anafe_count": None}  # brief no menciona
        dual = self._bernardi_dual()
        assumps = _build_assumptions(analysis, None, dual, config_defaults={})
        anafe = next((a for a in assumps if a["field"] == "Anafe — cantidad"), None)
        assert anafe is not None, (
            "Anafe assumption debe aparecer aunque el brief no lo mencione "
            "(fallback a dual_read)"
        )
        assert "1 anafe" in anafe["value"]
        assert anafe["source"] == "dual_read"
        assert "detectado en plano" in anafe["value"]

    def test_pileta_assumption_falls_back_to_dual_read(self):
        analysis = {"pileta_simple_doble": None, "pileta_mentioned": False}
        dual = self._bernardi_dual()
        assumps = _build_assumptions(analysis, None, dual, config_defaults={})
        pileta = next((a for a in assumps if a["field"] == "Pileta — bachas"), None)
        assert pileta is not None
        assert pileta["source"] == "dual_read"
        assert "detectada en plano" in pileta["value"]

    def test_brief_gas_electrico_still_wins_with_note(self):
        """Si brief dice '2 anafes (gas + electrico)' pero dual_read solo
        detectó 1: brief gana por precedencia y note marca divergencia."""
        analysis = {
            "anafe_count": 2, "anafe_gas_y_electrico": True,
            "pileta_simple_doble": None, "pileta_mentioned": False,
        }
        dual = self._bernardi_dual()
        assumps = _build_assumptions(analysis, None, dual, config_defaults={})
        anafe = next(a for a in assumps if a["field"] == "Anafe — cantidad")
        assert "2 anafes" in anafe["value"]
        assert anafe["source"] == "brief"
        assert anafe["note"] is not None
        assert "divergencia" in anafe["note"].lower()

    def test_no_anafe_no_pileta_when_neither_source_has_them(self):
        """Dual read sin anafe/pileta + brief sin mencionar → no emitir
        assumption vacía. El resumen no debe mencionar anafes."""
        analysis = {"anafe_count": None}
        dual = {"sectores": [{
            "id": "cocina", "tipo": "cocina",
            "tramos": [{
                "id": "t1", "descripcion": "Mesada",
                "largo_m": {"valor": 2.0}, "ancho_m": {"valor": 0.6},
                "m2": {"valor": 1.2}, "zocalos": [], "features": {},
            }],
        }]}
        assumps = _build_assumptions(analysis, None, dual, config_defaults={})
        assert not any("Anafe" in a["field"] for a in assumps)
        assert not any("bachas" in a.get("field", "").lower() for a in assumps)
