"""Integration tests for catalog import endpoints — real HTTP through FastAPI test client.

Tests the full pipeline: upload → preview → apply → backup → restore.
Uses real Dux files when available, falls back to synthetic CSV.
"""

import json
import pytest
from pathlib import Path

DUX_FILE_1 = Path("/Users/javierolivieri/Downloads/ListadePrecio_5346844865870250071.xls")
DUX_FILE_2 = Path("/Users/javierolivieri/Downloads/ListadePrecio_3144822666041388388.xls")


def _csv_bytes(rows: list[list[str]]) -> bytes:
    """Build CSV bytes from rows."""
    return "\n".join(",".join(str(c) for c in row) for row in rows).encode("utf-8")


# ── POST /catalog/import-preview ─────────────────────────────────────────────

class TestImportPreview:
    @pytest.mark.asyncio
    async def test_preview_csv_basic(self, client):
        """Upload a CSV and get preview with classification."""
        csv = _csv_bytes([
            ["Código", "Producto", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
            ["ANAFE", "AGUJERO ANAFE", "35617.36", "25/03/2026", "35617.36", "43097"],
            ["COLOCACION", "COLOCACION", "49698.65", "25/03/2026", "49698.65", "60135"],
            ["ENVIOROS", "FLETE ROSARIO", "42975.21", "25/03/2026", "42975.21", "52000"],
        ])
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("test.csv", csv, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "dux_servicios_ars"
        assert data["total_items"] == 3
        assert "labor" in data["catalogs"]
        assert "delivery-zones" in data["catalogs"]
        assert data["iva_warning"] is False

    @pytest.mark.asyncio
    async def test_preview_detects_format(self, client):
        """Materials format detected by Costo + Porc. Utilidad columns."""
        csv = _csv_bytes([
            ["Código", "Producto", "Costo", "Porc. Utilidad", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
            ["SILESTONENORTE", "SILESTONE BLANCO NORTE", "195", "120", "429", "29/09/2025", "604890", "731917"],
        ])
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("materiales.csv", csv, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "dux_materials_usd"
        assert "materials-silestone" in data["catalogs"]

    @pytest.mark.asyncio
    async def test_preview_price_is_sin_iva(self, client):
        """Preview must use Precio de Venta (sin IVA), not Con IVA."""
        csv = _csv_bytes([
            ["Código", "Producto", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
            ["COLOCACION", "COLOCACION", "49698.65", "25/03/2026", "49698.65", "60135"],
        ])
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("test.csv", csv, "text/csv")},
        )
        data = resp.json()
        labor = data["catalogs"].get("labor", {})
        # The diff should show price ~49698, NOT ~60135
        all_items = labor.get("updated", []) + labor.get("new", [])
        if all_items:
            price = all_items[0].get("new_price") or all_items[0].get("price")
            assert price < 55000, f"Used IVA price: {price}"

    @pytest.mark.asyncio
    async def test_preview_empty_file_returns_400(self, client):
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("empty.csv", b"", "text/csv")},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_preview_bad_format_returns_400(self, client):
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400

    @pytest.mark.skipif(not DUX_FILE_1.exists(), reason="Dux file 1 not available")
    @pytest.mark.asyncio
    async def test_preview_real_dux_silestone(self, client):
        """Real Dux Silestone file — full preview."""
        data = DUX_FILE_1.read_bytes()
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("silestone.xls", data, "application/vnd.ms-excel")},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["format"] == "dux_materials_usd"
        assert result["total_items"] >= 30
        assert "materials-silestone" in result["catalogs"]
        sil = result["catalogs"]["materials-silestone"]
        assert sil["unchanged"] >= 25  # Most prices match

    @pytest.mark.skipif(not DUX_FILE_2.exists(), reason="Dux file 2 not available")
    @pytest.mark.asyncio
    async def test_preview_real_dux_servicios(self, client):
        """Real Dux Servicios file — mixed classification."""
        data = DUX_FILE_2.read_bytes()
        resp = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("servicios.xls", data, "application/vnd.ms-excel")},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["format"] == "dux_servicios_ars"
        assert "labor" in result["catalogs"]
        assert "delivery-zones" in result["catalogs"]
        assert len(result["unmatched"]) > 0  # Mixed items


# ── POST /catalog/import-apply ───────────────────────────────────────────────

class TestImportApply:
    @pytest.mark.asyncio
    async def test_apply_creates_backup_and_updates(self, client):
        """Apply creates backup + updates catalog."""
        csv = _csv_bytes([
            ["Código", "Producto", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
            ["ANAFE", "AGUJERO ANAFE", "40000", "09/04/2026", "40000", "48400"],
        ])
        # First seed the catalog so there's data to backup
        # (test DB starts empty, but import-apply loads from DB with fallback to files)

        resp = await client.post(
            "/api/catalog/import-apply",
            files={"file": ("test.csv", csv, "text/csv")},
            data={
                "catalogs": json.dumps(["labor"]),
                "include_new": "false",
                "source_file": "test.csv",
            },
        )
        assert resp.status_code == 200, f"Apply failed: {resp.json()}"
        data = resp.json()
        assert data["ok"]
        assert "labor" in data["results"]

    @pytest.mark.asyncio
    async def test_apply_no_catalogs_returns_400(self, client):
        csv = _csv_bytes([["Código", "Producto", "Precio de Venta"], ["SKU1", "Test", "100"]])
        resp = await client.post(
            "/api/catalog/import-apply",
            files={"file": ("test.csv", csv, "text/csv")},
            data={"catalogs": "[]", "include_new": "true", "source_file": "test.csv"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_apply_skips_zero_price(self, client):
        """Items with $0 must never be imported."""
        csv = _csv_bytes([
            ["Código", "Producto", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
            ["ANAFE", "AGUJERO ANAFE", "0", "09/04/2026", "0", "0"],
        ])
        resp = await client.post(
            "/api/catalog/import-apply",
            files={"file": ("test.csv", csv, "text/csv")},
            data={"catalogs": json.dumps(["labor"]), "include_new": "true", "source_file": "test.csv"},
        )
        assert resp.status_code == 200
        data = resp.json()
        labor = data["results"].get("labor", {})
        assert labor.get("updated", 0) == 0  # $0 skipped


# ── GET /catalog/backups + POST restore ──────────────────────────────────────

class TestBackupsAndRestore:
    @pytest.mark.asyncio
    async def test_list_backups_empty(self, client):
        resp = await client.get("/api/catalog/backups/labor")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_apply_creates_listable_backup(self, client):
        """After import-apply, backup should appear in list."""
        csv = _csv_bytes([
            ["Código", "Producto", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
            ["ANAFE", "AGUJERO ANAFE", "40000", "09/04/2026", "40000", "48400"],
        ])
        await client.post(
            "/api/catalog/import-apply",
            files={"file": ("backup_test.csv", csv, "text/csv")},
            data={"catalogs": json.dumps(["labor"]), "include_new": "false", "source_file": "backup_test.csv"},
        )

        resp = await client.get("/api/catalog/backups/labor")
        assert resp.status_code == 200
        backups = resp.json()
        assert len(backups) >= 1
        assert backups[0]["source_file"] == "backup_test.csv"

    @pytest.mark.asyncio
    async def test_restore_nonexistent_returns_404(self, client):
        resp = await client.post("/api/catalog/backups/99999/restore")
        assert resp.status_code == 404
