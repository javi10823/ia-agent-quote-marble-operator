"""Tests de brief_analyzer — extracción de contexto del brief del operador.

Cubre regex fallback (sin LLM) + comportamiento del schema + robustez
cuando el LLM falla."""
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.quote_engine.brief_analyzer import (
    EMPTY_SCHEMA,
    _analyze_regex_fallback,
    analyze_brief,
)


# ── Regex fallback: cobertura de campos ─────────────────────────────────────

class TestRegexFallback:
    def test_empty_brief_returns_schema(self):
        out = _analyze_regex_fallback("")
        assert set(out.keys()) == set(EMPTY_SCHEMA.keys())
        assert out["extraction_method"] == "regex_fallback"

    def test_client_name_clean_extraction(self):
        """El nombre no debe arrastrar SIN/CON/etc."""
        out = _analyze_regex_fallback("material silestone cliente Erica Bernardi SIN zocalos en rosario")
        assert out["client_name"] == "Erica Bernardi"

    def test_client_with_compound_name(self):
        out = _analyze_regex_fallback("cliente Maria Jose Perez de Gomez")
        # Limita a 4 palabras title case
        assert out["client_name"] is not None
        assert "Perez" in out["client_name"]

    def test_material_clean(self):
        out = _analyze_regex_fallback("material pura prima onix white mate Cliente: Juan")
        assert out["material"] is not None
        assert "Cliente" not in out["material"]
        assert "Pura" in out["material"] or "prima" in out["material"].lower()

    def test_localidad(self):
        out = _analyze_regex_fallback("cliente Juan en Rosario con colocacion")
        assert out["localidad"] == "Rosario"

    def test_zocalos_si(self):
        out = _analyze_regex_fallback("cocina con zocalos")
        assert out["zocalos"] == "yes"

    def test_zocalos_no(self):
        out = _analyze_regex_fallback("cocina sin zocalos")
        assert out["zocalos"] == "no"

    def test_colocacion(self):
        assert _analyze_regex_fallback("con colocacion")["colocacion"] == "yes"
        assert _analyze_regex_fallback("sin colocacion")["colocacion"] == "no"
        assert _analyze_regex_fallback("cocina juan")["colocacion"] is None

    def test_pileta_doble(self):
        out = _analyze_regex_fallback("cocina con pileta doble")
        assert out["pileta_mentioned"] is True
        assert out["pileta_simple_doble"] == "doble"

    def test_pileta_apoyo(self):
        out = _analyze_regex_fallback("baño pileta de apoyo")
        assert out["pileta_type"] == "apoyo"

    def test_pileta_empotrada(self):
        out = _analyze_regex_fallback("baño pileta bajomesada")
        assert out["pileta_type"] == "empotrada"

    def test_johnson_sku(self):
        out = _analyze_regex_fallback("pileta Johnson Q37 en rosario")
        assert out["mentions_johnson"] is True
        assert "Q37" in (out["johnson_sku"] or "")

    def test_anafe_count_explicit(self):
        out = _analyze_regex_fallback("cocina con 2 anafes")
        assert out["anafe_count"] == 2
        assert out["anafe_mentioned"] is True

    def test_anafe_gas_y_electrico(self):
        out = _analyze_regex_fallback("anafe a gas y anafe eléctrico")
        assert out["anafe_gas_y_electrico"] is True
        assert out["anafe_count"] == 2

    def test_isla_mention(self):
        out = _analyze_regex_fallback("cocina con isla central")
        assert out["isla_mentioned"] is True

    def test_work_types_multi(self):
        out = _analyze_regex_fallback("cocina y baño silestone")
        assert "cocina" in out["work_types"]
        assert "baño" in out["work_types"]

    def test_edificio(self):
        out = _analyze_regex_fallback("edificio Ventus 5 tipologías")
        assert out["es_edificio"] is True

    def test_descuento_arq(self):
        out = _analyze_regex_fallback("arquitecta 5%")
        assert out["descuento_mentioned"] is True
        assert out["descuento_tipo"] == "arquitecta"
        assert out["descuento_pct"] == 5.0

    def test_frentin_regrueso_pulido(self):
        out = _analyze_regex_fallback("con frentin y regrueso y pulido")
        assert out["frentin_mentioned"] is True
        assert out["regrueso_mentioned"] is True
        assert out["pulido_mentioned"] is True


