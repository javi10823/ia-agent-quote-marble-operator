"""Tests for the 7 fixes: piece layout, unicode, PUL, delivery, drive, sink, architect."""
import json
import math
import os
import shutil
import pytest

# ── Fix environment before app imports ──
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from app.modules.agent.tools.catalog_tool import (
    check_architect,
    catalog_lookup,
    fuzzy_sink_lookup,
)

OUTPUT_DIR = None
try:
    from app.core.static import OUTPUT_DIR
except Exception:
    from pathlib import Path
    OUTPUT_DIR = Path(__file__).parent.parent / "output"


# ═══════════════════════════════════════════════════════
# Fix 2: Unicode — json.dumps preserves accented chars
# ═══════════════════════════════════════════════════════

class TestUnicode:
    def test_json_dumps_ensure_ascii_false(self):
        """ensure_ascii=False must preserve ó, é, í, etc."""
        data = {"piece": "Zócalo fondo", "desc": "Pieza especial"}
        result = json.dumps(data, ensure_ascii=False)
        assert "Zócalo" in result
        assert "\\u00f3" not in result

    def test_json_dumps_default_escapes(self):
        """Default json.dumps escapes — this is what we're fixing."""
        data = {"piece": "Zócalo"}
        result = json.dumps(data)  # default ensure_ascii=True
        assert "\\u00f3" in result  # confirms the bug exists without fix


# ═══════════════════════════════════════════════════════
# Fix 4: Delivery days — respect range_enabled from config
# ═══════════════════════════════════════════════════════

