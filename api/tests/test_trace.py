"""Unit tests para `app.modules.agent._trace`.

El módulo es puro (solo logging + dict transforms), así que los tests
asertan sobre las salidas de los helpers `snapshot_*` y `diff_breakdown`.
Los `log_*` helpers (side-effect: logging.info) se ejercitan vía captura
del caplog para garantizar que no explotan y que el prefijo es estable.

Estos tests son un guard contra regresiones en el formato de logs — si
algo cambia el shape del snapshot, saltan los tests y revisamos si fue
intencional (y actualizamos a la vez el log grep de operación).
"""
from __future__ import annotations

import logging

import pytest

from app.modules.agent._trace import (
    _fp,
    snapshot_dual_read,
    snapshot_commercial_attrs,
    snapshot_derived_pieces,
    diff_breakdown,
    log_http_enter,
    log_stream_enter,
    log_bd_mutation,
    log_tool_call,
    log_tool_result,
    log_apply_answers,
    log_build_commercial_attrs,
    log_build_derived_isla_pieces,
    log_build_verified_context,
    log_reopen,
    log_messages_persist,
    log_sse_structural,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers puros — snapshots
# ═══════════════════════════════════════════════════════════════════════


def _dr_cocina_isla() -> dict:
    """Shape real de un dual_read con cocina (2 tramos) + isla (1 tramo)."""
    return {
        "sectores": [
            {
                "id": "cocina", "tipo": "cocina",
                "tramos": [
                    {"id": "t1", "largo_m": {"valor": 2.05}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.23}},
                    {"id": "t2", "largo_m": {"valor": 2.95}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.77}},
                ],
            },
            {
                "id": "isla", "tipo": "isla",
                "tramos": [
                    {"id": "t3", "largo_m": {"valor": 1.80}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.08}},
                ],
            },
        ],
    }


class TestSnapshotDualRead:
    def test_dimensions_flatten_sectors_and_tramos(self):
        snap = snapshot_dual_read(_dr_cocina_isla())
        assert snap["sectores"] == 2
        assert snap["tramos_total"] == 3
        assert snap["dimensions"][0] == {
            "sector": "cocina", "tipo": "cocina", "tramo": "t1",
            "largo": 2.05, "ancho": 0.60, "m2": 1.23,
        }
        assert snap["dimensions"][2] == {
            "sector": "isla", "tipo": "isla", "tramo": "t3",
            "largo": 1.80, "ancho": 0.60, "m2": 1.08,
        }

    def test_empty_returns_zero(self):
        assert snapshot_dual_read(None) == {"sectores": 0, "dimensions": []}
        snap = snapshot_dual_read({})
        assert snap["sectores"] == 0
        assert snap["dimensions"] == []

    def test_numeric_raw_values_supported(self):
        """Caso con `largo_m` primitivo en lugar de {"valor": ...}."""
        dr = {
            "sectores": [
                {"id": "cocina", "tipo": "cocina", "tramos": [
                    {"id": "t1", "largo_m": 2.05, "ancho_m": 0.60, "m2": 1.23},
                ]},
            ],
        }
        snap = snapshot_dual_read(dr)
        assert snap["dimensions"][0]["largo"] == 2.05


class TestSnapshotCommercialAttrs:
    def test_extracts_value_and_source(self):
        attrs = {
            "anafe_count": {"value": 1, "source": "dual_read"},
            "isla_presence": {"value": True, "source": "operator_answer"},
        }
        snap = snapshot_commercial_attrs(attrs)
        assert snap == {
            "anafe_count": {"value": 1, "source": "dual_read"},
            "isla_presence": {"value": True, "source": "operator_answer"},
        }

    def test_divergences_counted_not_expanded(self):
        attrs = {
            "anafe_count": {"value": 1, "source": "brief"},
            "divergences": [{"field": "x"}, {"field": "y"}],
        }
        snap = snapshot_commercial_attrs(attrs)
        assert snap["_divergences"] == 2

    def test_none_returns_empty(self):
        assert snapshot_commercial_attrs(None) == {}


