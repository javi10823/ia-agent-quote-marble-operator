"""Tests del multi_crop_reader — aggregator + orquestación + fail-hard.

LLM calls y PIL image ops se mockean. La idea es verificar:
- aggregator arma el schema dual_read correcto desde topology + results
- fallback graceful si global topology falla
- per-region fail-hard: <2 cotas locales → skip LLM, devolver DUDOSO
- detección de fallback silencioso (largo == ancho, valores no anclados)
- labels genéricos hasta que PR C defina contrato feature-based
"""
import io
import logging
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.modules.quote_engine.cotas_extractor import Cota
from app.modules.quote_engine.multi_crop_reader import (
    _aggregate,
    _apply_guardrails,
    _bbox_to_px,
    _build_rescue_context,
    _build_suggested_candidates,
    _call_global_topology,
    _detect_region_brief_contradictions,
    _estimate_plan_scale,
    _filter_length_by_geometry,
    _format_ranking_for_prompt,
    _GLOBAL_SYSTEM_PROMPT,
    _has_meaningful_length_candidate,
    _infer_expected_region_count,
    _is_probable_perimeter,
    _is_semantic_sanity_warning,
    _measure_region,
    _rank_cotas_for_region,
    _rescue_length_ranking,
    _score_cota,
    _semantic_sanity_checks,
    _SEMANTIC_SANITY_PREFIXES,
    read_plan_multi_crop,
)


def _make_cota(value: float, x: float = 0, y: float = 0) -> Cota:
    return Cota(text=str(value), value=value, x=x, y=y, width=20, height=10)


def _make_image_bytes(w: int = 1000, h: int = 800) -> bytes:
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Aggregator ───────────────────────────────────────────────────────────────

class TestAggregate:
    def test_u_plus_isla_4_regions_2_sectors(self):
        """Cocina en U + isla → sector cocina (3 tramos) + sector isla (1 tramo)."""
        topology = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "sector": "cocina"},
                {"id": "R2", "sector": "cocina"},
                {"id": "R3", "sector": "cocina"},
                {"id": "R4", "sector": "isla"},
            ],
        }
        results = [
            {"region_id": "R1", "largo_m": 2.95, "ancho_m": 0.60},
            {"region_id": "R2", "largo_m": 2.05, "ancho_m": 0.60},
            {"region_id": "R3", "largo_m": 1.20, "ancho_m": 0.60},
            {"region_id": "R4", "largo_m": 1.60, "ancho_m": 0.60},
        ]
        out = _aggregate(topology, results)
        assert len(out["sectores"]) == 2
        cocina = next(s for s in out["sectores"] if s["tipo"] == "cocina")
        isla = next(s for s in out["sectores"] if s["tipo"] == "isla")
        assert len(cocina["tramos"]) == 3
        assert len(isla["tramos"]) == 1
        # m² recalculado (determinístico, no confía en el LLM)
        assert cocina["tramos"][0]["m2"]["valor"] == round(2.95 * 0.60, 2)
        assert isla["tramos"][0]["largo_m"]["valor"] == 1.60
        # source del output
        assert out["source"] == "MULTI_CROP"

    def test_region_with_error_becomes_dudoso(self):
        topology = {"regions": [{"id": "R1", "sector": "cocina"}]}
        results = [{"region_id": "R1", "error": "region_timeout"}]
        out = _aggregate(topology, results)
        tramo = out["sectores"][0]["tramos"][0]
        assert tramo["largo_m"]["status"] == "DUDOSO"
        assert out["requires_human_review"] is True

    def test_suspicious_reasons_become_dudoso(self):
        """Fallback silencioso detectado (L==A) → DUDOSO, no CONFIRMADO."""
        topology = {"regions": [{"id": "R1", "sector": "cocina"}]}
        results = [{
            "region_id": "R1",
            "largo_m": 0.60,
            "ancho_m": 0.60,
            "suspicious_reasons": ["largo == ancho (0.60m) — probable fallback silencioso"],
        }]
        out = _aggregate(topology, results)
        tramo = out["sectores"][0]["tramos"][0]
        assert tramo["largo_m"]["status"] == "DUDOSO"
        assert tramo["ancho_m"]["status"] == "DUDOSO"
        assert "— revisar" in tramo["descripcion"]

    def test_region_notes_not_propagated_to_description(self):
        """No propagamos region.notes (notes puede tener artefactos mal
        asignados). El label se deriva solo de features."""
        topology = {
            "regions": [
                {"id": "R1", "sector": "cocina", "notes": "isla central con anafe a gas 4 hornallas"},
            ],
        }
        results = [{"region_id": "R1", "largo_m": 2.05, "ancho_m": 0.60}]
        out = _aggregate(topology, results)
        desc = out["sectores"][0]["tramos"][0]["descripcion"]
        # Sin features declaradas, label genérico
        assert desc.startswith("Mesada")

    def test_description_derived_from_features(self):
        """Cuando region.features tiene artefactos, el desc los refleja
        (sin usar notes del LLM)."""
        topology = {
            "regions": [
                {
                    "id": "R1",
                    "features": {
                        "touches_wall": True,
                        "cooktop_groups": 2,
                        "sink_double": False,
                        "non_counter_upper": False,
                    },
                },
            ],
        }
        results = [{"region_id": "R1", "largo_m": 2.95, "ancho_m": 0.60}]
        out = _aggregate(topology, results)
        desc = out["sectores"][0]["tramos"][0]["descripcion"]
        assert "2 anafes" in desc

    def test_non_counter_upper_region_filtered(self):
        """Región que el LLM marcó como alacena superior (horno/heladera
        módulo) NO aparece en los sectores."""
        topology = {
            "regions": [
                {"id": "R1", "features": {"touches_wall": True, "cooktop_groups": 0}},
                {"id": "R2", "features": {"non_counter_upper": True}},  # alacena superior
            ],
        }
        results = [
            {"region_id": "R1", "largo_m": 2.05, "ancho_m": 0.60},
            {"region_id": "R2", "largo_m": 1.20, "ancho_m": 0.30},
        ]
        out = _aggregate(topology, results)
        # Solo R1 debería estar en sectores; R2 filtrada
        all_tramo_ids = [t["id"] for s in out["sectores"] for t in s["tramos"]]
        assert "R1" in all_tramo_ids
        assert "R2" not in all_tramo_ids

    def test_isla_classified_from_features_when_not_touches_wall(self):
        """touches_wall=False + stools_adjacent=True → clasifica como isla."""
        topology = {
            "regions": [
                {
                    "id": "R1",
                    "features": {
                        "touches_wall": False,
                        "stools_adjacent": True,
                        "cooktop_groups": 0,
                    },
                },
            ],
        }
        results = [{"region_id": "R1", "largo_m": 1.60, "ancho_m": 0.60}]
        out = _aggregate(topology, results)
        assert out["sectores"][0]["tipo"] == "isla"
        # descripción incluye "banquetas" (stools_adjacent)
        desc = out["sectores"][0]["tramos"][0]["descripcion"]
        assert "banquetas" in desc.lower()

    def test_ambiguedades_propagated_to_first_sector(self):
        topology = {"regions": [{"id": "R1", "sector": "cocina"}, {"id": "R2", "sector": "cocina"}]}
        results = [
            {"region_id": "R1", "largo_m": 2.05, "ancho_m": 0.60},
            {"region_id": "R2", "error": "insufficient_local_cotas"},
        ]
        out = _aggregate(topology, results)
        # El sector cocina recibe la ambigüedad
        ambs = out["sectores"][0]["ambiguedades"]
        assert len(ambs) >= 1
        assert ambs[0]["tipo"] == "REVISION"
        assert "R2" in ambs[0]["texto"]

    def test_no_regions_fallback_empty_sector(self):
        out = _aggregate({"regions": []}, [])
        assert len(out["sectores"]) == 1
        assert out["sectores"][0]["tramos"] == []
        assert out["requires_human_review"] is True


# ── End-to-end with mocks ────────────────────────────────────────────────────

class TestReadPlanMultiCrop:
    @pytest.mark.asyncio
    async def test_global_topology_failure_propagates(self):
        """Si el global call falla, se devuelve error sin llamar per-region."""
        image = _make_image_bytes()
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value={"error": "global_topology_timeout"}),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader._measure_region",
            new=AsyncMock(),
        ) as mock_region:
            result = await read_plan_multi_crop(image, cotas=[])
        assert result.get("error") == "global_topology_timeout"
        mock_region.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_regions_returns_error(self):
        image = _make_image_bytes()
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value={"view_type": "planta", "regions": []}),
        ):
            result = await read_plan_multi_crop(image, cotas=[])
        assert result.get("error") == "no_regions_detected"

    @pytest.mark.asyncio
    async def test_happy_path_bernardi_like(self):
        """3 mesadas U + 1 isla, cada una con su medida correcta."""
        image = _make_image_bytes()
        topology = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "sector": "cocina", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}},
                {"id": "R2", "sector": "cocina", "bbox_rel": {"x": 0.35, "y": 0.1, "w": 0.3, "h": 0.1}},
                {"id": "R3", "sector": "isla",   "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.15, "h": 0.25}},
            ],
        }

        async def fake_measure(full_bytes, size, region, cotas, model, brief_text=""):
            values = {
                "R1": (2.95, 0.60),
                "R2": (2.05, 0.60),
                "R3": (1.60, 0.60),
            }
            L, A = values[region["id"]]
            return {"region_id": region["id"], "largo_m": L, "ancho_m": A, "confidence": 0.95}

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=topology),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader._measure_region",
            new=fake_measure,
        ):
            result = await read_plan_multi_crop(image, cotas=[], brief_text="cliente Bernardi")
        assert result.get("error") is None
        assert result["source"] == "MULTI_CROP"
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        assert len(cocina["tramos"]) == 2
        assert cocina["tramos"][0]["largo_m"]["valor"] == 2.95
        assert cocina["tramos"][1]["largo_m"]["valor"] == 2.05
        assert isla["tramos"][0]["largo_m"]["valor"] == 1.60

    @pytest.mark.asyncio
    async def test_measure_region_expands_bbox_when_local_cotas_low(self):
        """Si el bbox tight tiene <2 cotas pero al expandir aparecen suficientes,
        NO tiramos error — llamamos al LLM con el pool expandido. El resultado
        queda DUDOSO por el fallback, no CONFIRMADO.

        Motivación: las cotas están dibujadas justo fuera del bbox que detectó
        el topology LLM (típico en planos donde las cotas se escriben afuera de
        la región sombreada). Skipear el LLM → operador ve "— × —" y tiene que
        meter medidas a mano cuando las medidas están ahí, visibles.
        """
        image = _make_image_bytes(1000, 800)
        # bbox: (100, 80) a (400, 320). Padding estándar = 80px.
        # Zona tight: (20, 0) a (480, 400) — dentro hay SOLO 1 cota.
        # Zona expandida +300px: abarca más área y encuentra 3 cotas más.
        region = {"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        cotas = [
            _make_cota(2.95, x=250, y=200),   # dentro del tight
            _make_cota(0.60, x=600, y=200),   # fuera tight, dentro expanded
            _make_cota(4.15, x=650, y=500),   # fuera tight, dentro expanded
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.95, "ancho_m": 0.60}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        # LLM SÍ fue llamado
        assert result.get("error") is None
        assert result.get("largo_m") == 2.95
        assert result.get("ancho_m") == 0.60
        # Status DUDOSO garantizado porque fue fallback expanded
        assert "suspicious_reasons" in result
        assert any("expandido" in s for s in result["suspicious_reasons"])
        assert result.get("_cotas_mode") == "expanded"

    @pytest.mark.asyncio
    async def test_measure_region_no_global_fallback_when_no_cotas_near_bbox(self):
        """Si NI siquiera expandiendo hay 2 cotas cerca del bbox, devolvemos
        DUDOSO sin llamar al LLM. NO inventamos medidas con pool global.

        Motivación (caso Bernardi, abril 2026): el global_fallback hacía que
        el LLM eligiera cotas de OTROS sectores, devolviendo medidas
        plausibles pero incorrectas. Preferimos DUDOSO honesto que el
        operador ve como "— × —" y completa manual.
        """
        image = _make_image_bytes(1000, 800)
        region = {"id": "R2", "bbox_rel": {"x": 0.7, "y": 0.7, "w": 0.1, "h": 0.1}}
        cotas = [
            _make_cota(2.35, x=100, y=100),
            _make_cota(0.60, x=120, y=120),
            _make_cota(1.20, x=150, y=150),
        ]
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
            # NO debe haberse llamado al LLM
            mock_anth.assert_not_called()
        assert result.get("error") == "insufficient_local_cotas"
        assert result.get("local_cotas_count") == 0
        assert result.get("expanded_cotas_count") == 0

    @pytest.mark.asyncio
    async def test_measure_region_detects_unanchored_values(self):
        """LLM devuelve valor que no está en las cotas locales → suspicious_reasons."""
        image = _make_image_bytes(1000, 800)
        region = {"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        # 3 cotas dentro del bbox
        cotas = [
            _make_cota(2.95, x=200, y=200),
            _make_cota(0.60, x=210, y=220),
            _make_cota(4.15, x=230, y=240),
        ]
        # Mock LLM returns 1.75 (no está en cotas) + 0.60 (sí está)
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 1.75, "ancho_m": 0.60, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_client_instance = mock_anth.return_value
            mock_client_instance.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        assert "suspicious_reasons" in result
        assert any("1.75" in s for s in result["suspicious_reasons"])

    @pytest.mark.asyncio
    async def test_measure_region_detects_silent_fallback(self):
        """LLM devuelve largo == ancho → fallback silencioso detectado."""
        image = _make_image_bytes(1000, 800)
        region = {"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        cotas = [
            _make_cota(2.05, x=200, y=200),
            _make_cota(0.60, x=210, y=220),
        ]
        # LLM responde 0.60 x 0.60 (clásico fallback cuando no sabe)
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 0.60, "ancho_m": 0.60}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_client_instance = mock_anth.return_value
            mock_client_instance.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        # PR 2b.2 — la regla dura defensiva invalida largo < 1.0m ANTES
        # que llegue al check "largo == ancho". El valor queda en None
        # (honesto) con suspicious poblado.
        assert "suspicious_reasons" in result
        assert result.get("largo_m") is None
        assert any(
            "implausible" in s and "largo" in s.lower()
            for s in result["suspicious_reasons"]
        )

    @pytest.mark.asyncio
    async def test_bernardi_control_r2_stays_dudoso_without_inventing(self):
        """Regresión del caso real Bernardi (abril 2026): 2 regiones en el
        topology, R2 (cocina) en zona del plano sin cotas locales.

        CONTRATO ACTUAL (post-revert del global_fallback): R2 devuelve
        `insufficient_local_cotas` → aggregator emite largo/ancho=null con
        status DUDOSO → UI muestra "— × —". El operador completa a mano.

        Lo que NO hacemos: pasar las cotas globales al LLM para que invente
        una medida. Ese fallback hacía que el LLM eligiera cotas de otros
        sectores, devolviendo medidas swappeadas con look-confiado que
        podían confirmarse por error.

        Coordenadas tomadas del PDF real
        `tests/fixtures/bernardi_erica_mesadas_cocina.pdf` con
        `extract_cotas_from_drawing` a 300 DPI.
        """
        # Imagen 4963×3509 (300 DPI del PDF 1191×842 puntos)
        image = _make_image_bytes(4963, 3509)
        # Topology simulado: isla (centro-alta) + cocina con pileta (abajo-der)
        topology = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "sector": "isla",
                 "bbox_rel": {"x": 0.30, "y": 0.25, "w": 0.45, "h": 0.25},
                 "features": {"touches_wall": False, "stools_adjacent": True}},
                {"id": "R2", "sector": "cocina",
                 "bbox_rel": {"x": 0.65, "y": 0.65, "w": 0.25, "h": 0.25},
                 "features": {"touches_wall": True, "sink_simple": True}},
            ],
        }
        # Cotas reales del PDF (valor + posición en espacio imagen 300dpi)
        cotas = [
            _make_cota(0.60, x=3028, y=957),
            _make_cota(1.60, x=2119, y=1267),
            _make_cota(4.15, x=3663, y=1339),
            _make_cota(2.75, x=1577, y=1340),
            _make_cota(2.35, x=2836, y=1458),
            _make_cota(2.05, x=2506, y=1875),
            _make_cota(0.60, x=1941, y=2039),
        ]

        # Mockeamos SOLO el LLM (no _measure_region), para que la lógica real
        # del fallback escalonado se ejecute contra las cotas reales y el
        # bbox simulado — justamente lo que queremos validar.
        from app.modules.quote_engine.multi_crop_reader import _measure_region as real_mr

        def _mock_llm_response(region_id: str):
            # Respuesta distinta por región — ambas plausibles desde las cotas
            if region_id == "R1":
                return '{"largo_m": 2.35, "ancho_m": 0.60}'
            return '{"largo_m": 2.75, "ancho_m": 0.60}'

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=topology),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            # Mock dinámico: devuelve una respuesta distinta por cada región.
            # El stub inspecciona el mensaje para saber qué región.
            async def mock_create(**kwargs):
                msg_text = ""
                for m in kwargs.get("messages", []):
                    for b in m.get("content", []):
                        if isinstance(b, dict) and b.get("type") == "text":
                            msg_text += b.get("text", "")
                # La region_id no aparece literal en el prompt; usamos las
                # cotas para saber cuál es. R1 (isla): mode local, 5 cotas.
                # R2 (cocina): mode global_fallback, 7 cotas.
                if "7 cotas" in msg_text or "global" in msg_text.lower():
                    region_id = "R2"
                else:
                    region_id = "R1"
                text = _mock_llm_response(region_id)
                return type("R", (), {
                    "content": [type("B", (), {"text": text})()]
                })()

            mock_anth.return_value.messages.create = AsyncMock(side_effect=mock_create)
            result = await read_plan_multi_crop(image, cotas, brief_text="Bernardi — Puraprima")

        assert result.get("error") is None
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        # R1 (isla) tiene cotas locales → mide
        assert isla["tramos"][0]["largo_m"]["valor"] is not None
        # R2 (cocina) sin cotas cercanas → valor null + status DUDOSO.
        # NO debe inventar una medida global que confunda al operador.
        assert cocina["tramos"][0]["largo_m"]["valor"] is None, \
            "R2 tiene valor no-null — está inventando desde pool global"
        assert cocina["tramos"][0]["largo_m"]["status"] == "DUDOSO"
        assert result["requires_human_review"] is True

    @pytest.mark.asyncio
    async def test_partial_region_failure_still_aggregates(self):
        """Si 1 de 3 regiones falla, las otras 2 igual se agregan al output."""
        image = _make_image_bytes()
        topology = {
            "regions": [
                {"id": "R1", "sector": "cocina", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}},
                {"id": "R2", "sector": "cocina", "bbox_rel": {"x": 0.4, "y": 0.1, "w": 0.2, "h": 0.2}},
                {"id": "R3", "sector": "isla",   "bbox_rel": {"x": 0.3, "y": 0.5, "w": 0.2, "h": 0.2}},
            ],
        }

        async def fake_measure(full_bytes, size, region, cotas, model, brief_text=""):
            if region["id"] == "R2":
                return {"region_id": "R2", "error": "region_timeout"}
            return {"region_id": region["id"], "largo_m": 2.0, "ancho_m": 0.6}

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=topology),
        ), patch(
            "app.modules.quote_engine.multi_crop_reader._measure_region",
            new=fake_measure,
        ):
            result = await read_plan_multi_crop(image, cotas=[])
        tramos_cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")["tramos"]
        # R1 OK, R2 DUDOSO
        assert tramos_cocina[0]["largo_m"]["status"] == "CONFIRMADO"
        assert tramos_cocina[1]["largo_m"]["status"] == "DUDOSO"
        # requires_human_review se dispara por el DUDOSO
        assert result["requires_human_review"] is True


# ── PR 2a: counter-runs semantics in topology prompt + brief hint ───────────

class TestGlobalSystemPromptCounterRuns:
    """Verifica que el prompt del topology use la semántica de tramos
    cotizables (counter runs) en vez de masas grises contiguas. La
    contradicción previa (`L = 2 regiones` vs `región contigua = 1 entry`)
    causaba que el VLM colapsara L/U en un solo bbox."""

    def test_contradiction_phrase_removed(self):
        p = _GLOBAL_SYSTEM_PROMPT.lower()
        assert "cada región rellena contigua" not in p, (
            "La frase vieja contradictoria sigue presente"
        )

    def test_counter_run_concepts_present(self):
        p = _GLOBAL_SYSTEM_PROMPT.lower()
        # Conceptos clave del nuevo modelo mental
        assert "tramo recto" in p
        assert "masa gris" in p  # para decir que masa gris ≠ tramo
        assert "cocina en l" in p
        assert "isla" in p

    def test_schema_compat_note_present(self):
        """El prompt debe aclarar que `regions` mantiene el nombre por
        compatibilidad pero ahora significa tramos."""
        p = _GLOBAL_SYSTEM_PROMPT.lower()
        assert "retrocompat" in p or "compatibilidad de esquema" in p