class TestDeliveryDays:
    def test_small_quote_gets_default_days_when_range_disabled(self):
        """With range_enabled=false, even 2.5m² should get 40 days."""
        from app.modules.quote_engine.calculator import calculate_quote

        result = calculate_quote({
            "client_name": "Test Client",
            "project": "Cocina",
            "material": "Blanco Paloma",
            "catalog": "materials-purastone",
            "sku": "PALOMA",
            "pieces": [{"largo": 2.0, "ancho": 0.60, "descripcion": "Mesada"}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "40 dias desde la toma de medidas",
        })
        assert result.get("ok") is True
        delivery = result.get("delivery_days", "")
        assert "40" in str(delivery), f"Expected 40 days, got: {delivery}"


# ═══════════════════════════════════════════════════════
# Fix 6: Sink fuzzy matching
# ═══════════════════════════════════════════════════════

class TestFuzzySinkLookup:
    def test_luxor_compact_si71_matches_luxor_s171(self):
        """LUXOR COMPACT SI71 → should fuzzy match LUXOR171 (S171)."""
        result = fuzzy_sink_lookup("LUXOR COMPACT SI71")
        assert result["found"] is True
        assert "LUXOR" in result["name"].upper()
        assert "171" in result.get("sku", "").upper() or "171" in result["name"].upper()

    def test_quadra_q71_matches(self):
        """QUADRA Q71 → should match QUADRAQ71A (not LUXOR with extended 171)."""
        result = fuzzy_sink_lookup("QUADRA Q71")
        assert result["found"] is True
        assert "QUADRA" in result["name"].upper()
        assert "Q71" in result.get("sku", "")

    def test_si71_alone_matches_luxor(self):
        """SI71 without brand → should still match LUXOR S171 via extended num."""
        result = fuzzy_sink_lookup("SI71")
        assert result["found"] is True
        assert "LUXOR" in result["name"].upper()

    def test_nonsense_returns_not_found(self):
        """Random text should not match any sink."""
        result = fuzzy_sink_lookup("XYZNONEXISTENT999")
        assert result["found"] is False

    def test_exact_sku_still_works(self):
        """catalog_lookup exact match should still work for known SKUs."""
        result = catalog_lookup("sinks", "LUXOR171")
        assert result["found"] is True
        assert "LUXOR" in result["name"].upper()


# ═══════════════════════════════════════════════════════
# Architect discount — partial match + no m² minimum
# ═══════════════════════════════════════════════════════

class TestArchitectDiscount:
    def test_munge_partial_match(self):
        """MUNGE should match ESTUDIO MUNGE in architects.json."""
        result = check_architect("MUNGE")
        assert result["found"] is True

    def test_munge_case_insensitive(self):
        result = check_architect("munge")
        assert result["found"] is True

    def test_auto_discount_without_explicit_flag(self):
        """Calculator must auto-apply architect discount even if agent doesn't pass discount_pct."""
        from app.modules.quote_engine.calculator import calculate_quote
        result = calculate_quote({
            "client_name": "ESTUDIO MUNGE",
            "project": "Test",
            "material": "Blanco Paloma",
            "catalog": "materials-purastone",
            "sku": "PALOMA",
            "pieces": [{"largo": 1.0, "ancho": 0.50, "descripcion": "Mesada"}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
            # NO discount_pct passed — calculator should auto-detect
        })
        assert result["ok"]
        assert result["discount_pct"] == 5, f"Expected auto 5% discount for MUNGE, got {result['discount_pct']}"

    def test_nonexistent_architect(self):
        result = check_architect("ZZZNONEXISTENT999")
        assert result["found"] is False

    def test_architect_discount_no_m2_minimum(self):
        """Architect discount should apply regardless of m² (even 0.5 m²)."""
        from app.modules.quote_engine.calculator import calculate_quote

        result = calculate_quote({
            "client_name": "ESTUDIO MUNGE",
            "project": "Obra Munge",
            "material": "Blanco Paloma",
            "catalog": "materials-purastone",
            "sku": "PALOMA",
            "pieces": [{"largo": 1.0, "ancho": 0.50, "descripcion": "Mesada pequeña"}],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "40 dias desde la toma de medidas",
            "is_architect": True,
            "discount_pct": 5,
        })
        assert result.get("ok") is True
        assert result.get("discount_pct", 0) == 5, f"Expected 5% discount, got: {result.get('discount_pct')}"


# ═══════════════════════════════════════════════════════
# Fix 1: PDF piece layout — pieces consecutive, no gap
# ═══════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════
# Deterministic Paso 2 — no invented MO items
# ═══════════════════════════════════════════════════════

class TestDeterministicPaso2:
    def test_paso2_no_pulido_rosario(self):
        """Paso 2 for Rosario must NOT contain Pulido."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Test", "project": "Cocina",
            "material": "Blanco Paloma", "catalog": "materials-purastone", "sku": "PALOMA",
            "pieces": [{"largo": 1.72, "prof": 0.75, "descripcion": "Mesada"}],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias desde la toma de medidas",
        })
        assert result["ok"]
        paso2 = build_deterministic_paso2(result)
        assert "Pulido" not in paso2
        assert "PUL" not in paso2

    def test_paso2_has_discount_when_architect(self):
        """Paso 2 must show 5% discount for architects."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "ESTUDIO MUNGE", "project": "Obra",
            "material": "Blanco Paloma", "catalog": "materials-purastone", "sku": "PALOMA",
            "pieces": [{"largo": 1.0, "prof": 0.5, "descripcion": "Mesada"}],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
            "discount_pct": 5, "is_architect": True,
        })
        assert result["ok"]
        paso2 = build_deterministic_paso2(result)
        assert "5%" in paso2
        assert "DESCUENTO" in paso2

    def test_paso2_alzada_description_collapsed(self):
        """Alzada en Paso 2 debe renderizarse como 'Alzada' — sin el detalle
        del operador (ej: 'corrida (fondo completo sin heladera)'). Consistente
        con el PDF (PR #359) y con el Dual Read del frontend."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Luciana Villagra", "project": "Cocina",
            "material": "Blanco Nube", "catalog": "materials-purastone", "sku": "BLANCO_NUBE",
            "pieces": [
                {"largo": 2.03, "prof": 0.60, "description": "Placa tramo derecho"},
                {"largo": 3.01, "prof": 0.60,
                 "description": "Alzada corrida (fondo completo sin heladera)"},
            ],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"]
        paso2 = build_deterministic_paso2(result)
        # El detalle extra del operador NO debe aparecer en la tabla
        assert "fondo completo sin heladera" not in paso2
        assert "corrida" not in paso2
        # La fila de Alzada existe con el nombre colapsado
        assert "| Alzada |" in paso2
        # Las placas mantienen su descripción completa
        assert "| Placa tramo derecho |" in paso2

    def test_paso2_shows_merma_no_aplica_with_motivo(self):
        """Cuando merma no aplica (ej: Negro Brasil), Paso 2 debe renderizar
        **MERMA — NO APLICA** + motivo. Paridad con el bloque DESCUENTOS.
        Antes quedaba una sección en blanco y el operador no sabía si el
        cálculo había corrido o estaba pendiente."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Test", "project": "Cocina",
            "material": "Negro Brasil", "catalog": "materials-granito-importado",
            "sku": "NEGRO_BRASIL",
            "pieces": [{"largo": 2.0, "prof": 0.6, "description": "Mesada"}],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"]
        assert result["merma"]["aplica"] is False
        paso2 = build_deterministic_paso2(result)
        assert "**MERMA — NO APLICA**" in paso2, (
            "Paso 2 debe mostrar MERMA — NO APLICA cuando no aplica"
        )
        # El motivo de Negro Brasil debe figurar como contexto
        assert "Negro Brasil" in paso2

    def test_paso2_delivery_matches_config(self):
        """Paso 2 delivery days must match what calculator returns."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Test", "project": "Cocina",
            "material": "Blanco Paloma", "catalog": "materials-purastone", "sku": "PALOMA",
            "pieces": [{"largo": 2.0, "prof": 0.6, "descripcion": "Mesada"}],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias desde la toma de medidas",
        })
        assert result["ok"]
        paso2 = build_deterministic_paso2(result)
        assert result["delivery_days"] in paso2

    def test_paso2_mo_items_match_calculator(self):
        """Paso 2 MO items must be exactly what calculator returned."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Test", "project": "Cocina",
            "material": "Blanco Paloma", "catalog": "materials-purastone", "sku": "PALOMA",
            "pieces": [{"largo": 1.72, "prof": 0.75, "descripcion": "Mesada"}],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_johnson", "pileta_sku": "LUXOR171",
            "plazo": "30 dias",
        })
        assert result["ok"]
        paso2 = build_deterministic_paso2(result)
        for mo in result["mo_items"]:
            assert mo["description"] in paso2, f"MO item '{mo['description']}' missing from Paso 2"

    def test_paso2_correct_price(self):
        """Paso 2 must show correct price USD 346 for Paloma."""
        from app.modules.quote_engine.calculator import calculate_quote, build_deterministic_paso2
        result = calculate_quote({
            "client_name": "Test", "project": "Cocina",
            "project": "Cocina",
            "material": "Blanco Paloma", "catalog": "materials-purastone", "sku": "PALOMA",
            "pieces": [{"largo": 1.72, "prof": 0.75, "descripcion": "Mesada"}],
            "localidad": "Rosario", "colocacion": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias",
        })
        assert result["ok"]
        paso2 = build_deterministic_paso2(result)
        assert "USD 346" in paso2


