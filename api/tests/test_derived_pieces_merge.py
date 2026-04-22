"""Tests para PR #386 — materializar piezas derivadas (patas de isla)
como tramos reales del despiece.

Criterios del operador:
  1. Después de [CONTEXT_CONFIRMED], las patas aparecen como tramos del
     sector isla del dual_read_result.
  2. Reconfirmar contexto no duplica (idempotencia).
  3. Edit del operador en una pata preserva el valor en [DUAL_READ_CONFIRMED]
     (no se pisa con el recompute determinístico).
  4. Paso 2 y PDF leen de una única fuente (el despiece) — no hay doble
     conteo contra un `derived_pieces` legacy en el system prompt.
  5. /reopen-context limpia los tramos `_derived:true` para que la próxima
     confirmación de contexto regenere desde cero.
"""
from __future__ import annotations

import copy

import pytest

from app.modules.quote_engine.dual_reader import (
    merge_derived_pieces_into_dual_read,
    merge_alzada_tramos_into_dual_read,
    clear_all_derived_tramos,
    dual_read_has_derived_pieces,
    build_derived_isla_pieces,
    build_verified_context,
    _sector_visible_perimeter,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers puros: merge_derived_pieces_into_dual_read
# ═══════════════════════════════════════════════════════════════════════


def _dr_with_isla() -> dict:
    """Dual_read con cocina + isla (1 tramo mesada principal)."""
    return {
        "sectores": [
            {
                "id": "cocina", "tipo": "cocina",
                "tramos": [
                    {"id": "c1", "descripcion": "Mesada cocina",
                     "largo_m": {"valor": 2.50}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.50}},
                ],
            },
            {
                "id": "isla", "tipo": "isla",
                "tramos": [
                    {"id": "i1", "descripcion": "Mesada isla",
                     "largo_m": {"valor": 2.03}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.22}},
                ],
            },
        ],
    }


def _derived_3_patas() -> list[dict]:
    """Shape real que devuelve `build_derived_isla_pieces` para 3 patas
    (frontal + 2 laterales), alto=0.90, prof=0.60, largo_isla=2.03."""
    return [
        {"description": "Pata frontal isla", "largo": 2.03, "prof": 0.90, "m2": 1.83, "source": "derived_from_operator_answers"},
        {"description": "Pata lateral isla izq", "largo": 0.60, "prof": 0.90, "m2": 0.54, "source": "derived_from_operator_answers"},
        {"description": "Pata lateral isla der", "largo": 0.60, "prof": 0.90, "m2": 0.54, "source": "derived_from_operator_answers"},
    ]


