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

    # ───────────────────────────────────────────────────────
    # PR #387 — frentín + regrueso en verified_context
    # ───────────────────────────────────────────────────────
    #
    # Antes: `tramo.frentin` / `tramo.regrueso` vivían en el dual_read
    # pero no se inyectaban al system prompt. Claude podía omitirlos del
    # Paso 2. Ahora se emiten explícitos bajo `SECTOR: X` con el mismo
    # formato que los zócalos (el agente ya sabe parsear ese formato).

    def _tramo_with_field(self, field: str, items: list) -> dict:
        """Helper: construye un dual_read con un tramo que tiene `field`
        (frentin/regrueso) seteado."""
        dr = _build_single_result(_sample_result(), "SOLO_SONNET")
        dr["sectores"][0]["tramos"][0][field] = items
        return dr

    def test_emits_frentin_under_sector(self):
        dr = self._tramo_with_field(
            "frentin",
            [{"lado": "frente", "ml": 6.22, "alto_m": 0.05}],
        )
        ctx = build_verified_context(dr)
        assert "Frentín frente" in ctx
        assert "6.22ml" in ctx
        assert "0.05m" in ctx

    def test_emits_regrueso_under_sector(self):
        dr = self._tramo_with_field(
            "regrueso",
            [{"lado": "frente", "ml": 3.5, "alto_m": 0.03}],
        )
        ctx = build_verified_context(dr)
        assert "Regrueso frente" in ctx
        assert "3.5ml" in ctx

    def test_frentin_without_alto_renders_only_ml(self):
        """Si no hay alto_m, mostrar solo los ml — no inventar multiplicación."""
        dr = self._tramo_with_field(
            "frentin",
            [{"lado": "frente", "ml": 2.40}],
        )
        ctx = build_verified_context(dr)
        assert "Frentín frente: 2.4ml" in ctx
        assert "0.4ml × " not in ctx  # no debería haber "× <algo>m"

    def test_empty_frentin_list_noop(self):
        """Tramo con `frentin: []` no emite nada. El caso más común hoy."""
        dr = self._tramo_with_field("frentin", [])
        ctx = build_verified_context(dr)
        assert "Frentín" not in ctx
        assert "Regrueso" not in ctx

    def test_zero_ml_items_skipped(self):
        """Items con `ml=0` se ignoran — mismo criterio que zócalos
        (operador los descartó intencionalmente)."""
        dr = self._tramo_with_field(
            "frentin",
            [{"lado": "frente", "ml": 0, "alto_m": 0.05}],
        )
        ctx = build_verified_context(dr)
        assert "Frentín" not in ctx

    def test_multiple_items_all_emitted(self):
        dr = self._tramo_with_field(
            "frentin",
            [
                {"lado": "frente", "ml": 2.50, "alto_m": 0.05},
                {"lado": "lateral", "ml": 0.60, "alto_m": 0.05},
            ],
        )
        ctx = build_verified_context(dr)
        assert "Frentín frente" in ctx
        assert "Frentín lateral" in ctx

    def test_frentin_and_regrueso_coexist(self):
        """Un tramo puede tener ambos — deben salir los dos."""
        dr = _build_single_result(_sample_result(), "SOLO_SONNET")
        dr["sectores"][0]["tramos"][0]["frentin"] = [
            {"lado": "frente", "ml": 2.00, "alto_m": 0.05},
        ]
        dr["sectores"][0]["tramos"][0]["regrueso"] = [
            {"lado": "frente", "ml": 2.00, "alto_m": 0.03},
        ]
        ctx = build_verified_context(dr)
        assert "Frentín frente" in ctx
        assert "Regrueso frente" in ctx

    def test_malformed_items_ignored(self):
        """Si un item no es dict o no tiene ml → skip sin explotar."""
        dr = self._tramo_with_field(
            "frentin",
            [None, "not a dict", {"lado": "frente", "ml": 2.0, "alto_m": 0.05}],
        )
        ctx = build_verified_context(dr)
        # El único item válido se emite
        assert ctx.count("Frentín") == 1
        assert "Frentín frente" in ctx


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


