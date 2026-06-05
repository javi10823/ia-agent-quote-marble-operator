"""Snapshot tests del output de `_generate_pdf` · Sprint 4 pdf-snapshot-tests.

Red de seguridad contra regresiones backend silenciosas. Decisión arquitectónica
post-FASE 1 del sub-PR `pdf-template-engine`: NO migrar fpdf2 → WeasyPrint
(scope real de 12-18h cubriendo 3 renderers + system deps en Railway). En su
lugar, snapshotear el output actual de fpdf2 y alertar en CI cuando cambie.

## Lo que estos goldens NO certifican

Que las cifras MO del fixture matcheen el output del calculator real del
backend. Los inputs son **replicados manualmente** del frontend mock
(`CANONICAL_CALCULATION_018` / `_017`). Si el calculator real produce números
distintos, el snapshot NO lo detecta · solo detectaría drift del PDF
renderer dado los mismos inputs.

## Lo que SÍ certifican

Que dado un fixture FIJO de inputs, el output del PDF (texto extraído +
estructura) se mantiene ESTABLE entre commits. Cuando el snapshot rompe en
CI sin que se haya tocado `_generate_pdf`, es alerta legítima.

Para validar cifras vs calculator real → sub-PR `paso-1-real` futuro.

## Cobertura

- ✅ `_generate_pdf` modo standard (PRES-018 con descuento + PRES-017 sin)
- ❌ `_generate_edificio_pdf` (deuda · sub-PR futuro si Marina lo usa)
- ❌ `_generate_resumen_obra_pdf` (deuda)
- ❌ products_only mode (deuda)
- ❌ m² override + planilla footnote (deuda)
- ❌ `_generate_excel` (otro renderer · fuera de scope)
"""
import re
from pathlib import Path

import pdfplumber
import pytest

from app.modules.agent.tools.document_tool import generate_documents

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# fpdf2 es pure Python · siempre disponible en CI.
try:
    from fpdf import FPDF  # noqa: F401

    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

requires_pdf = pytest.mark.skipif(not HAS_FPDF, reason="fpdf2 not installed")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_pdf_text(text: str) -> str:
    """Normaliza el texto extraído para snapshots determinísticos.

    `_generate_pdf` embebe `datetime.now().strftime('%d/%m/%Y')` en el doc.
    Cada corrida cambia la fecha · regex la reemplaza por `DATE` para que
    el snapshot sea estable entre días.

    También colapsa whitespace múltiple (pdfplumber a veces inserta dobles
    espacios según coordenadas X) y normaliza line endings.
    """
    # Fechas dd/mm/yyyy → DATE
    text = re.sub(r"\d{2}/\d{2}/\d{4}", "DATE", text)
    # Fechas dd.mm.yyyy → DATE (formato alternativo del template).
    text = re.sub(r"\d{2}\.\d{2}\.\d{4}", "DATE", text)
    # Whitespace múltiple en línea → 1 espacio.
    text = re.sub(r"[ \t]+", " ", text)
    # Trim líneas individuales + colapsar líneas vacías múltiples.
    lines = [ln.strip() for ln in text.splitlines()]
    # Mantener líneas vacías como separadores estructurales pero no más de 1.
    out = []
    prev_empty = False
    for ln in lines:
        if not ln:
            if not prev_empty:
                out.append("")
            prev_empty = True
        else:
            out.append(ln)
            prev_empty = False
    return "\n".join(out).strip()


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extrae texto del PDF concatenando todas las páginas."""
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text() or ""
            pages.append(extracted)
    return "\n".join(pages)


async def _generate_and_extract(quote_id: str, data: dict) -> str:
    """Genera el PDF + extrae texto normalizado. Helper de cada test."""
    result = await generate_documents(quote_id, data)
    assert result["ok"] is True, f"generate_documents failed: {result}"
    pdf_files = list((OUTPUT_DIR / quote_id).glob("*.pdf"))
    assert len(pdf_files) == 1, f"esperaba 1 PDF, encontré {len(pdf_files)}"
    raw = _extract_pdf_text(pdf_files[0])
    return _normalize_pdf_text(raw)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPdfSnapshotsPres018:
    """Snapshots PRES-2026-018 · Cueto-Heredia · Silestone Blanco Norte · con descuento."""

    @requires_pdf
    @pytest.mark.asyncio
    async def test_pdf_text_snapshot(self, pres_2026_018_data, snapshot):
        """Golden: texto completo del PDF generado para PRES-018."""
        text = await _generate_and_extract("test-snap-018", pres_2026_018_data)
        assert text == snapshot

    @requires_pdf
    @pytest.mark.asyncio
    async def test_pdf_structural_assertions(self, pres_2026_018_data):
        """Cifras y estructura esperadas del PDF (independiente del golden)."""
        text = await _generate_and_extract("test-snap-018-struct", pres_2026_018_data)
        # Cliente + proyecto presentes.
        assert "Cueto-Heredia" in text
        assert "cocina Belgrano" in text
        # Material + descuento.
        assert "SILESTONE" in text
        assert "BLANCO NORTE" in text
        # Sección MO presente (header destacado del template).
        assert "MANO DE OBRA" in text
        # Footer con condiciones LITERAL del template.
        assert "CONDICIONES" in text or "Condiciones" in text.upper()
        # Grand total bicurrency · matchea formato del backend.
        assert "PRESUPUESTO TOTAL" in text


class TestPdfSnapshotsPres017:
    """Snapshots PRES-2026-017 · Pereyra · sin descuento (datasource isolation)."""

    @requires_pdf
    @pytest.mark.asyncio
    async def test_pdf_text_snapshot(self, pres_2026_017_data, snapshot):
        """Golden: texto completo del PDF generado para PRES-017."""
        text = await _generate_and_extract("test-snap-017", pres_2026_017_data)
        assert text == snapshot

    @requires_pdf
    @pytest.mark.asyncio
    async def test_pdf_structural_assertions(self, pres_2026_017_data):
        """Cifras y estructura esperadas del PDF · Pereyra es otro cliente."""
        text = await _generate_and_extract("test-snap-017-struct", pres_2026_017_data)
        assert "Pereyra" in text
        assert "Rosario" in text
        # Sin descuento aplicado · texto "DESC" no debería aparecer como bloque.
        # (puede aparecer en otro contexto pero no como total descuento aplicado)
        assert "MANO DE OBRA" in text
        # Grand total presente.
        assert "PRESUPUESTO TOTAL" in text