class TestMergeDerivedPiecesIntoDualRead:
    def test_adds_tramos_to_isla_sector(self):
        """Criterio 1: las patas quedan como tramos del sector isla."""
        result = merge_derived_pieces_into_dual_read(_dr_with_isla(), _derived_3_patas())
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        # 1 mesada + 3 patas = 4 tramos
        assert len(isla["tramos"]) == 4
        # Mesada preservada primera
        assert isla["tramos"][0]["descripcion"] == "Mesada isla"
        # Patas agregadas con shape correcto
        pata_frontal = isla["tramos"][1]
        assert pata_frontal["descripcion"] == "Pata frontal isla"
        assert pata_frontal["largo_m"] == {"valor": 2.03, "status": "CONFIRMADO"}
        assert pata_frontal["ancho_m"] == {"valor": 0.90, "status": "CONFIRMADO"}
        assert pata_frontal["m2"] == {"valor": 1.83, "status": "CONFIRMADO"}
        assert pata_frontal["zocalos"] == []
        assert pata_frontal["_derived"] is True
        assert pata_frontal["_derived_source"] == "derived_from_operator_answers"

    def test_idempotent_replaces_existing_derived(self):
        """Criterio 2: re-correr con las mismas piezas no duplica.
        Las patas existentes se reemplazan con las nuevas."""
        step1 = merge_derived_pieces_into_dual_read(_dr_with_isla(), _derived_3_patas())
        step2 = merge_derived_pieces_into_dual_read(step1, _derived_3_patas())
        isla = next(s for s in step2["sectores"] if s["tipo"] == "isla")
        assert len(isla["tramos"]) == 4  # no se agregaron patas nuevas

    def test_idempotent_with_different_values_replaces(self):
        """Si el operador cambia el alto de patas (ej: 0.90 → 0.80), las
        viejas se descartan y se agregan las nuevas."""
        step1 = merge_derived_pieces_into_dual_read(_dr_with_isla(), _derived_3_patas())
        # Re-correr con alto diferente
        new_pieces = [
            {"description": "Pata frontal isla", "largo": 2.03, "prof": 0.80, "m2": 1.62, "source": "x"},
            {"description": "Pata lateral isla izq", "largo": 0.60, "prof": 0.80, "m2": 0.48, "source": "x"},
            {"description": "Pata lateral isla der", "largo": 0.60, "prof": 0.80, "m2": 0.48, "source": "x"},
        ]
        step2 = merge_derived_pieces_into_dual_read(step1, new_pieces)
        isla = next(s for s in step2["sectores"] if s["tipo"] == "isla")
        assert len(isla["tramos"]) == 4
        pata_frontal = isla["tramos"][1]
        assert pata_frontal["ancho_m"]["valor"] == 0.80

    def test_empty_pieces_cleans_existing(self):
        """Criterio 5: `derived_pieces=[]` limpia los `_derived:true` sin
        agregar. Usado por /reopen-context y cuando el operador cambia
        la respuesta a "no hay patas"."""
        step1 = merge_derived_pieces_into_dual_read(_dr_with_isla(), _derived_3_patas())
        isla = next(s for s in step1["sectores"] if s["tipo"] == "isla")
        assert len(isla["tramos"]) == 4
        step2 = merge_derived_pieces_into_dual_read(step1, [])
        isla = next(s for s in step2["sectores"] if s["tipo"] == "isla")
        # Solo la mesada queda
        assert len(isla["tramos"]) == 1
        assert isla["tramos"][0]["descripcion"] == "Mesada isla"

    def test_none_pieces_cleans_existing(self):
        step1 = merge_derived_pieces_into_dual_read(_dr_with_isla(), _derived_3_patas())
        step2 = merge_derived_pieces_into_dual_read(step1, None)
        isla = next(s for s in step2["sectores"] if s["tipo"] == "isla")
        assert len(isla["tramos"]) == 1

    def test_no_isla_sector_noop(self):
        """Sin sector isla, no se agrega nada (las patas no tienen sentido)."""
        dr = {
            "sectores": [
                {"id": "cocina", "tipo": "cocina", "tramos": []},
            ],
        }
        result = merge_derived_pieces_into_dual_read(dr, _derived_3_patas())
        assert result == dr

    def test_does_not_mutate_input(self):
        """Funcional puro — el dict original queda intacto."""
        dr = _dr_with_isla()
        snapshot = copy.deepcopy(dr)
        merge_derived_pieces_into_dual_read(dr, _derived_3_patas())
        assert dr == snapshot

    def test_preserves_non_isla_sectors_untouched(self):
        """Cocina no se toca."""
        dr = _dr_with_isla()
        result = merge_derived_pieces_into_dual_read(dr, _derived_3_patas())
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        assert cocina["tramos"][0]["descripcion"] == "Mesada cocina"
        assert len(cocina["tramos"]) == 1

    def test_preserves_user_edited_mesada_isla(self):
        """Criterio 3: la mesada principal (no `_derived`) se preserva
        aunque reconfirmemos patas."""
        dr = _dr_with_isla()
        # Simular edit del operador en la mesada isla
        dr["sectores"][1]["tramos"][0]["largo_m"]["valor"] = 1.80
        dr["sectores"][1]["tramos"][0]["m2"]["valor"] = 1.08
        result = merge_derived_pieces_into_dual_read(dr, _derived_3_patas())
        mesada = next(s for s in result["sectores"] if s["tipo"] == "isla")["tramos"][0]
        # Preservada con el valor editado
        assert mesada["largo_m"]["valor"] == 1.80
        assert mesada["m2"]["valor"] == 1.08

    def test_empty_dual_read_returns_empty(self):
        assert merge_derived_pieces_into_dual_read(None, _derived_3_patas()) == {}
        assert merge_derived_pieces_into_dual_read({}, _derived_3_patas()) == {}


