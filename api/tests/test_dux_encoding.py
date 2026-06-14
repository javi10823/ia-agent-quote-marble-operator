"""Tests del fallback de encoding del parser CSV · sub-PR 22.2.b (Bug 1).

Antes: `_read_csv` asumía utf-8-sig → los CSV guardados desde Excel en
Windows AR (latin-1 / cp1252) rompían con UnicodeDecodeError → 500/400 sin
mensaje claro. Ahora: fallback explícito a latin-1 + ValueError
user-friendly si ninguno sirve (rama defensiva · latin-1 decodifica todo).
"""
from __future__ import annotations

import pytest

from app.modules.catalog.import_parser import _read_csv


HEADER = "Código,Producto,Precio de Venta"


class TestCsvEncodingFallback:
    def test_utf8_sig_with_bom(self):
        raw = ("﻿" + HEADER + "\nSKU1,Mañana,100").encode("utf-8")
        headers, rows = _read_csv(raw)
        # El BOM no debe quedar pegado a la primera columna
        assert headers[0].strip("﻿") == "Código"
        assert rows[0][1] == "Mañana"

    def test_latin1_fallback(self):
        # "Código" / "Mañana" en latin-1 → bytes inválidos para utf-8-sig
        raw = (HEADER + "\nSKU1,Mañana,100").encode("latin-1")
        with pytest.raises(UnicodeDecodeError):
            raw.decode("utf-8-sig")
        # El parser debe sobrevivir vía fallback latin-1
        headers, rows = _read_csv(raw)
        assert "Producto" in headers
        assert rows[0][0] == "SKU1"
        assert rows[0][1] == "Mañana"


class TestCsvEncodingFallbackEndpoint:
    @pytest.mark.asyncio
    async def test_preview_accepts_latin1_csv(self, client):
        """End-to-end: un CSV latin-1 ya no rompe el import-preview."""
        body = (
            "Código,Producto,Precio de Venta\n"
            "COLOCACION,COLOCACIÓN ESPECIAL,49698.65\n"
        ).encode("latin-1")
        r = await client.post(
            "/api/catalog/import-preview",
            files={"file": ("dux_latin1.csv", body, "text/csv")},
        )
        assert r.status_code == 200, r.text
        assert "catalogs" in r.json()
