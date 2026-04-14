"""Regression test for PR #5 — backfill material_price_base from catalog.

Bug DINALE 14/04/2026: cada presupuesto emitía el warning
"Falta material_price_base — no se puede verificar IVA del material"
porque el schema de `generate_documents` no expone ese campo al LLM.

Fix: `_backfill_material_price_base` llena el campo desde el catálogo
antes de correr las validaciones.
"""
from __future__ import annotations

import pytest

from app.modules.agent.agent import _backfill_material_price_base
from app.modules.agent.tools.validation_tool import validate_despiece


def _llm_style_quote_without_base() -> dict:
    """Exactly how the LLM constructs the dict when calling generate_documents."""
    return {
        "client_name": "DINALE S.A.",
        "project": "Unidad Penitenciaria N°12",
        "material_name": "GRANITO GRIS MARA EXTRA 2 ESP",
        "material_m2": 31.37,
        "material_price_unit": 224825,  # ARS con IVA
        "material_currency": "ARS",
        "discount_pct": 15,
        "sectors": [{"label": "Obra", "pieces": ["2.15 x 0.60 ME01-B"]}],
        "sinks": [],
        "mo_items": [
            {"description": "Agujero y pegado pileta", "quantity": 19,
             "unit_price": 62045, "base_price": 51276, "total": 1178855},
        ],
        "total_ars": 7371446,
        "total_usd": 0,
        # NO material_price_base — schema doesn't expose it to the LLM
    }


class TestBackfillMaterialPriceBase:
    def test_backfill_populates_missing_base(self):
        """Backfill debe copiar el precio base del catálogo al dict."""
        q = _llm_style_quote_without_base()
        assert "material_price_base" not in q
        _backfill_material_price_base([q])
        assert q.get("material_price_base"), q
        # Debe ser el precio SIN IVA (price_ars_base del catálogo)
        assert q["material_price_base"] == 185806.03

    def test_backfill_idempotent_when_present(self):
        """Si ya hay base, no sobrescribir."""
        q = _llm_style_quote_without_base()
        q["material_price_base"] = 999999
        _backfill_material_price_base([q])
        assert q["material_price_base"] == 999999

    def test_backfill_silent_for_unknown_material(self):
        """Material no-catalogado: no crash, solo no llena."""
        q = _llm_style_quote_without_base()
        q["material_name"] = "INVENTED NONEXISTENT MATERIAL XYZ"
        del q["material_price_unit"]  # avoid downstream validator issues
        # Should not raise
        _backfill_material_price_base([q])
        # Base queda ausente
        assert not q.get("material_price_base")

    def test_backfill_skips_when_unit_inconsistent_with_catalog(self):
        """Si el price_unit del agente no coincide con catalog.base × IVA,
        NO backfillear — evita convertir el warning en error bloqueante
        (fixtures legacy, drift de precios, overrides manuales)."""
        q = _llm_style_quote_without_base()
        q["material_price_unit"] = 999999  # inconsistente a propósito
        _backfill_material_price_base([q])
        assert not q.get("material_price_base"), (
            "backfill debe saltar cuando unit ≠ round(base × IVA)"
        )

    def test_validator_no_longer_warns_after_backfill(self):
        """Integration: post-backfill, validate_despiece no debe emitir el
        warning 'Falta material_price_base' para el caso DINALE."""
        q = _llm_style_quote_without_base()
        _backfill_material_price_base([q])
        # Add minimal fields the validator needs
        q["material_total"] = round(q["material_m2"] * q["material_price_unit"])
        q["discount_amount"] = round(q["material_total"] * q["discount_pct"] / 100)
        q["merma"] = {"aplica": False, "desperdicio": 0, "sobrante_m2": 0, "motivo": "edificio"}
        q["piece_details"] = [
            {"description": "Mesada", "largo": 2.15, "dim2": 0.60, "m2": 1.625, "quantity": 1},
        ]
        result = validate_despiece(q)
        warning_text = " ".join(result.warnings)
        assert "Falta material_price_base" not in warning_text, result.warnings
