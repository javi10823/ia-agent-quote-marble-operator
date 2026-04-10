"""Tests for catalog import parser — Dux format detection, classification, diff."""

import json
import pytest
from pathlib import Path

from app.modules.catalog.import_parser import (
    detect_format,
    read_file,
    extract_items,
    build_sku_index,
    classify_items,
    generate_diff,
    parse_import_file,
)

CATALOG_DIR = Path(__file__).parent.parent / "catalog"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_catalogs() -> dict[str, list]:
    """Load current catalogs from JSON files."""
    catalogs = {}
    for f in CATALOG_DIR.glob("*.json"):
        name = f.stem
        if name in ("config", "stock", "architects"):
            continue
        data = json.loads(f.read_text())
        items = data if isinstance(data, list) else data.get("items", [])
        catalogs[name] = items
    return catalogs


DUX_FILE_1 = Path("/Users/javierolivieri/Downloads/ListadePrecio_5346844865870250071.xls")
DUX_FILE_2 = Path("/Users/javierolivieri/Downloads/ListadePrecio_3144822666041388388.xls")


# ── Format detection ─────────────────────────────────────────────────────────

class TestFormatDetection:
    def test_dux_materials_usd(self):
        assert detect_format(["Código", "Producto", "Costo", "Porc. Utilidad", "Precio de Venta"]) == "dux_materials_usd"

    def test_dux_servicios_ars(self):
        assert detect_format(["Código", "Producto", "Precio de Venta", "Ultima Modificacion"]) == "dux_servicios_ars"

    def test_csv_generic(self):
        assert detect_format(["sku", "nombre", "precio"]) == "csv_generic"


# ── File reading ─────────────────────────────────────────────────────────────

class TestFileReading:
    @pytest.mark.skipif(not DUX_FILE_1.exists(), reason="Dux file 1 not available")
    def test_read_dux_xls_materials(self):
        data = DUX_FILE_1.read_bytes()
        headers, rows = read_file(data, "test.xls")
        assert "Código" in headers or "código" in [h.lower() for h in headers]
        assert len(rows) >= 30  # Silestone has ~33 items

    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    def test_read_dux_xls_servicios(self):
        data = DUX_FILE_2.read_bytes()
        headers, rows = read_file(data, "test.xls")
        assert len(rows) >= 70  # Servicios has ~79 items

    def test_read_csv(self):
        csv_data = b"sku,nombre,precio\nSKU1,Material Test,100.50\nSKU2,Material 2,200\n"
        headers, rows = read_file(csv_data, "test.csv")
        assert headers == ["sku", "nombre", "precio"]
        assert len(rows) == 2


# ── Item extraction ──────────────────────────────────────────────────────────

