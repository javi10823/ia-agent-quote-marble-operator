"""Tests para PR #439 (P1.3) — `notes` aparece en PDF/Excel.

**Plan Fase 1 — P1.3** del análisis de modificabilidad (29/04/2026).

**Bug detectado en el análisis:**

`Quote.notes` se persistía vía `PATCH /quotes/{id}` y `EditableField`
del frontend, pero **nunca aparecía en el PDF ni Excel**. Los
renderers `_generate_pdf` / `_generate_excel` leen de `data["notes"]`
pero el handler del agente no inyectaba `Quote.notes` en `qdata`
antes de invocar generate_documents.

Resultado: el operador escribía notas para el cliente, las veía en
el chat/detalle, pero el PDF entregado al cliente NO las tenía.

**Fix:**

1. **`agent.py:5727`** (handler `generate_documents` post-save):
   leer `Quote.notes` de DB e inyectar en `qdata["notes"]` antes
   de invocar `generate_documents()`.

2. **`document_tool._generate_pdf`** (función line 1285): bloque
   "NOTAS" antes de CONDICIONES si `data["notes"]` no vacío.

3. **`document_tool._generate_excel`** (función line 1681): bloque
   "NOTAS" análogo, con merge de celdas y alto auto-calculado.

**Tests cubren:**

- PDF/Excel con notes presente → aparece bloque "NOTAS".
- PDF/Excel con notes vacío/None → NO aparece (no ruido).
- Notes con saltos de línea → multi-cell respeta.
- Drift guard: el handler inyecta antes de llamar al renderer.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _ars_data_with_notes(notes: str | None) -> dict:
    """Quote ARS típico para tests del render."""
    return {
        "client_name": "Test Cliente",
        "project": "Test Proyecto",
        "delivery_days": "30 días",
        "material_name": "GRANITO GRIS MARA EXTRA 2 ESP",
        "material_m2": 5.0,
        "material_price_unit": 224825,
        "material_currency": "ARS",
        "discount_pct": 0,
        "thickness_mm": 20,
        "sectors": [{"label": "Cocina", "pieces": ["Mesada 2.0 × 0.6"]}],
        "sinks": [],
        "mo_items": [
            {"description": "Colocación", "quantity": 5, "unit_price": 50000, "base_price": 41322, "total": 250000},
        ],
        "total_ars": 1374125,
        "total_usd": 0,
        "is_edificio": False,
        "notes": notes,
    }


def _pdf_text(pdf_path: Path) -> str:
    """Extrae texto del PDF con pdftotext (poppler). Skipea si no
    está instalado."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout
    except FileNotFoundError:
        pytest.skip("pdftotext not installed")


# ═══════════════════════════════════════════════════════════════════════
# PDF render
# ═══════════════════════════════════════════════════════════════════════