# ── LLM entry point con fallback ────────────────────────────────────────────

class TestAnalyzeBriefFallback:
    @pytest.mark.asyncio
    async def test_empty_brief_returns_empty_schema(self):
        out = await analyze_brief("")
        assert out["extraction_method"] == "empty"
        assert all(out[k] == v for k, v in EMPTY_SCHEMA.items() if k != "extraction_method")

    @pytest.mark.asyncio
    async def test_llm_timeout_falls_back_to_regex(self):
        import asyncio
        fake_client = type("F", (), {})()
        fake_client.messages = type("M", (), {})()

        async def timeout_create(**kwargs):
            raise asyncio.TimeoutError()

        fake_client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch(
            "app.modules.quote_engine.brief_analyzer.anthropic.AsyncAnthropic",
            return_value=fake_client,
        ):
            out = await analyze_brief("cliente Juan en Rosario con zocalos")
        # Regex fallback extrajo datos
        assert out["extraction_method"] == "regex_fallback"
        assert out["client_name"] == "Juan"
        assert out["localidad"] == "Rosario"
        assert out["zocalos"] == "yes"

    @pytest.mark.asyncio
    async def test_llm_api_error_falls_back(self):
        fake_client = type("F", (), {})()
        fake_client.messages = type("M", (), {})()
        fake_client.messages.create = AsyncMock(side_effect=RuntimeError("api error"))
        with patch(
            "app.modules.quote_engine.brief_analyzer.anthropic.AsyncAnthropic",
            return_value=fake_client,
        ):
            out = await analyze_brief("silestone rosario")
        assert out["extraction_method"] == "regex_fallback"

    @pytest.mark.asyncio
    async def test_llm_malformed_json_falls_back(self):
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": "not a json at all"})()]
        })()
        fake_client = type("F", (), {})()
        fake_client.messages = type("M", (), {})()
        fake_client.messages.create = AsyncMock(return_value=mock_response)
        with patch(
            "app.modules.quote_engine.brief_analyzer.anthropic.AsyncAnthropic",
            return_value=fake_client,
        ):
            out = await analyze_brief("silestone rosario")
        assert out["extraction_method"] == "regex_fallback"

    @pytest.mark.asyncio
    async def test_llm_success_with_clean_extraction(self):
        """Happy path: LLM devuelve JSON limpio y se usa tal cual."""
        json_payload = (
            '{"client_name": "Erica Bernardi", "material": "Puraprima Onix White Mate", '
            '"localidad": "Rosario", "zocalos": "no", "colocacion": "yes", '
            '"work_types": ["cocina"], "isla_mentioned": true, "anafe_count": 2, '
            '"anafe_gas_y_electrico": true, "pileta_mentioned": true, '
            '"pileta_simple_doble": "doble", "es_edificio": false}'
        )
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": json_payload})()]
        })()
        fake_client = type("F", (), {})()
        fake_client.messages = type("M", (), {})()
        fake_client.messages.create = AsyncMock(return_value=mock_response)
        with patch(
            "app.modules.quote_engine.brief_analyzer.anthropic.AsyncAnthropic",
            return_value=fake_client,
        ):
            out = await analyze_brief("...")
        assert out["extraction_method"] == "llm"
        assert out["client_name"] == "Erica Bernardi"
        assert out["material"] == "Puraprima Onix White Mate"
        assert out["zocalos"] == "no"
        assert out["anafe_count"] == 2
        assert out["pileta_simple_doble"] == "doble"