class TestItemExtraction:
    @pytest.mark.skipif(not DUX_FILE_1.exists(), reason="Dux file 1 not available")
    def test_extract_materials_usd(self):
        data = DUX_FILE_1.read_bytes()
        headers, rows = read_file(data, "test.xls")
        fmt = detect_format(headers)
        assert fmt == "dux_materials_usd"

        items = extract_items(headers, rows, fmt)
        assert len(items) >= 30

        # Check a known SKU
        norte = next((i for i in items if i["sku"] == "SILESTONENORTE"), None)
        assert norte is not None
        assert norte["price_no_vat"] == 429.0  # USD sin IVA
        assert norte["currency"] == "USD"

    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    def test_extract_servicios_ars(self):
        data = DUX_FILE_2.read_bytes()
        headers, rows = read_file(data, "test.xls")
        fmt = detect_format(headers)
        assert fmt == "dux_servicios_ars"

        items = extract_items(headers, rows, fmt)
        assert len(items) >= 70

        # Check a known labor SKU
        anafe = next((i for i in items if i["sku"] == "ANAFE"), None)
        assert anafe is not None
        assert abs(anafe["price_no_vat"] - 35617.36) < 1  # ARS sin IVA
        assert anafe["currency"] == "ARS"

    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    def test_never_uses_iva_price(self):
        """Parser must use Precio de Venta (sin IVA), NEVER Precio Con IVA."""
        data = DUX_FILE_2.read_bytes()
        headers, rows = read_file(data, "test.xls")
        items = extract_items(headers, rows, detect_format(headers))

        colocacion = next((i for i in items if i["sku"] == "COLOCACION"), None)
        assert colocacion is not None
        # sin IVA: ~49698.65, con IVA: ~60135
        assert colocacion["price_no_vat"] < 55000, (
            f"Parser used IVA price! Got {colocacion['price_no_vat']}, expected ~49698"
        )


    def test_prices_rounded_to_2_decimals(self):
        """Extracted prices must have at most 2 decimal places."""
        headers = ["Código", "Producto", "Costo", "Porc. Utilidad", "Precio de Venta"]
        rows = [
            ["SKU1", "Material A", 100, 50, 298448.48303928],
            ["SKU2", "Material B", 80, 40, 180189.046773336],
            ["SKU3", "Material C", 50, 25, 100.5],         # already 1 decimal
            ["SKU4", "Material D", 60, 30, 200],            # integer
        ]
        items = extract_items(headers, rows, "dux_materials_usd")
        for item in items:
            price = item["price_no_vat"]
            assert price is not None
            # Check at most 2 decimals
            assert price == round(price, 2), (
                f"SKU {item['sku']}: price {price} has more than 2 decimals, expected {round(price, 2)}"
            )
        assert items[0]["price_no_vat"] == 298448.48
        assert items[1]["price_no_vat"] == 180189.05
        assert items[2]["price_no_vat"] == 100.5
        assert items[3]["price_no_vat"] == 200.0


# ── Classification ───────────────────────────────────────────────────────────

class TestClassification:
    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    def test_classify_mixed_file(self):
        """Servicios file contains labor + delivery + unmatched items."""
        catalogs = _load_catalogs()
        data = DUX_FILE_2.read_bytes()
        headers, rows = read_file(data, "test.xls")
        items = extract_items(headers, rows, detect_format(headers))

        sku_index = build_sku_index(catalogs)
        classified = classify_items(items, sku_index)

        assert "labor" in classified
        assert "delivery-zones" in classified
        assert len(classified["labor"]) >= 20
        assert len(classified["delivery-zones"]) >= 20
        # Unmatched items exist (materials, new zones, etc.)
        assert len(classified.get("_unmatched", [])) > 0


# ── Diff generation ──────────────────────────────────────────────────────────

