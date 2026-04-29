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

    # ── PR #429 — bug del operador: header en una sola línea ──────────
    def test_single_line_with_pipe_separators(self):
        """Caso DYSCON real: 'CLIENTE: DYSCON S.A. OBRA: Unidad Penal N°8
        — Piñero PAGO: Contado | ENTREGA: A confirmar'. Todo en una
        línea. El parser anterior agarraba 'DYSCON S.A. OBRA: Unidad
        Penal... PAGO: Contado' en client_name. Ahora corta ante el
        siguiente label conocido."""
        brief = (
            "CLIENTE: DYSCON S.A. OBRA: Unidad Penal N°8 — Piñero "
            "PAGO: Contado | ENTREGA: A confirmar"
        )
        c, p = _extract_client_project(brief)
        assert c == "DYSCON S.A.", f"client_name contaminado: {c!r}"
        assert p == "Unidad Penal N°8 — Piñero", (
            f"project contaminado: {p!r}"
        )

    def test_uppercase_labels(self):
        """`CLIENTE` / `OBRA` en mayúsculas (formato original DYSCON)."""
        brief = "CLIENTE: ACME OBRA: Edificio X"
        c, p = _extract_client_project(brief)
        assert c == "ACME"
        assert p == "Edificio X"

    def test_pipe_separator_only(self):
        """Cuando el separador es solo `|` (sin label intermedio)."""
        brief = "CLIENTE: Juan | OBRA: Casa"
        c, p = _extract_client_project(brief)
        assert c == "Juan"
        assert p == "Casa"

    def test_does_not_grab_pago_field(self):
        """`PAGO:` debe cortar el match de cliente/obra."""
        brief = "OBRA: Edificio Sur PAGO: Contado"
        _, p = _extract_client_project(brief)
        assert p == "Edificio Sur", f"vi {p!r}"


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

# ═══════════════════════════════════════════════════════════════════════
# Builder Paso 2 markdown products_only (PR #429)
# ═══════════════════════════════════════════════════════════════════════


