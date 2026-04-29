"""Tests para PR #427 — detector + parser determinísticos del modo
products_only + fix del rebote en `_check_pegadopileta`.

**Caso DYSCON 29/04/2026** (continuación del bug):

PR #424 implementó el modo `products_only` en calculator + validator
+ renderers. PERO el flujo upstream del agente (text-parser,
context_analysis, dual_read) seguía corriendo IGUAL para briefs de
"solo piletas" → mostraba "Análisis de contexto" con frentín
inventado y un despiece falso ANTES de llegar al cálculo correcto.

Y al confirmar el Paso 2 products_only, el `generate_documents`
rebotaba en `_check_pegadopileta` porque el calculator NO inyecta
MO de pileta en este modo, pero el validator lo exigía.

Este PR:
1. Detector + parser determinísticos para skipear contexto+despiece.
2. Short-circuit en `agent.py:stream_chat` antes del text-parser.
3. Validator `_check_pegadopileta`: skip si `_quote_mode==products_only`.

**Regresión crítica que el test inverso protege:**
products_only=False + pileta="empotrada_johnson" + mo_items=[]
DEBE seguir fallando (validator catches). Sin esto, el fix
enmascara bugs futuros del flujo normal.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.products_only_detector import (
    build_products_only_material_label,
    is_products_only_brief,
    parse_products_brief,
    _extract_qty,
    _extract_sku,
    _extract_discount,
    _extract_client_project,
)
from app.modules.agent.tools.validation_tool import _check_pegadopileta


# ═══════════════════════════════════════════════════════════════════════
# Detector — 3 señales obligatorias
# ═══════════════════════════════════════════════════════════════════════


_DYSCON_BRIEF = """2 — PILETAS (solo producto)
CLIENTE: DYSCON S.A.
OBRA: Unidad Penal N°8 — Piñero
PAGO: Contado | ENTREGA: A confirmar
ARCHIVO: 'DYSCON SA - Piletas - 29.04.2026'

PRODUCTO — solo piletas, sin MO, sin flete:
Pileta Johnson E50 × 32 unidades
Descuento 5% sobre total → línea separada visible