class TestSnapshotDerivedPieces:
    def test_compact_shape(self):
        pieces = [
            {"description": "Pata frontal isla", "largo": 2.03, "prof": 0.9, "m2": 1.83, "source": "derived"},
            {"description": "Pata lateral izq", "largo": 0.6, "prof": 0.9, "m2": 0.54, "source": "derived"},
        ]
        snap = snapshot_derived_pieces(pieces)
        assert len(snap) == 2
        assert snap[0]["descripcion"] == "Pata frontal isla"
        assert snap[0]["largo"] == 2.03


# ═══════════════════════════════════════════════════════════════════════
# diff_breakdown
# ═══════════════════════════════════════════════════════════════════════


class TestDiffBreakdown:
    def test_added_removed_modified(self):
        pre = {"total_ars": 100, "material_name": "X"}
        post = {"total_ars": 200, "dual_read_result": {"sectores": []}}
        diff = diff_breakdown(pre, post)
        assert diff["added"] == ["dual_read_result"]
        assert diff["removed"] == ["material_name"]
        assert "total_ars" in diff["modified"]
        assert diff["modified"]["total_ars"] == {"before": 100, "after": 200}

    def test_critical_keys_get_snapshot_not_fingerprint(self):
        """Para `dual_read_result` el diff imprime el snapshot compacto,
        no un fingerprint opaco — así el log de Railway es grepeable."""
        pre = {"dual_read_result": {"sectores": []}}
        post = {"dual_read_result": _dr_cocina_isla()}
        diff = diff_breakdown(pre, post)
        change = diff["modified"]["dual_read_result"]
        assert change["before"]["tramos_total"] == 0
        assert change["after"]["tramos_total"] == 3
        assert change["after"]["dimensions"][0]["sector"] == "cocina"

    def test_non_critical_keys_get_fingerprint(self):
        """Para keys no-críticas usamos fingerprint para no inflar logs."""
        pre = {"brief_analysis": {"x": 1}}
        post = {"brief_analysis": {"x": 2}}
        diff = diff_breakdown(pre, post)
        change = diff["modified"]["brief_analysis"]
        assert "before_fp" in change and "after_fp" in change
        assert change["before_fp"] != change["after_fp"]

    def test_no_change_returns_empty(self):
        pre = {"total_ars": 100}
        post = {"total_ars": 100}
        diff = diff_breakdown(pre, post)
        assert diff == {"added": [], "removed": [], "modified": {}}

    def test_none_handled(self):
        diff = diff_breakdown(None, {"x": 1})
        assert diff["added"] == ["x"]


class TestFingerprint:
    def test_stable_and_compact(self):
        fp = _fp({"b": 1, "a": 2})
        assert fp.startswith("sha=") and "len=" in fp

    def test_same_payload_same_fp(self):
        assert _fp({"a": 1}) == _fp({"a": 1})

    def test_different_payload_different_fp(self):
        assert _fp({"a": 1}) != _fp({"a": 2})


# ═══════════════════════════════════════════════════════════════════════
# Side-effect helpers (smoke tests: no explotan + logs tienen prefijo)
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def trace_caplog(caplog):
    """Captura logs del logger `agent.trace`."""
    caplog.set_level(logging.INFO, logger="agent.trace")
    return caplog


