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
    _call_global_topology,
    _GLOBAL_SYSTEM_PROMPT,
    _infer_expected_region_count,
    _measure_region,
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
        assert "suspicious_reasons" in result
        assert any("largo == ancho" in s for s in result["suspicious_reasons"])

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