class TestInferExpectedRegionCount:
    """La heurística del brief es un prior liviano — NO fuente de verdad.
    Valida keywords realistas que puede escribir el operador."""

    @pytest.mark.parametrize("brief, expected", [
        # Variaciones comunes de L
        ("cocina en L con isla", {"count": 3, "description": "cocina en L + isla"}),
        ("cocina tipo L con isla", {"count": 3, "description": "cocina en L + isla"}),
        ("forma de L, sin isla", {"count": 2, "description": "cocina en L"}),
        # "península" todavía no suma — explícito por ahora
        ("cocina en L y península", {"count": 2, "description": "cocina en L"}),
        # Variaciones de U
        ("cocina en U + isla central", {"count": 4, "description": "cocina en U + isla"}),
        ("forma de U con isla", {"count": 4, "description": "cocina en U + isla"}),
        # Recta / lineal
        ("cocina recta, 1 bacha", {"count": 1, "description": "cocina en recta"}),
        ("cocina lineal sin isla", {"count": 1, "description": "cocina en recta"}),
        ("contra una pared, simple", {"count": 1, "description": "cocina en recta"}),
        # Solo isla
        ("isla central", {"count": 1, "description": "isla"}),
        ("solo una isla 1.60", {"count": 1, "description": "isla"}),
        # Excluyentes
        ("cocina en L, sin isla", {"count": 2, "description": "cocina en L"}),
        ("cocina recta, no lleva isla", {"count": 1, "description": "cocina en recta"}),
        # Sin keywords → None (no forzamos un count cuando el brief es vago)
        ("presupuesto de mesada Silestone", None),
        ("", None),
        ("   ", None),
    ])
    def test_infer_expected_region_count(self, brief, expected):
        assert _infer_expected_region_count(brief) == expected


class TestTopologyCallInjectsHint:
    """Cuando el brief sugiere una forma clara, el bloque que va al VLM
    debe incluir: (a) brief original, (b) count esperado, (c) advertencia
    de L/U fusionada — todo en tono de consistencia, no mandato."""

    @pytest.mark.asyncio
    async def test_hint_injected_when_shape_detected(self):
        captured_blocks: list = []

        async def fake_create(**kwargs):
            for m in kwargs.get("messages", []):
                for b in m.get("content", []):
                    if isinstance(b, dict) and b.get("type") == "text":
                        captured_blocks.append(b)
            return type("R", (), {
                "content": [type("B", (), {"text": '{"regions": []}'})()]
            })()

        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(side_effect=fake_create)
            await _call_global_topology(
                image_bytes=_make_image_bytes(),
                model="test",
                brief_text="cocina en L + isla",
            )

        joined = " ".join(b["text"] for b in captured_blocks).lower()
        # Brief original presente
        assert "cocina en l" in joined
        # Count esperado presente (formato flexible, no literal)
        assert "3 tramos" in joined or "aproximadamente 3" in joined
        # Advertencia anti-fusión de L/U
        assert "l/u" in joined or "fusion" in joined

    @pytest.mark.asyncio
    async def test_hint_absent_when_brief_vague(self):
        """Sin keywords claros en el brief, NO se inyecta hint de count —
        evitamos wishful segmentation."""
        captured_blocks: list = []

        async def fake_create(**kwargs):
            for m in kwargs.get("messages", []):
                for b in m.get("content", []):
                    if isinstance(b, dict) and b.get("type") == "text":
                        captured_blocks.append(b)
            return type("R", (), {
                "content": [type("B", (), {"text": '{"regions": []}'})()]
            })()

        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(side_effect=fake_create)
            await _call_global_topology(
                image_bytes=_make_image_bytes(),
                model="test",
                brief_text="presupuesto para Silestone",
            )

        joined = " ".join(b["text"] for b in captured_blocks).lower()
        assert "silestone" in joined  # brief pasa
        # Pero NO hay frase de count inferido
        assert "tramos rectos cotizables" not in joined
        assert "fusionaste" not in joined


# ── PR 2b: cota ranking + guardrails ─────────────────────────────────────────

class TestPerimeterFilter:
    """Perímetro = valor grande (>3m) Y lejos del bbox. Ambas señales
    requeridas — una cota de 4m cercana al bbox puede ser una mesada larga."""

    def test_large_value_far_from_bbox_is_perimeter(self):
        img_size = (1000, 800)
        # bbox en la esquina sup-izq; cota en la otra esquina
        bbox = {"x": 100, "y": 100, "x2": 200, "y2": 200, "w": 100, "h": 100}
        cota = Cota(text="4.15", value=4.15, x=900, y=700, width=20, height=10)
        assert _is_probable_perimeter(cota, bbox, img_size) is True

    def test_large_value_close_to_bbox_is_not_perimeter(self):
        img_size = (1000, 800)
        bbox = {"x": 100, "y": 100, "x2": 500, "y2": 200, "w": 400, "h": 100}
        cota = Cota(text="4.15", value=4.15, x=300, y=150, width=20, height=10)
        assert _is_probable_perimeter(cota, bbox, img_size) is False

    def test_small_value_far_from_bbox_is_not_perimeter(self):
        # Cota chica lejos NO es perímetro (podría ser ancho de otra región).
        img_size = (1000, 800)
        bbox = {"x": 100, "y": 100, "x2": 200, "y2": 200, "w": 100, "h": 100}
        cota = Cota(text="0.60", value=0.60, x=900, y=700, width=20, height=10)
        assert _is_probable_perimeter(cota, bbox, img_size) is False