# ═══════════════════════════════════════════════════════
# PR #374 — commercial_attrs + wording authority
# ═══════════════════════════════════════════════════════

from app.modules.quote_engine.dual_reader import (  # noqa: E402
    build_commercial_attrs,
    _source_wording,
)


class TestSourceWording:
    """Regla central: 'confirmado' SOLO si source=operator_answer."""

    def test_operator_answer_is_confirmado(self):
        assert _source_wording("operator_answer") == "confirmado por operador"

    def test_operator_alias(self):
        assert _source_wording("operator") == "confirmado por operador"

    def test_brief_is_del_brief_not_confirmado(self):
        wording = _source_wording("brief")
        assert "confirmado" not in wording
        assert "brief" in wording

    def test_dual_read_is_detectado_not_confirmado(self):
        wording = _source_wording("dual_read")
        assert "confirmado" not in wording
        assert "detectado" in wording

    def test_default_or_none_is_revisar(self):
        assert "revisar" in _source_wording("default")
        assert "revisar" in _source_wording(None)
        assert "revisar" in _source_wording("unknown_source")


class TestBuildCommercialAttrsBernardi:
    """Precedencia canónica:
        operator_answer > brief > dual_read > default

    Bernardi en el log real: brief sin mención de anafe, dual_read
    detectó 1 anafe (cooktop_groups=1), pero el resumen comercial decía
    '2 anafes confirmados'. Fix: inyectar anafe_count estructurado con
    source=dual_read al verified_context.
    """

    def _bernardi_dual(self) -> dict:
        return {
            "sectores": [
                {
                    "id": "cocina", "tipo": "cocina",
                    "tramos": [{
                        "id": "t1", "descripcion": "Mesada",
                        "largo_m": {"valor": 2.05},
                        "ancho_m": {"valor": 0.60},
                        "m2": {"valor": 1.23},
                        "zocalos": [], "features": {
                            "cooktop_groups": 1, "sink_simple": True,
                            "sink_double": False, "has_pileta": True,
                        },
                    }],
                },
                {
                    "id": "isla", "tipo": "isla",
                    "tramos": [{
                        "id": "t2", "descripcion": "Isla",
                        "largo_m": {"valor": 1.60},
                        "ancho_m": {"valor": 0.60},
                        "m2": {"valor": 0.96},
                        "zocalos": [], "features": {},
                    }],
                },
            ],
        }

    def test_anafe_from_dual_read_when_brief_silent(self):
        analysis = {"anafe_count": None}
        attrs = build_commercial_attrs(
            analysis=analysis, dual_result=self._bernardi_dual(),
        )
        assert attrs["anafe_count"] == {"value": 1, "source": "dual_read"}

    def test_pileta_from_dual_read_when_brief_silent(self):
        analysis = {"pileta_simple_doble": None, "pileta_mentioned": True}
        attrs = build_commercial_attrs(
            analysis=analysis, dual_result=self._bernardi_dual(),
        )
        assert attrs["pileta_simple_doble"] == {"value": "simple", "source": "dual_read"}

    def test_operator_answer_overrides_brief_and_dual_read(self):
        """Precedencia máxima: si el operador respondió, ganamos por WO.
        Caso Javi: 'es 1 anafe y 1 pileta doble' — brief dice 'simple',
        dual_read dice 'simple', operador cambia a 'doble'."""
        analysis = {"pileta_simple_doble": "simple", "pileta_mentioned": True}
        attrs = build_commercial_attrs(
            analysis=analysis,
            dual_result=self._bernardi_dual(),
            operator_answers=[{"id": "pileta_simple_doble", "value": "doble"}],
        )
        assert attrs["pileta_simple_doble"] == {
            "value": "doble", "source": "operator_answer",
        }

    def test_operator_anafe_override_to_1_stops_dual_read_2(self):
        """Si el LLM antes contaba 2 por la imagen y operador respondió
        anafe_count=1, el commercial_attrs debe usar 1 con
        source=operator_answer → en el verified_context se imprime como
        'confirmado por operador'."""
        analysis = {"anafe_count": None}
        dual = self._bernardi_dual()
        # forzar cooktop_groups=2 (simulando el error del VLM de imagen)
        dual["sectores"][0]["tramos"][0]["features"]["cooktop_groups"] = 2
        attrs = build_commercial_attrs(
            analysis=analysis, dual_result=dual,
            operator_answers=[{"id": "anafe_count", "value": "1"}],
        )
        assert attrs["anafe_count"] == {"value": 1, "source": "operator_answer"}

    def test_divergence_surfaces_when_brief_contradicts_dual_read(self):
        """Brief dice '2 anafes' pero dual_read dice 1 → divergence se
        surface como array en el output para que el LLM la muestre como
        'revisar', no la esconda."""
        analysis = {"anafe_count": 2, "anafe_gas_y_electrico": True}
        attrs = build_commercial_attrs(
            analysis=analysis, dual_result=self._bernardi_dual(),
        )
        # Brief gana por precedencia
        assert attrs["anafe_count"] == {"value": 2, "source": "brief"}
        # Y la divergencia queda registrada
        divs = attrs.get("divergences") or []
        assert any(d["field"] == "anafe_count" for d in divs)
        anafe_div = next(d for d in divs if d["field"] == "anafe_count")
        assert anafe_div["brief_value"] == 2
        assert anafe_div["dual_read_value"] == 1

    def test_operator_answers_passed_through_for_llm_visibility(self):
        """Respuestas del operador a pending_questions (ej: profundidad
        isla, alzada) pasan en bloque al verified_context para que el LLM
        las vea como 'confirmadas'."""
        attrs = build_commercial_attrs(
            analysis={}, dual_result=self._bernardi_dual(),
            operator_answers=[
                {"id": "isla_profundidad", "value": "0.60", "label": "0.60 m"},
                {"id": "isla_patas", "value": "frontal_y_laterales",
                 "label": "Sí — frontal + ambos laterales"},
            ],
        )
        assert len(attrs["operator_answers"]) == 2
        ids = {a["id"] for a in attrs["operator_answers"]}
        assert ids == {"isla_profundidad", "isla_patas"}


