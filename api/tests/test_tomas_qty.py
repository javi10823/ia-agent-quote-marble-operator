"""Tests for `tomas_qty` — override explícito del operador para Agujero
de toma corriente.

Historia:
- PR #7 (DINALE 14/04/2026): fix para respetar override cuando el
  operador declaraba "Agujero de toma × 1" en el brief.
- PR #376 (Bernardi 21/04/2026): enforcement duro de alzada.
  El agujero de toma corriente se hace físicamente EN LA ALZADA —
  sin alzada, no hay dónde agujerear. Se eliminó la heurística
  zócalo-alto/revestimiento. Ahora el calculator requiere:
      (1) alzada presente en el despiece, AND
      (2) tomas_qty explícito en input.
"""
from __future__ import annotations

import re

import pytest

from app.modules.quote_engine.calculator import calculate_quote


# ── Regex mirror (también vive en agent.py) ─────────────────────────

_TOMAS_PATTERNS = [
    r'agujero\s+(?:de\s+)?toma(?:s)?\s*(?:de\s+corriente)?[^\n]{0,30}?[×x]\s*(\d{1,2})',
    r'agujero\s+(?:de\s+)?toma(?:s)?\s*(?:de\s+corriente)?[^\n]{0,30}?(\d{1,2})\s+unidad',
    r'(\d{1,2})\s+agujero(?:s)?\s+(?:de\s+)?toma',
]


def _detect_tomas(text: str) -> int | None:
    for pat in _TOMAS_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                qty = int(m.group(1))
                if 1 <= qty <= 50:
                    return qty
            except ValueError:
                continue
    return None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Agujero de toma × 1", 1),
        ("Agujero de toma × 1 unidad", 1),
        ("Agujero de toma x 2 unidades", 2),
        ("Agujero toma corriente × 4", 4),
        ("3 agujeros de toma", 3),
        ("Agujero de toma de corriente × 2", 2),
    ],
)
def test_tomas_regex_positive(text, expected):
    assert _detect_tomas(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "pileta × 3", "agujero anafe × 1", "toma de medidas en obra"],
)
def test_tomas_regex_negative(text):
    assert _detect_tomas(text) is None


class TestTomasQtyOverride:
    """Override explícito propaga al MO del presupuesto CUANDO HAY ALZADA.

    Post PR #376: todos los casos que agregan toma requieren alzada
    en el despiece.
    """

    def test_tomas_qty_creates_mo_line_with_alzada(self):
        result = calculate_quote({
            "client_name": "DINALE",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 31.37},
                {"description": "Alzada", "largo": 2.0, "prof": 0.10},
            ],
            "localidad": "rosario",
            "plazo": "4 meses",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "tomas_qty": 1,
        })
        assert result.get("ok"), result
        toma = [m for m in result["mo_items"] if "toma" in m["description"].lower() and "flete" not in m["description"].lower()]
        assert len(toma) == 1, f"Expected 1 Agujero toma line, got: {[m['description'] for m in result['mo_items']]}"
        assert toma[0]["quantity"] == 1

    def test_tomas_qty_greater_than_one_with_alzada(self):
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 20},
                {"description": "Alzada", "largo": 2.0, "prof": 0.10},
            ],
            "localidad": "rosario",
            "plazo": "30 dias",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "tomas_qty": 3,
        })
        toma = next(m for m in result["mo_items"] if m["description"] == "Agujero toma corriente")
        assert toma["quantity"] == 3
        # total ≈ unit_price × 3 (±1 rounding por ÷1.05 edificio)
        assert abs(toma["total"] - toma["unit_price"] * 3) <= 2

    def test_no_tomas_qty_no_alzada_no_toma(self):
        """Sin tomas_qty, sin alzada → no hay toma. Obvio."""
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.60}],
            "localidad": "rosario",
            "plazo": "30 dias",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
        })
        toma = [m for m in result["mo_items"] if "toma" in m["description"].lower() and "flete" not in m["description"].lower()]
        assert len(toma) == 0


