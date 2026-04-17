"""Tests for dual vision reader — reconciliation, flow control, context injection."""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from app.modules.quote_engine.dual_reader import (
    reconcile,
    dual_read_crop,
    build_verified_context,
    _compare_float,
    _build_single_result,
    _check_m2,
)


# ═══════════════════════════════════════════════════════
# Helper: sample model outputs
# ═══════════════════════════════════════════════════════

def _sample_result(largo=1.55, ancho=0.60, m2=0.93, confident=0.95,
                   zocalos=None, tipo="recta"):
    if zocalos is None:
        zocalos = [{"lado": "frontal", "ml": 1.55, "alto_m": 0.07}]
    return {
        "sectores": [{
            "id": "cocina",
            "tipo": tipo,
            "tramos": [{
                "id": "tramo_1",
                "descripcion": "Mesada cocina tramo 1",
                "largo_m": largo,
                "ancho_m": ancho,
                "m2": m2,
                "zocalos": zocalos,
                "frentin": [],
                "regrueso": [],
                "notas": [],
            }],
            "m2_placas": m2,
            "m2_zocalos": sum(z["ml"] * z.get("alto_m", 0.07) for z in zocalos),
            "m2_total": round(m2 + sum(z["ml"] * z.get("alto_m", 0.07) for z in zocalos), 2),
            "ambiguedades": [],
            "confident": confident,
        }],
    }


# ═══════════════════════════════════════════════════════
# Reconciliation tests
# ═══════════════════════════════════════════════════════