class TestVerifiedContextWithCommercialAttrs:
    """El texto inyectado al system prompt debe:
    1. Incluir el bloque de atributos comerciales cuando hay commercial_attrs.
    2. Usar wording escalonado según source (no "confirmado" para todo).
    3. Incluir divergencias visibles.
    """

    def _min_confirmed(self) -> dict:
        return {
            "sectores": [{
                "id": "cocina",
                "tramos": [{
                    "id": "t1", "descripcion": "Mesada",
                    "largo_m": {"valor": 2.05},
                    "ancho_m": {"valor": 0.60},
                    "m2": {"valor": 1.23},
                    "zocalos": [],
                }],
            }],
        }

    def test_without_commercial_attrs_is_backwards_compatible(self):
        ctx = build_verified_context(self._min_confirmed())
        # Sigue teniendo el header clásico, no rompe callers legacy.
        assert "VERIFICADAS" in ctx
        # Pero NO tiene el bloque nuevo.
        assert "ATRIBUTOS COMERCIALES" not in ctx

    def test_with_dual_read_source_uses_detectado_not_confirmado(self):
        """Bernardi: anafe source=dual_read → wording 'detectado en plano'."""
        ctx = build_verified_context(
            self._min_confirmed(),
            commercial_attrs={"anafe_count": {"value": 1, "source": "dual_read"}},
        )
        assert "ATRIBUTOS COMERCIALES" in ctx
        assert "anafe_count: 1" in ctx
        assert "source=dual_read" in ctx
        assert "detectado en plano" in ctx
        # La palabra "confirmado" NO debe aparecer en el bloque comercial
        # asociada al anafe.
        commercial_block = ctx.split("ATRIBUTOS COMERCIALES")[1]
        # Permitido solo como parte de la instrucción "confirmado SOLO si..."
        # pero no aplicado al campo.
        assert "anafe_count: 1" in commercial_block
        anafe_line = next(
            line for line in commercial_block.splitlines() if "anafe_count: 1" in line
        )
        assert "detectado" in anafe_line and "confirmado" not in anafe_line

    def test_with_operator_answer_source_uses_confirmado(self):
        """Si el operador respondió, el wording SÍ es 'confirmado'."""
        ctx = build_verified_context(
            self._min_confirmed(),
            commercial_attrs={"anafe_count": {"value": 1, "source": "operator_answer"}},
        )
        anafe_line = next(
            line for line in ctx.splitlines() if "anafe_count: 1" in line
        )
        assert "confirmado por operador" in anafe_line

    def test_divergences_shown_with_revisar_flag(self):
        ctx = build_verified_context(
            self._min_confirmed(),
            commercial_attrs={
                "anafe_count": {"value": 2, "source": "brief"},
                "divergences": [{
                    "field": "anafe_count",
                    "brief_value": 2,
                    "dual_read_value": 1,
                }],
            },
        )
        assert "DIVERGENCIAS" in ctx
        assert "brief=2 vs plano=1" in ctx
        assert "revisar" in ctx.lower()

    def test_imperative_instructions_present(self):
        """El bloque comercial debe ser imperativo: decir al LLM que NO
        re-cuente desde la imagen y cuáles son las reglas de wording."""
        ctx = build_verified_context(
            self._min_confirmed(),
            commercial_attrs={"anafe_count": {"value": 1, "source": "dual_read"}},
        )
        assert "USÁ SOLO" in ctx or "usá solo" in ctx.lower()
        assert "NO re-cuentes" in ctx or "no re-cuentes" in ctx.lower()
        assert "operator_answer" in ctx  # regla de wording

    def test_operator_answers_listed_as_confirmed(self):
        ctx = build_verified_context(
            self._min_confirmed(),
            commercial_attrs={
                "operator_answers": [
                    {"id": "isla_profundidad", "value": "0.60", "label": "0.60 m"},
                ],
            },
        )
        assert "operator_answer" in ctx
        assert "CONFIRMADAS" in ctx or "confirmadas" in ctx.lower()
        assert "isla_profundidad" in ctx
        assert "0.60" in ctx