class TestTomaCorrienteRequiresAlzada:
    """PR #376 — Enforcement duro: `Agujero toma corriente` SOLO si hay
    alzada en el despiece. Sin alzada, el ítem se ignora con warning.

    Caso central: Bernardi 21/04/2026 — cocina con anafe eléctrico, sin
    alzada. El LLM infería `tomas_qty=1` por la presencia de anafe; el
    calculator lo agregaba sin validar. Ahora el calculator lo ignora y
    surface-ea la inconsistencia como warning.
    """

    def _bernardi_inputs(self, tomas_qty=None, include_alzada=False):
        pieces = [
            {"description": "Mesada cocina 1 (c/pileta)",
             "largo": 2.05, "prof": 0.60},
            {"description": "Mesada cocina 2 (c/anafe)",
             "largo": 2.95, "prof": 0.60},
            {"description": "Isla", "largo": 1.60, "prof": 0.60},
        ]
        if include_alzada:
            pieces.append({"description": "Alzada", "largo": 2.05, "prof": 0.10})
        inputs = {
            "client_name": "Erica Bernardi",
            "project": "Cocina e Isla",
            "material": "PURA PRIMA ONIX WHITE MATE",
            "pieces": pieces,
            "localidad": "rosario",
            "plazo": "30 días",
            "is_edificio": False,
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "anafe": True,
        }
        if tomas_qty is not None:
            inputs["tomas_qty"] = tomas_qty
        return inputs

    def test_bernardi_sin_alzada_ignora_tomas_qty_llm_inferred(self):
        """Caso central: el LLM pasa tomas_qty=1 (infiriendo desde anafe
        eléctrico) pero no hay alzada en el despiece. El calculator NO
        agrega el ítem. El MO queda sin 'Agujero toma corriente'."""
        result = calculate_quote(self._bernardi_inputs(tomas_qty=1))
        assert result.get("ok"), result
        tomas = [
            m for m in result["mo_items"]
            if "toma" in m["description"].lower()
            and "flete" not in m["description"].lower()
        ]
        assert len(tomas) == 0, (
            f"Sin alzada, NO debería haber toma corriente. Got: "
            f"{[m['description'] for m in result['mo_items']]}"
        )

    def test_bernardi_sin_alzada_surfaces_warning(self):
        """Cuando tomas_qty se ignora por falta de alzada, el resultado
        debe incluir un warning claro para revisión manual."""
        result = calculate_quote(self._bernardi_inputs(tomas_qty=1))
        warns = result.get("warnings") or []
        assert any(
            "alzada" in (w or "").lower() and ("toma" in (w or "").lower() or "tomas_qty" in (w or "").lower())
            for w in warns
        ), (
            f"Esperaba un warning mencionando 'alzada' y toma. Got: {warns}"
        )

    def test_bernardi_con_alzada_y_explicit_tomas_agrega(self):
        """Si se agrega alzada al despiece Y viene tomas_qty, el item SÍ
        se agrega (regla válida)."""
        result = calculate_quote(
            self._bernardi_inputs(tomas_qty=1, include_alzada=True),
        )
        tomas = [
            m for m in result["mo_items"]
            if m["description"] == "Agujero toma corriente"
        ]
        assert len(tomas) == 1
        assert tomas[0]["quantity"] == 1

    def test_con_alzada_sin_tomas_qty_no_infiere(self):
        """Tener alzada NO es suficiente: el calculator no inventa un
        toma si no viene tomas_qty explícito. Esto cierra el path de
        inferencia libre."""
        result = calculate_quote(
            self._bernardi_inputs(tomas_qty=None, include_alzada=True),
        )
        tomas = [
            m for m in result["mo_items"]
            if "toma" in m["description"].lower()
            and "flete" not in m["description"].lower()
        ]
        assert len(tomas) == 0

    def test_heuristica_zocalo_alto_no_agrega_toma_automatica(self):
        """PR #376 eliminó la heurística 'zócalo alto > 10cm → toma
        automática'. Validación explícita de la regresión: un zócalo
        alto sin alzada ya NO dispara una toma corriente."""
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina con zócalo alto",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60},
                # Zócalo con alto >10cm — antes disparaba el auto-add
                {"description": "Zócalo", "largo": 2.0, "prof": 0.05, "alto": 0.15},
            ],
            "localidad": "rosario",
            "plazo": "30 días",
            "is_edificio": False,
            "colocacion": True,
            "pileta": "empotrada_cliente",
        })
        tomas = [
            m for m in result["mo_items"]
            if "toma" in m["description"].lower()
            and "flete" not in m["description"].lower()
        ]
        assert len(tomas) == 0, (
            "Zócalo alto (>10cm) ya no debería agregar toma corriente "
            "automáticamente. La heurística fue eliminada en PR #376."
        )

    def test_heuristica_revestimiento_no_agrega_toma_automatica(self):
        """PR #376 eliminó la heurística 'revestimiento → toma
        automática'. Validación explícita de la regresión."""
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina con revestimiento",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60},
                {"description": "Revestimiento de pared", "largo": 2.0, "prof": 0.5},
            ],
            "localidad": "rosario",
            "plazo": "30 días",
            "is_edificio": False,
            "colocacion": True,
            "pileta": "empotrada_cliente",
        })
        tomas = [
            m for m in result["mo_items"]
            if "toma" in m["description"].lower()
            and "flete" not in m["description"].lower()
        ]
        assert len(tomas) == 0


class TestHasAlzadaPiece:
    """Helper puro — detecta si el despiece contiene al menos una pieza
    de alzada. Mismo criterio que el renderer (desc empieza con 'alzada')."""

    def test_detects_plain_alzada(self):
        from app.modules.quote_engine.calculator import _has_alzada_piece
        assert _has_alzada_piece([
            {"description": "Mesada", "largo": 2.0},
            {"description": "Alzada", "largo": 2.0},
        ]) is True

    def test_detects_case_insensitive(self):
        from app.modules.quote_engine.calculator import _has_alzada_piece
        assert _has_alzada_piece([{"description": "ALZADA", "largo": 2.0}]) is True
        assert _has_alzada_piece([{"description": "alzada", "largo": 2.0}]) is True
        assert _has_alzada_piece([{"description": "Alzada trasera", "largo": 2.0}]) is True

    def test_tolera_whitespace_inicial(self):
        from app.modules.quote_engine.calculator import _has_alzada_piece
        assert _has_alzada_piece([{"description": "  Alzada", "largo": 2.0}]) is True

    def test_no_detecta_mesada_normal(self):
        from app.modules.quote_engine.calculator import _has_alzada_piece
        assert _has_alzada_piece([
            {"description": "Mesada cocina", "largo": 2.0},
            {"description": "Zócalo", "largo": 2.0},
        ]) is False

    def test_no_detecta_mencion_en_medio_de_descripcion(self):
        """Solo matchea si empieza con 'alzada'. Una mesada que mencione
        la palabra 'alzada' en el medio no cuenta como alzada."""
        from app.modules.quote_engine.calculator import _has_alzada_piece
        assert _has_alzada_piece([
            {"description": "Mesada con alzada incluida", "largo": 2.0},
        ]) is False

    def test_lista_vacia_o_none(self):
        from app.modules.quote_engine.calculator import _has_alzada_piece
        assert _has_alzada_piece([]) is False
        assert _has_alzada_piece(None) is False