class TestReconciliacion:
    def test_confirmado(self):
        """Identical results → all CONFIRMADO."""
        opus = _sample_result(largo=1.55, ancho=0.60, m2=0.93)
        sonnet = _sample_result(largo=1.55, ancho=0.60, m2=0.93)
        result = reconcile(opus, sonnet)
        assert result["requires_human_review"] is False
        assert result["source"] == "DUAL"
        tramo = result["sectores"][0]["tramos"][0]
        assert tramo["largo_m"]["status"] == "CONFIRMADO"
        assert tramo["ancho_m"]["status"] == "CONFIRMADO"
        assert tramo["m2"]["status"] == "CONFIRMADO"

    def test_alerta(self):
        """Delta < 5% → ALERTA, value = average."""
        opus = _sample_result(largo=1.55, ancho=0.60)
        sonnet = _sample_result(largo=1.55, ancho=0.58)  # 3.3% diff
        result = reconcile(opus, sonnet)
        tramo = result["sectores"][0]["tramos"][0]
        assert tramo["ancho_m"]["status"] == "ALERTA"
        assert tramo["ancho_m"]["valor"] == pytest.approx(0.59, abs=0.01)

    def test_conflicto(self):
        """Delta > 5% → CONFLICTO, requires review."""
        opus = _sample_result(largo=1.55, ancho=0.60)
        sonnet = _sample_result(largo=1.55, ancho=0.50)  # 16.7% diff
        result = reconcile(opus, sonnet)
        assert result["requires_human_review"] is True
        tramo = result["sectores"][0]["tramos"][0]
        assert tramo["ancho_m"]["status"] == "CONFLICTO"
        assert "ancho_m" in result["conflict_fields"][0]

    def test_dudoso(self):
        """Low confidence → DUDOSO."""
        opus = _sample_result(confident=0.5)
        sonnet = _sample_result(confident=0.5)
        result = reconcile(opus, sonnet)
        assert result["requires_human_review"] is True
        tramo = result["sectores"][0]["tramos"][0]
        assert tramo["largo_m"]["status"] == "DUDOSO"

    def test_zocalos_match(self):
        """Matching zócalos by lado with ==."""
        zocs = [{"lado": "frontal", "ml": 1.74, "alto_m": 0.07}]
        opus = _sample_result(zocalos=zocs)
        sonnet = _sample_result(zocalos=zocs)
        result = reconcile(opus, sonnet)
        z = result["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["status"] == "CONFIRMADO"
        assert z["lado"] == "frontal"

    def test_zocalos_conflicto(self):
        """Different zócalo ml → CONFLICTO."""
        opus = _sample_result(zocalos=[{"lado": "frontal", "ml": 1.74, "alto_m": 0.07}])
        sonnet = _sample_result(zocalos=[{"lado": "frontal", "ml": 1.55, "alto_m": 0.07}])
        result = reconcile(opus, sonnet)
        z = result["sectores"][0]["tramos"][0]["zocalos"][0]
        assert z["status"] == "CONFLICTO"


# ═══════════════════════════════════════════════════════
# Flow control tests
# ═══════════════════════════════════════════════════════

class TestFlowControl:
    @pytest.mark.asyncio
    async def test_sonnet_confiado_no_llama_opus(self):
        """Sonnet confident ≥0.9 → Opus NOT called."""
        confident_result = _sample_result(confident=0.95)

        with patch("app.modules.quote_engine.dual_reader._call_vision", new_callable=AsyncMock) as mock:
            mock.return_value = confident_result
            result = await dual_read_crop(b"fake_image", "cocina", dual_enabled=True)

        # Sonnet called once, Opus never (total 1 call)
        assert mock.call_count == 1
        assert result["source"] == "SOLO_SONNET"

    @pytest.mark.asyncio
    async def test_sonnet_dudoso_llama_opus(self):
        """Sonnet confident < 0.9 → Opus called."""
        unsure_result = _sample_result(confident=0.7)

        call_count = {"sonnet": 0, "opus": 0}
        async def mock_vision(crop_bytes, model, timeout=15, cotas_text=None, brief_text=None):
            if "sonnet" in model.lower():
                call_count["sonnet"] += 1
                return unsure_result
            else:
                call_count["opus"] += 1
                return _sample_result(confident=0.95)

        with patch("app.modules.quote_engine.dual_reader._call_vision", side_effect=mock_vision):
            result = await dual_read_crop(b"fake_image", "cocina", dual_enabled=True)

        assert call_count["sonnet"] == 1
        assert call_count["opus"] == 1
        assert result["source"] == "DUAL"

    @pytest.mark.asyncio
    async def test_opus_timeout(self):
        """Opus timeout → returns SOLO_SONNET."""
        async def mock_vision(crop_bytes, model, timeout=15, cotas_text=None, brief_text=None):
            if "sonnet" in model.lower():
                return _sample_result(confident=0.7)
            else:
                return {"error": "Timeout after 15s", "model": model}

        with patch("app.modules.quote_engine.dual_reader._call_vision", side_effect=mock_vision):
            result = await dual_read_crop(b"fake_image", "cocina", dual_enabled=True)

        assert result["source"] == "SOLO_SONNET"

    @pytest.mark.asyncio
    async def test_dual_read_disabled(self):
        """dual_read_enabled=false → ONLY Sonnet, no Opus, no reconciliation."""
        call_models = []

        async def mock_vision(crop_bytes, model, timeout=15, cotas_text=None, brief_text=None):
            call_models.append(model)
            return _sample_result(confident=0.95)

        with patch("app.modules.quote_engine.dual_reader._call_vision", side_effect=mock_vision):
            result = await dual_read_crop(b"fake_image", "cocina", dual_enabled=False)

        # Only Sonnet called
        assert len(call_models) == 1
        assert "sonnet" in call_models[0].lower()
        # No reconciliation
        assert result["source"] == "SOLO_SONNET"
        assert result["requires_human_review"] is False

    @pytest.mark.asyncio
    async def test_both_fail(self):
        """Both models fail → error result."""
        with patch("app.modules.quote_engine.dual_reader._call_vision", new_callable=AsyncMock) as mock:
            mock.return_value = {"error": "API error"}
            result = await dual_read_crop(b"fake_image", "cocina", dual_enabled=True)

        assert "error" in result


# ═══════════════════════════════════════════════════════
# M2 validation
# ═══════════════════════════════════════════════════════

class TestM2Validation:
    def test_m2_warning_when_mismatch(self):
        result = _build_single_result(_sample_result(m2=1.50), "SOLO_SONNET")
        warning = _check_m2(result, planilla_m2=2.50)
        assert warning is not None
        assert "no coincide" in warning

    def test_m2_no_warning_when_close(self):
        result = _build_single_result(_sample_result(m2=0.93), "SOLO_SONNET")
        # m2_total ≈ 0.93 + zocalo area ≈ 1.04
        warning = _check_m2(result, planilla_m2=1.04)
        assert warning is None

    def test_m2_skip_when_null(self):
        result = _build_single_result(_sample_result(), "SOLO_SONNET")
        warning = _check_m2(result, planilla_m2=None)
        assert warning is None


# ═══════════════════════════════════════════════════════
# Context injection
# ═══════════════════════════════════════════════════════

class TestBuildVerifiedContext:
    def test_contains_verified_header(self):
        data = _build_single_result(_sample_result(), "SOLO_SONNET")
        ctx = build_verified_context(data)
        assert "VERIFICADAS" in ctx
        assert "FUENTE DE VERDAD" in ctx

    def test_contains_measurements(self):
        data = _build_single_result(
            _sample_result(largo=1.55, ancho=0.60, m2=0.93),
            "SOLO_SONNET",
        )
        ctx = build_verified_context(data)
        assert "1.55" in ctx
        assert "0.6" in ctx
        assert "0.93" in ctx

    def test_contains_zocalos(self):
        data = _build_single_result(
            _sample_result(zocalos=[{"lado": "frontal", "ml": 1.74, "alto_m": 0.07}]),
            "SOLO_SONNET",
        )
        ctx = build_verified_context(data)
        assert "frontal" in ctx
        assert "1.74" in ctx


# ═══════════════════════════════════════════════════════
# Compare float helper
# ═══════════════════════════════════════════════════════

class TestCompareFloat:
    def test_exact_match(self):
        status, val = _compare_float(1.55, 1.55)
        assert status == "CONFIRMADO"
        assert val == 1.55

    def test_small_delta(self):
        status, val = _compare_float(1.55, 1.53)  # 1.3% diff
        assert status == "ALERTA"
        assert val == pytest.approx(1.54, abs=0.01)

    def test_large_delta(self):
        status, val = _compare_float(1.55, 1.20)  # 22% diff
        assert status == "CONFLICTO"
        assert val is None

    def test_both_zero(self):
        status, val = _compare_float(0, 0)
        assert status == "CONFIRMADO"
