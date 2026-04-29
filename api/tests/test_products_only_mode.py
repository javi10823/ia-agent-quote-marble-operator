"""Tests para PR #424 — modo `products_only` (cotización solo producto).

**Caso DYSCON 29/04/2026** (screenshot del operador):

Brief: "Pileta Johnson E50 × 32 unidades, solo producto, sin MO,
sin flete, descuento 5%."

PDF generado tenía 4 bugs simultáneos:

1. **Bloque material vacío** "PILETAS JOHNSON - 20mm | 0 | $0 | $0"
   (fuzzy match malo de Sonnet pasando "Pileta Johnson" como material).
2. **MO inventada** "Piletas | 1 | $4.146.864 | $4.146.864" — Sonnet
   armó la línea con qty=1 y precio inflado en lugar de qty=32 ×
   precio unitario.
3. **Total = $4.146.864** (solo MO inventada) sin sumar las piletas
   ($4.365.120) → cliente cobrado **la mitad**.
4. **Descuento 5% no aparecía** en el PDF.

Estrategia (review feedback): nuevo modo `products_only` con
detección automática + validator ruidoso. Resuelve los 4 bugs en
una pasada en lugar de 3 parches.

**Test crítico explícito** (review feedback): regenerar PDF de un
`quote_breakdown` viejo que tenga `_quote_mode="products_only"`
persistido — eso simula el botón "regenerar PDF" sobre quotes ya
generados. Sin esto, el feature se rompe en regen.
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import (
    _calculate_quote_products_only,
    calculate_quote,
)
from app.modules.agent.tools.validation_tool import (
    _check_products_only_consistency,
    validate_despiece,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _dyscon_input(discount_pct=5, pileta_qty=32) -> dict:
    """Input mínimo para reproducir el caso DYSCON solo-producto."""
    return {
        "client_name": "DYSCON S.A.",
        "project": "Unidad Penal N°8 — Piñero",
        "plazo": "A confirmar",
        "pileta_sku": "E50",
        "pileta_qty": pileta_qty,
        "discount_pct": discount_pct,
        "pieces": [],  # ← clave de la detección
    }


# ═══════════════════════════════════════════════════════════════════════
# Detección automática (branch al inicio de calculate_quote)
# ═══════════════════════════════════════════════════════════════════════


class TestAutoDetection:
    def test_dyscon_input_triggers_products_only(self):
        """Input real DYSCON: pieces=[] + pileta_qty=32 → modo activado."""
        result = calculate_quote(_dyscon_input())
        assert result.get("ok") is True, f"calc falló: {result.get('error')}"
        assert result.get("_quote_mode") == "products_only"

    def test_normal_quote_does_not_trigger(self):
        """Regression: con pieces no vacío → flujo normal (sin _quote_mode)."""
        result = calculate_quote({
            "client_name": "Test",
            "project": "Test",
            "plazo": "30 días",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6, "quantity": 1},
            ],
        })
        assert result.get("ok") is True
        assert result.get("_quote_mode") != "products_only"

    def test_pieces_empty_but_colocacion_blocks_mode(self):
        """`colocacion=True` indica que el operador quiere instalación →
        NO entrar a products_only aunque pieces=[]. El flujo normal
        después fallará por falta de material, lo cual es correcto
        (NO enmascarar). Verificamos que el flujo NO redirige a
        products_only — si lo hiciera, daría un calc_result con
        `_quote_mode` que sería incorrecto."""
        with pytest.raises((KeyError, Exception)) as exc_info:
            # Si entrara a products_only, NO tiraría KeyError.
            # Si va al flujo normal, tira KeyError('material').
            calculate_quote({
                "client_name": "Test", "project": "Test", "plazo": "30",
                "pileta_sku": "E50", "pileta_qty": 1,
                "pieces": [],
                "colocacion": True,
            })
        # Confirmamos que la excepción es por falta de material —
        # señal de que pasó de largo el branch products_only.
        assert "material" in str(exc_info.value).lower()

    def test_no_pileta_no_sinks_does_not_trigger(self):
        """pieces=[] sin sinks ni pileta → no es products_only —
        el flujo normal va a fallar pero NO por products_only."""
        with pytest.raises((KeyError, Exception)) as exc_info:
            calculate_quote({
                "client_name": "Test", "project": "Test", "plazo": "30",
                "pieces": [],
            })
        assert "material" in str(exc_info.value).lower()


# ═══════════════════════════════════════════════════════════════════════
# DYSCON exact — caso real del screenshot
# ═══════════════════════════════════════════════════════════════════════


class TestDysconExact:
    """Replica el bug observado en el PDF del screenshot. Cada bug
    del reporte tiene su test."""

    def test_total_ars_includes_sinks(self):
        """**Bug 6 (crítico) del screenshot**: Total no sumaba las
        piletas → cliente cobrado de menos. Test explícito: total_ars
        DEBE incluir el subtotal de sinks menos descuento."""
        result = calculate_quote(_dyscon_input(discount_pct=5, pileta_qty=32))
        assert result.get("ok") is True
        sinks = result["sinks"]
        sinks_subtotal = sum(s["unit_price"] * s["quantity"] for s in sinks)
        expected_total = sinks_subtotal - round(sinks_subtotal * 0.05)
        assert result["total_ars"] == expected_total, (
            f"total_ars={result['total_ars']} no incluye sinks "
            f"({sinks_subtotal}) - descuento. Cliente cobrado mal."
        )

    def test_no_mo_items_in_dyscon_brief(self):
        """**Bug 2 del reporte**: el brief decía 'sin MO', el sistema
        inyectaba MO igual. En modo products_only mo_items DEBE estar
        vacío."""
        result = calculate_quote(_dyscon_input())
        assert result["mo_items"] == [], (
            f"products_only debe tener mo_items=[], vi {result['mo_items']}"
        )

    def test_no_material_in_dyscon_brief(self):
        """**Bug 1 del reporte**: PDF mostraba 'PILETAS JOHNSON - 20mm
        \\| 0 \\| $0 \\| $0' como material vacío. En products_only NO
        hay material (m2=0, name vacío)."""
        result = calculate_quote(_dyscon_input())
        assert result["material_m2"] == 0
        assert result["material_name"] == ""

    def test_sinks_quantity_is_32_not_1(self):
        """**Bug 3 del reporte**: el sistema mostraba qty=1 con precio
        inflado en lugar de qty=32. En products_only la pileta resuelta
        del catálogo conserva quantity=32."""
        result = calculate_quote(_dyscon_input(pileta_qty=32))
        sinks = result["sinks"]
        assert len(sinks) == 1, f"esperaba 1 sink, vi {len(sinks)}"
        assert sinks[0]["quantity"] == 32

    def test_discount_5pct_applied_to_sinks_subtotal(self):
        """**Bug 4 del reporte**: descuento 5% no aparecía. Test
        explícito: discount_amount = round(subtotal × 5%)."""
        result = calculate_quote(_dyscon_input(discount_pct=5))
        sinks_subtotal = sum(
            s["unit_price"] * s["quantity"] for s in result["sinks"]
        )
        assert result["discount_pct"] == 5
        assert result["discount_amount"] == round(sinks_subtotal * 0.05)


# ═══════════════════════════════════════════════════════════════════════
# Validator — ruidoso si data inconsistente
# ═══════════════════════════════════════════════════════════════════════


class TestValidatorProductsOnly:
    def _base_qdata(self, **overrides) -> dict:
        """Quote válido products_only — base para los tests negativos."""
        base = {
            "_quote_mode": "products_only",
            "material_m2": 0,
            "mo_items": [],
            "sinks": [
                {"name": "PILETA JOHNSON E50/18", "quantity": 32, "unit_price": 100000},
            ],
            "discount_amount": 0,
            "total_ars": 32 * 100000,
        }
        base.update(overrides)
        return base

    def test_valid_passes(self):
        errors, _ = _check_products_only_consistency(self._base_qdata())
        assert errors == []

    def test_non_products_only_skipped(self):
        """Si `_quote_mode` ≠ products_only, el check no aplica."""
        qdata = {"_quote_mode": "normal", "material_m2": 50}
        errors, _ = _check_products_only_consistency(qdata)
        assert errors == []

    def test_material_m2_nonzero_fails(self):
        qdata = self._base_qdata(material_m2=10)
        errors, _ = _check_products_only_consistency(qdata)
        assert len(errors) == 1
        assert "material_m2" in errors[0].lower()

    def test_mo_items_nonempty_fails(self):
        """Bug DYSCON: Sonnet inventaba mo_items. Validator lo agarra."""
        qdata = self._base_qdata(mo_items=[
            {"description": "Piletas", "quantity": 1, "unit_price": 4146864, "total": 4146864},
        ])
        errors, _ = _check_products_only_consistency(qdata)
        assert any("mo_items" in e.lower() for e in errors)
        # El error debe mencionar al menos una description del item
        # para que el operador sepa qué mo_item revisar.
        assert any("Piletas" in e for e in errors)

    def test_empty_sinks_fails(self):
        qdata = self._base_qdata(sinks=[])
        errors, _ = _check_products_only_consistency(qdata)
        assert any("sinks" in e.lower() for e in errors)

    def test_total_mismatch_fails(self):
        """Bug DYSCON crítico: total_ars no incluía las piletas
        (mostraba solo MO). Validator agarra el mismatch ruidosamente."""
        qdata = self._base_qdata(total_ars=4146864)  # ← solo MO inventada
        errors, _ = _check_products_only_consistency(qdata)
        assert any("total_ars" in e.lower() for e in errors)
        # El error debe incluir el delta numérico para diagnóstico.
        assert any("DYSCON" in e for e in errors), (
            "Error debería referenciar el caso DYSCON para que el "
            "lector entienda qué bug está agarrando."
        )

    def test_total_within_tolerance_passes(self):
        """Drift de ±1 ARS por rounding NO debe disparar error."""
        qdata = self._base_qdata(total_ars=32 * 100000 - 1)  # 1 ARS off
        errors, _ = _check_products_only_consistency(qdata)
        assert errors == []

    def test_pipeline_includes_check(self):
        """Drift guard: `_check_products_only_consistency` debe estar
        en el pipeline de `validate_despiece`. Si alguien lo saca, los
        bugs DYSCON pasan silenciosos."""
        qdata = {
            "_quote_mode": "products_only",
            "material_m2": 0,
            "mo_items": [{"description": "Piletas", "quantity": 1, "unit_price": 1, "total": 1}],
            "sinks": [{"name": "x", "quantity": 1, "unit_price": 100}],
            "total_ars": 100,
            "discount_amount": 0,
            # Otros campos para no romper otros checks.
            "material_currency": "ARS",
        }
        result = validate_despiece(qdata)
        # Esperamos al menos un error de products_only.
        assert any("products_only" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════
# Resolución de sinks
# ═══════════════════════════════════════════════════════════════════════


class TestSinksResolution:
    def test_sinks_explicit_used_verbatim(self):
        """Si Sonnet ya armó `sinks=[{name, qty, unit_price}]` → usar
        verbatim sin tocar el catálogo."""
        warnings_buf: list[str] = []
        result = _calculate_quote_products_only({
            "client_name": "X", "project": "Y", "plazo": "30",
            "sinks": [
                {"name": "Custom Sink", "quantity": 2, "unit_price": 50000},
            ],
            "discount_pct": 0,
        }, warnings_buf)
        assert result.get("ok") is True
        assert result["sinks"] == [
            {"name": "Custom Sink", "quantity": 2, "unit_price": 50000},
        ]

    def test_pileta_sku_lookup_from_catalog(self):
        """Sin `sinks` explícito pero con `pileta_sku` + `pileta_qty`,
        resuelve desde sinks.json."""
        warnings_buf: list[str] = []
        result = _calculate_quote_products_only({
            "client_name": "X", "project": "Y", "plazo": "30",
            "pileta_sku": "E50",
            "pileta_qty": 5,
            "discount_pct": 0,
        }, warnings_buf)
        assert result.get("ok") is True
        assert len(result["sinks"]) == 1
        assert result["sinks"][0]["quantity"] == 5
        assert "JOHNSON" in result["sinks"][0]["name"].upper()

    def test_pileta_sku_not_found_fails_loud(self):
        """SKU inexistente → error claro, NO default silencioso."""
        warnings_buf: list[str] = []
        result = _calculate_quote_products_only({
            "client_name": "X", "project": "Y", "plazo": "30",
            "pileta_sku": "NOEXISTE_SKU_INVENTADO_999",
            "pileta_qty": 1,
            "discount_pct": 0,
        }, warnings_buf)
        assert result.get("ok") is False
        assert "no encontrada" in result["error"].lower()

    def test_no_sinks_no_pileta_fails(self):
        """Sin sinks ni pileta_sku/qty → no hay nada que cotizar."""
        warnings_buf: list[str] = []
        result = _calculate_quote_products_only({
            "client_name": "X", "project": "Y", "plazo": "30",
            "discount_pct": 0,
        }, warnings_buf)
        assert result.get("ok") is False
        assert "ningún sink" in result["error"].lower() or "vacío" in result["error"].lower()

    def test_invalid_sink_shape_warned_and_skipped(self):
        """Sink mal formado (qty=0, sin name, etc.) → warning + skip,
        pero no bloquea si hay otros sinks válidos."""
        warnings_buf: list[str] = []
        result = _calculate_quote_products_only({
            "client_name": "X", "project": "Y", "plazo": "30",
            "sinks": [
                {"name": "OK", "quantity": 1, "unit_price": 100},
                {"name": "", "quantity": 5, "unit_price": 200},  # ← inválido
                {"quantity": 1, "unit_price": 50},               # ← sin name
            ],
            "discount_pct": 0,
        }, warnings_buf)
        assert result.get("ok") is True
        assert len(result["sinks"]) == 1


# ═══════════════════════════════════════════════════════════════════════
# Render PDF — bloques vacíos no aparecen
# ═══════════════════════════════════════════════════════════════════════


class TestPDFRender:
    """Tests E2E del PDF generado. Necesitan pdftotext (poppler-utils).
    Skipean si no está instalado."""

    def _calc_dyscon(self) -> dict:
        result = calculate_quote(_dyscon_input(discount_pct=5, pileta_qty=32))
        assert result.get("ok") is True
        return result

    def test_pdf_no_empty_material_block(self, tmp_path):
        from app.modules.agent.tools.document_tool import _generate_pdf
        out = tmp_path / "products_only.pdf"
        _generate_pdf(out, self._calc_dyscon())
        assert out.exists()
        import subprocess
        try:
            txt = subprocess.run(
                ["pdftotext", "-layout", str(out), "-"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except FileNotFoundError:
            pytest.skip("pdftotext not installed")
        # NO debe aparecer el bloque material vacío.
        assert "PILETAS JOHNSON - 20mm" not in txt, (
            f"Material vacío PILETAS JOHNSON - 20mm aparece en PDF "
            f"products_only:\n{txt[:1500]}"
        )
        # NO debe aparecer "MANO DE OBRA" header (no hay mo_items).
        assert "MANO DE OBRA" not in txt, (
            f"Header MO suelto en PDF sin mo_items:\n{txt[:1500]}"
        )

    def test_pdf_includes_pileta_product_with_qty(self, tmp_path):
        from app.modules.agent.tools.document_tool import _generate_pdf
        out = tmp_path / "products_only.pdf"
        _generate_pdf(out, self._calc_dyscon())
        import subprocess
        try:
            txt = subprocess.run(
                ["pdftotext", "-layout", str(out), "-"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except FileNotFoundError:
            pytest.skip("pdftotext not installed")
        # Pileta debe aparecer con quantity 32.
        assert "32" in txt
        assert "JOHNSON" in txt.upper()

    def test_pdf_has_discount_with_negative_amount(self, tmp_path):
        from app.modules.agent.tools.document_tool import _generate_pdf
        out = tmp_path / "products_only.pdf"
        _generate_pdf(out, self._calc_dyscon())
        import subprocess
        try:
            txt = subprocess.run(
                ["pdftotext", "-layout", str(out), "-"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except FileNotFoundError:
            pytest.skip("pdftotext not installed")
        # Línea de descuento con monto en negativo.
        assert "Descuento 5%" in txt or "Descuento 5" in txt
        import re
        assert re.search(r"-\s*\$\s*[\d.]+", txt), (
            f"Descuento debería tener monto en negativo:\n{txt[:1500]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Persistencia del flag — regen PDF de quote viejo
# ═══════════════════════════════════════════════════════════════════════


class TestQuoteModePersistence:
    """**Test crítico explícito** del review feedback (anti-bug por
    regresión): regenerar PDF a partir de un `quote_breakdown`
    persistido que tiene `_quote_mode="products_only"`.

    Simula el flow del botón "regenerar PDF" sobre un quote viejo.
    Sin esto, el feature se rompe en regen porque el render pierde
    el flag y vuelve al flujo normal (que emite material vacío).

    NO mockea Anthropic ni la DB — toma el dict del breakdown como
    si lo hubiéramos leído desde `quote.quote_breakdown` y lo pasa
    directo a `_generate_pdf`. Eso es exactamente lo que hace el
    handler de regen post-canonicalize.
    """

    def _persisted_breakdown(self) -> dict:
        """Shape que quedaría guardado en `Quote.quote_breakdown` JSON
        column después de un calculate_quote en modo products_only.
        Lo que recibe `_generate_pdf` cuando se regenera el PDF."""
        return {
            "_quote_mode": "products_only",
            "client_name": "DYSCON S.A.",
            "project": "Unidad Penal N°8 — Piñero",
            "delivery_days": "A confirmar",
            "material_name": "",
            "material_m2": 0,
            "material_price_unit": 0,
            "material_currency": "ARS",
            "thickness_mm": 0,
            "discount_pct": 5,
            "discount_amount": 218256,
            "sectors": [],
            "piece_details": [],
            "mo_items": [],
            "total_mo_ars": 0,
            "sinks": [
                {"name": "PILETA JOHNSON E50/18", "quantity": 32, "unit_price": 136410},
            ],
            "total_ars": 32 * 136410 - 218256,
            "total_usd": 0,
        }

    def test_regen_pdf_keeps_products_only_layout(self, tmp_path):
        """El PDF regenerado de un breakdown con `_quote_mode="products_only"`
        DEBE seguir respetando los gates: sin material, sin MO header."""
        from app.modules.agent.tools.document_tool import _generate_pdf
        breakdown = self._persisted_breakdown()
        out = tmp_path / "regen.pdf"
        _generate_pdf(out, breakdown)
        assert out.exists()
        import subprocess
        try:
            txt = subprocess.run(
                ["pdftotext", "-layout", str(out), "-"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except FileNotFoundError:
            pytest.skip("pdftotext not installed")
        # Sin bloque material vacío.
        assert "PILETAS JOHNSON - 20mm" not in txt
        # Sin header MO.
        assert "MANO DE OBRA" not in txt
        # Pileta SÍ está, con quantity.
        assert "32" in txt
        # Descuento visible.
        assert "Descuento 5" in txt

    def test_regen_excel_keeps_products_only_layout(self, tmp_path):
        """Excel regen debe respetar los mismos gates que el PDF."""
        from app.modules.agent.tools.document_tool import _generate_excel
        breakdown = self._persisted_breakdown()
        out = tmp_path / "regen.xlsx"
        _generate_excel(out, breakdown)
        assert out.exists()
        import zipfile
        with zipfile.ZipFile(str(out)) as z:
            shared = z.read("xl/sharedStrings.xml").decode("utf-8") if "xl/sharedStrings.xml" in z.namelist() else ""
            sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        all_text = shared + sheet
        # No "MANO DE OBRA" header en Excel.
        assert "MANO DE OBRA" not in all_text
        # Sí "Descuento 5%".
        assert "Descuento 5%" in all_text

    def test_quote_mode_in_visual_fields_drift_guard(self):
        """`_quote_mode` debe estar en `_VISUAL_FIELDS` de
        `_canonicalize_quotes_data_from_db` para que regenerar PDF
        de un quote viejo respete el modo. Si alguien lo saca, los
        regen vuelven a romperse."""
        # Lectura directa del módulo — no podemos importar la constante
        # porque vive dentro de la función. Usamos grep de archivo
        # como drift guard funcional.
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod._canonicalize_quotes_data_from_db)
        assert '"_quote_mode"' in src or "'_quote_mode'" in src, (
            "_quote_mode no está en _VISUAL_FIELDS de "
            "_canonicalize_quotes_data_from_db. Regen PDF de quotes "
            "products_only va a romperse — leer el comentario del PR #424."
        )