class TestLogHelpersSmoke:
    def test_log_http_enter_has_prefix(self, trace_caplog):
        log_http_enter("quote-1", "POST /x", foo="bar")
        assert any("[trace:http:quote-1]" in r.message for r in trace_caplog.records)

    def test_log_stream_enter_includes_bd_state(self, trace_caplog):
        log_stream_enter(
            quote_id="q1", user_message="cotizar",
            plan_bytes=None, extra_files=None,
            bd_pre={"verified_context": "X", "total_ars": 100},
        )
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:stream:q1]" in msg
        assert "has_verified_context" in msg

    def test_log_bd_mutation_only_when_diff(self, trace_caplog):
        log_bd_mutation("q1", "test", {"a": 1}, {"a": 1})
        # Sin diff → sin log
        assert not any("[trace:bd-mutation:q1]" in r.message for r in trace_caplog.records)
        log_bd_mutation("q1", "test", {"a": 1}, {"a": 2})
        assert any("[trace:bd-mutation:q1]" in r.message for r in trace_caplog.records)

    def test_log_tool_call_and_result(self, trace_caplog):
        log_tool_call("q1", "calculate_quote", {"pieces": []})
        log_tool_result("q1", "calculate_quote", {"ok": True, "total_ars": 100})
        msgs = [r.message for r in trace_caplog.records]
        assert any("[trace:tool-call:q1] calculate_quote" in m for m in msgs)
        assert any("[trace:tool-result:q1] calculate_quote" in m for m in msgs)

    def test_log_tool_result_with_empty_dict_still_logs(self, trace_caplog):
        """Antes el código filtraba tanto que imprimía `{}` y dejaba al
        operador ciego. Ahora al menos las keys aparecen."""
        log_tool_result("q1", "catalog_batch_lookup", {"material": {"price": 527}})
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "keys=['material']" in msg

    def test_log_apply_answers(self, trace_caplog):
        log_apply_answers(
            "q1", flow="ctx",
            dual_before={"sectores": []},
            dual_after={"sectores": [{"id": "c", "tramos": []}]},
            answers=[{"id": "isla_presence", "value": True}],
        )
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:apply-answers:q1]" in msg
        assert "isla_presence" in msg

    def test_log_build_commercial_attrs(self, trace_caplog):
        log_build_commercial_attrs("q1", flow="dr-confirmed", result={
            "anafe_count": {"value": 1, "source": "dual_read"},
        })
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:commercial-attrs:q1]" in msg
        assert "anafe_count" in msg

    def test_log_build_derived_isla_pieces(self, trace_caplog):
        log_build_derived_isla_pieces("q1", flow="dr-confirmed",
            pieces=[{"description": "Pata frontal", "largo": 2.03, "prof": 0.9}],
            warnings=[],
        )
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:derived-pieces:q1]" in msg
        assert "count=1" in msg

    def test_log_build_verified_context(self, trace_caplog):
        log_build_verified_context("q1", flow="dr-confirmed", text="MEDIDAS VERIFICADAS X")
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:verified-context:q1]" in msg
        assert "chars=" in msg and "fp=" in msg

    def test_log_reopen(self, trace_caplog):
        log_reopen(
            "q1", kind="measurements",
            bd_pre={"verified_context": "X", "material_name": "Y"},
            bd_post={"dual_read_result": {"sectores": []}},
            msgs_count_pre=10, msgs_count_post=4,
            truncate_matched=True,
        )
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:reopen:q1]" in msg
        assert "msgs=10→4" in msg
        assert "truncate_matched=True" in msg

    def test_log_messages_persist(self, trace_caplog):
        log_messages_persist(
            "q1", flow="stream_chat-save",
            added_turns=[{"role": "user", "content": "hola"}],
            total_count=5,
        )
        msg = "\n".join(r.message for r in trace_caplog.records)
        assert "[trace:messages-persist:q1]" in msg
        assert "added=1" in msg
        assert "total=5" in msg

    def test_log_sse_structural_filters_non_structural(self, trace_caplog):
        log_sse_structural("q1", "text", "lorem ipsum...")  # text chunk → NO loguear
        assert not any("[trace:sse:q1]" in r.message for r in trace_caplog.records)

        log_sse_structural("q1", "dual_read_result", '{"sectores":[]}')
        assert any("[trace:sse:q1] type=dual_read_result" in r.message for r in trace_caplog.records)

        log_sse_structural("q1", "done", "")
        assert any("[trace:sse:q1] type=done" in r.message for r in trace_caplog.records)