class TestBernardiEndToEndTruthfulness:
    """Caso Bernardi completo: el verified_context inyectado al LLM debe
    tener anafe=1 (no 2) con wording de no-certeza, aunque la imagen
    muestre dos cooktops visibles. El LLM no debería generar '2 anafes
    confirmados' porque el prompt le dice explícitamente:
    1. USÁ SOLO estos valores (no re-cuentes).
    2. Wording 'confirmado' SOLO si source=operator_answer.
    """

    def test_bernardi_verified_context_stops_double_count(self):
        confirmed_measures = {
            "sectores": [{
                "id": "cocina",
                "tramos": [{
                    "id": "t1", "descripcion": "Mesada con pileta",
                    "largo_m": {"valor": 2.05},
                    "ancho_m": {"valor": 0.60},
                    "m2": {"valor": 1.23},
                    "zocalos": [],
                }],
            }],
        }
        attrs = build_commercial_attrs(
            analysis={"anafe_count": None,
                      "pileta_simple_doble": None, "pileta_mentioned": True},
            dual_result={"sectores": [{
                "id": "cocina", "tipo": "cocina",
                "tramos": [{
                    "id": "t1", "descripcion": "Mesada",
                    "features": {"cooktop_groups": 1, "sink_simple": True,
                                 "has_pileta": True, "sink_double": False},
                }],
            }]},
            operator_answers=[],
        )
        ctx = build_verified_context(confirmed_measures, commercial_attrs=attrs)

        # El anafe debe aparecer como 1 detectado en plano (NO "2 anafes").
        assert "anafe_count: 1" in ctx
        assert "source=dual_read" in ctx
        # El LLM ve explícitamente la regla anti-overstatement.
        assert "NO re-cuentes desde la imagen" in ctx or "no re-cuentes desde la imagen" in ctx.lower()

    def test_bernardi_with_operator_correction_pileta_doble(self):
        """El operador responde 'pileta doble' en las preguntas bloqueantes.
        Eso debe ganar incluso si dual_read dijo 'simple'."""
        attrs = build_commercial_attrs(
            analysis={"pileta_simple_doble": None, "pileta_mentioned": True},
            dual_result={"sectores": [{
                "id": "cocina", "tipo": "cocina",
                "tramos": [{
                    "features": {"sink_simple": True, "sink_double": False,
                                 "has_pileta": True},
                }],
            }]},
            operator_answers=[{"id": "pileta_simple_doble", "value": "doble"}],
        )
        ctx = build_verified_context({"sectores": []}, commercial_attrs=attrs)
        assert "pileta_simple_doble: doble" in ctx
        assert "source=operator_answer" in ctx
        # Wording escalonado: operator_answer → "confirmado por operador"
        pileta_line = next(
            line for line in ctx.splitlines() if "pileta_simple_doble: doble" in line
        )
        assert "confirmado por operador" in pileta_line