REGLAS
* Solo producto de pileta
* Sin MO
* Sin flete
* Descuento 5% sobre piletas únicamente"""


class TestDetector:
    # ── Caso real DYSCON ──────────────────────────────────────────────
    def test_dyscon_brief_triggers(self):
        """El brief real del operador debe disparar el detector."""
        assert is_products_only_brief(_DYSCON_BRIEF) is True

    # ── Las 3 señales son requeridas (no 2 de 3) ─────────────────────
    def test_only_solo_producto_does_not_trigger(self):
        """Falta sin MO + producto."""
        assert is_products_only_brief("Solo producto") is False

    def test_only_sin_mo_does_not_trigger(self):
        """Falta solo producto + producto pileta."""
        assert is_products_only_brief("Cocina sin MO") is False

    def test_only_pileta_does_not_trigger(self):
        """Falta solo producto + sin MO."""
        assert is_products_only_brief("Pileta Johnson") is False

    def test_solo_producto_plus_sin_mo_no_pileta_does_not_trigger(self):
        """2 de 3 señales — falta producto pileta/bacha."""
        assert is_products_only_brief("solo producto, sin MO") is False

    def test_solo_producto_plus_pileta_no_sin_mo_does_not_trigger(self):
        """2 de 3 — falta 'sin MO'."""
        assert is_products_only_brief("solo producto, pileta Johnson E50") is False

    # ── Variantes de "solo producto" ─────────────────────────────────
    @pytest.mark.parametrize("phrase", [
        "solo producto",
        "solo piletas",
        "solo pileta",
        "solo bachas",
        "solo bacha",
        "sólo producto",
    ])
    def test_solo_phrase_variants(self, phrase):
        brief = f"{phrase}, sin MO, pileta Johnson"
        assert is_products_only_brief(brief) is True

    # ── Variantes de "sin MO" ────────────────────────────────────────
    @pytest.mark.parametrize("phrase", [
        "sin MO",
        "sin mo",
        "sin M.O.",
        "sin M.O",
        "sin mano de obra",
        "Sin Mano De Obra",
    ])
    def test_sin_mo_variants(self, phrase):
        brief = f"solo producto, {phrase}, pileta Johnson"
        assert is_products_only_brief(brief) is True

    # ── False positives a evitar ─────────────────────────────────────
    def test_normal_kitchen_brief_does_not_trigger(self):
        """Brief típico de cocina/edificio NO debe disparar."""
        brief = (
            "Cocina con mesada 2.5×0.6, zócalo atrás, pileta empotrada "
            "Johnson E50, anafe gas. Granito Gris Mara. Cliente Pérez."
        )
        assert is_products_only_brief(brief) is False

    def test_minimo_word_does_not_trigger_sin_mo(self):
        """'Mínimo 2m²' no debe matchear 'sin MO' por substring.
        Word boundary previene false positive de \\bmo\\b."""
        brief = "solo producto pileta, mínimo 2 unidades, fenólico"
        # NO tiene "sin MO" — solo "minimo" que contiene "mo".
        assert is_products_only_brief(brief) is False

    # ── Empty/None ───────────────────────────────────────────────────
    def test_empty_brief(self):
        assert is_products_only_brief("") is False

    def test_none_brief(self):
        assert is_products_only_brief(None) is False


# ═══════════════════════════════════════════════════════════════════════
# Parser — extracción de campos
# ═══════════════════════════════════════════════════════════════════════


class TestParserQty:
    @pytest.mark.parametrize("brief,expected", [
        ("Pileta E50 × 32", 32),
        ("Pileta E50 x 32", 32),
        ("Pileta E50 × 32 unidades", 32),
        ("Pileta E50 × 32 u", 32),
        ("32 unidades de pileta E50", 32),
        ("32u Johnson E50", 32),
    ])
    def test_qty_extraction(self, brief, expected):
        assert _extract_qty(brief) == expected

    def test_qty_none_when_no_number(self):
        assert _extract_qty("Pileta Johnson sin cantidad") is None


class TestParserSKU:
    @pytest.mark.parametrize("brief,expected", [
        ("Pileta Johnson E50 × 32", "E50"),
        ("Pileta Johnson E50/18", "E50/18"),
        ("Pileta Q71A", "Q71A"),
        # "Johnson LUXOR S171" — el regex requiere letra+dígito ej "S171".
        # "LUXOR" sin números NO matchea (es texto, no SKU). Aceptamos
        # "S171" como SKU canónico — Sonnet/operador puede pasar el
        # SKU completo si lo necesita.
        ("Johnson LUXOR S171", "S171"),
    ])
    def test_sku_extraction(self, brief, expected):
        assert _extract_sku(brief) == expected

    def test_sku_none_when_no_pattern(self):
        assert _extract_sku("Una pileta cualquiera") is None


class TestParserDiscount:
    @pytest.mark.parametrize("brief,expected", [
        ("descuento 5%", 5.0),
        ("Descuento 5%", 5.0),
        ("dto 5%", 5.0),
        ("dto. 5%", 5.0),
        ("5% descuento", 5.0),
        ("5% de descuento", 5.0),
        ("descuento 12.5%", 12.5),
        ("descuento 12,5%", 12.5),
    ])
    def test_discount_extraction(self, brief, expected):
        assert _extract_discount(brief) == expected

    def test_no_discount_returns_none(self):
        assert _extract_discount("Pileta sin descuento") is None


class TestParserClientProject:
    def test_dyscon_extracts_both(self):
        client, project = _extract_client_project(_DYSCON_BRIEF)
        assert client == "DYSCON S.A."
        assert "Unidad Penal N°8" in project

    def test_only_client(self):
        c, p = _extract_client_project("CLIENTE: Juan Pérez\nMaterial: granito")
        assert c == "Juan Pérez"
        assert p is None


class TestParserFull:
    def test_dyscon_full_parse(self):
        """End-to-end del parser sobre el brief real DYSCON."""
        result = parse_products_brief(_DYSCON_BRIEF)
        assert result is not None
        assert result["client_name"] == "DYSCON S.A."
        assert "Unidad Penal" in result["project"]
        assert result["pileta_sku"] == "E50"  # primer match
        assert result["pileta_qty"] == 32
        assert result["discount_pct"] == 5.0
        assert result["pieces"] == []

    def test_returns_none_without_qty(self):
        """Sin cantidad → no podemos cotizar → None."""
        result = parse_products_brief("Pileta Johnson E50 sin cantidad")
        assert result is None

    def test_returns_none_without_sku(self):
        """Sin SKU del producto → None."""
        result = parse_products_brief("32 unidades sin pileta")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# Validator fix: _check_pegadopileta skip en products_only
# ═══════════════════════════════════════════════════════════════════════


class TestValidatorPegadopiletaSkip:
    def test_products_only_with_pileta_set_does_not_fail(self):
        """**Bug original**: products_only + pileta='empotrada_johnson' +
        mo_items=[] → validator rebotaba con error de pileta sin MO,
        bloqueando generate_documents. Fix: skip si products_only."""
        qdata = {
            "_quote_mode": "products_only",
            "pileta": "empotrada_johnson",  # ← Sonnet a veces lo pasa
            "mo_items": [],                  # ← sin MO (correcto en este modo)
            "sinks": [{"name": "PILETA E50", "quantity": 32, "unit_price": 100000}],
        }
        errors, warnings = _check_pegadopileta(qdata)
        assert errors == [], (
            f"products_only debe skipear el check, vi errors={errors}"
        )

    def test_products_only_without_pileta_field_does_not_fail(self):
        """Caso happy path: products_only sin `pileta` field tampoco
        debe rebotar (skip aplica antes de leer pileta)."""
        qdata = {
            "_quote_mode": "products_only",
            "mo_items": [],
            "sinks": [{"name": "x", "quantity": 1, "unit_price": 100}],
        }
        errors, _ = _check_pegadopileta(qdata)
        assert errors == []

    # ── Test inverso (review feedback explícito): asegurar que el fix
    # NO enmascara bugs futuros del flujo normal ─────────────────────
    def test_normal_mode_pileta_without_mo_still_fails(self):
        """**Caso inverso CRÍTICO** (review feedback): si NO estamos
        en products_only y hay pileta='empotrada_johnson' sin
        mo_items de pileta, el validator DEBE seguir rebotando.

        Sin este test, el fix podría enmascarar bugs futuros del
        flujo normal donde Sonnet olvide inyectar la MO de pileta
        — el cliente terminaría sin la línea de MO en el PDF y se
        cobraría de menos."""
        qdata = {
            # NO _quote_mode → flujo normal
            "pileta": "empotrada_johnson",
            "mo_items": [],  # ← BUG: falta MO de pileta
            "sinks": [{"name": "PILETA", "quantity": 1, "unit_price": 50000}],
        }
        errors, _ = _check_pegadopileta(qdata)
        assert len(errors) == 1, (
            f"Flujo normal debe seguir rebotando, vi errors={errors}"
        )
        # `errors[0].lower()` convierte "MO" → "mo".
        assert "no hay ítem mo" in errors[0].lower()

    def test_normal_mode_with_pileta_mo_passes(self):
        """Regression del happy path normal: pileta + MO presente → OK."""
        qdata = {
            "pileta": "empotrada_johnson",
            "mo_items": [
                {"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 53840, "total": 53840},
            ],
        }
        errors, _ = _check_pegadopileta(qdata)
        assert errors == []

    def test_other_quote_mode_not_skipped(self):
        """Drift guard: solo `_quote_mode==products_only` skipea.
        Cualquier otro valor (ej. inventado/futuro) NO debe skipear
        — debe ir al check normal."""
        qdata = {
            "_quote_mode": "some_future_mode",  # ← NO products_only
            "pileta": "empotrada_johnson",
            "mo_items": [],
        }
        errors, _ = _check_pegadopileta(qdata)
        # NO se skipea → check normal corre → falla por falta de MO.
        assert len(errors) == 1


# ═══════════════════════════════════════════════════════════════════════
# End-to-end DYSCON: brief → calculate_quote → render OK
# ═══════════════════════════════════════════════════════════════════════


class TestEndToEndDyscon:
    def test_full_flow_calc_quote_from_dyscon_brief(self):
        """Brief DYSCON real → detector → parser → calculate_quote →
        calc_result válido products_only. Sin pasar por
        text_parser/context_analysis."""
        from app.modules.quote_engine.calculator import calculate_quote

        assert is_products_only_brief(_DYSCON_BRIEF)
        parsed = parse_products_brief(_DYSCON_BRIEF)
        assert parsed is not None

        result = calculate_quote(parsed)
        assert result.get("ok") is True, f"calc rebotó: {result.get('error')}"
        assert result.get("_quote_mode") == "products_only"
        assert result["material_m2"] == 0
        assert result["mo_items"] == []
        assert len(result["sinks"]) == 1
        assert result["sinks"][0]["quantity"] == 32

        # Total = sinks_subtotal - 5%
        sinks_subtotal = sum(
            s["unit_price"] * s["quantity"] for s in result["sinks"]
        )
        expected_total = sinks_subtotal - round(sinks_subtotal * 0.05)
        assert result["total_ars"] == expected_total

    def test_full_flow_passes_validator(self):
        """Drift guard E2E: el calc_result armado por el flow
        completo NO rebota en NINGÚN validator (ni el de pegadopileta
        que arreglamos, ni los demás)."""
        from app.modules.quote_engine.calculator import calculate_quote
        from app.modules.agent.tools.validation_tool import validate_despiece

        parsed = parse_products_brief(_DYSCON_BRIEF)
        result = calculate_quote(parsed)
        validation = validate_despiece(result)
        assert validation.ok is True, (
            f"validate_despiece rebotó products_only: {validation.errors}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Material label para listado del dashboard (PR #428)
# ═══════════════════════════════════════════════════════════════════════


class TestMaterialLabel:
    """**Caso del operador (29/04/2026)**: el listado del dashboard
    mostraba "—" (em-dash) en la columna material para quotes
    products_only, porque PR #427 persistía `material=""`. El
    operador no podía identificar qué cotización era al escanear
    la lista. Este helper construye un label descriptivo desde
    los sinks del calc_result."""

    def test_single_sink_format(self):
        """1 sink → 'NAME × QTY' sin sufijo de "más"."""
        sinks = [
            {"name": "PILETA JOHNSON E50/18", "quantity": 32, "unit_price": 100000},
        ]
        label = build_products_only_material_label(sinks)
        assert label == "PILETA JOHNSON E50/18 × 32"

    def test_multiple_sinks_first_plus_extra_count(self):
        """N sinks → primero + sufijo '(+N-1 más)' para indicar al
        operador que hay más productos sin ocupar todo el ancho del
        listado."""
        sinks = [
            {"name": "PILETA JOHNSON E50/18", "quantity": 32, "unit_price": 100000},
            {"name": "PILETA JOHNSON Q71A", "quantity": 5, "unit_price": 80000},
            {"name": "BACHA AUXILIAR", "quantity": 1, "unit_price": 50000},
        ]
        label = build_products_only_material_label(sinks)
        assert label == "PILETA JOHNSON E50/18 × 32 (+2 más)"

    def test_two_sinks_one_extra(self):
        """Boundary: exactly 2 sinks → '(+1 más)'."""
        sinks = [
            {"name": "PILETA A", "quantity": 1, "unit_price": 100},
            {"name": "PILETA B", "quantity": 2, "unit_price": 200},
        ]
        label = build_products_only_material_label(sinks)
        assert label == "PILETA A × 1 (+1 más)"

    def test_empty_sinks_returns_empty(self):
        """Defensivo: products_only no debería llegar acá sin sinks
        (el calculator rebota antes), pero si pasa, no romper —
        devolver string vacío para que el listado muestre '—' como
        antes y no algo confuso."""
        assert build_products_only_material_label([]) == ""

    def test_none_sinks_returns_empty(self):
        assert build_products_only_material_label(None) == ""

    def test_sink_without_name_uses_placeholder(self):
        """Defensivo: sink mal-formado sin name → 'PRODUCTO' como
        fallback. Mejor un label genérico que un crash o '—'."""
        sinks = [{"quantity": 5, "unit_price": 1000}]
        label = build_products_only_material_label(sinks)
        assert label == "PRODUCTO × 5"

    def test_sink_without_quantity_defaults_to_1(self):
        sinks = [{"name": "PILETA X", "unit_price": 1000}]
        label = build_products_only_material_label(sinks)
        assert label == "PILETA X × 1"

    def test_sink_with_whitespace_in_name_stripped(self):
        """Edge: nombre con espacios al borde NO debe meterlos en el
        label. Si los catálogos tienen names con padding, lo limpiamos."""
        sinks = [{"name": "  PILETA JOHNSON E50  ", "quantity": 32}]
        label = build_products_only_material_label(sinks)
        assert label == "PILETA JOHNSON E50 × 32"

    # ── End-to-end con el calc_result real ──────────────────────────
    def test_dyscon_full_label(self):
        """Caso DYSCON real: el calc_result que produce
        `_calculate_quote_products_only` debe generar un label
        identificable. Reproducimos el flujo completo."""
        from app.modules.quote_engine.calculator import calculate_quote
        parsed = parse_products_brief(_DYSCON_BRIEF)
        result = calculate_quote(parsed)
        assert result.get("ok") is True
        label = build_products_only_material_label(result["sinks"])
        # El nombre exacto del catálogo. Verificamos que contenga "JOHNSON" + qty.
        assert "JOHNSON" in label.upper()
        assert "× 32" in label
        """Drift guard E2E: el calc_result armado por el flow
        completo NO rebota en NINGÚN validator (ni el de pegadopileta
        que arreglamos, ni los demás)."""
        from app.modules.quote_engine.calculator import calculate_quote
        from app.modules.agent.tools.validation_tool import validate_despiece

        parsed = parse_products_brief(_DYSCON_BRIEF)
        result = calculate_quote(parsed)
        validation = validate_despiece(result)
        assert validation.ok is True, (
            f"validate_despiece rebotó products_only: {validation.errors}"
        )
