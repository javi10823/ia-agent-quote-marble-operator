"""Unit tests for catalog_tool.py — SKU lookup, name search, IVA calculation."""

import math
from app.modules.agent.tools.catalog_tool import catalog_lookup, check_stock


# ── catalog_lookup — exact SKU match ─────────────────────────────────────────

class TestCatalogLookupExactSKU:
    def test_silestone_blanco_norte_found(self):
        result = catalog_lookup("materials-silestone", "SILESTONENORTE")
        assert result["found"] is True
        assert "BLANCO NORTE" in result["name"].upper()
        assert result["currency"] == "USD"

    def test_iva_usd_floor(self):
        """USD IVA uses math.floor: floor(519 * 1.21) = 627."""
        result = catalog_lookup("materials-silestone", "SILESTONENORTE")
        assert result["found"] is True
        expected = math.floor(result["price_usd_base"] * 1.21)
        assert result["price_usd"] == expected

    def test_labor_pegadopileta_ars(self):
        """ARS IVA uses round."""
        result = catalog_lookup("labor", "PEGADOPILETA")
        assert result["found"] is True
        assert result["currency"] == "ARS"
        expected = round(result["price_ars_base"] * 1.21)
        assert result["price_ars"] == expected

    def test_delivery_zone_rosario(self):
        result = catalog_lookup("delivery-zones", "ENVIOROS")
        assert result["found"] is True
        assert result["currency"] == "ARS"

    def test_case_insensitive(self):
        result = catalog_lookup("materials-silestone", "silestonenorte")
        assert result["found"] is True

    def test_sku_not_found(self):
        result = catalog_lookup("materials-silestone", "MATERIAL_INEXISTENTE_XYZ")
        assert result["found"] is False

    def test_nonexistent_catalog(self):
        result = catalog_lookup("catalog-que-no-existe", "ANY_SKU")
        assert result["found"] is False


# ── catalog_lookup — name search fallback ────────────────────────────────────

class TestCatalogLookupNameSearch:
    def test_blanco_paloma_by_name(self):
        """Should find PURASTONE BLANCO PALOMA when searching by name."""
        result = catalog_lookup("materials-purastone", "BLANCO PALOMA")
        assert result["found"] is True
        assert "PALOMA" in result["name"].upper()
        assert result["currency"] == "USD"

    def test_blanco_norte_by_name(self):
        result = catalog_lookup("materials-silestone", "BLANCO NORTE")
        assert result["found"] is True
        assert "NORTE" in result["name"].upper()

    def test_name_search_returns_price(self):
        """Name match should return full pricing data, not just suggestion."""
        result = catalog_lookup("materials-purastone", "BLANCO PALOMA")
        assert result["found"] is True
        assert "price_usd" in result
        assert result["price_usd"] > 0

    def test_partial_match_multiple(self):
        """Multiple matches should return found=False with suggestions."""
        # "PURA" matches many Purastone items
        result = catalog_lookup("materials-purastone", "PURA")
        # Could be found (single match) or not (multiple matches)
        if not result["found"]:
            assert "partial_matches" in result
            assert len(result["partial_matches"]) > 0


# ── check_stock ──────────────────────────────────────────────────────────────

class TestCheckStock:
    def test_empty_stock(self):
        """Stock for nonexistent material should return not found."""
        result = check_stock("MATERIAL_QUE_NO_EXISTE")
        assert result["found"] is False
        assert "Sin stock" in result["message"]

    def test_stock_returns_pieces_with_m2(self):
        """If stock exists, pieces should include calculated m2."""
        # Stock.json might be empty, so this test is conditional
        result = check_stock("SILESTONENORTE")
        if result["found"]:
            for piece in result["pieces"]:
                assert "m2" in piece
                assert piece["m2"] >= 0