# ═══════════════════════════════════════════════════════
# PR #377 — build_derived_isla_pieces (bug Bernardi: laterales 0.90×0.90)
# ═══════════════════════════════════════════════════════

from app.modules.quote_engine.dual_reader import (  # noqa: E402
    build_derived_isla_pieces,
)


def _bernardi_measurements(largo_isla=1.60):
    """Medidas verificadas típicas de Bernardi: cocina con 2 mesadas
    + 1 sector isla con largo confirmado por el operador."""
    return {
        "sectores": [
            {
                "id": "cocina", "tipo": "cocina",
                "tramos": [
                    {"id": "t1", "descripcion": "Mesada con pileta",
                     "largo_m": {"valor": 2.05}, "ancho_m": {"valor": 0.60},
                     "m2": {"valor": 1.23}},
                    {"id": "t2", "descripcion": "Mesada 2",
                     "largo_m": {"valor": 2.95}, "ancho_m": {"valor": 0.60},
                     "m2": {"valor": 1.77}},
                ],
            },
            {
                "id": "isla", "tipo": "isla",
                "tramos": [
                    {"id": "t3", "descripcion": "Tapa isla",
                     "largo_m": {"valor": largo_isla},
                     "ancho_m": {"valor": 0.60},
                     "m2": {"valor": round(largo_isla * 0.60, 2)}},
                ],
            },
        ],
    }