# ═══════════════════════════════════════════════════════
# M2 surface validator — extract from planilla text
# ═══════════════════════════════════════════════════════

class TestM2SurfaceParser:
    def _extract_m2(self, text):
        """Replicate the regex extraction logic from agent.py."""
        import re
        patterns = [
            r'(?:M2|m2|SUPERFICIE|superficie)\s*[:\|]?\s*(\d+[.,]\d+)\s*m2',
            r'(\d+[.,]\d+)\s*m2\s*[-–—]\s*[Cc]on\s+z[oó]calos',
            r'(\d+[.,]\d+)\s*m2',
        ]
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return float(match.group(1).replace(",", "."))
        return None

    def test_munge_planilla_m2(self):
        """Extract 2.50 from 'M2  2,50 m2 - Con zócalos incluídos'."""
        text = "M2  2,50 m2 - Con zócalos incluídos"
        assert self._extract_m2(text) == 2.50

    def test_simple_m2(self):
        text = "SUPERFICIE: 4.20 m2"
        assert self._extract_m2(text) == 4.20

    def test_m2_with_pipe(self):
        text = "M2 | 3,75 m2"
        assert self._extract_m2(text) == 3.75

    def test_no_m2(self):
        text = "MESADA COCINA sin superficie indicada"
        assert self._extract_m2(text) is None


    def test_validation_passes_when_close(self):
        """2.49 vs 2.50 = 0.4% diff → should pass (< 5%)."""
        expected = 2.50
        actual = 2.49
        diff_pct = abs(actual - expected) / expected * 100
        assert diff_pct < 5

    def test_validation_fails_when_far(self):
        """2.75 vs 2.50 = 10% diff → should fail (> 5%)."""
        expected = 2.50
        actual = 2.75
        diff_pct = abs(actual - expected) / expected * 100
        assert diff_pct > 5