class TestDualReadHasDerivedPieces:
    def test_returns_true_when_isla_has_derived(self):
        dr = merge_derived_pieces_into_dual_read(_dr_with_isla(), _derived_3_patas())
        assert dual_read_has_derived_pieces(dr) is True

    def test_returns_false_on_clean_dual_read(self):
        assert dual_read_has_derived_pieces(_dr_with_isla()) is False

    def test_returns_false_on_empty(self):
        assert dual_read_has_derived_pieces(None) is False
        assert dual_read_has_derived_pieces({}) is False

    def test_detects_derived_in_any_sector(self):
        """Si por alguna razón hay `_derived:true` en otro sector
        (futuro: frentines, etc.), también lo detecta."""
        dr = {
            "sectores": [
                {"id": "cocina", "tipo": "cocina", "tramos": [
                    {"id": "fake", "_derived": True, "largo_m": {"valor": 1.0}},
                ]},
            ],
        }
        assert dual_read_has_derived_pieces(dr) is True


# ═══════════════════════════════════════════════════════════════════════
# Integración: build_derived_isla_pieces → merge → build_verified_context
# No doble conteo.
# ═══════════════════════════════════════════════════════════════════════


def _answers_patas_3_sides() -> list[dict]:
    """Answers que producen 3 patas (frontal + 2 laterales). El value
    `frontal_y_laterales` matchea la entry canónica de
    `_ISLA_PATAS_SIDES` en dual_reader.py."""
    return [
        {"id": "isla_patas", "value": "frontal_y_laterales", "label": "Frontal + 2 laterales"},
        {"id": "isla_patas_alto", "value": "0.90", "label": "0.90m"},
        {"id": "isla_profundidad", "value": "0.60", "label": "0.60m"},
    ]


class TestNoDoubleCountingInVerifiedContext:
    """Criterio 4: Paso 2 ve las piezas UNA sola vez.

    Antes del PR: las patas estaban en el sector ISLA (tramos) + en el
    bloque `[PIEZAS DERIVADAS]`. Si ambas fuentes se pasaran a
    build_verified_context, Claude las sumaría doble.

    Este PR: llamamos `build_verified_context(..., derived_pieces=None)`
    cuando ya están como tramos. El texto resultante menciona las patas
    SOLO como tramos bajo `SECTOR: ISLA`.
    """

    def test_patas_only_appear_once_as_tramos(self):
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=_answers_patas_3_sides(),
            verified_measurements=_dr_with_isla(),
        )
        assert pieces, "precondición: build_derived_isla_pieces debe emitir piezas"
        # Mergear al despiece
        dual_with_derived = merge_derived_pieces_into_dual_read(
            _dr_with_isla(), pieces,
        )
        # Llamar build_verified_context como lo hace el handler #386:
        # derived_pieces=None porque ya están como tramos.
        ctx = build_verified_context(
            dual_with_derived, commercial_attrs=None, derived_pieces=None,
        )
        # Las patas aparecen en el bloque de SECTOR: ISLA, una vez cada una.
        assert ctx.count("Pata frontal isla") == 1
        assert ctx.count("Pata lateral isla izq") == 1
        assert ctx.count("Pata lateral isla der") == 1
        # El bloque legacy `[PIEZAS DERIVADAS DE RESPUESTAS DEL OPERADOR`
        # NO debe aparecer.
        assert "PIEZAS DERIVADAS DE RESPUESTAS DEL OPERADOR" not in ctx

    def test_would_double_count_if_both_sources_passed(self):  # noqa: E501
        pass

    # Placeholder para la refactor de kind — ver tests más abajo en la
    # clase TestMergeAlzadaTramos que cubre el split por kind.


# ═══════════════════════════════════════════════════════════════════════
# PR #388 — Alzada como tramo derivado por sector
# ═══════════════════════════════════════════════════════════════════════


def _dr_cocina_L_and_bano() -> dict:
    """Dual_read con cocina en L (2 tramos) + baño vanitory (1 tramo).
    Ambos NO-isla → deberían recibir alzada."""
    return {
        "sectores": [
            {
                "id": "cocina", "tipo": "cocina",
                "tramos": [
                    {"id": "c1", "descripcion": "Cocina 1",
                     "largo_m": {"valor": 2.05}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.23}},
                    {"id": "c2", "descripcion": "Cocina 2",
                     "largo_m": {"valor": 2.95}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.77}},
                ],
            },
            {
                "id": "bano", "tipo": "baño",
                "tramos": [
                    {"id": "b1", "descripcion": "Vanitory",
                     "largo_m": {"valor": 1.20}, "ancho_m": {"valor": 0.50}, "m2": {"valor": 0.60}},
                ],
            },
        ],
    }