class TestBuildDerivedIslaPiecesBernardi:
    """Caso central del bug: operador confirmó patas solo_laterales,
    alto 0.90, prof isla 0.60. El LLM en Paso 1 emitía
        'Pata lateral isla izq | 0.90 × 0.90'
    cuando debería ser
        'Pata lateral isla izq | 0.60 × 0.90'.

    El helper determinístico resuelve esto calculando en backend:
    pata lateral = prof_isla × alto_patas.
    """

    def test_bernardi_solo_laterales_exact(self):
        """Caso EXACTO del bug — laterales deben salir 0.60 × 0.90."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_laterales"},
                {"id": "isla_patas_alto", "value": "0.90"},
                {"id": "isla_profundidad", "value": "0.60"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert warnings == []
        assert len(pieces) == 2
        izq = next(p for p in pieces if "izq" in p["description"].lower())
        der = next(p for p in pieces if "der" in p["description"].lower())
        assert izq["largo"] == 0.60 and izq["prof"] == 0.90
        assert der["largo"] == 0.60 and der["prof"] == 0.90
        assert izq["m2"] == 0.54
        assert der["m2"] == 0.54
        # Nunca 0.90×0.90
        assert not any(p["largo"] == 0.90 and p["prof"] == 0.90 for p in pieces)

    def test_frontal_y_ambos_laterales_emits_three(self):
        """Frontal usa largo_isla; laterales usan prof_isla."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "frontal_y_ambos_laterales"},
                {"id": "isla_patas_alto", "value": "0.90"},
                {"id": "isla_profundidad", "value": "0.60"},
            ],
            verified_measurements=_bernardi_measurements(largo_isla=1.60),
        )
        assert warnings == []
        assert len(pieces) == 3
        frontal = next(p for p in pieces if "frontal" in p["description"].lower())
        # Frontal = largo_isla × alto
        assert frontal["largo"] == 1.60 and frontal["prof"] == 0.90
        assert frontal["m2"] == 1.44
        # Laterales = prof_isla × alto
        laterales = [p for p in pieces if "lateral" in p["description"].lower()]
        assert len(laterales) == 2
        for lat in laterales:
            assert lat["largo"] == 0.60 and lat["prof"] == 0.90
            assert lat["m2"] == 0.54

    def test_solo_frontal_emits_one(self):
        pieces, _ = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_frontal"},
                {"id": "isla_patas_alto", "value": "0.90"},
                # prof no es necesaria si solo hay frontal
            ],
            verified_measurements=_bernardi_measurements(largo_isla=2.40),
        )
        assert len(pieces) == 1
        assert pieces[0]["description"].lower().startswith("pata frontal")
        assert pieces[0]["largo"] == 2.40
        assert pieces[0]["prof"] == 0.90

    def test_solo_frontal_does_not_require_profundidad(self):
        """Si solo hay frontal, la profundidad de la isla no se usa →
        debe poder emitir la pieza sin isla_profundidad."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_frontal"},
                {"id": "isla_patas_alto", "value": "0.90"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert warnings == []
        assert len(pieces) == 1

    def test_patas_no_emits_nothing(self):
        """'No lleva patas' → 0 piezas, sin warnings (es una respuesta
        válida, no una omisión)."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "no"},
                {"id": "isla_patas_alto", "value": "0.90"},
                {"id": "isla_profundidad", "value": "0.60"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert pieces == []
        assert warnings == []

    def test_missing_alto_emits_warning_no_pieces(self):
        """Falta isla_patas_alto → no emitir, warning claro."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "frontal_y_ambos_laterales"},
                {"id": "isla_profundidad", "value": "0.60"},
                # isla_patas_alto ausente
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert pieces == []
        assert len(warnings) == 1
        assert "isla_patas_alto" in warnings[0]

    def test_missing_prof_emits_warning_only_when_laterales(self):
        """Falta isla_profundidad pero solo hay frontal → NO es warning
        (no se usa la prof). Falta prof + hay laterales → SÍ warning."""
        # Solo frontal → sin warning, se emite la pieza
        pieces_ok, warns_ok = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_frontal"},
                {"id": "isla_patas_alto", "value": "0.90"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert len(pieces_ok) == 1
        assert warns_ok == []

        # Con laterales y sin prof → no emitir, warning
        pieces_miss, warns_miss = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_laterales"},
                {"id": "isla_patas_alto", "value": "0.90"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert pieces_miss == []
        assert len(warns_miss) == 1
        assert "isla_profundidad" in warns_miss[0]

    def test_missing_largo_isla_warning_only_when_frontal(self):
        """Si no hay sector isla en las medidas pero el operador pidió
        frontal → warning. Si pidió solo laterales → sin warning (frontal
        no se usa)."""
        measurements_no_isla = {"sectores": [{"tipo": "cocina", "tramos": []}]}

        # Frontal sin largo_isla → warning
        _, warns = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "frontal_y_ambos_laterales"},
                {"id": "isla_patas_alto", "value": "0.90"},
                {"id": "isla_profundidad", "value": "0.60"},
            ],
            verified_measurements=measurements_no_isla,
        )
        assert len(warns) == 1
        assert "largo_isla" in warns[0]

        # Solo laterales sin largo_isla → OK, no lo necesita
        pieces_lat, warns_lat = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_laterales"},
                {"id": "isla_patas_alto", "value": "0.90"},
                {"id": "isla_profundidad", "value": "0.60"},
            ],
            verified_measurements=measurements_no_isla,
        )
        assert len(pieces_lat) == 2
        assert warns_lat == []

    def test_custom_value_does_not_invent_pieces(self):
        """isla_patas='custom' — el LLM debe preguntar al operador.
        Helper devuelve warning, NO inventa piezas."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "custom",
                 "detail": "solo una pata detrás"},
                {"id": "isla_patas_alto", "value": "0.90"},
                {"id": "isla_profundidad", "value": "0.60"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert pieces == []
        assert len(warnings) == 1
        assert "custom" in warnings[0]

    def test_empty_inputs_return_empty(self):
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=None, verified_measurements=None,
        )
        assert pieces == []
        assert warnings == []
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[], verified_measurements={},
        )
        assert pieces == []
        assert warnings == []

    def test_no_isla_patas_answer_returns_empty_no_warning(self):
        """Operador no respondió la pregunta de patas (ej: no hay isla).
        Sin warnings ni piezas — no es una omisión real."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "alzada", "value": "no"},
                {"id": "isla_patas_alto", "value": "0.90"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert pieces == []
        assert warnings == []

    def test_custom_detail_parseable_alto(self):
        """isla_patas_alto='custom' con detail='0.75' → se parsea."""
        pieces, warnings = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_frontal"},
                {"id": "isla_patas_alto", "value": "custom", "detail": "0.75"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert warnings == []
        assert len(pieces) == 1
        assert pieces[0]["prof"] == 0.75

    def test_comma_decimal_accepted(self):
        """El operador puede ingresar '0,75' (coma) en el detail."""
        pieces, _ = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_frontal"},
                {"id": "isla_patas_alto", "value": "custom", "detail": "0,75 m"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert len(pieces) == 1
        assert pieces[0]["prof"] == 0.75

    def test_pieces_include_source_marker(self):
        """Cada pieza derivada debe marcarse con source para auditoría."""
        pieces, _ = build_derived_isla_pieces(
            operator_answers=[
                {"id": "isla_patas", "value": "solo_frontal"},
                {"id": "isla_patas_alto", "value": "0.90"},
            ],
            verified_measurements=_bernardi_measurements(),
        )
        assert all(p.get("source") == "derived_from_operator_answers" for p in pieces)


class TestVerifiedContextEmitsDerivedPiecesBlock:
    """El bloque 'PIEZAS DERIVADAS' debe aparecer en el texto del
    verified_context cuando hay piezas, con instrucciones imperativas
    de copiar literal. Y debe estar SEPARADO del bloque de atributos."""

    def _min_confirmed(self) -> dict:
        return {"sectores": [{"id": "cocina", "tramos": [{
            "id": "t1", "descripcion": "Mesada",
            "largo_m": {"valor": 2.0}, "ancho_m": {"valor": 0.60},
            "m2": {"valor": 1.20}, "zocalos": [],
        }]}]}

    def test_no_derived_block_when_empty(self):
        ctx = build_verified_context(self._min_confirmed(), derived_pieces=None)
        assert "PIEZAS DERIVADAS" not in ctx

    def test_derived_block_present_with_pieces(self):
        pieces = [
            {"description": "Pata lateral isla izq", "largo": 0.60, "prof": 0.90, "m2": 0.54},
            {"description": "Pata lateral isla der", "largo": 0.60, "prof": 0.90, "m2": 0.54},
        ]
        ctx = build_verified_context(self._min_confirmed(), derived_pieces=pieces)
        assert "PIEZAS DERIVADAS" in ctx
        assert "COPIALAS LITERAL" in ctx.upper() or "copialas literal" in ctx.lower()
        assert "NO recalcular" in ctx
        # Las dimensiones deben aparecer exactamente
        assert "0.6 × 0.9 = 0.54 m²" in ctx

    def test_separated_from_commercial_attrs_block(self):
        pieces = [
            {"description": "Pata frontal isla", "largo": 1.60, "prof": 0.90, "m2": 1.44},
        ]
        ctx = build_verified_context(
            self._min_confirmed(),
            commercial_attrs={"anafe_count": {"value": 1, "source": "dual_read"}},
            derived_pieces=pieces,
        )
        # Ambos bloques presentes
        assert "ATRIBUTOS COMERCIALES" in ctx
        assert "PIEZAS DERIVADAS" in ctx
        # Y separados: el de derivadas aparece después del de atributos
        # (orden estable para que el LLM los lea en secuencia natural:
        #  medidas → atributos → piezas derivadas).
        assert ctx.index("ATRIBUTOS COMERCIALES") < ctx.index("PIEZAS DERIVADAS")
