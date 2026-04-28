"""Tests para PR #412 — `build_deterministic_paso1`.

**Bug observado:** el Paso 1 markdown lo armaba el LLM Sonnet libremente
desde el response de `list_pieces`. El LLM ignoraba `piece.m2` y
`total_m2` (ya correctos en el response) y rehacía la cuenta como
`largo × prof` (m²/u, sin multiplicar por `qty`).

Caso real DYSCON (quote `bb4196f1` post-#411):
- `list_pieces` devolvió `total_m2=42.39` correcto.
- LLM mostró tabla con m²/u (1.15, 0.19, 0.93, 0.16) y total 9.43.
- LLM emitió un warning falso de "DISCREPANCIA DETECTADA" como
  efecto secundario.

**Fix (gemelo del Paso 2 determinístico):**
- `build_deterministic_paso1` en calculator construye el markdown
  desde el response de `list_pieces`. Una sola fuente de verdad.
- agent.py inyecta el resultado como `result["_paso1_rendered"]`.
- CONTEXT.md instruye al LLM a usarlo verbatim (regla absoluta,
  análoga a `_paso2_rendered`).

Cobertura:
- DYSCON exacto: 14 piezas con quantities mixtas, total = 42.39.
- Caso simple sin quantity: sin `(×N)`, total m² correcto.
- Header con cliente/proyecto/material.
- Render usa los valores literales del response (no recalcula).
- Total = `total_m2` del response (no suma de filas).
"""
from __future__ import annotations

import pytest

from app.modules.quote_engine.calculator import (
    build_deterministic_paso1,
    list_pieces,
)


# ═══════════════════════════════════════════════════════════════════════
# Caso DYSCON — 14 piezas con quantities mixtas, total 42.39
# ═══════════════════════════════════════════════════════════════════════


class TestDysconRender:
    def test_dyscon_full_render(self):
        """Brief DYSCON exacto: total esperado 42.39 m². Las filas
        muestran m² total (con qty aplicada), nunca m²/u."""
        pieces = [
            {"description": "M1 mesada", "largo": 1.92, "prof": 0.60, "quantity": 24},
            {"description": "M1 zócalo atrás", "largo": 1.92, "alto": 0.10, "quantity": 24},
            {"description": "M2 mesada (Office 32)", "largo": 1.70, "prof": 0.60, "quantity": 1},
            {"description": "M2 zócalo atrás", "largo": 1.70, "alto": 0.10, "quantity": 1},
            {"description": "M3 mesada (Office 12)", "largo": 2.50, "prof": 0.60, "quantity": 1},
            {"description": "M3 zócalo atrás", "largo": 2.50, "alto": 0.10, "quantity": 1},
            {"description": "M4 mesada (Office 27)", "largo": 2.50, "prof": 0.60, "quantity": 1},
            {"description": "M4 zócalo atrás", "largo": 2.50, "alto": 0.10, "quantity": 1},
            {"description": "M5 mesada (Office 53)", "largo": 1.80, "prof": 0.60, "quantity": 1},
            {"description": "M5 zócalo atrás", "largo": 1.80, "alto": 0.10, "quantity": 1},
            {"description": "M6 mesada (Office 80/83)", "largo": 1.55, "prof": 0.60, "quantity": 2},
            {"description": "M6 zócalo atrás", "largo": 1.55, "alto": 0.10, "quantity": 2},
            {"description": "M7 mesada (Office 87/90)", "largo": 1.50, "prof": 0.60, "quantity": 2},
            {"description": "M7 zócalo atrás", "largo": 1.50, "alto": 0.10, "quantity": 2},
        ]
        lp = list_pieces(pieces, is_edificio=True)
        assert lp["ok"] is True
        # Sanity: el response del list_pieces ya tiene 42.39.
        assert abs(lp["total_m2"] - 42.39) < 0.05

        md = build_deterministic_paso1(
            lp,
            client_name="DYSCON S.A.",
            project="Unidad Penal N°8 — Piñero",
            material="GRANITO GRIS MARA EXTRA 2 ESP",
        )
        # Header con cliente/obra/material.
        assert "DYSCON S.A." in md
        assert "Unidad Penal N°8 — Piñero" in md
        assert "GRANITO GRIS MARA EXTRA 2 ESP" in md
        # Total visible = 42,39 m² (coma decimal ARS-style).
        assert "42,39 m²" in md, (
            f"Total render regresión: '42,39 m²' no está en el markdown.\n{md}"
        )
        # NO debe aparecer "9,43" ni "9.43" (el bug viejo).
        assert "9,43" not in md and "9.43" not in md, (
            f"Regresión PR #412: el render contiene 9,43 (suma de m²/u). "
            f"Backend está re-introduciendo el bug del LLM.\n{md}"
        )
        # M1 mesada con qty=24 → fila con (×24) y m² = 27.60.
        assert "×24" in md
        # M6 mesada con qty=2 → fila con (×2) y m² = 1.86.
        assert "×2" in md


# ═══════════════════════════════════════════════════════════════════════
# Caso simple — 1 pieza sin quantity (residencial)
# ═══════════════════════════════════════════════════════════════════════


class TestSimpleRender:
    def test_simple_no_quantity(self):
        """Cocina particular: 1 mesada + 1 zócalo. Sin sufijo (×N),
        cant = '—'. Render compacto."""
        pieces = [
            {"description": "Mesada", "largo": 2.0, "prof": 0.6},
            {"description": "Zócalo trasero", "largo": 2.0, "alto": 0.05},
        ]
        lp = list_pieces(pieces, is_edificio=False)
        md = build_deterministic_paso1(
            lp,
            client_name="Pérez",
            project="Cocina Casa",
            material="Silestone Blanco Norte",
        )
        # Header básico.
        assert "Pérez" in md
        assert "Silestone Blanco Norte" in md
        # No debe haber sufijos (×N) — todas las piezas son qty=1.
        assert "×" not in md or md.count("×") == md.count("× 0"), (
            f"Caso simple no debe tener sufijos (×N). Render:\n{md}"
        )
        # La columna Cant debe mostrar `—` (em-dash) para qty=1.
        # (Verificamos que aparezca al menos 2 veces — una por cada pieza.)
        assert md.count("—") >= 2

    def test_total_uses_response_value_not_sum(self):
        """El TOTAL del render = `total_m2` del response, NO una suma
        manual de las filas. Prueba que si `total_m2` del response
        difiere de la suma visual (caso edge: rounding), respetamos
        el response."""
        # Inyectamos un response artificial con total que NO coincide
        # con la suma de las filas — el helper debe respetar `total_m2`.
        fake_response = {
            "ok": True,
            "pieces": [
                {"label": "Pieza A", "m2": 1.00, "qty": 1},
                {"label": "Pieza B", "m2": 2.00, "qty": 1},
            ],
            "total_m2": 99.99,  # ← intencionalmente raro
        }
        md = build_deterministic_paso1(
            fake_response, client_name="Test", project="Test", material="Test"
        )
        # El TOTAL debe reflejar 99.99, no 3.00.
        assert "99,99 m²" in md, (
            f"El render NO debe sumar filas — debe usar `total_m2` "
            f"literal del response. Got:\n{md}"
        )
        assert "3,00 m²" not in md