def _dr_isla_only() -> dict:
    return {
        "sectores": [
            {
                "id": "isla", "tipo": "isla",
                "tramos": [
                    {"id": "i1", "descripcion": "Mesada isla",
                     "largo_m": {"valor": 2.03}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.22}},
                ],
            },
        ],
    }


class TestSectorVisiblePerimeter:
    def test_sums_largos_of_non_derived_tramos(self):
        sector = {
            "id": "cocina", "tipo": "cocina",
            "tramos": [
                {"largo_m": {"valor": 2.05}},
                {"largo_m": {"valor": 2.95}},
            ],
        }
        assert _sector_visible_perimeter(sector) == 5.00

    def test_skips_derived_tramos(self):
        sector = {
            "id": "cocina", "tipo": "cocina",
            "tramos": [
                {"largo_m": {"valor": 2.05}},
                {"largo_m": {"valor": 1.80}, "_derived": True, "_derived_kind": "alzada"},
            ],
        }
        # Solo el 2.05, la alzada previa se ignora (no se usa para derivar nueva).
        assert _sector_visible_perimeter(sector) == 2.05

    def test_handles_primitive_largo(self):
        """Si `largo_m` es número crudo (no dict con valor), también funciona."""
        sector = {"tramos": [{"largo_m": 1.50}, {"largo_m": 2.00}]}
        assert _sector_visible_perimeter(sector) == 3.50

    def test_empty_sector(self):
        assert _sector_visible_perimeter(None) == 0.0
        assert _sector_visible_perimeter({}) == 0.0
        assert _sector_visible_perimeter({"tramos": []}) == 0.0


