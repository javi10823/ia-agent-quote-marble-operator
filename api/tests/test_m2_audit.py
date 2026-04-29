"""Tests para PR #418 — `log_m2_audit` helper.

**Por qué este PR (load-bearing observability):** caso DYSCON
post-#416/#417 mostró un mismatch entre `material_m2` (calculator) y
suma de `piece_details` (validador). Para diagnosticar el RC había que
pedirle al operador un dump de DB. Mal — la observabilidad es del
sistema, no del operador.

Este helper:
- Loguea estado calculator y validator con shape uniforme.
- Tag `[m2-audit:<quote_id>]` para `grep` rápido en Railway.
- Línea fuerte `MISMATCH` cuando delta > 0.01.
- NUNCA tira excepciones al caller.

Tests cubren:
- Shape del log calculator y validator.
- MISMATCH se dispara solo cuando delta supera el threshold.
- Tolerancia a piezas mal-formadas (None, no-dict, m2 unparseable).
- quote_id None se renderiza como "?" sin romper.
"""
from __future__ import annotations

import logging

import pytest

from app.modules.quote_engine.audit import (
    _format_piece,
    _sum_piece_details,
    log_m2_audit,
)


# ═══════════════════════════════════════════════════════════════════════
# _sum_piece_details — usado por el log de calculator
# ═══════════════════════════════════════════════════════════════════════


class TestSumPieceDetails:
    def test_basic_sum(self):
        pieces = [
            {"m2": 1.5, "quantity": 2},
            {"m2": 0.6, "quantity": 1},
        ]
        assert _sum_piece_details(pieces) == 3.6

    def test_empty(self):
        assert _sum_piece_details([]) == 0.0

    def test_none(self):
        assert _sum_piece_details(None) == 0.0

    def test_skips_non_dict(self):
        """Pieza mal formada NO debe romper la suma."""
        pieces = [
            {"m2": 2.0, "quantity": 1},
            "not-a-dict",
            {"m2": 1.5, "quantity": 1},
        ]
        assert _sum_piece_details(pieces) == 3.5

    def test_skips_unparseable_m2(self):
        pieces = [
            {"m2": "abc", "quantity": 1},  # unparseable
            {"m2": 2.0, "quantity": 1},
        ]
        assert _sum_piece_details(pieces) == 2.0

    def test_default_quantity_1(self):
        """Pieza sin quantity → asume 1."""
        pieces = [{"m2": 1.5}]
        assert _sum_piece_details(pieces) == 1.5


# ═══════════════════════════════════════════════════════════════════════
# _format_piece — shape de la línea por pieza
# ═══════════════════════════════════════════════════════════════════════


class TestFormatPiece:
    def test_primary_fields_present(self):
        line = _format_piece(0, {
            "description": "Mesada",
            "largo": 1.5,
            "dim2": 0.6,
            "quantity": 2,
            "m2": 0.9,
            "override": False,
            "_is_frentin": False,
        })
        # Todos los campos primary visibles.
        assert "piece[0]" in line
        assert "description='Mesada'" in line
        assert "largo=1.5" in line
        assert "dim2=0.6" in line
        assert "quantity=2" in line
        assert "m2=0.9" in line
        assert "override=False" in line
        assert "_is_frentin=False" in line
        # Derivados.
        assert "m2_unit=0.9" in line
        assert "m2_total=1.8" in line

    def test_optional_field_only_when_present(self):
        """`_derived_kind` se loguea solo si está en la pieza."""
        with_field = _format_piece(0, {
            "description": "x", "largo": 1, "dim2": 1, "quantity": 1,
            "m2": 1, "override": False, "_is_frentin": False,
            "_derived_kind": "regrueso",
        })
        without_field = _format_piece(0, {
            "description": "x", "largo": 1, "dim2": 1, "quantity": 1,
            "m2": 1, "override": False, "_is_frentin": False,
        })
        assert "_derived_kind='regrueso'" in with_field
        assert "_derived_kind" not in without_field

    def test_not_a_dict_does_not_raise(self):
        line = _format_piece(0, "not-a-dict")
        assert "not-a-dict" in line.lower()
        assert "piece[0]" in line

    def test_unparseable_m2_does_not_raise(self):
        line = _format_piece(0, {
            "description": "x", "largo": 1, "dim2": 1, "quantity": 1,
            "m2": "garbage", "override": False, "_is_frentin": False,
        })
        # No tira — emite placeholder.
        assert "m2_unit=<unparseable>" in line