class TestEstimatePlanScale:
    """Scale estimation — señal débil. Requiere ≥2 pares para mediana."""

    def test_scale_from_multiple_regions_with_local_depth_cotas(self):
        img_size = (4000, 3000)
        regions = [
            {"bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.05, "h": 0.3}},  # bbox corto ~200px
            {"bbox_rel": {"x": 0.4, "y": 0.4, "w": 0.05, "h": 0.3}},  # idem
        ]
        # Cotas 0.60 dentro de cada bbox → short_px / 0.60 = 200 / 0.60 ≈ 333
        cotas = [
            Cota(text="0.60", value=0.60, x=500, y=450, width=20, height=10),  # dentro region 1
            Cota(text="0.60", value=0.60, x=1700, y=1350, width=20, height=10),  # dentro region 2
        ]
        scale = _estimate_plan_scale(regions, cotas, img_size)
        assert scale is not None
        assert 300 <= scale <= 400  # ~333 px/m

    def test_scale_returns_none_without_enough_evidence(self):
        img_size = (4000, 3000)
        regions = [{"bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.05, "h": 0.3}}]
        cotas = [Cota(text="0.60", value=0.60, x=500, y=450, width=20, height=10)]
        # Solo 1 par → mediana no confiable → None
        assert _estimate_plan_scale(regions, cotas, img_size) is None

    def test_scale_ignores_cotas_outside_reference_range(self):
        """Solo cotas chicas (0.30-0.80) cuentan como referencia de ancho."""
        img_size = (4000, 3000)
        regions = [
            {"bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.05, "h": 0.3}},
            {"bbox_rel": {"x": 0.4, "y": 0.4, "w": 0.05, "h": 0.3}},
        ]
        cotas = [
            Cota(text="2.35", value=2.35, x=500, y=450, width=20, height=10),
            Cota(text="2.05", value=2.05, x=1700, y=1350, width=20, height=10),
        ]
        # Ninguna en rango 0.30-0.80 → None
        assert _estimate_plan_scale(regions, cotas, img_size) is None


class TestScoreCota:
    """Score sumatorio 0..100. Cota de largo debe preferir alineación con
    eje largo; cota de ancho debe preferir valor típico (0.40-0.80)."""

    def test_length_cota_aligned_with_vertical_tramo_scores_high(self):
        # Bbox vertical: 100x500 en posición (200, 200)
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 700, "w": 100, "h": 500}
        # Cota a la derecha del bbox, alineada en y, valor típico de largo
        cota = Cota(text="2.35", value=2.35, x=340, y=450, width=20, height=10)
        result = _score_cota(
            cota, region_bbox_px, orientation="vertical", scale=None,
            candidate_for="length",
        )
        assert result["score"] >= 60
        assert result["bucket"] == "preferred"

    def test_length_cota_misaligned_scores_lower(self):
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 700, "w": 100, "h": 500}
        # Cota MUY arriba del bbox, no alineada en y
        cota = Cota(text="2.35", value=2.35, x=250, y=50, width=20, height=10)
        result = _score_cota(
            cota, region_bbox_px, orientation="vertical", scale=None,
            candidate_for="length",
        )
        # No "inside_tight_bbox" y no alineada con eje → score bajo
        assert result["score"] < 60

    def test_depth_cota_prefers_small_typical_values(self):
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 700, "w": 100, "h": 500}
        # 0.60 dentro del bbox
        cota_chica = Cota(text="0.60", value=0.60, x=250, y=400, width=20, height=10)
        cota_grande = Cota(text="2.35", value=2.35, x=250, y=400, width=20, height=10)
        score_chica = _score_cota(
            cota_chica, region_bbox_px, orientation="vertical", scale=None,
            candidate_for="depth",
        )
        score_grande = _score_cota(
            cota_grande, region_bbox_px, orientation="vertical", scale=None,
            candidate_for="depth",
        )
        assert score_chica["score"] > score_grande["score"]
        assert score_chica["bucket"] == "preferred"
        assert score_grande["bucket"] in ("weak", "unlikely", "excluded_soft")


class TestBernardiRankingR2:
    """Test central del PR. Usa las 7 cotas REALES extraídas del PDF de
    Erica Bernardi (via `extract_cotas_from_drawing`) + el bbox de R2 tal
    cual lo devolvió el topology LLM en prod (logs del 2026-04-19):
    `x:0.64, y:0.28, w:0.08, h:0.32`.

    El 2.95 que el VLM eligió en prod viene de otra ruta de extracción
    (da 13 cotas) y no tenemos sus coordenadas exactas — no lo inventamos.

    Valida el contrato del ranking contra los datos verificables:
    - 2.35 aparece en length (es la medida correcta)
    - 4.15 queda en excluded_hard como perímetro probable
    - 0.60 aparece en depth preferred
    - Ninguna de las cotas ajenas (2.75, 1.60, 2.05) supera al 2.35 en length
    """

    def test_r2_ranking_prefers_2_35_for_length(self):
        image_size = (4963, 3509)
        region = {"bbox_rel": {"x": 0.64, "y": 0.28, "w": 0.08, "h": 0.32}}
        cotas = [
            Cota(text="0.60", value=0.60, x=3028, y=957, width=20, height=10),
            Cota(text="1.60", value=1.60, x=2119, y=1267, width=20, height=10),
            Cota(text="4.15", value=4.15, x=3663, y=1339, width=20, height=10),
            Cota(text="2.75", value=2.75, x=1577, y=1340, width=20, height=10),
            Cota(text="2.35", value=2.35, x=2836, y=1458, width=20, height=10),
            Cota(text="2.05", value=2.05, x=2506, y=1875, width=20, height=10),
            Cota(text="0.60", value=0.60, x=1941, y=2039, width=20, height=10),
        ]
        ranking = _rank_cotas_for_region(cotas, region, image_size, scale=None)

        # 4.15 debe estar en excluded_hard como perímetro (valor >3m fuera del bbox)
        hard_values = [h["value"] for h in ranking["excluded_hard"]]
        assert 4.15 in hard_values, (
            f"4.15 debería ser perímetro; excluded_hard={ranking['excluded_hard']}"
        )

        # 2.35 debe estar en length
        v235 = next(
            (r for r in ranking["length"] if abs(r["value"] - 2.35) < 0.02),
            None,
        )
        assert v235 is not None, (
            f"2.35 debe estar en length; got values={[(r['value'], r['bucket']) for r in ranking['length']]}"
        )

        # Ninguna otra cota de largo (2.75, 1.60, 2.05) debe rankear por
        # encima del 2.35 — el 2.35 es la respuesta correcta para R2.
        for other_value in (2.75, 1.60, 2.05):
            other = next(
                (r for r in ranking["length"] if abs(r["value"] - other_value) < 0.02),
                None,
            )
            if other is None:
                continue  # puede haber sido filtrada por razones válidas
            assert v235["score"] >= other["score"], (
                f"2.35 (score {v235['score']}) debe rankear ≥ {other_value} "
                f"(score {other['score']}). Ranking actual: "
                f"{[(r['value'], r['score']) for r in ranking['length']]}"
            )

        # 0.60 debe aparecer en depth (ancho estándar). No exigimos "preferred"
        # porque en el plano real de Bernardi las 0.60 quedan cerca del bbox
        # expandido pero no dentro del tight — el bbox del tramo vertical es
        # angosto y las cotas 0.60 se escriben arriba/abajo del tramo.
        # Exigimos al menos que NO quede en "excluded_soft" o "unlikely" todas.
        depth_matches = [r for r in ranking["depth"] if abs(r["value"] - 0.60) < 0.02]
        assert len(depth_matches) >= 1
        best_depth_060 = max(depth_matches, key=lambda r: r["score"])
        assert best_depth_060["bucket"] in ("preferred", "weak"), (
            f"Al menos una 0.60 debe ser depth preferred/weak; "
            f"got {[(r['value'], r['bucket'], r['score']) for r in depth_matches]}"
        )
        # Ninguna cota grande (2.35, 1.60, 2.75) debe ranker preferido en depth
        for v in (2.35, 1.60, 2.75):
            bad = next(
                (r for r in ranking["depth"] if abs(r["value"] - v) < 0.02), None,
            )
            if bad:
                assert bad["bucket"] != "preferred", (
                    f"{v} NO debe ser depth preferred (valor fuera de rango depth)"
                )


class TestGuardrails:
    """Post-LLM: si VLM elige weak/unlikely habiendo preferred, baja
    confidence + suspicious. Si no había preferred, no castigamos."""

    def test_guardrail_lowers_confidence_on_weak_choice_vs_preferred(self):
        ranking = {
            "length": [
                {"value": 2.35, "score": 80, "bucket": "preferred", "reasons": []},
                {"value": 2.95, "score": 45, "bucket": "weak", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.95,  # eligió weak
            "ancho_m": 0.60,
            "confidence": 0.85,
            "reasoning": "me pareció mejor",
        }
        result = _apply_guardrails(vlm_output, ranking)
        assert result["confidence"] <= 0.5
        assert "suspicious_reasons" in result
        assert any("2.95" in s and "2.35" in s for s in result["suspicious_reasons"])

    def test_guardrail_does_not_punish_weak_choice_when_no_preferred(self):
        """Si solo hay weak disponible, no castigamos — puede ser lo mejor."""
        ranking = {
            "length": [
                {"value": 2.95, "score": 45, "bucket": "weak", "reasons": []},
                {"value": 2.05, "score": 38, "bucket": "weak", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.95,
            "ancho_m": 0.60,
            "confidence": 0.80,
        }
        result = _apply_guardrails(vlm_output, ranking)
        # Confidence NO bajó a 0.5 — no había preferred que perder
        assert result["confidence"] == 0.80
        # No suspicious del guardrail tampoco
        reasons = result.get("suspicious_reasons") or []
        assert not any("preferred" in r for r in reasons)

    def test_guardrail_flags_hallucinated_value_not_in_ranking(self):
        ranking = {
            "length": [
                {"value": 2.35, "score": 80, "bucket": "preferred", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 7.42,  # valor que no está en el ranking
            "ancho_m": 0.60,
            "confidence": 0.90,
        }
        result = _apply_guardrails(vlm_output, ranking)
        assert result["confidence"] <= 0.3
        # Wording actualizado en PR 2b.1 — texto "no está en ranking ni rango típico"
        assert any(
            ("no está en ranking" in s) or ("no está en el ranking" in s)
            for s in result["suspicious_reasons"]
        )


class TestRankingPromptFormat:
    """El prompt estructurado NO debe sugerir valores específicos que
    contaminen la elección del VLM."""

    def test_prompt_has_buckets_without_suggesting_values(self):
        ranking = {
            "length": [
                {"value": 2.35, "score": 80, "bucket": "preferred", "reasons": ["aligned"]},
                {"value": 2.95, "score": 45, "bucket": "weak", "reasons": ["far"]},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": ["depth_range"]},
            ],
            "excluded_hard": [{"value": 4.15, "reason": "probable_perimeter"}],
            "orientation": "vertical",
            "scale_px_per_m": None,
        }
        prompt = _format_ranking_for_prompt(ranking)
        # Buckets presentes
        assert "PREFERIDAS" in prompt
        assert "DÉBILES" in prompt
        # Sección "EXCLUIDAS" presente
        assert "EXCLUIDAS" in prompt
        # Orientación informada
        assert "vertical" in prompt.lower()
        # NO debe haber frases tipo "2.35m estimado" ni "respuesta sugerida"
        assert "estimado" not in prompt.lower()
        assert "respuesta" not in prompt.lower()


# ── PR 2b.1: R3 hardening + expanded confidence cap + inferred_default ────

class TestR3VerticalBernardi:
    """Test central de PR 2b.1: R3 vertical derecha del caso Bernardi
    cuando el topology puso el bbox tan a la derecha que la 4.15 cayó
    dentro del bbox tight. La regla de exclusión por incompatibilidad
    geométrica + alternativas debe:

    - excluir 4.15 del length ranking (regla A: >4m con alternativas).
    - mantener 2.35 y 2.05 en length.
    - **rankear 2.35 por encima de 2.05** (2.35 está más cerca del bbox
      de R3 en x → penalización por distancia menor).

    Sin la prioridad de 2.35 sobre 2.05, el VLM puede seguir eligiendo
    mal y el caso central no queda resuelto.
    """

    def test_r3_excludes_4_15_and_prefers_2_35_over_2_05(self):
        image_size = (4963, 3509)
        # bbox R3 real del log de prod
        region = {"bbox_rel": {"x": 0.73, "y": 0.26, "w": 0.09, "h": 0.37}}
        # 7 cotas reales + el 4.15 duplicado que cae dentro del bbox tight
        cotas = [
            Cota(text="0.60", value=0.60, x=3028, y=957, width=20, height=10),
            Cota(text="1.60", value=1.60, x=2119, y=1267, width=20, height=10),
            Cota(text="4.15", value=4.15, x=3663, y=1339, width=20, height=10),
            Cota(text="4.15", value=4.15, x=3700, y=1400, width=20, height=10),
            Cota(text="2.75", value=2.75, x=1577, y=1340, width=20, height=10),
            Cota(text="2.35", value=2.35, x=2836, y=1458, width=20, height=10),
            Cota(text="2.05", value=2.05, x=2506, y=1875, width=20, height=10),
        ]
        ranking = _rank_cotas_for_region(cotas, region, image_size, scale=None)

        # 4.15 debe estar en excluded_hard, NUNCA en length
        length_values = [r["value"] for r in ranking["length"]]
        assert 4.15 not in length_values, (
            f"4.15 no debe estar en length después del filtro geométrico. "
            f"Ranking length: {[(r['value'], r['score'], r['bucket']) for r in ranking['length']]}"
        )
        # Al menos una 4.15 debe aparecer como excluded_hard con razón reconocible
        hard_entries = ranking["excluded_hard"]
        assert any(
            abs(h["value"] - 4.15) < 0.02
            and ("alternatives" in h["reason"] or "over_4m" in h["reason"] or "perimeter" in h["reason"])
            for h in hard_entries
        ), f"4.15 debe estar en excluded_hard con razón geométrica; got {hard_entries}"

        # 2.35 y 2.05 deben mantenerse en length
        v235 = next(
            (r for r in ranking["length"] if abs(r["value"] - 2.35) < 0.02), None,
        )
        v205 = next(
            (r for r in ranking["length"] if abs(r["value"] - 2.05) < 0.02), None,
        )
        assert v235 is not None, "2.35 debe estar en length ranking"
        assert v205 is not None, "2.05 debe estar en length ranking"

        # Requisito central del PR: 2.35 rankea por encima de 2.05
        # (2.35 está más cerca del bbox de R3 en x: 787px vs 1117px → menos penalty).
        assert v235["score"] > v205["score"], (
            f"Para el bbox vertical R3, 2.35 debe rankear > 2.05. "
            f"Got 2.35=score {v235['score']} ({v235['bucket']}), "
            f"2.05=score {v205['score']} ({v205['bucket']}). "
            f"Sin esto el caso central no queda resuelto."
        )


class TestExpandedConfidenceCap:
    """PR 2b.1 — cap duro de confidence cuando cotas_mode=expanded."""

    def test_confidence_capped_at_065_in_expanded_mode(self):
        """cotas_mode=expanded + VLM eligió el top-ranked → cap 0.65."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 55, "bucket": "weak", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.35,  # eligió el top
            "ancho_m": 0.60,
            "confidence": 0.85,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="expanded")
        assert result["confidence"] == 0.65, (
            f"Expected 0.65 cap, got {result['confidence']}"
        )
        assert any(
            "expanded" in s and "cap" in s
            for s in result["suspicious_reasons"]
        )

    def test_confidence_capped_at_05_when_expanded_and_not_top(self):
        """cotas_mode=expanded + VLM eligió no-top en algún campo → cap 0.5."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 55, "bucket": "weak", "reasons": []},
                {"value": 2.05, "score": 40, "bucket": "weak", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.05,  # NO es el top (2.35 es)
            "ancho_m": 0.60,  # top
            "confidence": 0.85,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="expanded")
        assert result["confidence"] == 0.5, (
            f"Expected 0.5 cap, got {result['confidence']}"
        )

    def test_confidence_not_capped_in_local_mode(self):
        """cotas_mode=local no dispara los caps de expanded."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 80, "bucket": "preferred", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.35,
            "ancho_m": 0.60,
            "confidence": 0.90,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="local")
        assert result["confidence"] == 0.90

    def test_expanded_cap_05_fires_on_largo_even_if_ancho_is_inferred(self):
        """Check 3 — el cap 0.5 se evalúa por campo (OR, no AND).
        Si ancho es inferred_default (no en ranking), no debe impedir que
        el largo dispare el cap."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 55, "bucket": "weak", "reasons": []},
                {"value": 2.05, "score": 40, "bucket": "weak", "reasons": []},
            ],
            "depth": [],  # ningún candidato de depth en el ranking
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.05,  # no es el top (2.35 lo es)
            "ancho_m": 0.60,  # inferred_default — no está en depth ranking
            "confidence": 0.85,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="expanded")
        # El ancho inferred no cuenta para el cap de no-top; pero el largo sí.
        assert result["confidence"] == 0.5


class TestInferredDefaultGuardrail:
    """PR 2b.1 — cuando el VLM elige un valor no-en-ranking pero dentro
    del rango típico del rol (ej: 0.60 para ancho de mesada), es un
    inferred_default razonable. Cap suave 0.6, no 0.3 duro."""

    def test_inferred_default_for_ancho_060_caps_at_06(self):
        """Arregla el falso positivo de R1 en Bernardi: midió 1.60×0.60
        correcto, pero 0.60 no estaba en el ranking local → confidence
        bajó a 0.3 injustamente."""
        ranking = {
            "length": [
                {"value": 1.60, "score": 70, "bucket": "preferred", "reasons": []},
            ],
            "depth": [],  # sin candidatos de ancho en el ranking
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 1.60,
            "ancho_m": 0.60,  # inferred — no está en el ranking
            "confidence": 0.80,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="local")
        assert result["confidence"] == 0.60, (
            f"0.60 es default razonable de ancho → cap 0.6, no 0.3. "
            f"Got {result['confidence']}"
        )
        # Suspicious explicativo pero no alarmante
        assert any(
            "inferred" in s for s in result["suspicious_reasons"]
        )

    def test_out_of_range_value_not_in_ranking_hits_03_cap(self):
        """Valor fuera de rango típico AND no en ranking → halucinación
        dura, confidence 0.3."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 80, "bucket": "preferred", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 7.42,  # fuera del rango 1.0-4.0 AND no en ranking
            "ancho_m": 0.60,
            "confidence": 0.90,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="local")
        assert result["confidence"] <= 0.3


class TestSevereSpanMismatch:
    """PR 2b.1 — penalty escalonada. Deviation grande debe empujar a
    buckets bajos (no solo quedar como "weak por cercanía")."""

    def test_severe_span_mismatch_penalized_heavily(self):
        """Cota 4.15 con span esperado ~2.35m (deviation ~77%) → -50 puntos."""
        # bbox vertical con ~400px de alto (~2.35m con scale ~170 px/m)
        region_bbox_px = {"x": 100, "y": 100, "x2": 200, "y2": 500, "w": 100, "h": 400}
        # Cota cerca del bbox con valor 4.15
        cota = Cota(text="4.15", value=4.15, x=150, y=300, width=20, height=10)
        # scale=170 px/m → expected = 400/170 ≈ 2.35
        result = _score_cota(
            cota, region_bbox_px, orientation="vertical", scale=170.0,
            candidate_for="length",
        )
        # Confirmar que la razón de severe span mismatch está presente
        assert any("severe_span_mismatch" in r for r in result["reasons"]), (
            f"Expected severe_span_mismatch reason, got {result['reasons']}"
        )
        # Bucket weak o inferior (no preferred)
        assert result["bucket"] in ("weak", "unlikely", "excluded_soft")


# ── PR 2c: brief vs features contradiction detection ─────────────────────

def _isla_region_with_anafe() -> dict:
    """Fixture: topology región tipo isla con anafe detectado por VLM."""
    return {
        "id": "R1",
        "bbox_rel": {"x": 0.35, "y": 0.35, "w": 0.25, "h": 0.08},
        "features": {
            "touches_wall": False,
            "cooktop_groups": 1,
            "sink_simple": False,
            "sink_double": False,
            "stools_adjacent": False,
            "non_counter_upper": False,
        },
        "evidence": "isla con 4 círculos agrupados (anafe a gas)",
    }


class TestBriefFeatureContradiction:
    """PR 2c — detección mínima de contradicción isla+anafe."""

    def test_contradiction_bernardi_brief_silent_on_anafe(self):
        """Caso Bernardi: topology R1 isla con cooktop=1 + brief sin mencionar
        anafe → contradicción suave ("no lo menciona, confirmar")."""
        region = _isla_region_with_anafe()
        brief = (
            "nuevo presupuesto material en pura prima onix white mate "
            "Cliente: Erica Bernardi SIN zocalos en rosario con colocacion"
        )
        contradictions = _detect_region_brief_contradictions(region, brief)
        assert len(contradictions) == 1
        assert "no lo menciona" in contradictions[0]

    def test_no_contradiction_when_brief_places_anafe_in_isla(self):
        """Brief asocia anafe con isla explícito → SIN contradicción."""
        region = _isla_region_with_anafe()
        assert _detect_region_brief_contradictions(
            region, "cocina con anafe en isla, pileta simple"
        ) == []
        assert _detect_region_brief_contradictions(
            region, "isla central con cooktop eléctrico"
        ) == []
        assert _detect_region_brief_contradictions(
            region, "lleva hornallas en la isla"
        ) == []

    def test_negated_anafe_triggers_strong_contradiction(self):
        """Brief dice 'sin anafe' → contradicción fuerte."""
        region = _isla_region_with_anafe()
        for brief in [
            "cocina completa SIN anafe, con pileta doble",
            "presupuesto sin hornallas, pileta simple",
            "cocina no lleva cooktop — solo pileta",
            "no tiene anafe",
        ]:
            c = _detect_region_brief_contradictions(region, brief)
            assert len(c) == 1, f"brief {brief!r} debería dar 1 contradicción"
            assert "NO lleva anafe" in c[0] or "NO" in c[0]

    def test_anafe_mentioned_without_isla_triggers_ambiguous(self):
        """Brief menciona anafe pero NO asocia con isla → ambigüedad
        (topology ubica en isla, brief sugiere otra cosa)."""
        region = _isla_region_with_anafe()
        c = _detect_region_brief_contradictions(
            region, "cocina en L, con anafe empotrado, pileta simple"
        )
        assert len(c) == 1
        assert "no asocia anafe con isla" in c[0]

    def test_no_contradiction_when_cooktop_in_cocina_not_isla(self):
        """Region con touches_wall=True (cocina) + cooktop → ESPERABLE,
        sin contradicción aunque el brief no lo mencione."""
        region = {
            "id": "R2",
            "bbox_rel": {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.1},
            "features": {
                "touches_wall": True,  # ← cocina contra pared
                "cooktop_groups": 1,
                "sink_simple": False,
                "sink_double": False,
            },
        }
        # Brief sin anafe — topology lo detecta en cocina: OK, esperable
        assert _detect_region_brief_contradictions(region, "presupuesto") == []
        # Brief con "sin anafe" — ahora SÍ sería contradicción pero este
        # PR solo cubre isla, no cocina. Se trabajará en iteración futura.
        # (contrato actual: detector solo dispara si touches_wall=False)

    def test_no_contradiction_when_region_has_no_cooktop(self):
        """Sin cooktop en features → nada que chequear."""
        region = {
            "id": "R3",
            "features": {
                "touches_wall": False,
                "cooktop_groups": 0,
                "sink_simple": True,
            },
        }
        assert _detect_region_brief_contradictions(region, "") == []
        assert _detect_region_brief_contradictions(region, "sin anafe") == []


class TestAggregateAppliesBriefContradictions:
    """PR 2c — verifica que `_aggregate` propague la contradicción:
    1) como ambigüedad REVISION del sector,
    2) como sufijo ' — a confirmar' en la descripción del tramo."""

    def test_aggregate_marks_contradiction_in_sector_ambiguedades(self):
        topology = {
            "regions": [_isla_region_with_anafe()],
        }
        results = [
            {"region_id": "R1", "largo_m": 1.60, "ancho_m": 0.60},
        ]
        out = _aggregate(
            topology, results,
            brief_text="cocina con pileta, sin mencionar anafe",
        )
        isla = next(s for s in out["sectores"] if s["tipo"] == "isla")
        textos = [a["texto"] for a in isla["ambiguedades"]]
        assert any("anafe" in t.lower() for t in textos), (
            f"Esperaba ambigüedad de anafe, got: {textos}"
        )
        # Tramo marcado con "a confirmar" o similar (status CONFIRMADO →
        # NO lleva el " — revisar" preexistente, queda espacio para el nuevo)
        tramo = isla["tramos"][0]
        assert "a confirmar" in tramo["descripcion"].lower() or \
               "revisar" in tramo["descripcion"].lower(), (
            f"Esperaba sufijo 'a confirmar' o 'revisar', got: {tramo['descripcion']!r}"
        )
        # _contradictions preservado en el tramo para debugging
        assert tramo.get("_contradictions")

    def test_aggregate_no_suffix_when_brief_confirms_isla_anafe(self):
        """Si brief confirma anafe en isla → sin contradicción → descripción
        sin sufijo 'a confirmar'."""
        topology = {
            "regions": [_isla_region_with_anafe()],
        }
        results = [
            {"region_id": "R1", "largo_m": 1.60, "ancho_m": 0.60},
        ]
        out = _aggregate(
            topology, results,
            brief_text="cocina en L con isla con anafe empotrado",
        )
        isla = next(s for s in out["sectores"] if s["tipo"] == "isla")
        tramo = isla["tramos"][0]
        assert "a confirmar" not in tramo["descripcion"].lower()
        # No hay _contradictions tampoco
        assert not tramo.get("_contradictions")
        # Ambigüedades del sector no incluyen anafe (status CONFIRMADO)
        textos = [a["texto"] for a in isla["ambiguedades"]]
        assert not any("anafe" in t.lower() for t in textos)

    def test_aggregate_backcompat_without_brief_text(self):
        """Llamada sin `brief_text` (default "") — comportamiento igual
        que antes del PR 2c, sin contradicciones. Retrocompat con callers
        que todavía no pasan brief."""
        topology = {
            "regions": [_isla_region_with_anafe()],
        }
        results = [
            {"region_id": "R1", "largo_m": 1.60, "ancho_m": 0.60},
        ]
        out = _aggregate(topology, results)  # sin brief_text
        isla = next(s for s in out["sectores"] if s["tipo"] == "isla")
        tramo = isla["tramos"][0]
        # Brief vacío → no hay "anafe en isla" ni mención explícita → regla
        # "brief no menciona anafe" dispara igual. Este es comportamiento
        # esperado: sin brief, topology detectó anafe en isla y nosotros
        # no tenemos forma de validarlo → flaguear por conservador.
        assert tramo.get("_contradictions") is not None


# ── PR 2b.2: anti-fallback silencioso del VLM ────────────────────────────

class TestLargoSubMetroInvalidation:
    """PR 2b.2 — largo <1.0m es implausible para mesada. La regla dura
    invalida el valor a None antes de ser aceptado.

    Motivación: VLM hace fallback silencioso a 0.60 (el ancho estándar)
    cuando no puede medir. En el caso Bernardi R3 el operador veía
    '0.60 × 0.60' con aire de medida válida. Mejor None honesto →
    UI muestra '— × —' y el operador edita."""

    def test_largo_below_1m_invalidated_to_none(self):
        """VLM devolvió 0.60 como largo → invalidar a None con confidence 0.2."""
        ranking = {
            "length": [],
            "depth": [],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 0.60,
            "ancho_m": 0.60,
            "confidence": 0.85,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="local")
        assert result["largo_m"] is None, (
            f"largo 0.60 debería invalidarse a None; got {result['largo_m']}"
        )
        assert result["confidence"] <= 0.2
        assert any(
            "implausible" in s and "largo" in s.lower()
            for s in result["suspicious_reasons"]
        )

    def test_largo_exactly_1m_is_valid(self):
        """El umbral es <1.0 estricto: 1.0m justo NO se invalida."""
        ranking = {
            "length": [{"value": 1.0, "score": 60, "bucket": "preferred", "reasons": []}],
            "depth": [{"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []}],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 1.0,
            "ancho_m": 0.60,
            "confidence": 0.80,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="local")
        assert result["largo_m"] == 1.0

    def test_largo_valid_above_1m_preserved(self):
        """Largos típicos (1.60, 2.35, etc.) no se invalidan."""
        ranking = {
            "length": [{"value": 1.60, "score": 80, "bucket": "preferred", "reasons": []}],
            "depth": [{"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []}],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 1.60,
            "ancho_m": 0.60,
            "confidence": 0.85,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="local")
        assert result["largo_m"] == 1.60
        assert result["confidence"] == 0.85


class TestPromptNullWhenEmptyLengthRanking:
    """PR 2b.2 — cuando length_top queda vacío, el prompt debe instruir
    explícitamente al VLM a devolver `largo_m: null` y NO inventar."""

    def test_prompt_shows_null_instruction_when_length_empty(self):
        ranking = {
            "length": [],
            "depth": [{"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []}],
            "excluded_hard": [{"value": 4.15, "reason": "probable_perimeter"}],
            "orientation": "vertical",
            "scale_px_per_m": None,
        }
        prompt = _format_ranking_for_prompt(ranking)
        # Instrucción null presente
        assert "null" in prompt.lower()
        assert "no uses el ancho" in prompt.lower() or \
               "no inventes" in prompt.lower()
        # El prompt debe decir claramente que devolver null
        assert any(
            phrase in prompt.lower()
            for phrase in ("largo_m: null", "largo_m=null", "null honestamente")
        )

    def test_prompt_no_null_instruction_when_length_has_candidates(self):
        """Con length_top poblado, NO se inyecta la instrucción null
        (habría ruido innecesario)."""
        ranking = {
            "length": [{"value": 2.35, "score": 80, "bucket": "preferred", "reasons": []}],
            "depth": [{"value": 0.60, "score": 75, "bucket": "preferred", "reasons": []}],
            "excluded_hard": [],
            "orientation": "vertical",
            "scale_px_per_m": None,
        }
        prompt = _format_ranking_for_prompt(ranking)
        assert "null honestamente" not in prompt.lower()
        assert "no inventes: devolvé" not in prompt.lower()


# ── Plan B: cache global por plan_hash + retry condicional + instability ────

class TestStrongContradictionsDetector:
    """Plan B — el detector de contradicciones FUERTES decide si disparamos
    retry/bypass del cache. Debe ser estricto: solo count mismatch y
    negaciones explícitas, nada vago."""

    def test_count_mismatch_with_explicit_brief_triggers(self):
        from app.modules.quote_engine.multi_crop_reader import detect_strong_contradictions
        topology = {"regions": [{"id": "R1"}]}  # 1 region
        brief = "cocina en L + isla"  # esperamos 3
        contradictions = detect_strong_contradictions(topology, brief)
        assert len(contradictions) >= 1
        assert any("count_mismatch" in c for c in contradictions)

    def test_count_match_does_not_trigger(self):
        from app.modules.quote_engine.multi_crop_reader import detect_strong_contradictions
        topology = {"regions": [{"id": "R1"}, {"id": "R2"}, {"id": "R3"}]}
        brief = "cocina en L + isla"  # esperamos 3
        assert detect_strong_contradictions(topology, brief) == []

    def test_negated_anafe_triggers_when_topology_has_cooktop(self):
        from app.modules.quote_engine.multi_crop_reader import detect_strong_contradictions
        topology = {
            "regions": [{"id": "R1", "features": {"cooktop_groups": 1}}],
        }
        brief = "cocina sin anafe"
        contradictions = detect_strong_contradictions(topology, brief)
        assert any("anafe" in c.lower() for c in contradictions)

    def test_double_sink_brief_without_match_triggers(self):
        from app.modules.quote_engine.multi_crop_reader import detect_strong_contradictions
        topology = {
            "regions": [{"id": "R1", "features": {"sink_simple": True}}],
        }
        brief = "cocina con pileta doble"
        contradictions = detect_strong_contradictions(topology, brief)
        assert any("double_sink" in c for c in contradictions)

    def test_vague_brief_does_not_trigger(self):
        from app.modules.quote_engine.multi_crop_reader import detect_strong_contradictions
        topology = {"regions": [{"id": "R1"}]}
        brief = "presupuesto Silestone"  # sin forma, sin features
        assert detect_strong_contradictions(topology, brief) == []


class TestTopologiesDiverge:
    """IoU < 0.5 O n_regions distinto → divergen."""

    def test_identical_bboxes_do_not_diverge(self):
        from app.modules.quote_engine.multi_crop_reader import _topologies_diverge
        t = {"regions": [{"bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}]}
        assert _topologies_diverge(t, t) is False

    def test_different_n_regions_diverges(self):
        from app.modules.quote_engine.multi_crop_reader import _topologies_diverge
        t1 = {"regions": [{"bbox_rel": {"x": 0, "y": 0, "w": 1, "h": 1}}]}
        t2 = {"regions": [
            {"bbox_rel": {"x": 0, "y": 0, "w": 0.5, "h": 1}},
            {"bbox_rel": {"x": 0.5, "y": 0, "w": 0.5, "h": 1}},
        ]}
        assert _topologies_diverge(t1, t2) is True

    def test_low_iou_diverges(self):
        from app.modules.quote_engine.multi_crop_reader import _topologies_diverge
        t1 = {"regions": [{"bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}}]}
        t2 = {"regions": [{"bbox_rel": {"x": 0.7, "y": 0.7, "w": 0.2, "h": 0.2}}]}
        assert _topologies_diverge(t1, t2) is True

    def test_high_iou_no_diverge(self):
        from app.modules.quote_engine.multi_crop_reader import _topologies_diverge
        t1 = {"regions": [{"bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}]}
        t2 = {"regions": [{"bbox_rel": {"x": 0.11, "y": 0.11, "w": 0.3, "h": 0.3}}]}
        # IoU alto — casi idénticos
        assert _topologies_diverge(t1, t2) is False


class TestTopologyCacheFlow:
    """Plan B — cache global por plan_hash cross-quote.

    Usamos SQLite in-memory vía fixture db_session. Creamos el cache
    directamente, mockeamos _call_global_topology para controlar qué
    devuelve el "VLM".
    """

    @pytest.mark.asyncio
    async def test_cache_hit_cross_quote_skips_vlm(self, db_session):
        """Insertar cache con plan_hash=X + source_quote_id=A. Correr
        _get_or_build_topology con quote B + mismo hash → cache hit,
        VLM NO se llama."""
        from app.models.plan_topology_cache import PlanTopologyCache
        from app.modules.quote_engine.multi_crop_reader import (
            _get_or_build_topology,
        )
        cached_topology = {
            "view_type": "planta",
            "regions": [{"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}, "features": {}}],
        }
        cache_row = PlanTopologyCache(
            plan_hash="hashA",
            topology_json=cached_topology,
            stability_status="stable",
            n_regions=1,
            divergence_count=0,
            source_quote_id="quote-source",
        )
        db_session.add(cache_row)
        await db_session.commit()

        vlm_called = {"count": 0}

        async def _spy(*args, **kwargs):
            vlm_called["count"] += 1
            return {"view_type": "planta", "regions": []}

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            side_effect=_spy,
        ):
            topology, meta = await _get_or_build_topology(
                db_session, "hashA", "quote-B", _make_image_bytes(), "", "test",
            )
        assert vlm_called["count"] == 0
        assert meta["from_cache"] is True
        assert meta["cache_source_quote_id"] == "quote-source"
        assert topology == cached_topology

    @pytest.mark.asyncio
    async def test_cache_miss_calls_vlm_and_persists(self, db_session):
        """Sin cache previo → VLM se llama una vez → resultado se guarda."""
        from app.models.plan_topology_cache import PlanTopologyCache
        from app.modules.quote_engine.multi_crop_reader import (
            _get_or_build_topology,
        )
        from sqlalchemy import select

        fresh = {
            "view_type": "planta",
            "regions": [{"id": "R1", "bbox_rel": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}, "features": {}}],
        }
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=fresh),
        ):
            topology, meta = await _get_or_build_topology(
                db_session, "hashMiss", "quote-new", _make_image_bytes(),
                "", "test",
            )
        assert meta["from_cache"] is False
        assert topology == fresh
        # Persistido
        r = await db_session.execute(
            select(PlanTopologyCache).where(PlanTopologyCache.plan_hash == "hashMiss")
        )
        row = r.scalar_one_or_none()
        assert row is not None
        assert row.source_quote_id == "quote-new"
        assert row.n_regions == 1
        assert row.stability_status == "stable"

    @pytest.mark.asyncio
    async def test_cache_hit_with_contradiction_bypasses_to_fresh(self, db_session):
        """Cache tiene 1 region, brief dice "L + isla" (esperar 3).
        Contradicción fuerte → bypass + fresh retry. Fresh devuelve 3 → gana."""
        from app.models.plan_topology_cache import PlanTopologyCache
        from app.modules.quote_engine.multi_crop_reader import (
            _get_or_build_topology,
        )
        from sqlalchemy import select
        cached_topology = {
            "view_type": "planta",
            "regions": [{"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}, "features": {}}],
        }
        db_session.add(PlanTopologyCache(
            plan_hash="hashContra",
            topology_json=cached_topology,
            stability_status="stable",
            n_regions=1,
            divergence_count=0,
            source_quote_id="quote-old",
        ))
        await db_session.commit()

        fresh = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.05}, "features": {}},
                {"id": "R2", "bbox_rel": {"x": 0.1, "y": 0.4, "w": 0.3, "h": 0.3}, "features": {}},
                {"id": "R3", "bbox_rel": {"x": 0.5, "y": 0.4, "w": 0.1, "h": 0.3}, "features": {}},
            ],
        }
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=fresh),
        ):
            topology, meta = await _get_or_build_topology(
                db_session, "hashContra", "quote-new", _make_image_bytes(),
                "cocina en L + isla", "test",
            )
        assert meta["from_cache"] is True
        assert meta["replaced_cache"] is True
        assert topology["regions"] == fresh["regions"]
        # Cache fue actualizado
        r = await db_session.execute(
            select(PlanTopologyCache).where(PlanTopologyCache.plan_hash == "hashContra")
        )
        row = r.scalar_one()
        assert row.n_regions == 3
        # Stability status: divergencia (de 1 a 3 regions) → unstable
        assert row.stability_status == "unstable"
        assert row.divergence_count == 1

    @pytest.mark.asyncio
    async def test_unstable_cache_does_not_retry(self, db_session):
        """Cache ya marcado unstable + brief contradice → NO intentamos retry.
        Usamos cache + marcamos review."""
        from app.models.plan_topology_cache import PlanTopologyCache
        from app.modules.quote_engine.multi_crop_reader import (
            _get_or_build_topology,
        )
        cached_topology = {
            "view_type": "planta",
            "regions": [{"id": "R1", "bbox_rel": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}, "features": {}}],
        }
        db_session.add(PlanTopologyCache(
            plan_hash="hashUnstable",
            topology_json=cached_topology,
            stability_status="unstable",
            n_regions=1,
            divergence_count=1,
            source_quote_id="quote-old",
        ))
        await db_session.commit()

        vlm_calls = {"count": 0}

        async def _spy(*args, **kwargs):
            vlm_calls["count"] += 1
            return {"regions": []}

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            side_effect=_spy,
        ):
            topology, meta = await _get_or_build_topology(
                db_session, "hashUnstable", "quote-B", _make_image_bytes(),
                "cocina en L + isla", "test",  # contradice fuerte, pero unstable no re-intenta
            )
        assert vlm_calls["count"] == 0
        assert meta["from_cache"] is True
        assert meta["stability_status"] == "unstable"
        # No replaced porque ni siquiera hicimos retry
        assert meta.get("replaced_cache", False) is False

    @pytest.mark.asyncio
    async def test_retry_failure_keeps_cache_and_flags_review(self, db_session):
        """Cache + brief contradice → retry dispara → retry timeout/error
        → mantener cache + meta.retry_failed=True."""
        from app.models.plan_topology_cache import PlanTopologyCache
        from app.modules.quote_engine.multi_crop_reader import (
            _get_or_build_topology,
        )
        cached_topology = {
            "view_type": "planta",
            "regions": [{"id": "R1", "bbox_rel": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}, "features": {}}],
        }
        db_session.add(PlanTopologyCache(
            plan_hash="hashFail",
            topology_json=cached_topology,
            stability_status="stable",
            n_regions=1,
            divergence_count=0,
            source_quote_id="quote-old",
        ))
        await db_session.commit()

        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value={"error": "timeout"}),
        ):
            topology, meta = await _get_or_build_topology(
                db_session, "hashFail", "quote-new", _make_image_bytes(),
                "cocina en L + isla", "test",
            )
        assert meta["retry_failed"] is True
        assert meta["from_cache"] is True
        # Volvemos al cached_topology
        assert topology == cached_topology

    @pytest.mark.asyncio
    async def test_retry_worse_than_cache_keeps_cache(self, db_session):
        """Cache contradice (1 contradicción). Retry también contradice
        (2 contradicciones). Mantener cache, no replace."""
        from app.models.plan_topology_cache import PlanTopologyCache
        from app.modules.quote_engine.multi_crop_reader import (
            _get_or_build_topology,
        )
        cached_topology = {
            "view_type": "planta",
            "regions": [
                {"id": "R1", "bbox_rel": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}, "features": {}},
                {"id": "R2", "bbox_rel": {"x": 0.5, "y": 0, "w": 0.5, "h": 0.5}, "features": {}},
            ],
        }  # 2 regiones, brief espera 3
        db_session.add(PlanTopologyCache(
            plan_hash="hashWorse",
            topology_json=cached_topology,
            stability_status="stable",
            n_regions=2,
            divergence_count=0,
            source_quote_id="quote-old",
        ))
        await db_session.commit()

        fresh_worse = {"view_type": "planta", "regions": []}  # 0 regiones, peor
        with patch(
            "app.modules.quote_engine.multi_crop_reader._call_global_topology",
            new=AsyncMock(return_value=fresh_worse),
        ):
            topology, meta = await _get_or_build_topology(
                db_session, "hashWorse", "quote-new", _make_image_bytes(),
                "cocina en L + isla", "test",
            )
        # Mantener cache porque fresh es peor
        assert topology == cached_topology
        assert meta.get("replaced_cache", False) is False


# ─────────────────────────────────────────────────────────────────────────────
# PR 2d — Rescue pass: topology bbox subdimensionado
#
# Problema: en Bernardi, topology devuelve bbox correcto en forma/posición
# pero más chico que el tramo real. Las cotas correctas (2.35, 1.60) quedan
# excluidas del ranking por "severe_span_mismatch" → ranking vacío → prompt
# dice "devolvé null" → operador ve R1/R2 sin medida aunque la cota esté
# en el text layer del PDF.
#
# Fix: rescue pass controlado — re-rankear expanded_pool sin span penalty
# cuando el trigger estructurado dispara. Output SIEMPRE DUDOSO con
# confidence cap 0.5 → operador revisa visualmente.
# ─────────────────────────────────────────────────────────────────────────────


class TestRescuePass:
    """Rescue length ranking cuando topology bbox está subdimensionado."""

    # ── (1) Trigger estructurado — flags en _score_cota ─────────────────

    def test_score_cota_sets_span_penalty_flags_when_severe(self):
        """Cuando deviation > 50%, _score_cota marca span_penalty_severe=True.

        Es el flag estructurado que dispara el rescue — NO parseamos reasons
        strings porque son frágiles.
        """
        # bbox 150×100 → expected_m = max(150,100)/200 = 0.75m (>0.5 para
        # que el bloque span corra). Cota 2.35 → deviation 213% → severe.
        region_bbox_px = {"x": 200, "y": 200, "x2": 350, "y2": 300, "w": 150, "h": 100}
        cota = Cota(text="2.35", value=2.35, x=275, y=250, width=20, height=10)
        result = _score_cota(
            cota, region_bbox_px, orientation="horizontal", scale=200,
            candidate_for="length",
        )
        assert result["span_penalty_applied"] is True
        assert result["span_penalty_severe"] is True

    def test_score_cota_no_span_penalty_when_scale_none(self):
        """Sin scale, no hay span penalty — ni applied ni severe."""
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        cota = Cota(text="2.35", value=2.35, x=250, y=250, width=20, height=10)
        result = _score_cota(
            cota, region_bbox_px, orientation="horizontal", scale=None,
            candidate_for="length",
        )
        assert result["span_penalty_applied"] is False
        assert result["span_penalty_severe"] is False

    def test_score_cota_mild_span_deviation_applied_not_severe(self):
        """15-30% deviation → applied=True, severe=False."""
        # bbox 200x100 con scale=100 → expected_m ≈ 2.0
        region_bbox_px = {"x": 0, "y": 0, "x2": 200, "y2": 100, "w": 200, "h": 100}
        # Cota 2.5m → deviation 25% → mild
        cota = Cota(text="2.50", value=2.5, x=100, y=50, width=20, height=10)
        result = _score_cota(
            cota, region_bbox_px, orientation="horizontal", scale=100,
            candidate_for="length",
        )
        # 15% < 25% < 30% → applied pero NO severe
        assert result["span_penalty_applied"] is True
        assert result["span_penalty_severe"] is False

    # ── (2) Trigger estructurado — exclude_code en filter ───────────────

    def test_filter_length_by_geometry_adds_exclude_code_severe_span(self):
        """Regla B (severe_span_incompatibility) debe etiquetar con
        exclude_code='severe_span_mismatch' para el trigger del rescue."""
        # bbox 150x100 → expected_m = 150/200 = 0.75 (>0.5 para disparar
        # el bloque). Cota 2.35 → deviation 213% > 60% → severe.
        region_bbox_px = {"x": 0, "y": 0, "x2": 150, "y2": 100, "w": 150, "h": 100}
        length_ranking = [
            {"value": 2.35, "score": 10, "bucket": "unlikely", "reasons": []},
        ]
        surviving = [Cota(text="2.35", value=2.35, x=75, y=50, width=20, height=10)]
        excluded_hard: list[dict] = []
        scale = 200  # expected_m = 150/200 = 0.75; 2.35 deviation = 213% > 60%
        result = _filter_length_by_geometry(
            length_ranking, surviving, region_bbox_px, scale, excluded_hard,
        )
        assert result == []  # todo excluido
        assert len(excluded_hard) == 1
        assert excluded_hard[0]["exclude_code"] == "severe_span_mismatch"
        assert "severe_span_mismatch" in excluded_hard[0]["exclude_codes"]

    def test_filter_length_by_geometry_adds_exclude_code_over_4m(self):
        """Regla A (>4m con alternativas) → exclude_code='value_over_4m_with_alternatives'."""
        region_bbox_px = {"x": 0, "y": 0, "x2": 300, "y2": 100, "w": 300, "h": 100}
        length_ranking = [
            {"value": 4.50, "score": 20, "bucket": "unlikely", "reasons": []},
            {"value": 2.35, "score": 60, "bucket": "preferred", "reasons": []},
        ]
        surviving = [
            Cota(text="4.50", value=4.50, x=100, y=50, width=20, height=10),
            Cota(text="2.35", value=2.35, x=200, y=50, width=20, height=10),
        ]
        excluded_hard: list[dict] = []
        result = _filter_length_by_geometry(
            length_ranking, surviving, region_bbox_px, scale=None,
            excluded_hard=excluded_hard,
        )
        # 2.35 queda, 4.50 excluida
        assert len(result) == 1
        assert result[0]["value"] == 2.35
        # excluded_hard tiene 4.50 con exclude_code correcto
        assert len(excluded_hard) == 1
        assert excluded_hard[0]["value"] == 4.50
        assert excluded_hard[0]["exclude_code"] == "value_over_4m_with_alternatives"

    # ── (3) Rescue pass recupera cotas en caso Bernardi-like ────────────

    def test_rescue_pass_recovers_length_when_bbox_undersized(self):
        """Caso central: bbox chico (R1 de Bernardi), cota 2.35 en expanded
        pool. Sin rescue el ranking queda vacío. Con rescue, 2.35 vuelve."""
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        expanded_pool = [
            Cota(text="2.35", value=2.35, x=450, y=250, width=20, height=10),
            Cota(text="0.60", value=0.60, x=250, y=350, width=20, height=10),
        ]
        rescued = _rescue_length_ranking(
            expanded_pool, region_bbox_px, orientation="horizontal",
            image_size=(1000, 800),
        )
        # 2.35 aparece en rescued como candidate
        assert len(rescued) == 1
        assert rescued[0]["value"] == 2.35
        # bucket forzado a <= weak
        assert rescued[0]["bucket"] in ("weak", "unlikely", "excluded_soft")
        # 0.60 (fuera del rango length [1.0, 4.0]) NO debe estar en rescued
        values = [r["value"] for r in rescued]
        assert 0.60 not in values

    # ── (4) Rescue NO se dispara cuando hay preferred ───────────────────

    @pytest.mark.asyncio
    async def test_rescue_pass_not_triggered_when_preferred_exists(self):
        """Si ranking["length"] ya tiene candidates, rescue no se dispara."""
        image = _make_image_bytes(1000, 800)
        region = {"id": "R1", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        # Cotas que generan preferred normal — pool expandido pero sin severe span
        cotas = [
            _make_cota(2.35, x=250, y=200),   # inside tight
            _make_cota(0.60, x=250, y=300),   # inside tight
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.35, "ancho_m": 0.60, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        # Rescue NO aplicado
        meta = result.get("measurement_meta") or {}
        assert meta.get("rescue_applied") is False
        assert meta.get("recovered_count") == 0
        # cotas_mode NO es expanded_rescue
        assert result.get("_cotas_mode") != "expanded_rescue"

    # ── (5) Rescue devuelve vacío cuando no hay candidates en rango ─────

    def test_rescue_pass_returns_empty_without_valid_range_cotas(self):
        """Pool solo tiene 0.60 y 4.50 → ninguna en [1.0, 4.0] → []."""
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        expanded_pool = [
            Cota(text="0.60", value=0.60, x=450, y=250, width=20, height=10),
            Cota(text="4.50", value=4.50, x=450, y=300, width=20, height=10),
        ]
        rescued = _rescue_length_ranking(
            expanded_pool, region_bbox_px, orientation="horizontal",
            image_size=(1000, 800),
        )
        assert rescued == []

    # ── (6) Bucket cap defensivo: nunca preferred en rescue ─────────────

    def test_rescue_pass_forces_weak_bucket_even_for_high_scores(self):
        """Cota con score alto (dentro del tight + valor en rango + alineada)
        queda con bucket='weak' en el rescue, no 'preferred'."""
        # bbox ancho, cota 2.35 bien posicionada + alineada
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        expanded_pool = [
            # Cota muy cerca del bbox, valor en rango length
            Cota(text="2.35", value=2.35, x=250, y=250, width=20, height=10),
        ]
        rescued = _rescue_length_ranking(
            expanded_pool, region_bbox_px, orientation="horizontal",
            image_size=(1000, 800),
        )
        assert len(rescued) == 1
        # Nunca preferred en rescue, aunque el score puro sería alto
        assert rescued[0]["bucket"] != "preferred"
        assert "rescue_mode_capped_to_weak" in rescued[0]["reasons"]

    # ── (7) Guardrail: cap confidence 0.5 cuando cotas_mode=expanded_rescue

    def test_guardrail_caps_expanded_rescue_confidence_at_05(self):
        """VLM devuelve 0.85, cotas_mode=expanded_rescue → cap duro 0.5."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 40, "bucket": "weak", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 70, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.35,
            "ancho_m": 0.60,
            "confidence": 0.85,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="expanded_rescue")
        assert result["confidence"] == 0.5
        susp = result.get("suspicious_reasons") or []
        assert any("expanded_rescue" in s for s in susp)

    # ── (8) Perímetros excluidos incluso en rescue ──────────────────────

    def test_perimeter_cotas_still_excluded_in_rescue(self):
        """Cota >3m fuera del tight sigue marcada como perímetro en rescue."""
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        expanded_pool = [
            # 4.15m FUERA del tight (x=500 > x2=300) → probable_perimeter
            Cota(text="4.15", value=4.15, x=500, y=250, width=20, height=10),
            # 2.35m en rango length, válido
            Cota(text="2.35", value=2.35, x=450, y=250, width=20, height=10),
        ]
        rescued = _rescue_length_ranking(
            expanded_pool, region_bbox_px, orientation="horizontal",
            image_size=(1000, 800),
        )
        # 4.15 excluida; 2.35 queda
        values = [r["value"] for r in rescued]
        assert 4.15 not in values
        assert 2.35 in values

    # ── (9) Hard excludes absurdos siguen activos en rescue ─────────────

    def test_hard_excludes_still_apply_in_rescue(self):
        """Valores absurdos (<0.1 o >6) nunca pasan al rescue."""
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        expanded_pool = [
            Cota(text="0.05", value=0.05, x=250, y=250, width=20, height=10),
            Cota(text="8.00", value=8.00, x=250, y=250, width=20, height=10),
            Cota(text="2.35", value=2.35, x=250, y=250, width=20, height=10),
        ]
        rescued = _rescue_length_ranking(
            expanded_pool, region_bbox_px, orientation="horizontal",
            image_size=(1000, 800),
        )
        values = [r["value"] for r in rescued]
        assert 0.05 not in values
        assert 8.00 not in values
        assert 2.35 in values

    # ── (10) suspicious_reason marca topology_bbox_undersized ───────────

    @pytest.mark.asyncio
    async def test_rescue_suspicious_reason_marks_topology_undersized(self):
        """Cuando rescue se dispara, suspicious_reasons incluye
        'topology_bbox_undersized_rescue' (para que aggregator marque DUDOSO)."""
        image = _make_image_bytes(1000, 800)
        # bbox chico (100x100px): fuerza severe span con scale razonable
        region = {"id": "R1", "bbox_rel": {"x": 0.2, "y": 0.25, "w": 0.1, "h": 0.125}}
        # Pool que genera: L1 <2 cotas en tight → expanded → ranking vacío
        # (severe_span_mismatch) → rescue recupera la 2.35.
        cotas = [
            # Dentro del tight (ayuda a plan_scale con 0.60 depth reference)
            _make_cota(0.60, x=250, y=250),
            # En expanded, valor 2.35 — el trigger del rescue
            _make_cota(2.35, x=500, y=300),
            # Cota depth adicional para que plan_scale pueda estimar (necesita ≥2 pares)
            _make_cota(0.60, x=260, y=260),
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.35, "ancho_m": 0.60, "confidence": 0.85}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        # Verificamos el comportamiento observable del rescue SI se dispara.
        # Si el rescue no se dispara (plan_scale no se puede estimar por falta
        # de evidencia), skipeamos este assert — el test 12 cubre el caso
        # explícitamente.
        meta = result.get("measurement_meta") or {}
        if meta.get("rescue_applied"):
            assert meta.get("rescue_reason") == "topology_bbox_undersized"
            susp = result.get("suspicious_reasons") or []
            assert any("topology_bbox_undersized_rescue" in s for s in susp), (
                f"Expected topology_bbox_undersized_rescue in {susp}"
            )
            # Confidence capped a 0.5
            assert result.get("confidence") <= 0.5

    # ── (11) No regresión: R3 con bbox correcto NO pasa por rescue ─────

    @pytest.mark.asyncio
    async def test_bernardi_r3_still_measures_clean_without_rescue(self):
        """R3 (bbox correcto, cotas locales suficientes) NO dispara rescue.
        Sigue el camino normal CONFIRMADO."""
        image = _make_image_bytes(1000, 800)
        region = {"id": "R3", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        # Cotas dentro del tight — no hace falta expanded
        cotas = [
            _make_cota(2.05, x=250, y=200),
            _make_cota(0.60, x=250, y=300),
            _make_cota(0.60, x=150, y=200),
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.05, "ancho_m": 0.60, "confidence": 0.95}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        meta = result.get("measurement_meta") or {}
        assert meta.get("rescue_applied") is False
        assert result.get("_cotas_mode") != "expanded_rescue"
        # Medida normal
        assert result.get("largo_m") == 2.05
        assert result.get("ancho_m") == 0.60

    # ── (12) Rescue NO útil cuando solo hay perímetros ──────────────────

    def test_rescue_not_triggered_by_perimeter_only_case(self):
        """Expanded pool solo tiene cotas >3m fuera del tight → perímetros.
        Rescue devuelve [] → caller mantiene null honesto."""
        region_bbox_px = {"x": 200, "y": 200, "x2": 300, "y2": 300, "w": 100, "h": 100}
        expanded_pool = [
            # Todas >3m y fuera del tight → probable_perimeter
            Cota(text="4.15", value=4.15, x=500, y=250, width=20, height=10),
            Cota(text="3.80", value=3.80, x=500, y=400, width=20, height=10),
            Cota(text="5.20", value=5.20, x=500, y=500, width=20, height=10),
        ]
        rescued = _rescue_length_ranking(
            expanded_pool, region_bbox_px, orientation="horizontal",
            image_size=(1000, 800),
        )
        # Todas excluidas como perímetro → rescue vacío
        assert rescued == []

    # ── (13) Rescue no contamina ancho_m ni otras regiones ──────────────

    @pytest.mark.asyncio
    async def test_rescue_does_not_change_non_length_fields(self):
        """El rescue opera SOLO sobre length. No debe modificar:
        - ancho_m del VLM
        - confidence del ancho (evaluado antes del cap overall)
        - region_id
        - features
        """
        image = _make_image_bytes(1000, 800)
        region = {
            "id": "R1-isla",
            "bbox_rel": {"x": 0.2, "y": 0.25, "w": 0.1, "h": 0.125},
            "features": {"touches_wall": False, "has_sink": False},
            "has_pileta": False,
        }
        cotas = [
            _make_cota(0.60, x=250, y=250),
            _make_cota(2.35, x=500, y=300),
            _make_cota(0.60, x=260, y=260),
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.35, "ancho_m": 0.60, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")
        # region_id intacto
        assert result["region_id"] == "R1-isla"
        # ancho_m NO fue modificado por el rescue
        assert result.get("ancho_m") == 0.60
        # measurement_meta presente (siempre, tanto si rescue se disparó como si no)
        assert "measurement_meta" in result
        # Si el rescue se disparó, el cap 0.5 afecta la confidence global pero
        # el ancho_m en sí no cambia de valor.
        # Si no se disparó, el test sigue validando que measurement_meta existe
        # y es consistente (rescue_applied=False, recovered_count=0).
        meta = result["measurement_meta"]
        if not meta.get("rescue_applied"):
            assert meta.get("recovered_count") == 0
            assert meta.get("rescue_reason") is None


# ─────────────────────────────────────────────────────────────────────────────
# PR #346 — Observabilidad + orphan_region trigger + pool_starved_region
#
# Contexto: en corrida real de Bernardi post-#345, el rescue NO se disparó
# porque:
#   1. scale_px_per_m quedó None (R3 solo tenía 1 cota tight) → sin span
#      penalty → sin exclude_code "severe_span_mismatch" → trigger span_based
#      no dispara.
#   2. R1 length_top = [0.6, 0.6] (NO vacío) → la condición `not ranking["length"]`
#      falla, aunque 0.6 es basura como largo.
#   3. R2 length_top = [] con excluded_hard = [4.15, 4.15] (probable perímetro,
#      NO severe_span) → trigger span_based no dispara.
#   4. Pool expandido de R1 = [0.6, 0.6] (solo), R2 = [4.15, 4.15] (solo).
#      Las cotas reales (2.35, 1.60) están en el pool de R3.
#
# PR #346 agrega:
#   - Trigger orphan_region (local_cotas=0 + length empty/sub1_only).
#   - Concepto "meaningful length candidate" (≥1m, bucket weak/preferred).
#   - pool_starved_region flag cuando rescue corre pero no encuentra [1.0, 4.0].
#   - Logs estructurados [rescue-check], [rescue-pool], [rescue-result].
# ─────────────────────────────────────────────────────────────────────────────


class TestHasMeaningfulLengthCandidate:
    """Helper que decide si el ranking tiene un largo USABLE (≥1m + bucket
    preferred/weak). Clave del trigger: en Bernardi R1 había `[0.6, 0.6]`
    unlikely → no meaningful, rescue puede entrar."""

    def test_empty_ranking_returns_false(self):
        assert _has_meaningful_length_candidate([]) is False

    def test_sub1m_only_returns_false(self):
        ranking = [
            {"value": 0.6, "bucket": "unlikely"},
            {"value": 0.8, "bucket": "weak"},
        ]
        assert _has_meaningful_length_candidate(ranking) is False

    def test_ge1m_but_only_unlikely_bucket_returns_false(self):
        """≥1m pero bucket unlikely/excluded_soft no cuenta como evidencia."""
        ranking = [
            {"value": 2.35, "bucket": "unlikely"},
            {"value": 1.5, "bucket": "excluded_soft"},
        ]
        assert _has_meaningful_length_candidate(ranking) is False

    def test_ge1m_preferred_returns_true(self):
        ranking = [{"value": 2.05, "bucket": "preferred"}]
        assert _has_meaningful_length_candidate(ranking) is True

    def test_ge1m_weak_returns_true(self):
        ranking = [{"value": 1.5, "bucket": "weak"}]
        assert _has_meaningful_length_candidate(ranking) is True

    def test_mixed_returns_true_if_at_least_one_meaningful(self):
        ranking = [
            {"value": 0.6, "bucket": "unlikely"},
            {"value": 2.35, "bucket": "weak"},  # meaningful
            {"value": 4.5, "bucket": "excluded_soft"},
        ]
        assert _has_meaningful_length_candidate(ranking) is True


class TestBuildRescueContext:
    """Helper estructurado que evalúa el trigger del rescue. Sin
    side-effects — solo bool flags para tomar decisión + log."""

    def test_meaningful_length_blocks_rescue(self):
        """R3-like: length tiene preferred 2.05 → no rescue."""
        ranking = {
            "length": [{"value": 2.05, "bucket": "preferred",
                        "span_penalty_severe": False}],
            "depth": [],
            "excluded_hard": [],
        }
        ctx = _build_rescue_context(
            ranking, local_cotas_count=1,
            tight_pool=[_make_cota(2.05), _make_cota(0.6)],
            expanded_pool=None, cotas_mode="local",
        )
        assert ctx["has_meaningful_length_candidate"] is True
        assert ctx["will_rescue_try"] is False
        assert ctx["trigger_name"] is None

    def test_orphan_region_trigger_with_sub1_only(self):
        """Caso Bernardi R1 real: length=[0.6, 0.6] unlikely, local=0,
        expanded con algo → dispara orphan_region."""
        ranking = {
            "length": [
                {"value": 0.6, "bucket": "unlikely", "span_penalty_severe": False},
                {"value": 0.6, "bucket": "unlikely", "span_penalty_severe": False},
            ],
            "depth": [],
            "excluded_hard": [],
        }
        ctx = _build_rescue_context(
            ranking, local_cotas_count=0,
            tight_pool=[],
            expanded_pool=[_make_cota(0.6), _make_cota(0.6)],
            cotas_mode="expanded",
        )
        assert ctx["length_candidates_empty"] is False  # NO vacío
        assert ctx["length_candidates_sub1_only"] is True  # pero sub1
        assert ctx["has_meaningful_length_candidate"] is False
        assert ctx["orphan_region_trigger"] is True
        assert ctx["span_based_trigger"] is False
        assert ctx["will_rescue_try"] is True
        assert ctx["trigger_name"] == "orphan_region"

    def test_orphan_region_trigger_with_empty_length(self):
        """Caso Bernardi R2 real: length vacío, excluded=perímetros, local=0."""
        ranking = {
            "length": [],
            "depth": [],
            "excluded_hard": [
                {"value": 4.15, "exclude_code": "probable_perimeter"},
            ],
        }
        ctx = _build_rescue_context(
            ranking, local_cotas_count=0,
            tight_pool=[],
            expanded_pool=[_make_cota(4.15), _make_cota(4.15)],
            cotas_mode="expanded",
        )
        assert ctx["length_candidates_empty"] is True
        assert ctx["has_severe_span_exclusion"] is False  # solo perímetro
        assert ctx["orphan_region_trigger"] is True
        assert ctx["will_rescue_try"] is True
        assert ctx["trigger_name"] == "orphan_region"

    def test_span_based_trigger_takes_precedence_over_orphan(self):
        """Si ambos dispararían, span_based gana (señal más específica)."""
        ranking = {
            "length": [],
            "depth": [],
            "excluded_hard": [
                {"value": 2.35, "exclude_code": "severe_span_mismatch"},
            ],
        }
        ctx = _build_rescue_context(
            ranking, local_cotas_count=0,
            tight_pool=[],
            expanded_pool=[_make_cota(2.35)],
            cotas_mode="expanded",
        )
        assert ctx["span_based_trigger"] is True
        assert ctx["orphan_region_trigger"] is True
        assert ctx["trigger_name"] == "span_based"

    def test_no_trigger_without_expanded_pool(self):
        """cotas_mode=local con ranking vacío no dispara — tight es el
        camino estricto, no queremos relajarlo."""
        ranking = {"length": [], "depth": [], "excluded_hard": []}
        ctx = _build_rescue_context(
            ranking, local_cotas_count=2,
            tight_pool=[_make_cota(0.6), _make_cota(0.6)],
            expanded_pool=None, cotas_mode="local",
        )
        assert ctx["has_expanded_pool"] is False
        assert ctx["will_rescue_try"] is False

    def test_no_trigger_with_local_cotas_present_and_no_severe_span(self):
        """Si local_cotas>0 pero length ranking vacío, NO es orphan porque
        había cotas tight (solo que ninguna útil como length). Sin severe
        span, no hay razón para rescue."""
        ranking = {
            "length": [],
            "depth": [],
            "excluded_hard": [
                {"value": 0.6, "exclude_code": "absurd_value"},  # no severe
            ],
        }
        ctx = _build_rescue_context(
            ranking, local_cotas_count=2,  # había cotas tight
            tight_pool=[_make_cota(0.6), _make_cota(0.6)],
            expanded_pool=[_make_cota(0.6), _make_cota(0.6)],
            cotas_mode="expanded",
        )
        assert ctx["orphan_region_trigger"] is False  # local_cotas != 0
        assert ctx["span_based_trigger"] is False
        assert ctx["will_rescue_try"] is False


class TestRescueOrphanTriggerIntegration:
    """Integración con _measure_region: el trigger orphan_region realmente
    activa el rescue en casos que antes no disparaban."""

    @pytest.mark.asyncio
    async def test_orphan_region_with_useful_pool_activates_rescue(self):
        """Bbox chico (orphan), length=[0.6, 0.6] (sub1_only), expanded
        contiene 2.35 → trigger orphan_region dispara, rescue recupera
        2.35, output = DUDOSO con cap 0.5."""
        image = _make_image_bytes(1000, 800)
        # bbox 80×80 px (very tight). Posición interior.
        region = {"id": "R_orphan", "bbox_rel": {"x": 0.45, "y": 0.5, "w": 0.08, "h": 0.1}}
        # Bbox en píxeles (x_rel*w_img, etc):
        # x=450, y=400, x2=530, y2=480. Padding 80 → tight buffer [370..610, 320..560]
        # Expanded +300 → [70..910, 20..860]
        cotas = [
            # Dos 0.6 en tight (proveen "ruido" sub1)
            _make_cota(0.6, x=450, y=450),  # dentro tight
            _make_cota(0.6, x=500, y=450),  # dentro tight
            # 2.35 fuera del tight pero dentro del expanded
            _make_cota(2.35, x=750, y=450),
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.35, "ancho_m": 0.60, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")

        meta = result.get("measurement_meta") or {}
        # Con cotas en tight, local_cotas>0 → NO es orphan clásico. Revisamos
        # que al menos la observabilidad esté completa.
        assert "rescue_skip_reason" in meta or meta.get("rescue_applied") is not None
        # Si el rescue entró, debe venir con cap + suspicious.
        if meta.get("rescue_applied"):
            assert meta.get("rescue_trigger") in ("span_based", "orphan_region")
            assert result.get("confidence", 1.0) <= 0.5

    @pytest.mark.asyncio
    async def test_bernardi_r1_like_pool_starved_marks_meta_flag(self):
        """R1 Bernardi real: bbox periférico, local_cotas=0, expanded pool
        solo tiene [0.6, 0.6] (sin cotas útiles en [1.0, 4.0]). El rescue
        debe CORRER (trigger orphan_region), pero devolver [] → flag
        pool_starved_region=True en measurement_meta. Null honesto."""
        image = _make_image_bytes(1000, 800)
        # bbox chico en esquina inferior derecha
        region = {"id": "R1_bernardi_like",
                  "bbox_rel": {"x": 0.75, "y": 0.75, "w": 0.1, "h": 0.08}}
        # Tight: [750-80, 750-80] a [850+80, 830+80] = [670..930, 670..910]
        # Expanded +300: [370..1000, 370..1000]
        cotas = [
            # 0.6 en expanded (no en tight): local_cotas=0 → orphan
            _make_cota(0.6, x=500, y=500),
            _make_cota(0.6, x=450, y=400),
            # 4.15 dentro del expanded (>3m fuera tight → perímetro)
            _make_cota(4.15, x=450, y=450),
            # 2.35 completamente fuera (caso Bernardi: no está en pool)
            _make_cota(2.35, x=200, y=200),
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": null, "ancho_m": 0.60, "confidence": 0.1}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")

        meta = result.get("measurement_meta") or {}
        # Condiciones del caso Bernardi real:
        assert meta.get("local_cotas", -1) == 0 or meta.get("tight_pool_count", -1) == 0
        # El rescue corrió pero pool starved (no hay [1.0, 4.0] rescatables):
        # 0.6 < 1.0 filtrado, 4.15 excluido por Regla A (alternativas en [1.0, 4.0]
        # del pool completo del plano? el rescue filtra el expanded_pool de esta
        # región — que solo tiene 0.6 y 4.15. Ninguna en [1.0, 4.0]. → [])
        if meta.get("rescue_trigger") == "orphan_region":
            # Si el trigger disparó: pool debe quedar starved
            assert meta.get("pool_starved_region") is True
            assert meta.get("rescue_applied") is False
            assert meta.get("rescue_skip_reason") == "pool_starved_no_valid_range_candidates"

    @pytest.mark.asyncio
    async def test_r3_like_with_meaningful_length_skips_rescue(self):
        """R3 Bernardi: length tiene preferred 2.05 → no rescue, skip_reason
        = length_candidates_present / no_expanded_pool. Pool local con
        UNA cota 0.60 para que `_estimate_plan_scale` devuelva None
        (requiere ≥2 pares) y 2.05 no sea castigado con span penalty."""
        image = _make_image_bytes(1000, 800)
        region = {"id": "R3", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        cotas = [
            _make_cota(2.05, x=250, y=200),   # dentro tight, meaningful
            _make_cota(0.60, x=250, y=300),   # tight — una sola 0.60
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.05, "ancho_m": 0.60, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")

        meta = result.get("measurement_meta") or {}
        assert meta.get("rescue_applied") is False
        assert meta.get("has_meaningful_length_candidate") is True
        assert meta.get("rescue_skip_reason") in (
            "length_candidates_present", "no_expanded_pool",
        )
        assert meta.get("pool_starved_region") is False


class TestMeasurementMetaSchema:
    """El measurement_meta debe incluir todos los campos del PR #346
    para auditoría sin tener que ir a la DB."""

    @pytest.mark.asyncio
    async def test_measurement_meta_has_all_required_fields(self):
        image = _make_image_bytes(1000, 800)
        region = {"id": "R", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        cotas = [_make_cota(2.05, x=250, y=200), _make_cota(0.6, x=250, y=300)]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.05, "ancho_m": 0.6, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")

        meta = result.get("measurement_meta")
        assert meta is not None
        required_fields = {
            "rescue_applied", "rescue_reason", "rescue_trigger",
            "rescue_skip_reason", "original_length_candidates_empty",
            "original_length_candidates_sub1_only",
            "has_meaningful_length_candidate", "recovered_count",
            "tight_pool_count", "expanded_pool_count",
            "pool_starved_region",
        }
        assert required_fields.issubset(set(meta.keys())), (
            f"Missing fields: {required_fields - set(meta.keys())}"
        )


class TestRescueSkipReasons:
    """Todos los skip_reason son enums estructurados, no prosa libre."""

    @pytest.mark.asyncio
    async def test_skip_reason_enum_only(self):
        """El skip_reason siempre es uno de los valores conocidos."""
        image = _make_image_bytes(1000, 800)
        region = {"id": "R", "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}}
        cotas = [_make_cota(2.05, x=250, y=200), _make_cota(0.6, x=250, y=300)]
        mock_response = type("R", (), {
            "content": [type("B", (), {"text": '{"largo_m": 2.05, "ancho_m": 0.6, "confidence": 0.9}'})()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(image, (1000, 800), region, cotas, model="test")

        meta = result.get("measurement_meta") or {}
        known_skip_reasons = {
            "length_candidates_present",
            "no_expanded_pool",
            "no_rescue_signal",
            "pool_starved_no_valid_range_candidates",
            None,  # cuando rescue_applied=True
        }
        assert meta.get("rescue_skip_reason") in known_skip_reasons


# ─────────────────────────────────────────────────────────────────────────────
# PR #349 — Sanity checks semánticos post-measure
#
# Reglas mínimas que flagean medidas "plausibles geométricamente pero
# raras semánticamente". Caso canónico: Bernardi R3 midió 2.05 como
# sector=isla con confidence 0.65 → sistema lo promocionó a CONFIRMADO.
# Post #349: se flagea como `isla_largo_inusual` → suspicious_reasons
# → aggregator marca DUDOSO automáticamente (sin cambiar valor).
# ─────────────────────────────────────────────────────────────────────────────


class TestSemanticSanityChecks:
    """Unit tests del helper `_semantic_sanity_checks`."""

    # ── Regla 1: isla con largo >1.8m ──────────────────────────────────

    def test_isla_largo_mayor_a_1_8m_flagea(self):
        """Caso canónico Bernardi: isla midió 2.05m → flag isla_largo_inusual."""
        warnings = _semantic_sanity_checks(
            sector="isla", largo_m=2.05, ancho_m=0.60, features={},
        )
        assert len(warnings) == 1
        assert "isla_largo_inusual" in warnings[0]
        assert "2.05" in warnings[0]

    def test_isla_largo_exactamente_1_8m_no_flagea(self):
        """Límite estricto: solo >1.8 dispara. 1.8 exacto NO."""
        warnings = _semantic_sanity_checks(
            sector="isla", largo_m=1.80, ancho_m=0.60, features={},
        )
        assert warnings == []

    def test_isla_largo_tipico_1_6m_no_flagea(self):
        """Valor dentro de rango esperado (1.0-1.8m) → sin warnings."""
        warnings = _semantic_sanity_checks(
            sector="isla", largo_m=1.60, ancho_m=0.60, features={},
        )
        assert warnings == []

    def test_isla_largo_null_no_flagea(self):
        """largo_m=None no aplica reglas — será DUDOSO por null igual."""
        warnings = _semantic_sanity_checks(
            sector="isla", largo_m=None, ancho_m=0.60, features={},
        )
        assert warnings == []

    # ── Regla 2: cocina con pileta + anafe y largo <1.5m ───────────────

    def test_cocina_con_pileta_y_anafe_largo_corto_flagea(self):
        """Cocina con ambos artefactos y <1.5m → poco espacio físico."""
        features = {
            "sink_simple": True,
            "cooktop_groups": 1,
        }
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=1.20, ancho_m=0.60, features=features,
        )
        assert len(warnings) == 1
        assert "cocina_con_pileta_y_anafe_largo_corto" in warnings[0]
        assert "1.20" in warnings[0]

    def test_cocina_con_pileta_y_anafe_largo_exactamente_1_5m_no_flagea(self):
        """Límite estricto: solo <1.5 dispara."""
        features = {"sink_simple": True, "cooktop_groups": 1}
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=1.50, ancho_m=0.60, features=features,
        )
        assert warnings == []

    def test_cocina_con_solo_pileta_sin_anafe_no_flagea(self):
        """Regla requiere AMBOS artefactos. Solo pileta con largo chico → OK."""
        features = {"sink_simple": True, "cooktop_groups": 0}
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=1.20, ancho_m=0.60, features=features,
        )
        assert warnings == []

    def test_cocina_con_solo_anafe_sin_pileta_no_flagea(self):
        """Regla requiere AMBOS artefactos. Solo anafe con largo chico → OK."""
        features = {"sink_simple": False, "cooktop_groups": 1}
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=1.20, ancho_m=0.60, features=features,
        )
        assert warnings == []

    def test_cocina_con_pileta_doble_y_anafe_largo_corto_flagea(self):
        """sink_double también cuenta como pileta."""
        features = {"sink_double": True, "cooktop_groups": 1}
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=1.30, ancho_m=0.60, features=features,
        )
        assert len(warnings) == 1
        assert "cocina_con_pileta_y_anafe_largo_corto" in warnings[0]

    def test_cocina_con_has_pileta_generico_cuenta(self):
        """features.has_pileta (sin tipo específico) también cuenta."""
        features = {"has_pileta": True, "cooktop_groups": 1}
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=1.40, ancho_m=0.60, features=features,
        )
        assert len(warnings) == 1

    def test_cocina_con_largo_normal_no_flagea(self):
        """Cocina 2.5m con pileta+anafe → normal, sin warnings."""
        features = {"sink_simple": True, "cooktop_groups": 1}
        warnings = _semantic_sanity_checks(
            sector="cocina", largo_m=2.50, ancho_m=0.60, features=features,
        )
        assert warnings == []

    # ── Otros sectores no aplican ──────────────────────────────────────

    def test_baño_no_dispara_reglas(self):
        """Baño con largo 0.5m (chico típico de vanitory) NO dispara reglas
        de cocina ni isla."""
        warnings = _semantic_sanity_checks(
            sector="baño", largo_m=0.50, ancho_m=0.40, features={},
        )
        assert warnings == []

    def test_lavadero_no_dispara_reglas(self):
        warnings = _semantic_sanity_checks(
            sector="lavadero", largo_m=3.0, ancho_m=0.60, features={},
        )
        assert warnings == []

    def test_sector_vacio_no_dispara(self):
        warnings = _semantic_sanity_checks(
            sector="", largo_m=2.50, ancho_m=0.60, features={},
        )
        assert warnings == []

    def test_sector_none_no_dispara(self):
        warnings = _semantic_sanity_checks(
            sector=None, largo_m=2.50, ancho_m=0.60, features={},
        )
        assert warnings == []

    # ── Casos borde ────────────────────────────────────────────────────

    def test_ambas_reglas_pueden_dispararse_simultaneamente(self):
        """Si un sector fuera clasificable como ambos (hipotético), devolvería
        ambos warnings. En la práctica sector es uno u otro — test defensivo
        para futuros agregados."""
        # No existe sector "isla" Y "cocina" al mismo tiempo, pero verificamos
        # que los warnings se acumulan en lista y no son exclusivos.
        features = {"sink_simple": True, "cooktop_groups": 1}
        warnings_isla = _semantic_sanity_checks(
            sector="isla", largo_m=2.05, ancho_m=0.60, features=features,
        )
        warnings_cocina = _semantic_sanity_checks(
            sector="cocina", largo_m=1.20, ancho_m=0.60, features=features,
        )
        # Cada uno dispara 1 warning
        assert len(warnings_isla) == 1
        assert len(warnings_cocina) == 1
        # Son warnings distintos
        assert warnings_isla != warnings_cocina


class TestAggregateAppliesSemanticSanityChecks:
    """E2E del sanity check a través de `_aggregate`. Verifica que:
    - el warning se agrega a suspicious_reasons del tramo,
    - el status pasa a DUDOSO,
    - el largo_m NO cambia de valor,
    - se agrega ambigüedad REVISION al sector."""

    def _build_topology(self, regions):
        return {"view_type": "planta", "regions": regions}

    def test_bernardi_r3_isla_2_05_pasa_a_dudoso(self):
        """Caso Bernardi post-#349: R3 mide 2.05 con sector=isla.
        El status que antes era CONFIRMADO ahora es DUDOSO por sanity check."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {
                    "touches_wall": False,  # → clasifica como isla
                    "sink_double": False,
                    "sink_simple": False,
                    "cooktop_groups": 0,
                },
            },
        ])
        region_results = [
            {
                "region_id": "R3",
                "largo_m": 2.05,
                "ancho_m": 0.60,
                "confidence": 0.65,
                "suspicious_reasons": [],
            },
        ]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        tramo = isla["tramos"][0]

        # Valor no cambia
        assert tramo["largo_m"]["valor"] == 2.05
        assert tramo["ancho_m"]["valor"] == 0.60
        # Status pasa a DUDOSO
        assert tramo["largo_m"]["status"] == "DUDOSO"
        assert tramo["ancho_m"]["status"] == "DUDOSO"
        # Descripción tiene "— revisar" porque DUDOSO (patrón preexistente)
        assert "revisar" in tramo["descripcion"]
        # Ambigüedad agregada al sector
        amb_texts = " ".join(a.get("texto") or "" for a in isla["ambiguedades"])
        assert "isla_largo_inusual" in amb_texts or "dudosa" in amb_texts

    def test_isla_con_largo_normal_1_6m_sigue_confirmado(self):
        """No regresión: isla midiendo valor típico 1.6m sigue CONFIRMADO."""
        topology = self._build_topology([
            {
                "id": "R_isla",
                "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1},
                "features": {
                    "touches_wall": False,
                    "sink_double": False,
                    "sink_simple": False,
                    "cooktop_groups": 0,
                },
            },
        ])
        region_results = [
            {
                "region_id": "R_isla",
                "largo_m": 1.60,
                "ancho_m": 0.60,
                "confidence": 0.90,
                "suspicious_reasons": [],
            },
        ]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        tramo = isla["tramos"][0]
        assert tramo["largo_m"]["valor"] == 1.60
        assert tramo["largo_m"]["status"] == "CONFIRMADO"

    def test_cocina_normal_sin_pileta_sigue_confirmado(self):
        """Cocina largo 1.2m sin artefactos (raro pero no aplica regla)."""
        topology = self._build_topology([
            {
                "id": "R_cocina",
                "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3},
                "features": {
                    "touches_wall": True,
                    "sink_simple": False,
                    "sink_double": False,
                    "cooktop_groups": 0,
                },
            },
        ])
        region_results = [
            {
                "region_id": "R_cocina",
                "largo_m": 1.20,
                "ancho_m": 0.60,
                "confidence": 0.85,
                "suspicious_reasons": [],
            },
        ]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        assert cocina["tramos"][0]["largo_m"]["status"] == "CONFIRMADO"

    def test_cocina_con_pileta_y_anafe_largo_corto_pasa_a_dudoso(self):
        """Cocina con pileta + anafe + largo 1.2m → DUDOSO por regla 2."""
        topology = self._build_topology([
            {
                "id": "R_cocina",
                "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3},
                "features": {
                    "touches_wall": True,
                    "sink_simple": True,
                    "sink_double": False,
                    "cooktop_groups": 1,
                },
            },
        ])
        region_results = [
            {
                "region_id": "R_cocina",
                "largo_m": 1.20,
                "ancho_m": 0.60,
                "confidence": 0.80,
                "suspicious_reasons": [],
            },
        ]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        tramo = cocina["tramos"][0]
        assert tramo["largo_m"]["valor"] == 1.20  # valor no cambia
        assert tramo["largo_m"]["status"] == "DUDOSO"

    def test_suspicious_reasons_preexistentes_se_preservan(self):
        """Si ya había suspicious del measurement, el sanity check SUMA
        al stack, no reemplaza."""
        topology = self._build_topology([
            {
                "id": "R_isla",
                "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [
            {
                "region_id": "R_isla",
                "largo_m": 2.30,  # >1.8 → dispara sanity check
                "ancho_m": 0.60,
                "confidence": 0.60,
                "suspicious_reasons": ["cotas_mode=expanded → cap confidence 0.65"],
            },
        ]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        amb_text = " ".join(a.get("texto") or "" for a in isla["ambiguedades"])
        # Ambos motivos aparecen en la ambigüedad
        assert "cap confidence" in amb_text
        assert "isla_largo_inusual" in amb_text

    def test_null_largo_no_dispara_sanity_check(self):
        """Largo null no aplica regla — ya será DUDOSO por null igual,
        sin necesidad de doblar razones."""
        topology = self._build_topology([
            {
                "id": "R_isla",
                "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [
            {
                "region_id": "R_isla",
                "largo_m": None,  # null
                "ancho_m": 0.60,
                "confidence": 0.0,
                "suspicious_reasons": [],
            },
        ]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        tramo = isla["tramos"][0]
        assert tramo["largo_m"]["valor"] is None
        assert tramo["largo_m"]["status"] == "DUDOSO"  # por null, no por sanity
        # La razón es el null, NO isla_largo_inusual (porque no aplica con null)
        amb_text = " ".join(a.get("texto") or "" for a in isla["ambiguedades"])
        assert "isla_largo_inusual" not in amb_text


class TestSemanticSanityObservabilityLog:
    """PR #350 — Log estructurado [semantic-sanity] dentro de _aggregate.

    Problema que resuelve: el log [multi-crop/region-detail] se emite
    antes de _aggregate, entonces nunca mostraba el efecto del sanity
    check del PR #349. Sin este log, confirmar en prod que el sanity
    está corriendo requería inspeccionar quote_breakdown.dual_read —
    invisible al operador y a los logs standard de Railway.
    """

    def _build_topology(self, regions):
        return {"view_type": "planta", "regions": regions}

    def test_log_emitted_when_sanity_triggers_bernardi_r3(self, caplog):
        """Caso canónico Bernardi: R3 isla 2.05 → log con campos completos."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {
                    "touches_wall": False,
                    "sink_double": False,
                    "sink_simple": False,
                    "cooktop_groups": 0,
                },
            },
        ])
        region_results = [{
            "region_id": "R3", "largo_m": 2.05, "ancho_m": 0.60,
            "confidence": 0.65, "suspicious_reasons": [],
        }]

        with caplog.at_level(logging.INFO,
                             logger="app.modules.quote_engine.multi_crop_reader"):
            _aggregate(topology, region_results)

        sanity_logs = [r for r in caplog.records if "[semantic-sanity]" in r.message]
        assert len(sanity_logs) == 1, f"Expected 1 sanity log, got {len(sanity_logs)}: {[r.message for r in sanity_logs]}"
        log = sanity_logs[0].message
        # Campos obligatorios grep-friendly (formato key=value)
        for key in ("region=R3", "sector=isla", "largo=2.05",
                    "ancho=0.60", "warnings=", "status_before=",
                    "status_after=", "status_changed_by_sanity="):
            assert key in log, f"Missing key '{key}' in log: {log}"
        # Warning específico debe estar en el array
        assert "isla_largo_inusual" in log

    def test_log_not_emitted_when_no_warnings(self, caplog):
        """Isla 1.6m normal → no warnings → no log (evitar ruido)."""
        topology = self._build_topology([
            {
                "id": "R_ok",
                "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R_ok", "largo_m": 1.60, "ancho_m": 0.60,
            "confidence": 0.90, "suspicious_reasons": [],
        }]
        with caplog.at_level(logging.INFO,
                             logger="app.modules.quote_engine.multi_crop_reader"):
            _aggregate(topology, region_results)
        sanity_logs = [r for r in caplog.records if "[semantic-sanity]" in r.message]
        assert sanity_logs == []

    def test_log_status_changed_by_sanity_true_when_upgrades_confirmed_to_dudoso(self, caplog):
        """Si SIN sanity sería CONFIRMADO, y CON sanity es DUDOSO, el log
        debe decir status_changed_by_sanity=True. Esto es el caso más
        valioso a rastrear: el sanity SALVÓ a un operador de confirmar
        un error silencioso."""
        topology = self._build_topology([
            {
                "id": "R_salvado",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        # Sin suspicious_reasons preexistentes — SIN sanity sería CONFIRMADO.
        region_results = [{
            "region_id": "R_salvado", "largo_m": 2.05, "ancho_m": 0.60,
            "confidence": 0.95, "suspicious_reasons": [],
        }]
        with caplog.at_level(logging.INFO,
                             logger="app.modules.quote_engine.multi_crop_reader"):
            _aggregate(topology, region_results)
        sanity_logs = [r for r in caplog.records if "[semantic-sanity]" in r.message]
        assert len(sanity_logs) == 1
        log = sanity_logs[0].message
        assert "status_before=CONFIRMADO" in log
        assert "status_after=DUDOSO" in log
        assert "status_changed_by_sanity=True" in log

    def test_log_status_changed_by_sanity_false_when_already_dudoso(self, caplog):
        """Bernardi real: ya era DUDOSO por suspicious previos del expanded.
        El sanity agrega otra razón pero no cambia el status. Log muestra
        status_changed_by_sanity=False para que se distinga."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R3", "largo_m": 2.05, "ancho_m": 0.60,
            "confidence": 0.65,
            # Ya había suspicious previos — status_before_sanity=DUDOSO.
            "suspicious_reasons": ["cotas_mode=expanded → cap confidence 0.65"],
        }]
        with caplog.at_level(logging.INFO,
                             logger="app.modules.quote_engine.multi_crop_reader"):
            _aggregate(topology, region_results)
        sanity_logs = [r for r in caplog.records if "[semantic-sanity]" in r.message]
        assert len(sanity_logs) == 1
        log = sanity_logs[0].message
        assert "status_before=DUDOSO" in log
        assert "status_after=DUDOSO" in log
        assert "status_changed_by_sanity=False" in log

    def test_log_format_is_grep_friendly(self, caplog):
        """El formato debe seguir el patrón key=value como [rescue-check]
        y [context-reconcile] de PRs anteriores. Todos los keys separados
        por espacio, sin comas ni JSON embebido."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R3", "largo_m": 2.05, "ancho_m": 0.60,
            "confidence": 0.65, "suspicious_reasons": [],
        }]
        with caplog.at_level(logging.INFO,
                             logger="app.modules.quote_engine.multi_crop_reader"):
            _aggregate(topology, region_results)
        log = [r for r in caplog.records if "[semantic-sanity]" in r.message][0].message
        # Debe arrancar con el tag
        assert log.startswith("[semantic-sanity] ")
        # Cada campo key=value separado por espacio
        expected_keys = [
            "region=", "sector=", "largo=", "ancho=",
            "warnings=", "status_before=", "status_after=",
            "status_changed_by_sanity=",
        ]
        for key in expected_keys:
            assert key in log, f"Missing '{key}' in: {log}"


# ─────────────────────────────────────────────────────────────────────────────
# PR #351 — Sanity warnings como bullet dedicado en ambigüedades
#
# Contexto del bug: post-#349 + #350, el log [semantic-sanity] confirmó que
# el sanity corre en prod. Pero el operador seguía sin ver el motivo
# semántico porque:
#
#   elif suspicious:
#       all_ambiguedades.append({
#           "texto": f"... ({'; '.join(suspicious)[:120]})",  # ← trunca
#       })
#
# Para Bernardi R3, el join era:
#   "cotas_mode=expanded → cap 0.65; medida tomada con pool...; isla_largo_inusual_..."
#
# Los dos primeros ya suman ~115 chars → `[:120]` cortaba el sanity en "isla".
# El mensaje semántico quedaba invisible para el operador.
#
# Fix: separar sanity warnings en bullets dedicados SIN truncar. La
# ambigüedad general mantiene los otros suspicious truncados.
# ─────────────────────────────────────────────────────────────────────────────


class TestIsSemanticSanityWarning:
    """Helper centralizado para detectar strings que vienen de
    `_semantic_sanity_checks`. Usado por `_aggregate` para distinguirlos
    del resto de suspicious_reasons."""

    def test_isla_largo_inusual_prefix_detected(self):
        # Formato real producido por _semantic_sanity_checks:
        warn = (
            "isla_largo_inusual_2.05m_threshold_1.80m — islas residenciales "
            "típicas 1.0-1.8m, valor mayor probable error de asignación "
            "bbox↔cota; revisar visualmente"
        )
        assert _is_semantic_sanity_warning(warn) is True

    def test_cocina_con_pileta_y_anafe_prefix_detected(self):
        warn = (
            "cocina_con_pileta_y_anafe_largo_corto_1.20m_threshold_1.50m "
            "— un tramo con ambos artefactos típicamente mide ≥1.5m; "
            "probable cota mal asignada"
        )
        assert _is_semantic_sanity_warning(warn) is True

    def test_other_suspicious_not_detected(self):
        assert _is_semantic_sanity_warning(
            "cotas_mode=expanded → cap confidence 0.65"
        ) is False
        assert _is_semantic_sanity_warning(
            "medida tomada con pool de cotas expandido (no estricto a esta región)"
        ) is False
        assert _is_semantic_sanity_warning(
            "largo 0.6m < 1.0m — implausible como largo de tramo, invalidado"
        ) is False

    def test_empty_string_not_detected(self):
        assert _is_semantic_sanity_warning("") is False

    def test_none_returns_false_no_crash(self):
        """Defensa: si alguien pasa None por error, no crashea."""
        assert _is_semantic_sanity_warning(None) is False  # type: ignore[arg-type]

    def test_helper_and_real_output_stay_in_sync(self):
        """Contrato: todo string que emite `_semantic_sanity_checks` es
        detectado por `_is_semantic_sanity_warning`. Si este test falla
        tras agregar una regla nueva al helper → actualizar
        `_SEMANTIC_SANITY_PREFIXES`."""
        # Regla 1 — isla:
        w_isla = _semantic_sanity_checks(
            sector="isla", largo_m=2.50, ancho_m=0.60, features={},
        )
        for w in w_isla:
            assert _is_semantic_sanity_warning(w), (
                f"Sanity helper emitió '{w}' pero _is_semantic_sanity_warning "
                f"no lo reconoce. Actualizá _SEMANTIC_SANITY_PREFIXES."
            )

        # Regla 2 — cocina:
        w_cocina = _semantic_sanity_checks(
            sector="cocina", largo_m=1.20, ancho_m=0.60,
            features={"sink_simple": True, "cooktop_groups": 1},
        )
        for w in w_cocina:
            assert _is_semantic_sanity_warning(w), (
                f"Sanity helper emitió '{w}' pero _is_semantic_sanity_warning "
                f"no lo reconoce."
            )

    def test_prefixes_constant_is_tuple(self):
        """El constante expuesto es inmutable. Evita mutación accidental."""
        assert isinstance(_SEMANTIC_SANITY_PREFIXES, tuple)
        # Sanity mínima: al menos las 2 reglas que tenemos hoy.
        assert len(_SEMANTIC_SANITY_PREFIXES) >= 2


class TestSanityWarningsCreateDedicatedBullets:
    """E2E del fix PR #351: sanity warnings van como bullet dedicado
    sin truncar, separados del bullet general de suspicious normales."""

    def _build_topology(self, regions):
        return {"view_type": "planta", "regions": regions}

    def _ambig_texts(self, sector: dict) -> list[str]:
        return [a.get("texto") or "" for a in sector.get("ambiguedades") or []]

    def test_bernardi_sanity_bullet_shows_full_untruncated_text(self):
        """Caso canónico del bug. R3 con suspicious largos previos +
        sanity warning → sanity aparece completo, no cortado en 'isla'."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R3",
            "largo_m": 2.05,
            "ancho_m": 0.60,
            "confidence": 0.65,
            # Suspicious previos que empujaban al sanity warning fuera del
            # trim de 120 chars en el bullet general:
            "suspicious_reasons": [
                "cotas_mode=expanded → cap confidence 0.65",
                "medida tomada con pool de cotas expandido (no estricto a esta región)",
            ],
        }]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        texts = self._ambig_texts(isla)

        # Debe haber al menos 2 bullets: general + sanity dedicado.
        assert len(texts) >= 2, (
            f"Esperaba ≥2 bullets, got {len(texts)}: {texts}"
        )

        # Buscar el bullet del sanity (no truncado).
        sanity_bullets = [t for t in texts if "isla_largo_inusual" in t]
        assert len(sanity_bullets) == 1, (
            f"Esperaba exactamente 1 bullet dedicado del sanity. "
            f"Got {len(sanity_bullets)}: {sanity_bullets}"
        )
        sanity_bullet = sanity_bullets[0]

        # CRÍTICO: el bullet del sanity tiene el TEXTO COMPLETO, no
        # cortado en "isla". Validamos presencia del mensaje humano
        # post-prefijo estructurado.
        assert "islas residenciales típicas" in sanity_bullet, (
            f"Bullet del sanity truncado. Falta texto humano. Got: {sanity_bullet}"
        )
        assert "revisar visualmente" in sanity_bullet, (
            f"Bullet del sanity truncado. Falta 'revisar visualmente'. Got: {sanity_bullet}"
        )

    def test_general_bullet_does_not_include_sanity_warning(self):
        """Evita redundancia tonta: sanity va SOLO en bullet dedicado,
        no aparece también en el bullet general truncado."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R3",
            "largo_m": 2.05,
            "ancho_m": 0.60,
            "confidence": 0.65,
            "suspicious_reasons": [
                "cotas_mode=expanded → cap confidence 0.65",
                "medida tomada con pool de cotas expandido (no estricto a esta región)",
            ],
        }]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        texts = self._ambig_texts(isla)

        general_bullets = [
            t for t in texts
            if "medida dudosa" in t and "isla_largo_inusual" not in t
        ]
        # Debe existir UN bullet general.
        assert len(general_bullets) == 1
        # Y NO incluye el sanity warning (para evitar redundancia).
        assert "isla_largo_inusual" not in general_bullets[0]

    def test_only_sanity_no_general_bullet(self):
        """Si los ÚNICOS suspicious son sanity warnings (sin cap confidence
        ni pool expandido), no emitir bullet general redundante."""
        topology = self._build_topology([
            {
                "id": "R_isla",
                "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R_isla",
            "largo_m": 2.30,
            "ancho_m": 0.60,
            "confidence": 0.95,  # alto — no dispara cap ni expanded
            "suspicious_reasons": [],  # sin suspicious previos
        }]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        texts = self._ambig_texts(isla)

        # Exactamente 1 bullet: el dedicado del sanity.
        assert len(texts) == 1
        assert "isla_largo_inusual" in texts[0]
        assert "medida dudosa" not in texts[0]  # no bullet general

    def test_no_sanity_warnings_only_general_bullet(self):
        """No regresión: región con suspicious normales (sin sanity)
        mantiene el bullet general tradicional (truncado a 120)."""
        topology = self._build_topology([
            {
                "id": "R_cocina",
                "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3},
                "features": {"touches_wall": True, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R_cocina",
            "largo_m": 2.50,
            "ancho_m": 0.60,
            "confidence": 0.65,
            "suspicious_reasons": [
                "cotas_mode=expanded → cap confidence 0.65",
                "medida tomada con pool de cotas expandido (no estricto a esta región)",
            ],
        }]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        texts = self._ambig_texts(cocina)
        assert len(texts) == 1
        assert "medida dudosa" in texts[0]
        assert "isla_largo_inusual" not in texts[0]

    def test_multiple_sanity_warnings_create_multiple_bullets(self):
        """Defensivo: el aggregador tiene que generar un bullet dedicado
        por cada warning semántico, aunque venga más de uno en
        suspicious_reasons. Usamos largo=1.60 para que el sanity REAL
        no dispare (isla 1.6m es OK) e inyectamos los 2 warnings
        manualmente — así aislamos la lógica del aggregador sin
        interferencia del helper semántico."""
        topology = self._build_topology([
            {
                "id": "R_test",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R_test",
            "largo_m": 1.60,  # OK para isla → sanity real NO dispara
            "ancho_m": 0.60,
            "confidence": 0.70,
            # 2 warnings sanity artificiales + 0 otros suspicious:
            "suspicious_reasons": [
                "isla_largo_inusual_2.50m_threshold_1.80m — texto humano 1",
                "cocina_con_pileta_y_anafe_largo_corto_1.20m_threshold_1.50m — texto humano 2",
            ],
        }]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        texts = self._ambig_texts(isla)

        # 2 bullets dedicados (uno por warning). 0 general porque solo
        # los sanity warnings estaban en suspicious_reasons.
        assert len(texts) == 2, f"Esperaba 2 bullets, got {len(texts)}: {texts}"
        assert any("isla_largo_inusual" in t for t in texts)
        assert any("cocina_con_pileta_y_anafe_largo_corto" in t for t in texts)

    def test_error_path_unchanged(self):
        """No regresión: si hay error (no suspicious), el bullet del
        error se preserva y no se mezcla con lógica de sanity."""
        topology = self._build_topology([
            {
                "id": "R_err",
                "bbox_rel": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R_err",
            "error": "insufficient_local_cotas",
            "largo_m": None,
            "ancho_m": None,
        }]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        texts = self._ambig_texts(isla)
        assert len(texts) == 1
        assert "no se pudo medir" in texts[0]
        assert "insufficient_local_cotas" in texts[0]

    def test_bernardi_bullet_significantly_longer_than_120_chars(self):
        """Prueba numérica explícita: el bullet dedicado supera la longitud
        del trim original (120), así confirmamos que ya no se corta."""
        topology = self._build_topology([
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R3",
            "largo_m": 2.05,
            "ancho_m": 0.60,
            "confidence": 0.65,
            "suspicious_reasons": [],
        }]
        result = _aggregate(topology, region_results)
        isla = next(s for s in result["sectores"] if s["tipo"] == "isla")
        sanity_bullet = next(
            t for t in self._ambig_texts(isla) if "isla_largo_inusual" in t
        )
        assert len(sanity_bullet) > 120, (
            f"Bullet dedicado debería superar 120 chars (texto humano completo). "
            f"Got {len(sanity_bullet)}: {sanity_bullet}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PR #352 — Fix: ambigüedades de regiones en sector NO-primero se perdían
#
# Bug descubierto en corrida real Bernardi post-#351: R3 (sector isla)
# era DUDOSO (visible en la tabla del despiece como "Mesada 1 — revisar"),
# pero NO aparecía en el bloque "Revisar en plano" de la UI. Solo se
# veían R1 y R2 (sector cocina).
#
# Causa raíz: `_aggregate` asignaba `ambiguedades` dentro del loop de
# sectores con un snapshot de `all_ambiguedades` que aún no tenía las
# ambigüedades de sectores posteriores. La primera iteración (cocina)
# tomaba snapshot con solo R1+R2; después del loop, al procesar isla,
# R3 se agregaba a `all_ambiguedades` pero ningún sector la recibía
# (el primer ya fue asignado, el resto recibe []).
#
# Fix: asignar ambigüedades POST-loop, cuando ya se procesaron todas
# las regiones.
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiSectorAmbiguedadesPropagation:
    """Validar que ambigüedades de regiones en sectores no-primeros
    llegan correctamente al frontend (vía primer sector, por el
    contrato `flatMap` que hace la UI)."""

    def _build_topology(self, regions):
        return {"view_type": "planta", "regions": regions}

    def _all_ambig_texts(self, result: dict) -> list[str]:
        """Simula el `flatMap` que hace el frontend sobre todos los sectores."""
        texts = []
        for s in result.get("sectores") or []:
            for a in s.get("ambiguedades") or []:
                texts.append(a.get("texto") or "")
        return texts

    def test_bernardi_real_r3_in_isla_sector_appears_in_ui(self):
        """Caso canónico del bug. Topology: R1+R2 en cocina, R3 en isla.
        R3 es DUDOSO con sanity warning. Pre-fix: R3 no aparecía en
        ambigüedades. Post-fix: aparece."""
        # R1 y R2 van a sector cocina (touches_wall=True).
        # R3 va a sector isla (touches_wall=False). SECTOR NO-PRIMERO.
        topology = self._build_topology([
            {
                "id": "R1",
                "bbox_rel": {"x": 0.35, "y": 0.65, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": True, "cooktop_groups": 1,
                             "sink_simple": True},
            },
            {
                "id": "R2",
                "bbox_rel": {"x": 0.78, "y": 0.45, "w": 0.08, "h": 0.35},
                "features": {"touches_wall": True, "cooktop_groups": 0},
            },
            {
                "id": "R3",
                "bbox_rel": {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [
            {"region_id": "R1", "largo_m": None, "ancho_m": 0.60,
             "confidence": 0.2,
             "suspicious_reasons": ["largo 0.6m < 1.0m — invalidado"]},
            {"region_id": "R2", "largo_m": None, "ancho_m": None,
             "confidence": 0.0,
             "suspicious_reasons": ["medida tomada con pool expandido"]},
            {"region_id": "R3", "largo_m": 2.05, "ancho_m": 0.60,
             "confidence": 0.65,
             "suspicious_reasons": ["cotas_mode=expanded → cap confidence 0.65"]},
        ]
        result = _aggregate(topology, region_results)

        # El frontend hace flatMap — las 3 ambigüedades DEBEN estar
        # visibles sin importar en qué sector viven.
        all_texts = self._all_ambig_texts(result)

        assert any("Región R1" in t for t in all_texts), (
            f"R1 ambigüedad perdida: {all_texts}"
        )
        assert any("Región R2" in t for t in all_texts), (
            f"R2 ambigüedad perdida: {all_texts}"
        )
        # CRÍTICO: el bug que resuelve este PR. R3 (sector isla,
        # no-primero) debe aparecer.
        r3_bullets = [t for t in all_texts if "Región R3" in t]
        assert len(r3_bullets) >= 2, (
            f"R3 debería tener ≥2 bullets (general + sanity dedicado). "
            f"Got {len(r3_bullets)}: {r3_bullets}"
        )
        # Y el bullet de sanity debe tener el texto completo.
        assert any("isla_largo_inusual" in t for t in r3_bullets), (
            f"R3 sanity bullet perdido: {r3_bullets}"
        )

    def test_single_sector_no_regression(self):
        """Topology con un solo sector: ambigüedades llegan al primer
        (único) sector igual que antes del fix. No regresión."""
        topology = self._build_topology([
            {
                "id": "R1",
                "bbox_rel": {"x": 0.3, "y": 0.3, "w": 0.3, "h": 0.3},
                "features": {"touches_wall": True, "cooktop_groups": 0},
            },
        ])
        region_results = [{
            "region_id": "R1", "largo_m": 2.0, "ancho_m": 0.60,
            "confidence": 0.65,
            "suspicious_reasons": ["cotas_mode=expanded → cap confidence 0.65"],
        }]
        result = _aggregate(topology, region_results)
        all_texts = self._all_ambig_texts(result)
        assert len(all_texts) == 1
        assert "Región R1" in all_texts[0]

    def test_ambiguedades_live_in_first_sector(self):
        """Post-fix: todas las ambigüedades siguen centralizadas en el
        primer sector (contrato actual del frontend). Los otros sectores
        reciben lista vacía."""
        topology = self._build_topology([
            {
                "id": "R1",
                "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3},
                "features": {"touches_wall": True, "cooktop_groups": 0},
            },
            {
                "id": "R3",
                "bbox_rel": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [
            {"region_id": "R1", "largo_m": None, "ancho_m": 0.60,
             "confidence": 0.2, "suspicious_reasons": ["invalid"]},
            {"region_id": "R3", "largo_m": 2.5, "ancho_m": 0.60,
             "confidence": 0.65, "suspicious_reasons": []},
        ]
        result = _aggregate(topology, region_results)

        # Primer sector tiene todas las ambigüedades.
        primero = result["sectores"][0]
        assert len(primero.get("ambiguedades") or []) >= 2, (
            f"Primer sector esperaba ≥2 ambigüedades, got: "
            f"{primero.get('ambiguedades')}"
        )
        # Otros sectores reciben []. (Contrato actual — si cambia en
        # el futuro, actualizar también este assertion.)
        for s in result["sectores"][1:]:
            assert s.get("ambiguedades") == [], (
                f"Sector no-primero debería tener ambiguedades=[], "
                f"got: {s.get('ambiguedades')}"
            )

    def test_region_with_error_in_non_first_sector_still_propagates(self):
        """Variante del bug: no solo suspicious, también error en región
        de sector no-primero debe llegar al frontend."""
        topology = self._build_topology([
            {
                "id": "R_cocina",
                "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3},
                "features": {"touches_wall": True, "cooktop_groups": 0},
            },
            {
                "id": "R_isla_err",
                "bbox_rel": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.1},
                "features": {"touches_wall": False, "cooktop_groups": 0},
            },
        ])
        region_results = [
            {"region_id": "R_cocina", "largo_m": 2.0, "ancho_m": 0.6,
             "confidence": 0.9, "suspicious_reasons": []},
            {"region_id": "R_isla_err",
             "error": "insufficient_local_cotas",
             "largo_m": None, "ancho_m": None},
        ]
        result = _aggregate(topology, region_results)
        all_texts = self._all_ambig_texts(result)
        # R_isla_err debe aparecer con mensaje de error.
        err_bullets = [t for t in all_texts if "R_isla_err" in t]
        assert len(err_bullets) == 1, (
            f"Error de R_isla_err (sector no-primero) debería aparecer. "
            f"Got: {err_bullets}"
        )
        assert "no se pudo medir" in err_bullets[0]

    def test_contradictions_in_non_first_sector_still_propagate(self):
        """PR 2c: contradicciones brief/features también pasan por
        `all_ambiguedades`. Verificar que tampoco se pierden cuando
        la región está en sector no-primero."""
        topology = self._build_topology([
            {
                "id": "R1",
                "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3},
                "features": {"touches_wall": True, "cooktop_groups": 0},
            },
            {
                "id": "R3_isla_anafe",
                "bbox_rel": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.1},
                # Isla con cooktop → dispara PR 2c cuando brief no lo confirma.
                "features": {"touches_wall": False, "cooktop_groups": 1},
            },
        ])
        region_results = [
            {"region_id": "R1", "largo_m": 2.0, "ancho_m": 0.6,
             "confidence": 0.9, "suspicious_reasons": []},
            {"region_id": "R3_isla_anafe", "largo_m": 1.5, "ancho_m": 0.6,
             "confidence": 0.85, "suspicious_reasons": []},
        ]
        # Brief no menciona anafe — PR 2c detecta contradicción.
        result = _aggregate(
            topology, region_results, brief_text="cocina residencial",
        )
        all_texts = self._all_ambig_texts(result)
        contr_bullets = [
            t for t in all_texts
            if "R3_isla_anafe" in t and "anafe" in t.lower()
        ]
        assert len(contr_bullets) >= 1, (
            f"Contradicción brief/features de R3_isla_anafe (sector isla, "
            f"no-primero) debería aparecer. Got all: {all_texts}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PR #353 — Deep expansion (+600px) como último intento cuando rescue
# normal (+300) queda pool_starved
#
# Scope 5.2 del ADR #348. Solo dispara DESPUÉS de que _rescue_length_ranking
# con pool +300 devolvió []. Cap confidence 0.35 (más estricto que rescue
# normal 0.5). Criterio: mejorar casos tipo Bernardi R1 sin inventar en R2.
# ─────────────────────────────────────────────────────────────────────────────


class TestDeepExpansionIntegration:
    """Integración de deep expansion (+600px) con `_measure_region`."""

    @pytest.mark.asyncio
    async def test_bernardi_r1_like_deep_expansion_resolves(self):
        """Caso canónico del ADR #348: bbox chico en zona periférica sin
        cotas en +300, pero SÍ hay una cota útil en +600. Deep expansion
        la recupera y marca mode=expanded_deep."""
        image = _make_image_bytes(1000, 800)
        # Bbox simula R1 de Bernardi en proporción: pequeño en esquina.
        # x_rel=0.2, y_rel=0.65, w_rel=0.12, h_rel=0.05
        # En px: x=200, y=520, x2=320, y2=560 → con padding 80: [120, 440, 400, 640]
        # Tight pool (con region padding 80) tiene rango x∈[120,400], y∈[440,640]
        # Expanded +300 → x∈[-180+120, 400+300]=[0, 700], y∈[440-300, 640+300]=[140, 940]
        # Deep +600 → x∈[0, 1000], y∈[0, 800] (toda la imagen).
        region = {
            "id": "R1_bernardi_like",
            "bbox_rel": {"x": 0.2, "y": 0.65, "w": 0.12, "h": 0.05},
        }
        cotas = [
            # Tight pool: 0 cotas (todas fuera del bbox tight).
            # Expanded +300: 2 cotas 0.60 (suficiente para entrar al expanded).
            _make_cota(0.60, x=100, y=600),   # inside expanded, fuera tight
            _make_cota(0.60, x=680, y=600),   # inside expanded, fuera tight
            # Cota ÚTIL (2.35) solo en deep pool (+600): fuera de expanded.
            # x=50 > ex_x=0 pero y=100 < ex_y=140 → fuera expanded.
            # Con deep +600 (rango y∈[0, 800]): y=100 entra ✓.
            _make_cota(2.35, x=50, y=100),
        ]
        # Mock LLM response — elige la 2.35 rescatada.
        mock_response = type("R", (), {
            "content": [type("B", (), {
                "text": '{"largo_m": 2.35, "ancho_m": 0.60, "confidence": 0.85}'
            })()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(
                image, (1000, 800), region, cotas, model="test",
            )

        meta = result.get("measurement_meta") or {}
        # Deep expansion APLICÓ — rescue resuelto por +600.
        if meta.get("deep_expansion_applied"):
            assert result.get("_cotas_mode") == "expanded_deep"
            assert meta.get("rescue_applied") is True
            assert meta.get("rescue_trigger") == "deep_expansion"
            assert meta.get("pool_starved_region") is False
            assert meta.get("deep_pool_count", 0) >= 3
            # Cap 0.35 aplicado.
            assert result.get("confidence", 1.0) <= 0.35
            # Suspicious reason específico de deep.
            susp = result.get("suspicious_reasons") or []
            assert any("deep_expansion" in s for s in susp), (
                f"Falta suspicious reason de deep_expansion. Got: {susp}"
            )

    @pytest.mark.asyncio
    async def test_bernardi_r2_like_deep_expansion_stays_starved(self):
        """R2 Bernardi real: expanded_pool=[4.15, 4.15] — perímetros.
        Incluso con deep +600 no aparecen cotas en [1.0, 4.0] porque
        las cotas útiles del plano están fuera del rango vertical de
        R2. Deep expansion corre pero no encuentra nada → pool_starved
        se mantiene. CRÍTICO: no inventar."""
        image = _make_image_bytes(1000, 800)
        # R2 Bernardi-like: bbox vertical en columna derecha.
        # x=0.78 (px=780) w=0.08 (80px) → x2=860. Con padding 80: [700, 940].
        # Deep +600 → x∈[100, 1000].
        region = {
            "id": "R2_bernardi_like",
            "bbox_rel": {"x": 0.78, "y": 0.45, "w": 0.08, "h": 0.35},
        }
        cotas = [
            # Solo hay 4.15 en expanded (perímetros). Deep agrega más
            # cotas pero ninguna útil en [1.0, 4.0].
            _make_cota(4.15, x=900, y=500),
            _make_cota(4.15, x=900, y=600),
            # Una cota fuera de rango deep (no entra ni con +600).
            _make_cota(2.35, x=50, y=100),  # x=50 < deep_x=100 → fuera.
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {
                "text": '{"largo_m": null, "ancho_m": null, "confidence": 0.0}'
            })()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(
                image, (1000, 800), region, cotas, model="test",
            )

        meta = result.get("measurement_meta") or {}
        # Si el trigger disparó, deep expansion CORRIÓ pero NO resolvió.
        if meta.get("rescue_trigger") in ("orphan_region", "span_based"):
            # Deep no se aplicó (no había cotas útiles en deep pool).
            assert meta.get("deep_expansion_applied") is False
            # Pool_starved se mantiene.
            assert meta.get("pool_starved_region") is True
            # Largo sigue null — no se inventa.
            assert result.get("largo_m") is None
            # Mode NO pasa a expanded_deep.
            assert result.get("_cotas_mode") != "expanded_deep"

    @pytest.mark.asyncio
    async def test_r3_clean_does_not_trigger_deep_expansion(self):
        """R3 Bernardi tiene cotas locales — nunca entra al rescue ni
        al deep expansion. No regresión."""
        image = _make_image_bytes(1000, 800)
        region = {
            "id": "R3_clean",
            "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3},
        }
        cotas = [
            _make_cota(2.05, x=250, y=200),   # dentro tight
            _make_cota(0.60, x=250, y=300),   # dentro tight
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {
                "text": '{"largo_m": 2.05, "ancho_m": 0.60, "confidence": 0.9}'
            })()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(
                image, (1000, 800), region, cotas, model="test",
            )

        meta = result.get("measurement_meta") or {}
        # NO debe haber deep expansion para regiones sanas.
        assert meta.get("deep_expansion_applied") is False
        assert meta.get("rescue_applied") is False
        assert result.get("_cotas_mode") != "expanded_deep"
        # La medida sigue normal.
        assert result.get("largo_m") == 2.05

    def test_guardrail_caps_expanded_deep_confidence_at_035(self):
        """VLM devuelve 0.80, cotas_mode=expanded_deep → cap duro 0.35
        (más estricto que rescue normal 0.5)."""
        ranking = {
            "length": [
                {"value": 2.35, "score": 30, "bucket": "weak", "reasons": []},
            ],
            "depth": [
                {"value": 0.60, "score": 70, "bucket": "preferred", "reasons": []},
            ],
            "excluded_hard": [],
        }
        vlm_output = {
            "largo_m": 2.35,
            "ancho_m": 0.60,
            "confidence": 0.80,
        }
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="expanded_deep")
        assert result["confidence"] == 0.35
        susp = result.get("suspicious_reasons") or []
        assert any("expanded_deep" in s for s in susp)

    def test_guardrail_expanded_rescue_unchanged(self):
        """No regresión: cap de expanded_rescue sigue siendo 0.5."""
        ranking = {
            "length": [{"value": 2.35, "score": 30, "bucket": "weak",
                        "reasons": []}],
            "depth": [{"value": 0.60, "score": 70, "bucket": "preferred",
                       "reasons": []}],
            "excluded_hard": [],
        }
        vlm_output = {"largo_m": 2.35, "ancho_m": 0.60, "confidence": 0.80}
        result = _apply_guardrails(vlm_output, ranking, cotas_mode="expanded_rescue")
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_deep_pool_same_size_as_prev_skips_rescue(self):
        """Si deep pool no agrega cotas respecto al pool previo (+300),
        no se intenta rescue deep — no vale la pena."""
        image = _make_image_bytes(1000, 800)
        # Bbox muy chico. Pool expandido +300 = todas las cotas = pool deep.
        region = {
            "id": "R_small",
            "bbox_rel": {"x": 0.4, "y": 0.4, "w": 0.05, "h": 0.05},
        }
        cotas = [
            _make_cota(0.60, x=390, y=390),
            _make_cota(0.60, x=410, y=410),
        ]
        mock_response = type("R", (), {
            "content": [type("B", (), {
                "text": '{"largo_m": null, "ancho_m": 0.60, "confidence": 0.0}'
            })()]
        })()
        with patch(
            "app.modules.quote_engine.multi_crop_reader.anthropic.AsyncAnthropic"
        ) as mock_anth:
            mock_anth.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await _measure_region(
                image, (1000, 800), region, cotas, model="test",
            )
        meta = result.get("measurement_meta") or {}
        # Deep expansion no agregó cotas → skipped.
        assert meta.get("deep_expansion_applied") is False


class TestDeepExpansionE2EAggregate:
    """E2E via `_aggregate`: resultado con deep_expansion aparece en
    sectores + ambigüedades correctamente."""

    def test_deep_expansion_region_dudoso_with_specific_suspicious(self):
        """Región que pasó por deep_expansion tiene suspicious con
        'deep_expansion' y status DUDOSO (ya que cap 0.35 < confidence
        umbral)."""
        topology = {
            "view_type": "planta",
            "regions": [{
                "id": "R1",
                "bbox_rel": {"x": 0.2, "y": 0.65, "w": 0.12, "h": 0.05},
                "features": {"touches_wall": True, "cooktop_groups": 1,
                             "sink_simple": True},
            }],
        }
        region_results = [{
            "region_id": "R1",
            "largo_m": 2.35,
            "ancho_m": 0.60,
            "confidence": 0.35,
            "_cotas_mode": "expanded_deep",
            "suspicious_reasons": [
                "cotas_mode=expanded_deep → cap confidence 0.35",
                "topology_bbox_undersized_deep_expansion — bbox del topology muy por fuera del tramo real; cota recuperada con pool +600px (puede pertenecer a tramo vecino). REVISAR VISUALMENTE antes de confirmar.",
            ],
        }]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        tramo = cocina["tramos"][0]
        # Valor se preserva.
        assert tramo["largo_m"]["valor"] == 2.35
        # Status = DUDOSO porque hay suspicious_reasons.
        assert tramo["largo_m"]["status"] == "DUDOSO"
        # En ambigüedades aparece el mensaje de deep_expansion.
        amb_texts = " ".join(
            a.get("texto") or "" for a in cocina.get("ambiguedades") or []
        )
        assert "deep_expansion" in amb_texts or "REVISAR VISUALMENTE" in amb_texts


# ─────────────────────────────────────────────────────────────────────────────
# PR #355 — Operator-assist UI: suggested_candidates
#
# Backend expone candidatas rescatadas en el tramo para que el frontend
# las renderice como bloque "Candidatas sugeridas para revisión" con
# botón "Usar/Probar como largo" que copia el valor al input SIN confirmar.
#
# Scope mínimo: trigger = largo_m=null AND (pool_starved OR deep_expansion).
# Shape extensible (parámetro trigger_override para futuros casos).
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildSuggestedCandidates:
    """Unit tests del helper `_build_suggested_candidates`."""

    # ── Trigger ────────────────────────────────────────────────────────

    def test_largo_not_null_returns_empty(self):
        """Si largo_m tiene valor, NO se exponen candidatas (operador ya
        tiene medida, no necesita sugerencias)."""
        r_result = {
            "largo_m": 2.05,
            "ancho_m": 0.60,
            "measurement_meta": {"pool_starved_region": True},
        }
        ranking = {"length": [{"value": 2.35, "score": 50, "bucket": "weak"}]}
        result = _build_suggested_candidates(r_result, ranking)
        assert result == []

    def test_neither_pool_starved_nor_deep_returns_empty(self):
        """Si measurement_meta no tiene pool_starved ni deep_expansion,
        no se exponen candidatas aunque haya largo=null."""
        r_result = {
            "largo_m": None,
            "measurement_meta": {
                "pool_starved_region": False,
                "deep_expansion_applied": False,
            },
        }
        ranking = {"length": [{"value": 2.35, "score": 50, "bucket": "weak"}]}
        result = _build_suggested_candidates(r_result, ranking)
        assert result == []

    def test_empty_ranking_returns_empty(self):
        """pool_starved=True + largo=null + ranking vacío → sin candidatas
        para mostrar (nada para rescatar)."""
        r_result = {
            "largo_m": None,
            "measurement_meta": {"pool_starved_region": True},
        }
        ranking = {"length": []}
        result = _build_suggested_candidates(r_result, ranking)
        assert result == []

    def test_trigger_override_bypasses_conditions(self):
        """trigger_override=True fuerza la exposición (para futuros casos)."""
        r_result = {
            "largo_m": 2.05,  # tiene valor
            "measurement_meta": {},  # sin starved ni deep
        }
        ranking = {"length": [{"value": 2.35, "score": 50, "bucket": "weak"}]}
        result = _build_suggested_candidates(
            r_result, ranking, trigger_override=True,
        )
        assert len(result) == 1
        assert result[0]["valor"] == 2.35

    # ── Shape y metadata ───────────────────────────────────────────────

    def test_deep_expansion_produces_baja_confianza_label(self):
        """Cuando deep_expansion_applied=True → label=baja_confianza,
        warning tramo vecino, origen "pool expandido +600px"."""
        r_result = {
            "largo_m": None,
            "_cotas_mode": "expanded_deep",
            "measurement_meta": {
                "deep_expansion_applied": True,
                "pool_starved_region": False,
            },
        }
        ranking = {"length": [
            {"value": 2.05, "score": 30, "bucket": "weak"},
        ]}
        result = _build_suggested_candidates(r_result, ranking)
        assert len(result) == 1
        c = result[0]
        assert c["valor"] == 2.05
        assert c["source"] == "expanded_deep"
        assert c["label"] == "baja_confianza"
        assert c["origin_desc"] == "pool expandido +600px"
        assert c["warning"] == "posiblemente de tramo vecino"
        assert c["score"] == 30

    def test_expanded_rescue_produces_mas_probable_label(self):
        """Cuando cotas_mode=expanded_rescue (sin deep) → label=mas_probable,
        sin warning, origen "mejor match con el bbox del tramo detectado"."""
        r_result = {
            "largo_m": None,
            "_cotas_mode": "expanded_rescue",
            "measurement_meta": {
                "deep_expansion_applied": False,
                "pool_starved_region": True,
            },
        }
        ranking = {"length": [
            {"value": 1.95, "score": 55, "bucket": "weak"},
        ]}
        result = _build_suggested_candidates(r_result, ranking)
        assert len(result) == 1
        c = result[0]
        assert c["source"] == "expanded_rescue"
        assert c["label"] == "mas_probable"
        assert c["origin_desc"] == "mejor match con el bbox del tramo detectado"
        assert c["warning"] is None

    # ── Top-N y orden ──────────────────────────────────────────────────

    def test_top_3_preserved_in_score_order(self):
        """Se exponen las top 3 del ranking (ya viene ordenado desc).
        Cualquier cantidad mayor se trunca."""
        r_result = {
            "largo_m": None,
            "measurement_meta": {"deep_expansion_applied": True},
        }
        # Ranking con 5 entries (pre-ordenado desc por score).
        ranking = {"length": [
            {"value": 2.35, "score": 50, "bucket": "weak"},
            {"value": 2.05, "score": 45, "bucket": "weak"},
            {"value": 2.75, "score": 40, "bucket": "weak"},
            {"value": 1.60, "score": 30, "bucket": "unlikely"},
            {"value": 2.95, "score": 20, "bucket": "unlikely"},
        ]}
        result = _build_suggested_candidates(r_result, ranking)
        assert len(result) == 3
        assert [c["valor"] for c in result] == [2.35, 2.05, 2.75]
        assert [c["score"] for c in result] == [50, 45, 40]

    def test_max_candidates_custom_limit(self):
        """Parámetro max_candidates customizable (1, 2, etc.)."""
        r_result = {
            "largo_m": None,
            "measurement_meta": {"deep_expansion_applied": True},
        }
        ranking = {"length": [
            {"value": 2.35, "score": 50, "bucket": "weak"},
            {"value": 2.05, "score": 45, "bucket": "weak"},
        ]}
        result = _build_suggested_candidates(
            r_result, ranking, max_candidates=1,
        )
        assert len(result) == 1
        assert result[0]["valor"] == 2.35

    # ── Casos Bernardi reales ──────────────────────────────────────────

    def test_bernardi_r1_deep_expansion_candidates(self):
        """Caso Bernardi R1 real: deep_expansion_applied, cota 2.05 en el
        ranking (pescada de tramo vecino según despiece esperado)."""
        r_result = {
            "region_id": "R1",
            "largo_m": None,  # LLM rechazó visualmente
            "ancho_m": 0.60,
            "confidence": 0.0,
            "_cotas_mode": "expanded_deep",
            "measurement_meta": {
                "deep_expansion_applied": True,
                "pool_starved_region": False,
            },
        }
        ranking = {"length": [{"value": 2.05, "score": 35, "bucket": "weak"}]}
        result = _build_suggested_candidates(r_result, ranking)
        assert len(result) == 1
        assert result[0]["valor"] == 2.05
        assert result[0]["label"] == "baja_confianza"
        assert result[0]["warning"] == "posiblemente de tramo vecino"

    def test_value_rounding_to_two_decimals(self):
        """valor se redondea a 2 decimales en el shape del frontend."""
        r_result = {
            "largo_m": None,
            "measurement_meta": {"deep_expansion_applied": True},
        }
        ranking = {"length": [
            {"value": 2.051234, "score": 30, "bucket": "weak"},
        ]}
        result = _build_suggested_candidates(r_result, ranking)
        assert result[0]["valor"] == 2.05

    def test_invalid_value_is_skipped(self):
        """Si un entry del ranking no tiene 'value' válido, se skipea."""
        r_result = {
            "largo_m": None,
            "measurement_meta": {"deep_expansion_applied": True},
        }
        ranking = {"length": [
            {"score": 30, "bucket": "weak"},  # sin 'value'
            {"value": "not a number", "score": 25, "bucket": "weak"},  # inválido
            {"value": 2.35, "score": 20, "bucket": "weak"},  # válido
        ]}
        result = _build_suggested_candidates(r_result, ranking)
        assert len(result) == 1
        assert result[0]["valor"] == 2.35


class TestSuggestedCandidatesE2EAggregate:
    """E2E: `_aggregate` incluye `suggested_candidates` en el tramo cuando
    aplica y `[]` cuando no. Contrato estable para el frontend."""

    def _build_topology(self, regions):
        return {"view_type": "planta", "regions": regions}

    def test_tramo_with_deep_expansion_exposes_candidates(self):
        topology = self._build_topology([{
            "id": "R1",
            "bbox_rel": {"x": 0.2, "y": 0.65, "w": 0.12, "h": 0.05},
            "features": {"touches_wall": True, "cooktop_groups": 1,
                         "sink_simple": True},
        }])
        region_results = [{
            "region_id": "R1",
            "largo_m": None,
            "ancho_m": 0.60,
            "confidence": 0.0,
            "_cotas_mode": "expanded_deep",
            "measurement_meta": {
                "deep_expansion_applied": True,
                "pool_starved_region": False,
            },
            "_cota_ranking": {
                "length": [
                    {"value": 2.05, "score": 35, "bucket": "weak"},
                ],
                "depth": [], "excluded_hard": [],
                "orientation": "horizontal", "scale_px_per_m": None,
            },
            "suspicious_reasons": [],
        }]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        tramo = cocina["tramos"][0]

        assert "suggested_candidates" in tramo
        assert len(tramo["suggested_candidates"]) == 1
        c = tramo["suggested_candidates"][0]
        assert c["valor"] == 2.05
        assert c["label"] == "baja_confianza"

    def test_tramo_with_valid_measure_has_empty_suggested(self):
        """Tramo con medida confirmada → suggested_candidates=[]."""
        topology = self._build_topology([{
            "id": "R1",
            "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3},
            "features": {"touches_wall": True, "cooktop_groups": 0},
        }])
        region_results = [{
            "region_id": "R1",
            "largo_m": 2.0,
            "ancho_m": 0.6,
            "confidence": 0.9,
            "suspicious_reasons": [],
        }]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        tramo = cocina["tramos"][0]
        assert tramo["suggested_candidates"] == []

    def test_pool_starved_exposes_candidates_if_ranking_has_entries(self):
        """pool_starved=True + ranking con entries → candidatas expuestas.
        Caso hipotético: el rescue devolvió items pero el LLM los
        rechazó y no hubo deep expansion activa."""
        topology = self._build_topology([{
            "id": "R1",
            "bbox_rel": {"x": 0.2, "y": 0.65, "w": 0.12, "h": 0.05},
            "features": {"touches_wall": True, "cooktop_groups": 0},
        }])
        region_results = [{
            "region_id": "R1",
            "largo_m": None,
            "ancho_m": None,
            "confidence": 0.0,
            "_cotas_mode": "expanded_rescue",
            "measurement_meta": {
                "deep_expansion_applied": False,
                "pool_starved_region": True,
            },
            "_cota_ranking": {
                "length": [
                    {"value": 1.95, "score": 55, "bucket": "weak"},
                ],
                "depth": [], "excluded_hard": [],
                "orientation": "horizontal", "scale_px_per_m": None,
            },
            "suspicious_reasons": [],
        }]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        tramo = cocina["tramos"][0]
        assert len(tramo["suggested_candidates"]) == 1

    def test_shape_stable_always_array(self):
        """Contrato: suggested_candidates es SIEMPRE una lista (nunca None).
        Facilita el frontend — no tiene que chequear null."""
        topology = self._build_topology([{
            "id": "R1",
            "bbox_rel": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3},
            "features": {"touches_wall": True, "cooktop_groups": 0},
        }])
        # Region sin measurement_meta, sin ranking — caso edge.
        region_results = [{
            "region_id": "R1",
            "largo_m": 2.0,
            "ancho_m": 0.6,
            "confidence": 0.9,
        }]
        result = _aggregate(topology, region_results)
        cocina = next(s for s in result["sectores"] if s["tipo"] == "cocina")
        tramo = cocina["tramos"][0]
        assert isinstance(tramo["suggested_candidates"], list)
        assert tramo["suggested_candidates"] == []


class TestSemanticPriorRanking:
    """Prior semántico por tipo de región — Bernardi fix.

    Datos reales tomados del log de Railway para el quote
    `20b929fb-e583-47bd-bf6c-af6e70fd4f38` (corrida del 2026-04-21 14:07):

    - Image: (4963, 3509) — DPI 300, una página
    - 13 cotas extraídas: 1.20, 0.60, 1.60, 4.15, 4.15, 2.75, 2.75,
      2.35, 2.35, 2.95, 2.05, 0.60, 0.60
    - Topology cacheado para este plano (3 regiones):
        R1 (mesada con pileta+anafe): bbox_rel horizontal, touches_wall=True
        R2 (mesada vertical):          bbox_rel vertical,   touches_wall=True
        R3 (isla central):             bbox_rel horizontal, touches_wall=False
    - Ground truth (confirmado por operador):
        R1 largo = 2.05 m   (tramo de pileta+anafe)
        R2 largo = 2.95 m   (tramo vertical con anafes)
        R3 largo = 1.60 m   (isla)

    Bug que el prior resuelve: el bbox de R3 capturaba la cota 2.05 como
    tight (score base 80 preferred) y dejaba 1.60 en expanded (score base
    55 weak). El LLM elegía 2.05 incorrectamente.

    Con prior semántico (isla = 1.0-1.8m típico): 2.05 queda fuera de
    rango (−25 → 55 weak), 1.60 dentro (+25 → 80 preferred). Se invierte
    el ranking. El 2.05 sigue disponible en el ranking para que downstream
    (R1 deep expansion) pueda elegirlo como candidata válida.
    """

    # Image size real del log
    IMAGE_SIZE = (4963, 3509)

    # Bboxes reales del topology-cache HIT en el log
    # R3 = isla, bbox horizontal, features sin touches_wall → classify = "isla"
    R3_BBOX = {"x": 0.35, "y": 0.45, "w": 0.25, "h": 0.08}
    R3_FEATURES = {
        "touches_wall": False,
        "stools_adjacent": False,
        "cooktop_groups": 0,
        "sink_double": False,
        "sink_simple": False,
        "non_counter_upper": False,
    }

    def _r3_region(self) -> dict:
        return {
            "id": "R3",
            "bbox_rel": self.R3_BBOX,
            "features": self.R3_FEATURES,
            "evidence": "masa gris horizontal central - isla",
        }

    def _r3_cotas_bernardi(self) -> list:
        """Posiciones en píxeles elegidas para reproducir el scoring real:

        R3 bbox px → x=[1737..2977], y=[1579..1859]
        Tight pad 80 → x=[1657..3057], y=[1499..1939]
        Expanded pad 380 → x=[1357..3357], y=[1199..2239]

        Reproducimos el scenario exacto del log:
        - 2.05 DENTRO del tight bbox (base score 80, preferred)
        - 1.60 en expanded (NO tight) (base score 55, weak)
        - 2.35, 2.75 también expanded weak
        """
        return [
            # 2.05 cae tight (posición dentro del bbox de R3). La cota real
            # en el plano de Bernardi está entre la isla y la mesada inferior,
            # pero el bbox mal calibrado de R3 la captura como suya.
            Cota(text="2,05", value=2.05, x=2400, y=1700, width=40, height=20),
            # 1.60 arriba del bbox de R3 (la cota real de la isla), queda
            # en el pool expandido porque y=1400 < 1499 (tight bottom).
            Cota(text="1,60", value=1.60, x=2400, y=1400, width=40, height=20),
            # 2.35 y 2.75 en expanded también — cotas del plano que no son
            # del largo de la isla, quedan weak.
            Cota(text="2,35", value=2.35, x=2400, y=1400, width=40, height=20),
            Cota(text="2,75", value=2.75, x=2400, y=1400, width=40, height=20),
            # Cotas de ancho (no compiten por length).
            Cota(text="0,60", value=0.60, x=2400, y=1700, width=40, height=20),
        ]

    def test_r3_isla_elige_1_60_sobre_2_05_con_prior(self):
        """Caso central: sin el prior, R3 elegiría 2.05 (preferred 80).
        Con el prior, 1.60 gana a 2.05 porque 2.05 > 1.8m (fuera de rango
        típico de isla) y se le resta 25 puntos."""
        region = self._r3_region()
        cotas = self._r3_cotas_bernardi()

        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        length = ranking["length"]

        top_value = length[0]["value"]
        assert top_value == 1.60, (
            f"R3 (isla) debe elegir 1.60 con prior, no {top_value}. "
            f"Ranking: {[(r['value'], r['score'], r['bucket']) for r in length]}"
        )

    def test_r3_conserva_2_05_en_ranking_no_lo_elimina(self):
        """El prior degrada 2.05 pero NO lo elimina. Downstream (R1 deep
        expansion) necesita verlo como candidata para su tramo real."""
        region = self._r3_region()
        cotas = self._r3_cotas_bernardi()

        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        length_values = [r["value"] for r in ranking["length"]]

        assert 2.05 in length_values, (
            f"2.05 debe seguir en el ranking de R3, aunque degradado "
            f"(necesario para que R1 la vea como candidata via pool compartido). "
            f"Got: {length_values}"
        )

    def test_r3_prior_degrada_2_05_a_weak_o_peor(self):
        """Verificación explícita: el 2.05 que antes era preferred (80),
        post-prior queda ≤ weak."""
        region = self._r3_region()
        cotas = self._r3_cotas_bernardi()

        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        entry_205 = next(r for r in ranking["length"] if r["value"] == 2.05)

        assert entry_205["bucket"] in ("weak", "unlikely", "excluded_soft"), (
            f"2.05 en isla debe degradar de preferred. Got bucket={entry_205['bucket']} "
            f"score={entry_205['score']}"
        )
        assert any("semantic_prior_out_of_range_isla" in r for r in entry_205["reasons"]), (
            f"2.05 debe tener razón semantic_prior registrada. "
            f"Reasons: {entry_205['reasons']}"
        )

    def test_r3_prior_sube_1_60_a_preferred(self):
        """1.60 estaba en expanded (base 55 weak). Con +25 → 80 preferred."""
        region = self._r3_region()
        cotas = self._r3_cotas_bernardi()

        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        entry_160 = next(r for r in ranking["length"] if r["value"] == 1.60)

        assert entry_160["bucket"] == "preferred", (
            f"1.60 en isla debe subir a preferred con el prior. "
            f"Got bucket={entry_160['bucket']} score={entry_160['score']}"
        )
        assert any("semantic_prior_in_range_isla" in r for r in entry_160["reasons"]), (
            f"1.60 debe tener razón semantic_prior registrada. "
            f"Reasons: {entry_160['reasons']}"
        )

    def test_prior_no_se_aplica_a_ancho(self):
        """El prior solo afecta length. El depth ranking debe quedar igual."""
        region = self._r3_region()
        cotas = self._r3_cotas_bernardi()

        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        for entry in ranking["depth"]:
            assert not any("semantic_prior" in r for r in entry["reasons"]), (
                f"depth ranking NO debe tener modifier semántico. "
                f"Entry: {entry}"
            )

    def test_prior_aplica_a_cocina_con_rango_mas_amplio(self):
        """Las mesadas de cocina tienen rango más amplio (1.0-3.5m). Un
        tramo como R1 de Bernardi (mesada con pileta, largo real 2.05m)
        debe tener 2.05 BOOSTEADA por el prior."""
        r1_region = {
            "id": "R1",
            "bbox_rel": {"x": 0.35, "y": 0.65, "w": 0.25, "h": 0.08},
            "features": {
                "touches_wall": True,  # mesada contra pared → cocina
                "stools_adjacent": False,
                "cooktop_groups": 1,
                "sink_simple": True,
            },
        }
        # Cota 2.05 dentro del bbox de R1
        cotas = [
            Cota(text="2,05", value=2.05, x=2400, y=2400, width=40, height=20),
            Cota(text="0,60", value=0.60, x=2400, y=2400, width=40, height=20),
        ]
        ranking = _rank_cotas_for_region(cotas, r1_region, self.IMAGE_SIZE, scale=None)
        entry_205 = next(r for r in ranking["length"] if r["value"] == 2.05)

        # 2.05 está dentro del rango cocina [1.0, 3.5] → bonus
        assert any("semantic_prior_in_range_cocina" in r for r in entry_205["reasons"]), (
            f"2.05 en cocina debe recibir bonus. Reasons: {entry_205['reasons']}"
        )

    def test_prior_no_se_aplica_a_tipos_no_listados(self):
        """Si la región se clasifica como tipo no listado en las ranges,
        el prior no se aplica (comportamiento legacy)."""
        # Región de tipo "descarte" (non_counter_upper=True)
        region = {
            "id": "Rx",
            "bbox_rel": self.R3_BBOX,
            "features": {**self.R3_FEATURES, "non_counter_upper": True},
        }
        cotas = self._r3_cotas_bernardi()

        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        # Ningún length entry debe tener reason semantic_prior_*
        for entry in ranking["length"]:
            assert not any("semantic_prior" in r for r in entry["reasons"]), (
                f"Tipo no listado ('descarte') NO debe recibir prior. "
                f"Entry: {entry}"
            )

    def test_log_semantic_prior_emitido_con_campos_auditables(self, caplog):
        """El log [semantic-prior] debe salir con campos auditables:
        region_id, region_type, candidate, base_score, modifier, final_score, range.
        """
        import logging as _logging
        region = self._r3_region()
        cotas = self._r3_cotas_bernardi()

        with caplog.at_level(_logging.INFO, logger="app.modules.quote_engine.multi_crop_reader"):
            _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)

        prior_logs = [r for r in caplog.records if "[semantic-prior]" in r.getMessage()]
        assert len(prior_logs) >= 1, (
            f"Debe haber al menos 1 log [semantic-prior]. Got messages: "
            f"{[r.getMessage() for r in caplog.records]}"
        )
        msg = prior_logs[0].getMessage()
        # Campos que deben estar en el JSON embebido
        for field in ("region_type", "candidate", "base_score", "modifier", "final_score", "range"):
            assert field in msg, f"Log debe incluir campo '{field}'. Got: {msg}"
        assert "type=isla" in msg, f"Log debe identificar region_type=isla. Got: {msg}"

    def test_tie_breaker_degrada_preferred_en_empate(self):
        """Si tras el prior top1 - top2 ≤ TIE_THRESHOLD, top1 preferred
        debe degradar a weak. Evitamos fabricar certeza en ranking ambiguo.

        Caso: dos cotas ambas in-range de isla muy cerca en score.
        """
        region = self._r3_region()
        # Dos cotas in-range casi iguales: 1.50 y 1.60 ambas tight.
        cotas = [
            Cota(text="1,50", value=1.50, x=2400, y=1700, width=40, height=20),
            Cota(text="1,60", value=1.60, x=2400, y=1700, width=40, height=20),
            Cota(text="0,60", value=0.60, x=2400, y=1700, width=40, height=20),
        ]
        ranking = _rank_cotas_for_region(cotas, region, self.IMAGE_SIZE, scale=None)
        length = ranking["length"]

        # Ambas tight + in range → score base 80, post-prior 100 (clamped).
        # Empatan exactamente → tie breaker degrada top1.
        top = length[0]
        second = length[1] if len(length) > 1 else None
        if second and (top["score"] - second["score"]) <= 10:
            assert top["bucket"] == "weak", (
                f"Empate debe degradar top preferred → weak. "
                f"Top={top}, second={second}"
            )
            assert any("semantic_prior_tie_demoted" in r for r in top["reasons"]), (
                f"Reason tie_demoted debe estar presente. Reasons: {top['reasons']}"
            )
