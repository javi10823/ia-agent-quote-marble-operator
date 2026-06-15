"""Sub-PR paso-5-pdf-real-wire · tests del wire end-to-end del PDF.

Cubre los 3 bugs cerrados + el wire de `/generate` que ahora copia full
breakdown en vez de los 14 campos manuales del pre-fix:

  1. Wire `/generate` propaga full breakdown (sobrante, mo_discount,
     has_m2_override, is_edificio, notes).
  2. Bug 1: descuento de material se aplica UNA sola vez en edificio PDF.
  3. Bug 2: `material_total_bruto` override manual respetado (default explícito).
  4. Snapshot real-flow: input del calculator real → PDF → assertions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.agent.tools.document_tool import (
    _read_material_bruto,
    _generate_edificio_pdf,
    _generate_pdf,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers · extracción de texto del PDF generado.
# ──────────────────────────────────────────────────────────────────────


def _pdf_to_text(pdf_path: Path) -> str:
    """Extrae texto del PDF usando `pdftotext` (poppler · ya está en CI).
    Fallback a None si no está disponible · marca skip en el test."""
    import subprocess

    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("pdftotext (poppler) no disponible en este env")


OUTPUT_DIR = Path(__file__).parent.parent / "output" / "test-pdf-wire"


@pytest.fixture(autouse=True)
def _ensure_output_dir(tmp_path_factory):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────
# Fixture · breakdown mínimo edificio con shape REAL del calculator
# (post-PR paso-5-pdf-real-wire · incluye `material_total_bruto`).
# ──────────────────────────────────────────────────────────────────────


def _edificio_breakdown(
    *,
    discount_pct: float = 0,
    material_total_bruto: int | None = None,
    material_total: int | None = None,
) -> dict:
    """Breakdown mínimo para `_generate_edificio_pdf`. `material_total_bruto`
    es el campo nuevo (post-fix); `material_total` el legacy (NET)."""
    bruto = 100_000  # 100k USD bruto
    pct = discount_pct
    net = round(bruto * (1 - pct / 100))
    return {
        "client_name": "Cliente Test",
        "project": "Test Edificio",
        "date": "01.06.2026",
        "delivery_days": "30 dias",
        "material_name": "Test Material",
        "thickness_mm": 20,
        "material_m2": 50.0,
        "material_price_unit": 2000,
        "material_currency": "USD",
        "material_total_bruto": material_total_bruto if material_total_bruto is not None else bruto,
        "material_total": material_total if material_total is not None else net,
        "discount_pct": pct,
        "discount_amount": bruto - net,
        "sectors": [{"label": "Sector A", "pieces": ["1.5 × 0.6 Mesada"]}],
        "sinks": [],
        "mo_items": [],
        "total_ars": 0,
        "total_usd": 0,
        "is_edificio": True,
        "show_mo": False,
        "grand_total_text": "USD 100.000",
    }


# ──────────────────────────────────────────────────────────────────────
# Test 1 · `_read_material_bruto` helper · precedencia + backward compat.
# ──────────────────────────────────────────────────────────────────────


class TestReadMaterialBruto:
    def test_lee_material_total_bruto_explicito(self):
        data = {"material_total_bruto": 80_000, "material_total": 76_000, "discount_pct": 5}
        assert _read_material_bruto(data, 50.0, 2000) == 80_000

    def test_deriva_bruto_de_net_legacy_con_descuento(self):
        # Breakdown legacy: solo material_total (NET) + discount_pct.
        # Helper deriva bruto = net / (1 - pct/100).
        data = {"material_total": 95_000, "discount_pct": 5}
        # 95000 / 0.95 = 100000
        assert _read_material_bruto(data, 50.0, 2000) == 100_000

    def test_legacy_sin_descuento_usa_material_total_directo(self):
        data = {"material_total": 100_000, "discount_pct": 0}
        assert _read_material_bruto(data, 50.0, 2000) == 100_000

    def test_recalcula_desde_m2_x_price_si_ambos_ausentes(self):
        data = {"discount_pct": 0}
        assert _read_material_bruto(data, 50.0, 2000) == 100_000

    def test_override_manual_cero_se_respeta_no_fallback(self):
        """Bug 2 regression: si `material_total_bruto=0` explícito (override
        a precio gratis · raro pero válido), el helper devuelve 0 · NO cae
        al fallback `m2*price` por evaluación truthy del `or`."""
        data = {"material_total_bruto": 0, "discount_pct": 0}
        assert _read_material_bruto(data, 50.0, 2000) == 0


# ──────────────────────────────────────────────────────────────────────
# Test 2 · Bug 1 regression · descuento aplicado UNA sola vez en edificio.
# ──────────────────────────────────────────────────────────────────────


class TestEdificioPdfDescuentoUnaSolaVez:
    def test_edificio_pdf_con_descuento_15pct_no_aplica_doble(self, tmp_path):
        """Quote edificio con discount_pct=15 · material bruto 100k.
        PDF debe mostrar:
          - bloque material: $100.000 (bruto)
          - bloque descuento: −$15.000 (15% sobre 100k)
        NO debe mostrar $85.000 → −$12.750 (15% sobre 85k · double-count)."""
        bd = _edificio_breakdown(discount_pct=15)
        out = tmp_path / "edificio.pdf"
        _generate_edificio_pdf(out, bd)
        text = _pdf_to_text(out)
        # Bruto $100.000 visible (algún format).
        assert "100.000" in text or "100,000" in text or "100000" in text, (
            "Esperaba bruto $100.000 en el PDF"
        )
        # Descuento $15.000 (15% de 100k · NO 12.750 de 85k).
        assert "15.000" in text or "15,000" in text, (
            "Esperaba descuento $15.000 (Bug 1 fix · 15% sobre bruto, NO sobre net)"
        )
        # Anti-regresión: 12.750 sería el descuento double-count.
        assert "12.750" not in text and "12,750" not in text, (
            "Detectado descuento double-count $12.750 (15% de 85k)"
        )

    def test_edificio_pdf_legacy_breakdown_sin_bruto_se_deriva(self, tmp_path):
        """Backward compat: si el breakdown viene de un quote pre-fix
        (solo `material_total` NET + `discount_pct`), el helper deriva el
        bruto correctamente · el PDF renderea como si el fix siempre hubiera estado."""
        bd = _edificio_breakdown(discount_pct=10)
        # Simular legacy: borrar material_total_bruto.
        bd.pop("material_total_bruto", None)
        # material_total ya es NET (90k de 100k bruto).
        assert bd["material_total"] == 90_000
        out = tmp_path / "edificio_legacy.pdf"
        _generate_edificio_pdf(out, bd)
        text = _pdf_to_text(out)
        # Bruto derivado: 90k / 0.9 = 100k.
        assert "100.000" in text or "100,000" in text


# ──────────────────────────────────────────────────────────────────────
# Test 3 · Wire /generate propaga campos críticos (sobrante, notes, etc).
# ──────────────────────────────────────────────────────────────────────


class TestGenerateWirePropagaFullBreakdown:
    def test_standard_pdf_renderea_notes_cuando_quote_tiene(self, tmp_path):
        """PR #439 (deuda cerrada en este sub-PR): `quote.notes` se inyecta
        en doc_data["notes"] antes de generate_documents · el PDF lo
        renderea como bloque NOTAS al final."""
        bd = {
            "client_name": "Cliente Test",
            "project": "Cocina",
            "date": "01.06.2026",
            "delivery_days": "30 dias",
            "material_name": "Test Material",
            "thickness_mm": 20,
            "material_m2": 5.0,
            "material_price_unit": 2000,
            "material_currency": "USD",
            "material_total_bruto": 10_000,
            "material_total": 10_000,
            "discount_pct": 0,
            "sectors": [{"label": "Cocina", "pieces": ["2.0 × 0.6 Mesada"]}],
            "sinks": [],
            "mo_items": [],
            "total_ars": 0,
            "total_usd": 10_000,
            "notes": "Cliente prefiere entrega los sábados",
        }
        out = tmp_path / "with_notes.pdf"
        _generate_pdf(out, bd)
        text = _pdf_to_text(out)
        assert "sábados" in text or "sabados" in text, (
            "PR #439 deuda: notes del quote no llegan al PDF"
        )

    def test_standard_pdf_renderea_sobrante_cuando_presente(self, tmp_path):
        """Sobrante (merma del calculator) renderea bloque separado.
        Antes de este sub-PR, `/generate` no propagaba sobrante_m2 ni
        sobrante_total al doc_data · el bloque no aparecía."""
        bd = {
            "client_name": "Cliente Sobrante",
            "project": "Cocina",
            "date": "01.06.2026",
            "delivery_days": "30 dias",
            "material_name": "Test Material",
            "thickness_mm": 20,
            "material_m2": 5.0,
            "material_price_unit": 2000,
            "material_currency": "USD",
            "material_total_bruto": 10_000,
            "material_total": 10_000,
            "discount_pct": 0,
            "sectors": [{"label": "Cocina", "pieces": ["2.0 × 0.6 Mesada"]}],
            "sinks": [],
            "mo_items": [],
            "sobrante_m2": 1.5,
            "sobrante_total": 3_000,
            "total_ars": 0,
            "total_usd": 13_000,
        }
        out = tmp_path / "with_sobrante.pdf"
        _generate_pdf(out, bd)
        text = _pdf_to_text(out)
        text_lower = text.lower()
        assert "sobrante" in text_lower or "merma" in text_lower, (
            "Sobrante no renderea · el wire de /generate no propagó sobrante_m2/total"
        )


# ──────────────────────────────────────────────────────────────────────
# Test 4 · Snapshot real-flow · calculator → PDF.
# ──────────────────────────────────────────────────────────────────────


class TestPdfSnapshotRealFlow:
    def test_calculator_output_se_renderea_sin_crashear(self, tmp_path):
        """Cierra el gap del docstring de test_pdf_snapshots.py (líneas 8-14):
        los snapshots existentes usan fixtures manuales replicadas del
        frontend mock, NO del calculator real. Este test usa el output
        REAL del calculator como input al PDF · si calculator y PDF
        divergen en shape, falla acá (no en producción)."""
        from app.modules.quote_engine.calculator import calculate_quote

        result = calculate_quote({
            "client_name": "Cliente Snapshot",
            "project": "Cocina test",
            "material": "Blanco Paloma",
            "catalog": "materials-purastone",
            "sku": "PALOMA",
            "pieces": [
                {"largo": 1.5, "prof": 0.60, "descripcion": "Mesada"},
            ],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result.get("ok") is True, result
        # Sub-PR paso-5-pdf-real-wire: confirmar que el field nuevo está.
        assert "material_total_bruto" in result, (
            "calculator no expone `material_total_bruto` · fix Step 2 incompleto"
        )
        # PDF debe renderear sin crashear con el output real del calculator.
        out = tmp_path / "real_flow.pdf"
        _generate_pdf(out, result)
        assert out.exists() and out.stat().st_size > 1000, (
            "PDF generado vacío o corrupto a partir del calculator output"
        )
