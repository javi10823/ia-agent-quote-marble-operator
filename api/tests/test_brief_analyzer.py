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

    # ── Sub-PR sprint-4/contacto-extraction-fix · phone + email ────────
    # Cierra deuda documentada desde PR #483 (sub-PR 9.3). Backend ahora
    # extrae phone y email del bloque "Contacto:" del brief o de las
    # palabras-ancla típicas. Filtra falsos positivos (IDs, DNIs, CUITs).

    def test_phone_with_tel_ancla(self):
        """'Tel: X' → phone extraído (limpio sin formato)."""
        out = _analyze_regex_fallback("Tel: 3464696027")
        assert out["phone"] == "3464696027"

    def test_phone_with_cel_ancla_formatted(self):
        """'Cel: (0346) 4-696027' → '03464696027' (sin formato)."""
        out = _analyze_regex_fallback("Cel: (0346) 4-696027")
        assert out["phone"] == "03464696027"

    def test_phone_ignores_naked_id_without_ancla(self):
        """ID del brief Micaela 'DA-1781136799652-KVZU' sin palabra-ancla
        → phone=null. Sin ancla no extraemos."""
        out = _analyze_regex_fallback("Order ID: DA-1781136799652-KVZU")
        assert out["phone"] is None

    def test_phone_ignores_naked_dni_without_ancla(self):
        """'DNI: 12345678' (sin 'Tel:') → phone=null."""
        out = _analyze_regex_fallback("DNI 12345678 cliente Juan")
        assert out["phone"] is None

    def test_email_extracted(self):
        """'Email: x@y.com' → email extraído."""
        out = _analyze_regex_fallback(
            "Cliente Marina Email: marina@example.com en Rosario"
        )
        assert out["email"] == "marina@example.com"

    def test_email_handles_compound_tld(self):
        """TLDs largos tipo .com.ar funcionan."""
        out = _analyze_regex_fallback("contacto@dangelo.com.ar")
        assert out["email"] == "contacto@dangelo.com.ar"

    def test_no_phone_no_email_both_null(self):
        """Brief sin Tel ni Email → ambos campos null."""
        out = _analyze_regex_fallback("Mesada 2x0.60 silestone en rosario")
        assert out["phone"] is None
        assert out["email"] is None

    def test_brief_micaela_e2e_phone_and_email(self):
        """Caso real del brief Micaela: 'Contacto: ... — Tel: ... —
        Email: ...'. Ambos extraídos."""
        brief = (
            "Lead completo\n"
            "Contacto: Micaela Volattire — Tel: 3464696027 — "
            "Email: micaelavolattire.1234@gmail.com\n"
            "Trabajo: Cocina"
        )
        out = _analyze_regex_fallback(brief)
        assert out["phone"] == "3464696027"
        assert out["email"] == "micaelavolattire.1234@gmail.com"

    def test_micaela_id_not_confused_with_phone(self):
        """Drift guard del brief Micaela real: el ID interno
        'DA-1781136799652-KVZU' aparece en el mismo brief que el tel
        legítimo. No debe confundirse — solo el que tiene 'Tel:' ancla."""
        brief = (
            "DA-1781136799652-KVZU\n"
            "Contacto: Micaela — Tel: 3464696027"
        )
        out = _analyze_regex_fallback(brief)
        assert out["phone"] == "3464696027"

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

    def test_frentin_regrueso_pulido_yes(self):
        # Bug 5 (PR #485) — schema ternary. Brief estructurado típico
        # tiene cada trabajo extra en su propia línea con "X: Sí".
        out = _analyze_regex_fallback(
            "Frentín: Sí\nRegrueso: Sí\nPulido: Sí"
        )
        assert out["frentin"] == "yes"
        assert out["regrueso"] == "yes"
        assert out["pulido"] == "yes"

    # ── Bug 5 · PR #485 · frentin/regrueso/pulido ternary ─────────────

    def test_frentin_brief_explicit_no(self):
        """Brief estructurado típico: 'Frentín: No'. Antes colapsaba a
        `frentin_mentioned=False` (igual que 'no mencionado') y el
        sistema perdía la decisión del operador. Ahora es `frentin='no'`
        explícito."""
        out = _analyze_regex_fallback("Frentín: No")
        assert out["frentin"] == "no"

    def test_regrueso_brief_explicit_no(self):
        out = _analyze_regex_fallback("Regrueso: No")
        assert out["regrueso"] == "no"

    def test_pulido_brief_explicit_si(self):
        out = _analyze_regex_fallback("Pulido: Sí")
        assert out["pulido"] == "yes"

    def test_sin_frentin_is_no(self):
        # Activación Issue follow-up PR #425. Antes "sin frentín"
        # daba `frentin_mentioned=True` y se documentaba como deuda.
        # Hoy ese formato es claramente "no".
        out = _analyze_regex_fallback("Mesada sin frentín, solo zócalo")
        assert out["frentin"] == "no"

    def test_frentin_not_mentioned_is_null(self):
        """Si el brief no menciona frentín en absoluto → null (distinto
        de 'no' explícito). Importante para el mapping a card: null
        es silencio, 'no' es decisión."""
        out = _analyze_regex_fallback("Mesada 2x0.60 en silestone")
        assert out["frentin"] is None
        assert out["regrueso"] is None
        assert out["pulido"] is None

    def test_brief_micaela_e2e_yes_no_extraction(self):
        """E2E del brief estructurado de Micaela Volattire — debe
        extraer frentin='no' Y regrueso='no' (ambos explícitos en
        el brief con 'X: No')."""
        brief = (
            "Lead completo. Cliente Micaela. Cocina mesada 1.40 × 0.55. "
            "Material Granito Gris Perla. Colocación: No. "
            "Pileta: compra en D'Angelo. "
            "Zócalo: Sí. Frentín: No. Regrueso: No. Ciudad: Casilda."
        )
        out = _analyze_regex_fallback(brief)
        assert out["frentin"] == "no"
        assert out["regrueso"] == "no"
        # Pulido no se menciona → silencio.
        assert out["pulido"] is None


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

    @pytest.mark.asyncio
    async def test_llm_call_uses_temperature_zero(self):
        """Bug 5 fix · PR #485 — drift guard. El LLM call DEBE usar
        temperature=0 para output determinístico. Sin este lock,
        Run1≠Run2 con mismo brief (causa raíz de variabilidad
        observada en briefs de Micaela)."""
        json_payload = '{"client_name": "X"}'
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
            await analyze_brief("any brief")
        # Asegurar que `temperature=0` se pasó al call.
        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert call_kwargs.get("temperature") == 0, (
            "LLM call DEBE usar temperature=0 para output determinístico. "
            "Si esto cambia, revisar lección #56 antes de mergear."
        )