class TestMergeAlzadaTramos:
    def test_adds_one_tramo_per_non_isla_sector(self):
        dr = _dr_cocina_L_and_bano()
        result = merge_alzada_tramos_into_dual_read(dr, alto_m=0.10, active=True)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        bano = next(s for s in result["sectores"] if s["tipo"] == "baño")

        # Cocina: 2 tramos originales + 1 alzada
        assert len(cocina["tramos"]) == 3
        alz_cocina = cocina["tramos"][-1]
        assert alz_cocina["descripcion"] == "Alzada cocina"
        assert alz_cocina["largo_m"]["valor"] == 5.00  # 2.05 + 2.95
        assert alz_cocina["ancho_m"]["valor"] == 0.10
        assert alz_cocina["m2"]["valor"] == 0.50
        assert alz_cocina["_derived"] is True
        assert alz_cocina["_derived_kind"] == "alzada"

        # Baño: 1 tramo original + 1 alzada
        assert len(bano["tramos"]) == 2
        alz_bano = bano["tramos"][-1]
        assert alz_bano["descripcion"] == "Alzada bano"  # id es "bano"
        assert alz_bano["largo_m"]["valor"] == 1.20
        assert alz_bano["ancho_m"]["valor"] == 0.10

    def test_skips_isla_sector(self):
        dr = _dr_isla_only()
        result = merge_alzada_tramos_into_dual_read(dr, alto_m=0.10, active=True)
        isla = result["sectores"][0]
        # La isla no recibe alzada — sigue con su único tramo de mesada.
        assert len(isla["tramos"]) == 1
        assert not any(t.get("_derived_kind") == "alzada" for t in isla["tramos"])

    def test_active_false_only_cleans(self):
        """Si el operador responde 'no' a alzada, se limpian las previas
        sin agregar nuevas."""
        dr = _dr_cocina_L_and_bano()
        with_alzada = merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        cleaned = merge_alzada_tramos_into_dual_read(with_alzada, 0.10, active=False)
        # Cocina vuelve a sus 2 tramos originales
        cocina = next(s for s in cleaned["sectores"] if s["tipo"] == "cocina")
        assert len(cocina["tramos"]) == 2
        assert not any(t.get("_derived_kind") == "alzada" for t in cocina["tramos"])

    def test_zero_alto_only_cleans(self):
        """alto_m=0 o None equivale a active=False."""
        dr = _dr_cocina_L_and_bano()
        result = merge_alzada_tramos_into_dual_read(dr, alto_m=0, active=True)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        assert len(cocina["tramos"]) == 2

        result2 = merge_alzada_tramos_into_dual_read(dr, alto_m=None, active=True)
        cocina2 = next(s for s in result2["sectores"] if s["tipo"] == "cocina")
        assert len(cocina2["tramos"]) == 2

    def test_idempotent_same_alto(self):
        """Llamar 2 veces con el mismo alto no duplica."""
        dr = _dr_cocina_L_and_bano()
        step1 = merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        step2 = merge_alzada_tramos_into_dual_read(step1, 0.10, active=True)
        cocina = next(s for s in step2["sectores"] if s["tipo"] == "cocina")
        assert len(cocina["tramos"]) == 3  # 2 originales + 1 alzada (no 2 alzadas)

    def test_idempotent_different_alto_replaces(self):
        """Cambiar el alto de 10cm a 5cm reemplaza (no agrega)."""
        dr = _dr_cocina_L_and_bano()
        step1 = merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        step2 = merge_alzada_tramos_into_dual_read(step1, 0.05, active=True)
        cocina = next(s for s in step2["sectores"] if s["tipo"] == "cocina")
        assert len(cocina["tramos"]) == 3
        alz = next(t for t in cocina["tramos"] if t.get("_derived_kind") == "alzada")
        assert alz["ancho_m"]["valor"] == 0.05
        assert alz["m2"]["valor"] == 0.25  # 5.00 × 0.05

    def test_does_not_mutate_input(self):
        dr = _dr_cocina_L_and_bano()
        snapshot = copy.deepcopy(dr)
        merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        assert dr == snapshot

    def test_empty_dual_read(self):
        assert merge_alzada_tramos_into_dual_read(None, 0.10) == {}
        assert merge_alzada_tramos_into_dual_read({}, 0.10) == {}

    def test_sector_with_no_visible_tramos_skipped(self):
        """Si un sector solo tiene tramos derivados (no mesada original),
        no se le agrega alzada."""
        dr = {
            "sectores": [
                {"id": "cocina", "tipo": "cocina", "tramos": [
                    # Solo un tramo ficticio ya derivado (edge case):
                    {"largo_m": {"valor": 1.0}, "_derived": True, "_derived_kind": "foo"},
                ]},
            ],
        }
        result = merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        cocina = result["sectores"][0]
        # No se agregó alzada (perímetro=0 porque el único tramo es derivado)
        assert not any(t.get("_derived_kind") == "alzada" for t in cocina["tramos"])

    def test_coexists_with_isla_patas(self):
        """Alzada en cocina + patas en isla → ambos kinds coexisten."""
        dr = {
            "sectores": [
                {"id": "cocina", "tipo": "cocina", "tramos": [
                    {"largo_m": {"valor": 2.00}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.20}},
                ]},
                {"id": "isla", "tipo": "isla", "tramos": [
                    {"largo_m": {"valor": 1.80}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.08}},
                ]},
            ],
        }
        patas = [
            {"description": "Pata frontal isla", "largo": 1.80, "prof": 0.90, "m2": 1.62, "source": "x"},
        ]
        with_patas = merge_derived_pieces_into_dual_read(dr, patas)
        with_both = merge_alzada_tramos_into_dual_read(with_patas, 0.10, active=True)

        isla = next(s for s in with_both["sectores"] if s["tipo"] == "isla")
        cocina = next(s for s in with_both["sectores"] if s["tipo"] == "cocina")
        # Isla tiene mesada + pata (no alzada — es isla)
        assert len(isla["tramos"]) == 2
        assert any(t.get("_derived_kind") == "isla_pata" for t in isla["tramos"])
        assert not any(t.get("_derived_kind") == "alzada" for t in isla["tramos"])
        # Cocina tiene mesada + alzada (no patas)
        assert len(cocina["tramos"]) == 2
        assert any(t.get("_derived_kind") == "alzada" for t in cocina["tramos"])

    def test_merge_patas_does_not_pisa_alzada_in_same_sector(self):
        """Guard: si por alguna razón hubiera alzada y luego corremos el
        helper de patas (kind='isla_pata') sobre el mismo dual_read, la
        alzada debe sobrevivir (solo se pisan los de kind='isla_pata')."""
        dr = {
            "sectores": [
                {"id": "isla", "tipo": "isla", "tramos": [
                    {"largo_m": {"valor": 1.80}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.08}},
                    # Hipotético: alguien puso alzada en isla (no deberíamos
                    # pero el helper no debería borrarlo al reconfirmar patas)
                    {"largo_m": {"valor": 1.80}, "_derived": True, "_derived_kind": "alzada"},
                ]},
            ],
        }
        new_patas = [{"description": "Pata frontal isla", "largo": 1.80, "prof": 0.90, "m2": 1.62}]
        result = merge_derived_pieces_into_dual_read(dr, new_patas)
        isla = result["sectores"][0]
        # La alzada sigue, la pata se agregó
        assert any(t.get("_derived_kind") == "alzada" for t in isla["tramos"])
        assert any(t.get("_derived_kind") == "isla_pata" for t in isla["tramos"])


