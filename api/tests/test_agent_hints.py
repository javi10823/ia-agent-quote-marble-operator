"""Tests for agent hint injection — requirement reminders, multi-material detection, pileta signal."""

import pytest
from app.modules.agent.agent import _build_requirement_reminder


class TestRequirementReminder:
    """Tests for _build_requirement_reminder — detects explicit requirements in conversation."""

    def test_bacha_keyword(self):
        result = _build_requirement_reminder("cotizar bacha johnson", None)
        assert result is not None
        assert "PILETA/BACHA" in result

    def test_pileta_keyword(self):
        result = _build_requirement_reminder("con pileta empotrada", None)
        assert result is not None
        assert "PILETA/BACHA" in result

    def test_compra_bacha_semantic(self):
        """'compra la bacha' should trigger pileta reminder."""
        result = _build_requirement_reminder("compra la bacha en d'angelo", None)
        assert result is not None
        assert "PILETA/BACHA" in result

    def test_compra_pileta_semantic(self):
        result = _build_requirement_reminder("compra pileta acá", None)
        assert result is not None
        assert "PILETA/BACHA" in result

    def test_la_pide_semantic(self):
        result = _build_requirement_reminder("la pide con bacha", None)
        assert result is not None
        assert "PILETA/BACHA" in result

    def test_no_pileta_no_match(self):
        """Message without pileta/bacha keywords should not trigger."""
        result = _build_requirement_reminder("mesada de silestone 2m x 0.6", None)
        # Should not detect pileta
        if result:
            assert "PILETA/BACHA" not in result

    def test_conversation_history_scan(self):
        """Keywords in earlier messages should also trigger."""
        history = [
            {"role": "user", "content": "necesito cotizar con bacha"},
            {"role": "assistant", "content": "Perfecto, voy a calcular."},
        ]
        result = _build_requirement_reminder("acá va el plano", history)
        assert result is not None
        assert "PILETA/BACHA" in result

    def test_anafe_detection(self):
        result = _build_requirement_reminder("mesada con corte de anafe", None)
        assert result is not None
        assert "ANAFE" in result

    def test_multiple_requirements(self):
        result = _build_requirement_reminder("mesada con bacha y anafe, con zocalo", None)
        assert result is not None
        assert "PILETA/BACHA" in result
        assert "ANAFE" in result
        assert "ZÓCALO" in result


class TestMultiMaterialDetection:
    """Tests for multi-material hint injection logic."""

    def _has_multi_mat(self, msg: str) -> bool:
        """Replicate the detection logic from agent.py."""
        _msg_lower = msg.lower()
        _multi_mat_patterns = [" y ", " o ", "opción 1", "opcion 1", "alternativa", "también en ", "tambien en "]
        _material_keywords = ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto",
                              "granito", "mármol", "marmol", "negro brasil", "carrara"]
        _mat_count = sum(1 for mk in _material_keywords if mk in _msg_lower)
        return _mat_count >= 2 and any(p in _msg_lower for p in _multi_mat_patterns)

    def test_two_materials_with_y(self):
        assert self._has_multi_mat("presupuestar en Silestone Norte y Dekton Kelya")

    def test_two_materials_with_o(self):
        assert self._has_multi_mat("cotizar Silestone Blanco Norte o Purastone Paloma")

    def test_two_materials_with_tambien(self):
        assert self._has_multi_mat("también en Dekton, además del Silestone")

    def test_single_material_no_trigger(self):
        assert not self._has_multi_mat("mesada en Silestone Blanco Norte 2m x 0.6")

    def test_no_materials_no_trigger(self):
        assert not self._has_multi_mat("mesada de cocina 2m x 0.6 con bacha")
