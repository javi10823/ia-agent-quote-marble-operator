"""Tests for quote_engine — calculator + API endpoint."""

import pytest
from unittest.mock import patch
from app.modules.quote_engine.calculator import (
    calculate_m2,
    calculate_merma,
    calculate_quote,
    _find_material,
    _find_flete,
)


# ── calculate_m2 ─────────────────────────────────────────────────────────────

class TestCalculateM2:
    def test_simple_mesada(self):
        pieces = [{"description": "Mesada", "largo": 2.0, "prof": 0.6}]
        m2, details = calculate_m2(pieces)
        assert m2 == 1.2

    def test_mesada_with_zocalo(self):
        pieces = [
            {"description": "Mesada", "largo": 2.0, "prof": 0.6},
            {"description": "Zócalo", "largo": 2.0, "alto": 0.05},
        ]
        m2, details = calculate_m2(pieces)
        assert m2 == 1.3

    def test_mesada_en_L(self):
        pieces = [
            {"description": "Tramo A", "largo": 2.41, "prof": 0.6},
            {"description": "Tramo B", "largo": 1.37, "prof": 0.6},
        ]
        m2, details = calculate_m2(pieces)
        # 2.41*0.6 + 1.37*0.6 = 1.446 + 0.822 = 2.268 → round(2) = 2.27
        assert m2 == 2.27

    def test_empty_pieces(self):
        m2, details = calculate_m2([])
        assert m2 == 0


# ── calculate_merma ──────────────────────────────────────────────────────────

class TestCalculateMerma:
    def test_silestone_no_sobrante(self):
        """Desperdicio < 1.0 → no aplica."""
        result = calculate_merma(1.80, "SILESTONE BLANCO NORTE")
        assert result["aplica"] is False
        assert result["desperdicio"] < 1.0

    def test_silestone_con_sobrante(self):
        """Desperdicio >= 1.0 → sobrante = desperdicio/2."""
        result = calculate_merma(0.80, "SILESTONE BLANCO NORTE")
        assert result["aplica"] is True
        assert result["sobrante_m2"] > 0
        assert result["sobrante_m2"] == pytest.approx(result["desperdicio"] / 2, abs=0.01)

    def test_negro_brasil_never(self):
        result = calculate_merma(0.5, "GRANITO NEGRO BRASIL")
        assert result["aplica"] is False
        assert "Negro Brasil" in result["motivo"]

    def test_granito_natural_no_merma(self):
        result = calculate_merma(2.0, "GRANITO GRIS MARA")
        assert result["aplica"] is False
        assert "natural" in result["motivo"].lower()

    def test_purastone_placa_entera(self):
        """Purastone uses full plate (4.20 m2) as reference."""
        result = calculate_merma(2.0, "PURASTONE BLANCO PALOMA")
        # desperdicio = 4.20 - 2.0 = 2.20 >= 1.0 → aplica
        assert result["aplica"] is True


# ── _find_material ───────────────────────────────────────────────────────────

class TestFindMaterial:
    def test_silestone_found(self):
        result = _find_material("Silestone Blanco Norte")
        assert result["found"] is True
        assert result["currency"] == "USD"

    def test_purastone_by_name(self):
        result = _find_material("Blanco Paloma")
        assert result["found"] is True
        assert "PALOMA" in result["name"].upper()

    def test_not_found(self):
        result = _find_material("Material Inexistente XYZ")
        assert result["found"] is False


# ── _find_flete ──────────────────────────────────────────────────────────────

class TestFindFlete:
    def test_rosario(self):
        result = _find_flete("Rosario")
        assert result["found"] is True
        assert result["price_ars"] > 0

    def test_funes(self):
        result = _find_flete("Funes")
        assert result["found"] is True


# ── calculate_quote (full flow) ──────────────────────────────────────────────