class TestClearAllDerivedTramos:
    def test_removes_all_kinds(self):
        dr = _dr_cocina_L_and_bano()
        dr["sectores"].append({
            "id": "isla", "tipo": "isla",
            "tramos": [
                {"id": "i1", "largo_m": {"valor": 1.80}, "ancho_m": {"valor": 0.60}, "m2": {"valor": 1.08}},
            ],
        })
        # Agregar patas + alzadas
        with_patas = merge_derived_pieces_into_dual_read(dr, [
            {"description": "Pata frontal isla", "largo": 1.80, "prof": 0.90, "m2": 1.62},
        ])
        with_both = merge_alzada_tramos_into_dual_read(with_patas, 0.10, active=True)
        # Limpiar todo
        cleaned = clear_all_derived_tramos(with_both)
        for sector in cleaned["sectores"]:
            assert not any(t.get("_derived") for t in sector["tramos"])

    def test_preserves_non_derived(self):
        dr = _dr_cocina_L_and_bano()
        cleaned = clear_all_derived_tramos(dr)
        # Sin cambios: no había nada derivado
        cocina = next(s for s in cleaned["sectores"] if s["tipo"] == "cocina")
        assert len(cocina["tramos"]) == 2

    def test_empty_input(self):
        assert clear_all_derived_tramos(None) == {}
        assert clear_all_derived_tramos({}) == {}


class TestAlzadaAppearsInVerifiedContext:
    """Integración: post-merge, verified_context muestra la alzada como
    tramo bajo SECTOR: X. Claude la ve ahí sin bloque aparte."""

    def test_alzada_tramo_emitted(self):
        dr = _dr_cocina_L_and_bano()
        with_alzada = merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        ctx = build_verified_context(with_alzada, commercial_attrs=None, derived_pieces=None)
        assert "Alzada cocina" in ctx
        assert "5.0m × 0.1m" in ctx  # perímetro × alto
        assert "Alzada bano" in ctx

    def test_no_alzada_when_only_isla(self):
        dr = _dr_isla_only()
        with_alzada = merge_alzada_tramos_into_dual_read(dr, 0.10, active=True)
        ctx = build_verified_context(with_alzada, commercial_attrs=None, derived_pieces=None)
        assert "Alzada" not in ctx
        """Contra-ejemplo: si el handler accidentalmente pasara
        derived_pieces a build_verified_context TAMBIÉN con los tramos
        mergeados, las patas aparecen DOS veces. Este test documenta la
        razón del `derived_pieces=None` del handler."""
        pieces, _ = build_derived_isla_pieces(
            operator_answers=_answers_patas_3_sides(),
            verified_measurements=_dr_with_isla(),
        )
        dual_with_derived = merge_derived_pieces_into_dual_read(
            _dr_with_isla(), pieces,
        )
        ctx_bad = build_verified_context(
            dual_with_derived, commercial_attrs=None, derived_pieces=pieces,
        )
        # La pata frontal aparece 2 veces (tramos + bloque derivado).
        assert ctx_bad.count("Pata frontal isla") == 2
        assert "PIEZAS DERIVADAS" in ctx_bad
