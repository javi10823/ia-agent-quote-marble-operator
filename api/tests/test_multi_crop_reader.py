"""Tests del multi_crop_reader — aggregator + orquestación + fail-hard.

LLM calls y PIL image ops se mockean. La idea es verificar:
- aggregator arma el schema dual_read correcto desde topology + results
- fallback graceful si global topology falla
- per-region fail-hard: <2 cotas locales → skip LLM, devolver DUDOSO
- detección de fallback silencioso (largo == ancho, valores no anclados)
- labels genéricos hasta que PR C defina contrato feature-based
"""
from unittest.mock import AsyncMock, patch

import io
import pytest
from PIL import Image

from app.modules.quote_engine.cotas_extractor import Cota
from app.modules.quote_engine.multi_crop_reader import (
    _aggregate,
    _apply_guardrails,
    _bbox_to_px,
    _call_global_topology,
    _detect_region_brief_contradictions,
    _estimate_plan_scale,
    _format_ranking_for_prompt,
    _GLOBAL_SYSTEM_PROMPT,
    _infer_expected_region_count,
    _is_probable_perimeter,
    _measure_region,
    _rank_cotas_for_region,
    _score_cota,
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