# ═══════════════════════════════════════════════════════════════════════
# log_m2_audit — shape del header + MISMATCH
# ═══════════════════════════════════════════════════════════════════════


class TestLogM2Audit:
    def test_calculator_header_shape(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.modules.quote_engine.audit"):
            log_m2_audit(
                quote_id="abc-123",
                source="calculator",
                material_m2=10.5,
                piece_details=[
                    {"description": "M1", "largo": 1, "dim2": 1, "quantity": 1, "m2": 10.5, "override": False, "_is_frentin": False},
                ],
            )
        msgs = [r.message for r in caplog.records]
        full = "\n".join(msgs)
        assert "[m2-audit:abc-123]" in full
        assert "calculator" in full
        assert "material_m2=10.5" in full
        assert "sum_piece_details=10.5" in full
        assert "pieces=1" in full

    def test_validator_header_shape(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.modules.quote_engine.audit"):
            log_m2_audit(
                quote_id="abc-123",
                source="validator",
                material_m2=10.5,
                piece_details=[
                    {"description": "M1", "largo": 1, "dim2": 1, "quantity": 1, "m2": 10.5, "override": False, "_is_frentin": False},
                ],
                recomputed_total=10.5,
            )
        full = "\n".join(r.message for r in caplog.records)
        assert "[m2-audit:abc-123]" in full
        assert "validator" in full
        assert "recomputed_total=10.5" in full
        assert "delta=0.0" in full

    def test_mismatch_calculator_emits_warning(self, caplog):
        """material_m2 != sum(piece_details) → línea MISMATCH warning."""
        with caplog.at_level(logging.INFO, logger="app.modules.quote_engine.audit"):
            log_m2_audit(
                quote_id="dyscon",
                source="calculator",
                material_m2=48.58,  # como en el caso real
                piece_details=[
                    {"description": "x", "largo": 1, "dim2": 1, "quantity": 1, "m2": 45.55, "override": False, "_is_frentin": False},
                ],
            )
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("MISMATCH" in w.message for w in warnings), \
            f"esperaba MISMATCH warning, vi: {[w.message for w in warnings]}"
        msg = next(w.message for w in warnings if "MISMATCH" in w.message)
        assert "delta=" in msg
        assert "calculator_vs_piece_details" in msg

    def test_mismatch_validator_emits_warning(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.modules.quote_engine.audit"):
            log_m2_audit(
                quote_id="dyscon",
                source="validator",
                material_m2=48.584,
                piece_details=[
                    {"description": "x", "largo": 1, "dim2": 1, "quantity": 1, "m2": 45.55, "override": False, "_is_frentin": False},
                ],
                recomputed_total=45.55,
            )
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("MISMATCH" in w.message for w in warnings)
        msg = next(w.message for w in warnings if "MISMATCH" in w.message)
        assert "stored_material_m2_vs_recomputed" in msg
        assert "delta=" in msg

    def test_no_mismatch_within_tolerance(self, caplog):
        """delta <= 0.01 → NO emite MISMATCH (alineado con validator)."""
        with caplog.at_level(logging.INFO, logger="app.modules.quote_engine.audit"):
            log_m2_audit(
                quote_id="x",
                source="calculator",
                material_m2=10.005,
                piece_details=[
                    {"description": "p", "largo": 1, "dim2": 1, "quantity": 1, "m2": 10.0, "override": False, "_is_frentin": False},
                ],
            )
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("MISMATCH" in w.message for w in warnings)

    def test_quote_id_none_renders_as_question_mark(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.modules.quote_engine.audit"):
            log_m2_audit(
                quote_id=None,
                source="calculator",
                material_m2=1.0,
                piece_details=[],
            )
        full = "\n".join(r.message for r in caplog.records)
        assert "[m2-audit:?]" in full

    def test_helper_never_raises(self):
        """Garbage input no debe romper. Es observabilidad, no negocio."""
        # Llamadas con shapes inesperados — todas deben retornar None.
        log_m2_audit(quote_id=None, source="calculator", material_m2=None, piece_details=None)
        log_m2_audit(quote_id="x", source="unknown", material_m2="not-a-number", piece_details="not-a-list")
        log_m2_audit(quote_id="x", source="calculator", material_m2=1, piece_details=[None, "garbage", 42])
        # Si llegamos acá sin excepción, OK.