class TestPDFNotes:
    def test_pdf_with_notes_renders_notas_block(self, tmp_path):
        """Caso del análisis: notes presente → bloque "NOTAS" + texto."""
        from app.modules.agent.tools.document_tool import _generate_pdf
        out = tmp_path / "with_notes.pdf"
        _generate_pdf(out, _ars_data_with_notes("Cliente prefiere entrega por la mañana."))
        txt = _pdf_text(out)
        assert "NOTAS" in txt, f"Bloque NOTAS no aparece:\n{txt[:1500]}"
        assert "Cliente prefiere entrega por la mañana" in txt, (
            f"Texto de las notas no aparece:\n{txt[:1500]}"
        )

    def test_pdf_without_notes_no_block(self, tmp_path):
        """**Regression**: notes vacío/None NO debe agregar header
        "NOTAS" suelto sin contenido."""
        from app.modules.agent.tools.document_tool import _generate_pdf
        out = tmp_path / "no_notes.pdf"
        _generate_pdf(out, _ars_data_with_notes(None))
        txt = _pdf_text(out)
        assert "NOTAS" not in txt, (
            f"Header NOTAS aparece sin contenido:\n{txt[:1500]}"
        )

    def test_pdf_with_empty_notes_no_block(self, tmp_path):
        """notes="" / "  " (solo whitespace) → NO renderiza."""
        from app.modules.agent.tools.document_tool import _generate_pdf
        for empty in ["", "   ", "\n\n"]:
            out = tmp_path / f"empty_{hash(empty)}.pdf"
            _generate_pdf(out, _ars_data_with_notes(empty))
            txt = _pdf_text(out)
            assert "NOTAS" not in txt, (
                f"NOTAS aparece con notes={empty!r}:\n{txt[:1500]}"
            )

    def test_pdf_multiline_notes(self, tmp_path):
        """Notes con saltos de línea → multi_cell respeta."""
        from app.modules.agent.tools.document_tool import _generate_pdf
        notes = (
            "Línea 1: importante.\n"
            "Línea 2: cliente vuelve mañana.\n"
            "Línea 3: confirmar pileta."
        )
        out = tmp_path / "multiline.pdf"
        _generate_pdf(out, _ars_data_with_notes(notes))
        txt = _pdf_text(out)
        assert "NOTAS" in txt
        assert "Línea 1" in txt
        assert "Línea 2" in txt
        assert "Línea 3" in txt


# ═══════════════════════════════════════════════════════════════════════
# Excel render
# ═══════════════════════════════════════════════════════════════════════


class TestExcelNotes:
    def _excel_text(self, xlsx_path: Path) -> str:
        """Read raw XML del sheet para verificar contenido sin parsear
        formulas."""
        import zipfile
        with zipfile.ZipFile(str(xlsx_path)) as z:
            shared = z.read("xl/sharedStrings.xml").decode("utf-8") if "xl/sharedStrings.xml" in z.namelist() else ""
            sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        return shared + sheet

    def test_excel_with_notes(self, tmp_path):
        from app.modules.agent.tools.document_tool import _generate_excel
        out = tmp_path / "with_notes.xlsx"
        _generate_excel(out, _ars_data_with_notes("Notas del cliente importantes."))
        txt = self._excel_text(out)
        assert "NOTAS" in txt, "Bloque NOTAS no aparece en Excel"
        assert "Notas del cliente importantes" in txt

    def test_excel_without_notes(self, tmp_path):
        """Notes None → NO header NOTAS suelto."""
        from app.modules.agent.tools.document_tool import _generate_excel
        out = tmp_path / "no_notes.xlsx"
        _generate_excel(out, _ars_data_with_notes(None))
        txt = self._excel_text(out)
        # OK si "NOTAS" no aparece. Si aparece dentro de otra string
        # (ej. "NOTAS DEL OPERADOR" en algún template legacy), filtrar.
        # En este template no hay otras "NOTAS" — esperamos ausencia total.
        assert "NOTAS" not in txt, (
            "Header NOTAS aparece en Excel sin contenido"
        )


# ═══════════════════════════════════════════════════════════════════════
# Drift guard del handler — inyecta notes desde DB
# ═══════════════════════════════════════════════════════════════════════


class TestHandlerInjectsNotes:
    def test_handler_reads_notes_from_db(self):
        """Drift guard: el handler de generate_documents debe leer
        `Quote.notes` y inyectarlo en qdata. Sin esta inyección, las
        notes nunca llegan al renderer (bug del análisis 29/04/2026)."""
        import inspect
        from app.modules.agent import agent as agent_mod
        src = inspect.getsource(agent_mod.AgentService._execute_tool)
        # El bloque debe leer _notes_quote.notes y asignar a qdata["notes"].
        assert "_notes_quote.notes" in src, (
            "Handler no lee Quote.notes — las notas nunca llegan al PDF."
        )
        assert 'qdata["notes"]' in src or "qdata['notes']" in src, (
            "Handler no inyecta notes en qdata. Sin esto, "
            "_generate_pdf no las renderiza aunque se hayan persistido."
        )