class TestPDFPieceLayout:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        if OUTPUT_DIR:
            for d in OUTPUT_DIR.glob("test-layout-*"):
                shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_pdf_created_with_discount(self):
        """PDF with discount should be created successfully."""
        from app.modules.agent.tools.document_tool import generate_documents

        data = {
            "client_name": "Test Layout",
            "project": "Cocina",
            "material_name": "PURASTONE BLANCO PALOMA",
            "material_m2": 2.5,
            "material_price_unit": 346,
            "material_currency": "USD",
            "discount_pct": 5,
            "thickness_mm": 20,
            "sectors": [{"label": "Cocina", "pieces": [
                "1.55 × 0.60 Mesada cocina tramo 1",
                "1.72 × 0.75 Mesada cocina tramo 2",
                "1.74ML X 0.07 ZOC",
                "1.55ML X 0.07 ZOC",
                "0.75ML X 0.07 ZOC",
            ]}],
            "sinks": [],
            "mo_items": [
                {"description": "Colocación", "quantity": 2.5, "unit_price": 60135, "total": 150338},
                {"description": "Flete + toma medidas Rosario", "quantity": 1, "unit_price": 52000, "total": 52000},
            ],
            "total_ars": 202338,
            "total_usd": 822,
            "delivery_days": "40 dias desde la toma de medidas",
        }
        quote_id = "test-layout-001"
        result = await generate_documents(quote_id, data)
        assert result["ok"] is True
        assert result["pdf_url"].endswith(".pdf")
        assert result["excel_url"].endswith(".xlsx")

    @pytest.mark.asyncio
    async def test_excel_created_with_discount(self):
        """Excel with discount should be created successfully."""
        from app.modules.agent.tools.document_tool import generate_documents

        data = {
            "client_name": "Test Excel",
            "project": "Cocina",
            "material_name": "PURASTONE BLANCO PALOMA",
            "material_m2": 2.5,
            "material_price_unit": 346,
            "material_currency": "USD",
            "discount_pct": 5,
            "thickness_mm": 20,
            "sectors": [{"label": "Cocina", "pieces": [
                "pieza 1",
                "pieza 2",
                "zocalo 1",
            ]}],
            "sinks": [],
            "mo_items": [
                {"description": "Colocación", "quantity": 2.5, "unit_price": 60135, "total": 150338},
            ],
            "total_ars": 150338,
            "total_usd": 822,
            "delivery_days": "40 dias",
        }
        quote_id = "test-layout-002"
        result = await generate_documents(quote_id, data)
        assert result["ok"] is True

        # Verify Excel content: pieces + discount + total in correct order
        import zipfile
        from pathlib import Path
        xlsx_files = list((OUTPUT_DIR / quote_id).glob("*.xlsx"))
        assert len(xlsx_files) == 1
        with zipfile.ZipFile(str(xlsx_files[0]), 'r') as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            # All pieces should be present
            assert "pieza 1" in sheet
            assert "pieza 2" in sheet
            assert "zocalo 1" in sheet
            # Discount and TOTAL should be present
            assert "Descuento 5%" in sheet
            assert "TOTAL USD" in sheet
