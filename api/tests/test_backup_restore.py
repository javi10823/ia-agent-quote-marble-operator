"""Ciclo completo backup → restore · sub-PR 22.2.b.

test_import_endpoints.py cubre apply→backup y restore-404; acá cubrimos el
ROUND-TRIP real: seed → apply (cambia precio + backup v1) → restore →
contenido vuelve a v1 + se crea un backup de seguridad pre-restore.
"""
from __future__ import annotations

import json

import pytest


def _servicios_csv(price: str) -> bytes:
    rows = [
        ["Código", "Producto", "Precio de Venta", "Ultima Modificacion", "Precio de Venta($)", "Precio De Venta Con IVA($)"],
        ["ANAFE", "AGUJERO ANAFE", price, "09/04/2026", price, "0"],
    ]
    return "\n".join(",".join(str(c) for c in r) for r in rows).encode("utf-8")


class TestBackupRestoreRoundTrip:
    @pytest.mark.asyncio
    async def test_full_cycle_restores_previous_content(self, client):
        # 1. Seed labor con un precio conocido (v1).
        seed = [{"sku": "ANAFE", "name": "AGUJERO ANAFE", "price_ars": 1000, "currency": "ARS", "price_includes_vat": False}]
        r = await client.put("/api/catalog/labor", json={"content": seed})
        assert r.status_code == 200, r.text

        # 2. Apply: sube ANAFE a 40000 → backea v1, deja v2.
        r = await client.post(
            "/api/catalog/import-apply",
            files={"file": ("dux_v2.csv", _servicios_csv("40000"), "text/csv")},
            data={"catalogs": json.dumps(["labor"]), "include_new": "false", "source_file": "dux_v2.csv"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"]

        # v2 activo: ANAFE = 40000
        cur = await client.get("/api/catalog/labor")
        anafe = next(i for i in cur.json() if i["sku"] == "ANAFE")
        assert anafe["price_ars"] == 40000

        # 3. Listar backups → tomar el más reciente (el de v1).
        b = await client.get("/api/catalog/backups/labor")
        assert b.status_code == 200
        backups = b.json()
        assert len(backups) >= 1
        backup_id = backups[0]["id"]

        # 4. Restaurar.
        r = await client.post(f"/api/catalog/backups/{backup_id}/restore")
        assert r.status_code == 200, r.text
        assert r.json()["ok"]
        assert r.json()["catalog"] == "labor"

        # 5. Contenido vuelve a v1 (ANAFE = 1000).
        cur = await client.get("/api/catalog/labor")
        anafe = next(i for i in cur.json() if i["sku"] == "ANAFE")
        assert anafe["price_ars"] == 1000

        # 6. Safety net: se creó un backup pre-restore del estado v2.
        b2 = await client.get("/api/catalog/backups/labor")
        assert len(b2.json()) > len(backups)
        assert any(
            "pre-restore" in (bk.get("source_file") or "") for bk in b2.json()
        )