class TestDiffGeneration:
    def test_diff_with_price_change(self):
        current = [
            {"sku": "SKU1", "name": "Item 1", "price_ars": 100},
            {"sku": "SKU2", "name": "Item 2", "price_ars": 200},
        ]
        new_items = [
            {"sku": "SKU1", "name": "Item 1", "price_no_vat": 120, "currency": "ARS"},
            {"sku": "SKU2", "name": "Item 2", "price_no_vat": 200, "currency": "ARS"},
        ]
        diff = generate_diff("test", current, new_items)
        assert len(diff["updated"]) == 1
        assert diff["updated"][0]["sku"] == "SKU1"
        assert diff["updated"][0]["old_price"] == 100
        assert diff["updated"][0]["new_price"] == 120
        assert diff["unchanged"] == 1

    def test_diff_with_new_item(self):
        current = [{"sku": "SKU1", "name": "Item 1", "price_ars": 100}]
        new_items = [
            {"sku": "SKU1", "name": "Item 1", "price_no_vat": 100, "currency": "ARS"},
            {"sku": "SKU3", "name": "Item 3", "price_no_vat": 300, "currency": "ARS"},
        ]
        diff = generate_diff("test", current, new_items)
        assert len(diff["new"]) == 1
        assert diff["new"][0]["sku"] == "SKU3"

    def test_diff_missing_items(self):
        current = [
            {"sku": "SKU1", "name": "Item 1", "price_ars": 100},
            {"sku": "SKU2", "name": "Item 2", "price_ars": 200},
        ]
        new_items = [
            {"sku": "SKU1", "name": "Item 1", "price_no_vat": 100, "currency": "ARS"},
        ]
        diff = generate_diff("test", current, new_items)
        assert len(diff["missing"]) == 1
        assert diff["missing"][0]["sku"] == "SKU2"

    def test_diff_zero_price_skipped(self):
        current = [{"sku": "SKU1", "name": "Item 1", "price_ars": 100}]
        new_items = [
            {"sku": "SKU1", "name": "Item 1", "price_no_vat": 0, "currency": "ARS"},
        ]
        diff = generate_diff("test", current, new_items)
        assert len(diff["zero_price"]) == 1
        assert len(diff["updated"]) == 0  # $0 items are not applied

    def test_diff_large_change_warning(self):
        current = [{"sku": "SKU1", "name": "Item 1", "price_ars": 100}]
        new_items = [
            {"sku": "SKU1", "name": "Item 1", "price_no_vat": 200, "currency": "ARS"},
        ]
        diff = generate_diff("test", current, new_items)
        assert len(diff["warnings"]) >= 1
        assert "100.0%" in diff["warnings"][0]

    def test_diff_currency_mismatch_uses_catalog_currency(self):
        """When file says USD but catalog is ARS, diff must use price_ars."""
        current = [
            {"sku": "GRAAMA", "name": "Granito Amadeus", "price_ars": 275957.91, "currency": "ARS"},
        ]
        new_items = [
            {"sku": "GRAAMA", "name": "Granito Amadeus", "price_no_vat": 298448.48, "currency": "USD"},
        ]
        diff = generate_diff("materials-granito-nacional", current, new_items)
        assert diff["currency"] == "ARS"
        assert diff["file_currency"] == "USD"
        assert diff["price_field"] == "price_ars"
        assert len(diff["updated"]) == 1
        assert diff["updated"][0]["old_price"] == 275957.91
        assert diff["updated"][0]["new_price"] == 298448.48
        assert diff["unchanged"] == 0


# ── Full pipeline ────────────────────────────────────────────────────────────

class TestFullPipeline:
    @pytest.mark.skipif(not DUX_FILE_1.exists(), reason="Dux file 1 not available")
    def test_pipeline_materials(self):
        """Full pipeline on Silestone Dux file."""
        catalogs = _load_catalogs()
        data = DUX_FILE_1.read_bytes()
        result = parse_import_file(data, "silestone.xls", catalogs)

        assert result["format"] == "dux_materials_usd"
        assert result["total_items"] >= 30
        assert "materials-silestone" in result["catalogs"]
        assert result["iva_warning"] is False

        sil_diff = result["catalogs"]["materials-silestone"]
        assert sil_diff["currency"] == "USD"
        # Most items should match (OK)
        assert sil_diff["unchanged"] >= 25

    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    def test_pipeline_servicios(self):
        """Full pipeline on Servicios/Flete Dux file."""
        catalogs = _load_catalogs()
        data = DUX_FILE_2.read_bytes()
        result = parse_import_file(data, "servicios.xls", catalogs)

        assert result["format"] == "dux_servicios_ars"
        assert result["total_items"] >= 70
        assert "labor" in result["catalogs"]
        assert "delivery-zones" in result["catalogs"]
        assert len(result["unmatched"]) > 0  # Materials mixed in

        labor_diff = result["catalogs"]["labor"]
        assert labor_diff["currency"] == "ARS"
        # Most labor items should match
        assert labor_diff["unchanged"] >= 25

    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    def test_pipeline_envber_diff(self):
        """ENVBER should show as updated (Dux=86776 vs catalog=68181)."""
        catalogs = _load_catalogs()
        data = DUX_FILE_2.read_bytes()
        result = parse_import_file(data, "servicios.xls", catalogs)

        dz_diff = result["catalogs"]["delivery-zones"]
        envber = next((u for u in dz_diff["updated"] if u["sku"] == "ENVBER"), None)
        assert envber is not None, f"ENVBER should be in updated list: {[u['sku'] for u in dz_diff['updated']]}"
        assert abs(envber["new_price"] - 86776.86) < 1
        assert abs(envber["old_price"] - 68181.82) < 1