class TestBuildPaso2ProductsOnly:
    """**Caso del operador (29/04/2026)**: el chat mostraba el Paso 2
    con bloques vacíos (MATERIAL en $0, MO en $0, "Precio unitario $0",
    pipe colgante) aunque el PDF/Excel salían bien. Este builder
    arma un markdown limpio para el modo products_only."""

    def _calc_dyscon(self) -> dict:
        from app.modules.quote_engine.calculator import calculate_quote
        parsed = parse_products_brief(_DYSCON_BRIEF)
        result = calculate_quote(parsed)
        assert result.get("ok") is True
        return result

    def test_no_material_block(self):
        """**Bug crítico del operador**: 'MATERIAL — — 0,00 m²' aparecía
        aunque material_m2=0. El builder products_only NO debe
        emitir esa fila."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "MATERIAL —" not in md
        assert "0,00 m²" not in md

    def test_no_mo_block(self):
        """No header MANO DE OBRA con $0."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "MANO DE OBRA" not in md
        assert "TOTAL MO" not in md

    def test_no_precio_unitario_block(self):
        """Bug operador: 'Precio unitario: Con IVA: $0 | Total: $0'
        no debe aparecer."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "Precio unitario" not in md

    def test_no_merma_block(self):
        """Bug: 'MERMA — NO APLICA / Cotización solo producto' es
        ruido en este flujo. El operador no necesita ver merma."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "MERMA" not in md

    def test_includes_products_table(self):
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "PILETAS" in md or "PRODUCTOS" in md
        assert "PILETA JOHNSON E50/18" in md
        assert "32" in md

    def test_includes_discount_with_negative_amount(self):
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "DESCUENTO — 5" in md  # 5% o 5.0%
        assert "sobre productos" in md
        # Monto en negativo (formato `- $X` o `-$X`).
        import re
        assert re.search(r"-\s*\$\s*[\d.]+", md), (
            f"Monto del descuento debe ser negativo:\n{md[:1000]}"
        )

    def test_includes_grand_total(self):
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        assert "GRAND TOTAL" in md
        # 32 × $136.410 = $4.365.120; -5% = -$218.256; total ≈ $4.146.864.
        # Verificamos que aparezca el formato de monto grande con puntos.
        import re
        assert re.search(r"\$\s*4\.\d{3}\.\d{3}", md), (
            f"Grand total ~$4M no aparece:\n{md[:1500]}"
        )

    def test_no_pipe_colgante_in_header(self):
        """**Bug operador**: 'Demora: A confirmar | ' con pipe flotando.
        El builder products_only NO debe tener pipe al final si la
        localidad está vacía (el caso normal del modo).

        Solo chequeamos las primeras 3 líneas (header + meta) — las
        filas de la tabla markdown terminan con `|` legítimamente."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        header_lines = md.split("\n")[:3]
        for line in header_lines:
            assert not line.rstrip().endswith("|"), (
                f"Línea con pipe colgante en header:\n{line!r}"
            )

    def test_header_has_clean_client_project(self):
        """Bug operador: el header decía
        'DYSCON S.A. OBRA: Unidad Penal N°8 — Piñero PAGO: Contado /
        Unidad Penal N°8 — Piñero PAGO: Contado' por el parser que
        agarraba todo. Tras el fix del parser, debe estar limpio."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        first_line = md.split("\n")[0]
        # NO debe aparecer "PAGO:" ni "OBRA:" en el title.
        assert "PAGO:" not in first_line, (
            f"Header contaminado con PAGO: {first_line!r}"
        )
        assert "OBRA:" not in first_line, (
            f"Header contaminado con OBRA: {first_line!r}"
        )

    def test_full_flow_dyscon_markdown_shape(self):
        """Smoke test del shape completo del Paso 2 products_only para
        DYSCON. Regla: que el operador, leyendo este markdown, no
        confunda con el flujo normal."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(self._calc_dyscon())
        # Header.
        assert md.startswith("## PASO 2 — Cotización de productos")
        assert "DYSCON S.A." in md
        # Cuerpo.
        assert "PILETA JOHNSON E50/18" in md
        # Discount.
        assert "DESCUENTO" in md
        # Grand total.
        assert "GRAND TOTAL" in md
        # Pregunta final.
        assert "Confirmás" in md or "Confirmar" in md

    # ── Regression del flujo NORMAL ──────────────────────────────────
    def test_normal_flow_still_has_material_block(self):
        """**Regression crítica**: el flujo normal (sin _quote_mode)
        debe seguir armando MATERIAL/MO como antes. Si esto rompe,
        cualquier cotización de mesada en producción queda sin
        bloques."""
        # Construyo un calc_result mínimo del flujo normal.
        normal_calc = {
            "client_name": "Test", "project": "Cocina",
            "date": "29.04.2026", "delivery_days": "30 días",
            "material_name": "GRANITO GRIS MARA",
            "material_m2": 5.0, "material_price_unit": 100000,
            "material_currency": "ARS",
            "material_total": 500000, "discount_pct": 0,
            "piece_details": [
                {"description": "Mesada", "largo": 2.5, "dim2": 0.6,
                 "m2": 1.5, "quantity": 1},
            ],
            "mo_items": [
                {"description": "Colocación", "quantity": 5.0,
                 "unit_price": 50000, "total": 250000},
            ],
            "sinks": [],
            "total_ars": 750000, "total_usd": 0,
            "merma": {"aplica": False},
        }
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        md = build_deterministic_paso2(normal_calc)
        # Flujo normal SÍ tiene estos bloques.
        assert "MATERIAL" in md
        assert "MANO DE OBRA" in md
        assert "GRANITO GRIS MARA" in md

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


# ═══════════════════════════════════════════════════════════════════════
# Drift guard — short-circuit emite `done` antes del return (PR #430)
# ═══════════════════════════════════════════════════════════════════════


class TestShortCircuitEmitsDone:
    """**Bug crítico observado en prod (29/04/2026):**

    Logs Railway mostraban `[products-only] short-circuit OK` pero
    después: nada. El operador confirmaba y "se cerraba todo, volvía
    al listado".

    Causa: el short-circuit del PR #427 hacía `return` SIN emitir
    `yield {"type": "done", "content": ""}`. El frontend espera ese
    evento para cerrar el stream SSE limpio, des-bloquear el composer
    y permitir al operador escribir "Confirmo". Sin él, el frontend
    timeoutea ("⚠️ servicio saturado"), interpreta el cierre como
    falla y redirige al listado.

    Todos los otros short-circuits del archivo emiten `done` (ver
    grep `\\"type\\":\\s*\\"done\\"` en agent.py — 10+ matches).

    Este test inspecciona el source de `stream_chat` y verifica que
    el bloque `[products-only]` SÍ tiene `yield {"type": "done"`
    antes del `return  # ← end turn` final. Si alguien refactoreriza
    y se olvida del done de nuevo, este test rompe.
    """

    def test_short_circuit_yields_done_before_return(self):
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService.stream_chat)
        # Buscar el bloque `[products-only] short-circuit OK` y verificar
        # que entre ese log y el `return  # ← end turn` haya un yield done.
        idx_log = src.find("[products-only] short-circuit OK")
        assert idx_log > 0, "No se encontró el log del short-circuit"
        # El return del short-circuit es el primero "return  # ← end turn"
        # después del log.
        idx_return = src.find("return  # ← end turn", idx_log)
        assert idx_return > idx_log, (
            "No se encontró el `return` final del short-circuit"
        )
        between = src[idx_log:idx_return]
        assert '"type": "done"' in between, (
            "Falta `yield {\"type\": \"done\"}` antes del `return` del "
            "short-circuit products_only. Sin ese evento, el frontend "
            "no cierra el stream y el operador no puede confirmar. "
            "Ver caso DYSCON 29/04/2026 / PR #430."
        )


# ═══════════════════════════════════════════════════════════════════════
# Confirm short-circuit (PR #431) — al confirmar genera PDF directo
# ═══════════════════════════════════════════════════════════════════════


class TestConfirmShortCircuit:
    """**Bug crítico observado en prod (caso DYSCON 29/04/2026, turno 2):**

    Después de PR #427 (brief solo-piletas → Paso 2 limpio) y PR #430
    (yield done para que el composer quede habilitado), el operador
    podía escribir "Confirmo" — pero el agent **no generaba el PDF**.

    Sonnet recibía el "Confirmo" sin tener el calc_result como
    tool_use en su contexto (solo el markdown del Paso 2). Decidía
    conservadoramente re-llamar `calculate_quote` → calculator
    detectaba products_only otra vez → emitía Paso 2 nuevo. Loop.

    **Fix (PR #431):** confirm short-circuit determinístico.
    Si hay breakdown products_only persistido Y `_user_intent` ==
    "confirm", llamamos `_execute_tool("generate_documents", ...)`
    directo desde código, bypaso Sonnet.

    Tests vía `inspect.getsource` (no mockeamos el stream agéntico
    completo — la lógica crítica es el guard `_user_intent == confirm`
    y el llamado directo a generate_documents)."""

    def test_user_intent_confirm_passes_strict_whitelist(self):
        """Recordatorio del whitelist (PR #416): solo confirmaciones
        explícitas disparan. El review feedback fue claro: la
        whitelist debe ser estricta para no auto-generar PDF cuando
        el operador escribe modificaciones."""
        from app.modules.agent.agent import _user_intent
        # Confirm explícito → pasa.
        for msg in ["Confirmo", "confirmo", "Dale", "OK generá",
                    "Sí", "yes", "perfecto"]:
            assert _user_intent(msg) == "confirm", (
                f"{msg!r} debería ser confirm"
            )

    def test_user_intent_modify_does_NOT_pass(self):
        """**Caso crítico**: 'no, cambiá la cantidad' / 'agregá otra
        pileta' / etc. NO deben disparar confirm. El short-circuit
        chequea exactamente `_user_intent == 'confirm'` — cualquier
        otro intent (modify, other) cae al flujo normal donde Sonnet
        maneja la modificación.

        Sin esta estrictez, el operador escribe 'cambiá la cantidad
        a 33' y el sistema le genera el PDF con la cantidad vieja —
        bug grave de cobro incorrecto."""
        from app.modules.agent.agent import _user_intent
        for msg in [
            "no, cambiá la cantidad",
            "agregá otra pileta",
            "sacá una pileta",
            "cambiar a 33 unidades",
            "no, está mal",
            "modificar el descuento al 10%",
            "el descuento es del 8%",
        ]:
            intent = _user_intent(msg)
            assert intent != "confirm", (
                f"{msg!r} NO debería ser confirm, vi intent={intent!r}. "
                f"Si pasa como confirm, el operador modifica y le "
                f"generamos PDF viejo → cobro incorrecto."
            )

    def test_short_circuit_block_exists_in_source(self):
        """Drift guard: el bloque `[products-only-confirm]` debe
        existir en `stream_chat`. Si alguien lo borra, este test
        rompe."""
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService.stream_chat)
        assert "[products-only-confirm] short-circuit OK" in src, (
            "Falta el log del confirm short-circuit. Sin él, el "
            "operador escribe 'Confirmo' y Sonnet re-emite el Paso 2 "
            "(bug DYSCON 29/04/2026 turno 2 / PR #431)."
        )

    def test_short_circuit_uses_user_intent_confirm_check(self):
        """Drift guard: el bloque debe chequear `_user_intent` ==
        "confirm" estrictamente. Si alguien lo cambia a un substring
        match de "confirm" o algo más laxo, mensajes como
        'cambiá la cantidad' podrían disparar el PDF y cobrar mal."""
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService.stream_chat)
        idx = src.find("[products-only-confirm] short-circuit OK")
        assert idx > 0
        # Buscamos hacia atrás el bloque del confirm short-circuit.
        # Empieza con el comentario `── PR #431`.
        idx_block_start = src.rfind("PR #431", 0, idx)
        assert idx_block_start > 0
        block = src[idx_block_start:idx]
        # Debe tener el guard estricto.
        assert "_user_intent(" in block, (
            "El confirm short-circuit no usa _user_intent — riesgo de "
            "matching laxo de 'confirm'."
        )
        assert '== "confirm"' in block, (
            "El check debe ser `_user_intent(...) == 'confirm'` "
            "estricto (no `in` ni substring). Sin esto el flujo "
            "podría disparar con 'cambiá' / 'corregí' / etc."
        )

    def test_short_circuit_calls_generate_documents_directly(self):
        """Drift guard: el bloque debe llamar `_execute_tool(
        "generate_documents", ...)`. Si en un refactor alguien lo
        cambia a `calculate_quote` (el bug original), el operador
        vuelve a ver Paso 2 en lugar del PDF."""
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService.stream_chat)
        idx_block_start = src.find("PR #431")
        assert idx_block_start > 0
        # Rango: desde "PR #431" (encabezado) hasta el header del
        # bloque siguiente "── PR #427 — Products-only short-circuit"
        # (el comentario header del otro bloque). NO usamos "PR #427"
        # solo porque el comentario del #431 menciona ese número.
        idx_block_end = src.find(
            "── PR #427 — Products-only short-circuit",
            idx_block_start,
        )
        assert idx_block_end > idx_block_start
        block = src[idx_block_start:idx_block_end]
        assert '"generate_documents"' in block, (
            "El confirm short-circuit no llama generate_documents. "
            "Sin esto, vuelve el bug DYSCON: Sonnet re-emite Paso 2."
        )

    def test_short_circuit_yields_done_before_return(self):
        """Drift guard: yield done antes del return (mismo patrón
        del PR #430). Buscamos el `yield {"type": "done"` literal
        después del log del short-circuit. Si está, OK; si no,
        bug de timeout en frontend."""
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService.stream_chat)
        idx_log = src.find("[products-only-confirm] short-circuit OK")
        assert idx_log > 0
        # Marcador de fin del bloque: el header del PR #427 siguiente.
        idx_block_end = src.find(
            "── PR #427 — Products-only short-circuit",
            idx_log,
        )
        assert idx_block_end > idx_log
        between = src[idx_log:idx_block_end]
        # Buscamos el yield done específico (no `# yield` en comentario).
        assert 'yield {"type": "done"' in between, (
            "Falta yield done en el confirm short-circuit. Sin esto "
            "el frontend timeoutea (bug PR #430 replicado)."
        )

    def test_preflight_validate_quote_data_skips_products_only(self):
        """**Bug del operador (29/04/2026, turno 2):** logs Railway
        mostraban:

            [products-only-confirm] generate_documents rejected:
            Pre-flight fallido para :
            ❌ Falta material
            ❌ Sin piezas definidas
            ❌ Sin ítems de mano de obra

        El validator `_validate_quote_data` (preflight de agent.py,
        distinto al `validate_despiece`) no respetaba el modo
        products_only y rebotaba con 3 errores.

        Fix: skip en products_only. Solo aplica los checks que sí
        tienen sentido (cliente, total, sinks)."""
        from app.modules.agent.agent import _validate_quote_data
        # Calc result válido products_only (lo que persistió el
        # short-circuit del PR #427).
        qdata = {
            "_quote_mode": "products_only",
            "client_name": "DYSCON S.A.",
            "project": "Unidad Penal N°8 — Piñero",
            "delivery_days": "A confirmar",
            "material_name": "",  # ← antes rebotaba "Falta material"
            "material_m2": 0,
            "sectors": [],         # ← antes rebotaba "Sin piezas"
            "mo_items": [],        # ← antes rebotaba "Sin ítems MO"
            "sinks": [
                {"name": "PILETA JOHNSON E50/18", "quantity": 32, "unit_price": 136410},
            ],
            "total_ars": 4146864,
        }
        errors, warnings = _validate_quote_data(qdata)
        assert errors == [], f"Preflight rebotó products_only: {errors}"

    def test_preflight_products_only_without_sinks_fails(self):
        """En products_only, la lista de sinks es obligatoria — sin
        eso no hay nada que cotizar. Validator debe fallar."""
        from app.modules.agent.agent import _validate_quote_data
        qdata = {
            "_quote_mode": "products_only",
            "client_name": "X",
            "delivery_days": "30 días",
            "sinks": [],  # ← vacío
            "total_ars": 0,
        }
        errors, _ = _validate_quote_data(qdata)
        assert any("sinks" in e.lower() or "productos" in e.lower() for e in errors)

    def test_preflight_products_only_without_client_fails(self):
        """Cliente sigue siendo obligatorio aún en products_only."""
        from app.modules.agent.agent import _validate_quote_data
        qdata = {
            "_quote_mode": "products_only",
            "client_name": "",
            "delivery_days": "30 días",
            "sinks": [{"name": "x", "quantity": 1, "unit_price": 100}],
            "total_ars": 100,
        }
        errors, _ = _validate_quote_data(qdata)
        assert any("cliente" in e.lower() for e in errors)

    def test_preflight_normal_mode_still_requires_material(self):
        """**Caso inverso CRÍTICO** (mismo patrón que PR #427): el
        flujo NORMAL debe seguir requiriendo material/sectors/mo_items.
        Sin este test, alguien borra el guard de products_only y el
        flujo normal se rompe sin darse cuenta."""
        from app.modules.agent.agent import _validate_quote_data
        qdata = {
            # Sin _quote_mode → flujo normal
            "client_name": "X",
            "delivery_days": "30 días",
            "material_name": "",  # ← falta
            "sectors": [],
            "mo_items": [],
            "total_ars": 100,
        }
        errors, _ = _validate_quote_data(qdata)
        # Debe rebotar por los 3 checks normales.
        assert any("material" in e.lower() for e in errors)
        assert any("piezas" in e.lower() for e in errors)
        assert any("mano de obra" in e.lower() for e in errors)

    def test_short_circuit_only_when_quote_mode_products_only(self):
        """Drift guard: el bloque debe chequear `_quote_mode ==
        "products_only"`. Si en un refactor sacan ese guard, el
        confirm short-circuit dispararía para CUALQUIER quote (con
        pileta o no), bypaseando el flujo normal."""
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService.stream_chat)
        idx_block_start = src.find("PR #431")
        # Rango: desde "PR #431" (encabezado) hasta el header del
        # bloque siguiente "── PR #427 — Products-only short-circuit"
        # (el comentario header del otro bloque). NO usamos "PR #427"
        # solo porque el comentario del #431 menciona ese número.
        idx_block_end = src.find(
            "── PR #427 — Products-only short-circuit",
            idx_block_start,
        )
        block = src[idx_block_start:idx_block_end]
        assert '"products_only"' in block, (
            "El confirm short-circuit no chequea _quote_mode. "
            "Sin ese guard, dispararía para cualquier quote y "
            "rompería el flujo normal de mesadas."
        )