class TestCalculateQuote:
    def test_simple_quote(self):
        result = calculate_quote({
            "client_name": "Test Client",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo", "largo": 2.0, "alto": 0.05},
            ],
            "localidad": "Rosario",
            "colocacion": True,
            "pileta": "empotrada_cliente",
            "anafe": True,
            "plazo": "30 días",
        })

        assert result["ok"] is True
        assert result["material_m2"] == 1.3
        assert result["material_currency"] == "USD"
        assert result["material_price_unit"] > 0
        assert result["total_usd"] > 0
        assert result["total_ars"] > 0
        assert len(result["mo_items"]) >= 3  # pileta + anafe + colocación + flete

    def test_quote_without_pileta_anafe(self):
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 1.5, "prof": 0.6}],
            "localidad": "Rosario",
            "colocacion": True,
            "plazo": "30 días",
        })

        assert result["ok"] is True
        # Should have colocación + flete only
        descriptions = [mo["description"] for mo in result["mo_items"]]
        assert any("Colocación" in d for d in descriptions)
        assert any("Flete" in d for d in descriptions)
        assert not any("pileta" in d.lower() for d in descriptions)
        assert not any("anafe" in d.lower() for d in descriptions)

    def test_tall_zocalo_adds_toma(self):
        """Zócalo > 10cm alto should auto-add 1 TOMAS to MO."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo", "largo": 2.0, "alto": 0.15},  # 15cm > 10cm
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"] is True
        descriptions = [mo["description"].lower() for mo in result["mo_items"]]
        assert any("toma corriente" in d for d in descriptions), f"TOMAS not found in MO: {descriptions}"

    def test_short_zocalo_no_toma(self):
        """Zócalo <= 10cm should NOT add TOMAS."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo", "largo": 2.0, "alto": 0.05},  # 5cm <= 10cm
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"] is True
        descriptions = [mo["description"].lower() for mo in result["mo_items"]]
        assert not any("toma corriente" in d for d in descriptions), f"TOMAS should not be in MO: {descriptions}"

    def test_flete_puerto_san_martin(self):
        """Puerto San Martín should resolve via zone_aliases in config.json."""
        result = calculate_quote({
            "client_name": "Test PSM",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 1.5, "prof": 0.6}],
            "localidad": "puerto san martin",
            "colocacion": True,
            "plazo": "30 días",
        })
        assert result["ok"] is True
        descriptions = [mo["description"].lower() for mo in result["mo_items"]]
        assert any("flete" in d and "san martin" in d for d in descriptions), f"Flete PSM not found: {descriptions}"

    def test_flete_pto_san_martin_alias(self):
        """Alias 'pto san martin' should also resolve."""
        result = _find_flete("pto san martin")
        assert result["found"] is True
        assert result["price_ars"] > 0

    def test_flete_unknown_zone_fails(self):
        """Unknown zone should return found=False, not silently skip."""
        result = _find_flete("atlantida")
        assert result["found"] is False
        assert "zone_aliases" in result.get("error", "").lower()

    def test_material_not_found_error(self):
        result = calculate_quote({
            "client_name": "Test",
            "material": "Material Fake XYZ",
            "pieces": [{"description": "Mesada", "largo": 1.0, "prof": 0.6}],
            "localidad": "Rosario",
            "plazo": "30 días",
        })

        assert result["ok"] is False
        assert "no encontrado" in result["error"].lower()

    def test_discount_applied(self):
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
            "localidad": "Rosario",
            "plazo": "30 días",
            "discount_pct": 10,
        })

        assert result["ok"] is True
        assert result["discount_pct"] == 10
        assert result["discount_amount"] > 0
        # material_total should be less than m2 × price
        full_price = round(result["material_m2"] * result["material_price_unit"])
        assert result["material_total"] < full_price


# ── API endpoint ─────────────────────────────────────────────────────────────

class TestQuoteEndpoint:
    @pytest.mark.asyncio
    async def test_simple_quote(self, client):
        with patch("app.modules.quote_engine.router.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            resp = await client.post("/api/v1/quote", json={
                "client_name": "Test API",
                "material": "Silestone Blanco Norte",
                "pieces": [
                    {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                ],
                "localidad": "Rosario",
                "plazo": "30 días",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["quotes"]) == 1
        q = data["quotes"][0]
        assert q["material_m2"] == 1.2
        assert q["material_currency"] == "USD"
        assert q["total_usd"] > 0
        assert q["total_ars"] > 0

    @pytest.mark.asyncio
    async def test_multi_material(self, client):
        with patch("app.modules.quote_engine.router.upload_to_drive", return_value={"ok": True, "drive_url": "https://drive.test"}):
            resp = await client.post("/api/v1/quote", json={
                "client_name": "Test Multi",
                "material": ["Silestone Blanco Norte", "Blanco Paloma"],
                "pieces": [
                    {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                ],
                "localidad": "Rosario",
                "plazo": "30 días",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["quotes"]) == 2
        materials = [q["material"] for q in data["quotes"]]
        assert any("NORTE" in m.upper() for m in materials)
        assert any("PALOMA" in m.upper() for m in materials)

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, client):
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            # missing material, pieces, localidad, plazo
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_material_not_found(self, client):
        resp = await client.post("/api/v1/quote", json={
            "client_name": "Test",
            "material": "Material Fake XYZ",
            "pieces": [{"description": "Mesada", "largo": 1.0, "prof": 0.6}],
            "localidad": "Rosario",
            "plazo": "30 días",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "no encontrado" in data["error"].lower()
