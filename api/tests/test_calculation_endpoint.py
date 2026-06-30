"""Tests para GET /api/quotes/{id}/calculation · sub-PR calculation-real-wire.

Cobertura:
- Helper unit tests · _format_ars · _format_usd · _format_qty_m2 · _is_flete_item
- Endpoint REST · residential complete · residential pending · edificio
  not_supported · quote 404
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.agent.router import (
    _format_ars,
    _format_usd,
    _format_qty_m2,
    _is_flete_item,
    _serialize_residential_calc,
)


# ═══════════════════════════════════════════════════════
# Helpers · format
# ═══════════════════════════════════════════════════════


class TestFormatHelpers:
    @pytest.mark.parametrize("value,expected", [
        (1234.56, "$1.234,56"),
        (198244, "$198.244,00"),
        (0, "$0,00"),
        (None, "—"),
        ("abc", "—"),
        (1500000.5, "$1.500.000,50"),
    ])
    def test_format_ars(self, value, expected):
        assert _format_ars(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (1822, "USD 1.822"),
        (519, "USD 519"),
        (0, "USD 0"),
        (None, "—"),
        ("xyz", "—"),
    ])
    def test_format_usd(self, value, expected):
        assert _format_usd(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (2.82, "2,82 m²"),
        (0.69, "0,69 m²"),
        (10, "10,00 m²"),
        (None, "—"),
    ])
    def test_format_qty_m2(self, value, expected):
        assert _format_qty_m2(value) == expected


# ═══════════════════════════════════════════════════════
# Heurística flete
# ═══════════════════════════════════════════════════════


class TestIsFlete:
    @pytest.mark.parametrize("item,expected", [
        ({"description": "Flete + toma medidas ibarlucea"}, True),
        ({"description": "flete rosario"}, True),
        ({"description": "FLETE × 5"}, True),
        ({"description": "  Flete extra"}, True),
        ({"description": "Agujero anafe"}, False),
        ({"description": "Agujero y pegado pileta"}, False),
        ({"description": "Colocación"}, False),
        ({"description": ""}, False),
        ({"description": None}, False),
        ({}, False),
    ])
    def test_heuristic(self, item, expected):
        assert _is_flete_item(item) == expected


# ═══════════════════════════════════════════════════════
# Serializer · _serialize_residential_calc
# ═══════════════════════════════════════════════════════


class _FakeQuote:
    """Quote fake compatible con _serialize_residential_calc."""
    def __init__(self, quote_id: str, notes: str = ""):
        self.id = quote_id
        self.notes = notes


def _hugo_zimaro_breakdown() -> dict:
    """Shape real del breakdown residential confirmado en PASO 0 EXP/EXP-2
    contra Railway DB · quote 3d09fa0f-24ca-498e-ba83-2caa759ab4ac."""
    return {
        "is_edificio": False,
        "material_name": "SILESTONE BLANCO NORTE",
        "material_m2": 2.82,
        "material_total": 1464,
        "material_total_bruto": 1464,
        "material_price_unit": 519,
        "material_price_base": 429.0,
        "material_currency": "USD",
        "material_type": "silestone",
        "discount_pct": 0,
        "discount_amount": 0,
        "mo_items": [
            {"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 65147, "base_price": 53840.17, "total": 65147},
            {"description": "Agujero anafe", "quantity": 1, "unit_price": 43097, "base_price": 35617.36, "total": 43097},
            {"description": "Flete + toma medidas ibarlucea", "quantity": 1, "unit_price": 90000, "base_price": 74380.17, "total": 90000},
        ],
        "merma": {
            "aplica": True,
            "desperdicio": 1.38,
            "sobrante_m2": 0.69,
            "motivo": "Desperdicio 1.38 m² ≥ 1.0 → sobrante 0.69 m²",
        },
        "sobrante_m2": 0.69,
        "sobrante_total": 358,
        "total_ars": 198244,
        "total_usd": 1822,
        "colocacion": False,
        "anafe": True,
        "pileta": "empotrada_cliente",
        "pileta_qty": 1,
        "sinks": [],
        "localidad": "ibarlucea",
        "delivery_days": "30 días",
        "piece_details": [
            {"description": "Mesada en L - parte 1", "largo": 2.4, "dim2": 0.6, "m2": 1.44, "quantity": 1},
        ],
        "ok": True,
    }


class TestSerializeResidential:
    def test_hugo_zimaro_residential_full(self):
        bd = _hugo_zimaro_breakdown()
        q = _FakeQuote("hugo-test-id", notes="Cliente trae bacha")
        resp = _serialize_residential_calc(bd, q)
        assert resp.status == "ok"
        assert resp.quoteId == "hugo-test-id"
        # Material
        assert len(resp.material["rows"]) == 1
        assert resp.material["rows"][0]["label"] == "SILESTONE BLANCO NORTE"
        assert resp.material["rows"][0]["qty"] == "2,82 m²"
        assert resp.material["rows"][0]["unit"] == "USD 519"
        assert resp.material["subtotal"] == "USD 1.464"
        # Merma aplica
        assert resp.merma.status == "aplica"
        assert resp.merma.chipLabel == "APLICA"
        assert resp.merma.rows and len(resp.merma.rows) == 1
        # Labor · 2 rows (skip flete)
        assert len(resp.labor["rows"]) == 2
        labels = [r["label"] for r in resp.labor["rows"]]
        assert "Agujero y pegado pileta" in labels
        assert "Agujero anafe" in labels
        # Flete extraído
        assert resp.flete.zona == "Ibarlucea"
        assert resp.flete.qty == "1 viaje"
        assert resp.flete.total == "$90.000,00"
        # Piletas · empotrada_cliente
        assert resp.piletas.variant == "na"
        assert "cliente" in resp.piletas.chipLabel.lower()
        # Totals
        assert resp.totals.ars.value == "$198.244,00"
        assert resp.totals.usd.value == "USD 1.822"
        # Banner
        assert "SILESTONE BLANCO NORTE" in resp.bannerSummary
        assert "2,82 m²" in resp.bannerSummary
        # DatosPdf
        assert resp.datosPdf.plazo == "30 días"
        assert resp.datosPdf.envio == "Incluye flete"
        assert resp.datosPdf.notas == "Cliente trae bacha"

    def test_merma_no_aplica(self):
        bd = _hugo_zimaro_breakdown()
        bd["merma"] = {"aplica": False, "motivo": "Negro Brasil — nunca merma"}
        q = _FakeQuote("test-no-merma")
        resp = _serialize_residential_calc(bd, q)
        assert resp.merma.status == "na"
        assert "Negro Brasil" in resp.merma.chipLabel

    def test_pileta_johnson_with_sinks(self):
        bd = _hugo_zimaro_breakdown()
        bd["pileta"] = "empotrada_johnson"
        bd["sinks"] = [{"name": "PILETA JOHNSON LUXOR S171", "quantity": 1, "unit_price": 268048}]
        q = _FakeQuote("test-johnson")
        resp = _serialize_residential_calc(bd, q)
        assert resp.piletas.variant == "info"
        assert "LUXOR" in (resp.piletas.sub or "")

    def test_pileta_apoyo(self):
        bd = _hugo_zimaro_breakdown()
        bd["pileta"] = "apoyo"
        q = _FakeQuote("test-apoyo")
        resp = _serialize_residential_calc(bd, q)
        assert resp.piletas.variant == "na"
        assert "apoyo" in resp.piletas.chipLabel.lower()

    def test_discount_applied(self):
        bd = _hugo_zimaro_breakdown()
        bd["discount_pct"] = 5
        bd["discount_amount"] = 73
        bd["material_total_bruto"] = 1537
        bd["material_total"] = 1464
        q = _FakeQuote("test-discount")
        resp = _serialize_residential_calc(bd, q)
        # 2 rows: material + discount
        assert len(resp.material["rows"]) == 2
        assert resp.material["rows"][1]["variant"] == "discount"
        assert "−" in resp.material["rows"][1]["total"]


# ═══════════════════════════════════════════════════════
# Endpoint REST · 4 escenarios
# ═══════════════════════════════════════════════════════


def _seed_quote(db_session, quote_id: str, breakdown: dict | None = None, notes: str = ""):
    from app.models.quote import Quote, QuoteStatus
    db_session.add(
        Quote(
            id=quote_id,
            client_name="Test Client",
            project="Cocina test",
            material="SILESTONE BLANCO NORTE",
            status=QuoteStatus.DRAFT,
            quote_breakdown=breakdown,
            notes=notes,
        )
    )


@pytest.mark.asyncio
class TestCalculationEndpoint:
    async def test_404_quote_not_found(self, client):
        random_id = str(uuid.uuid4())
        r = await client.get(f"/api/quotes/{random_id}/calculation")
        assert r.status_code == 404
        assert r.json()["detail"] == "quote_not_found"

    async def test_residential_pending_no_breakdown(self, client, db_session):
        qid = str(uuid.uuid4())
        _seed_quote(db_session, qid, breakdown=None)
        await db_session.commit()
        r = await client.get(f"/api/quotes/{qid}/calculation")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending"
        assert "Cálculo pendiente" in data["bannerSummary"]

    async def test_edificio_not_supported(self, client, db_session):
        qid = str(uuid.uuid4())
        _seed_quote(db_session, qid, breakdown={
            "is_edificio": True,
            "paso2_calc": {"calc_results": {"Negro Boreal": {}}},
        })
        await db_session.commit()
        r = await client.get(f"/api/quotes/{qid}/calculation")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending"
        assert "edificios" in data["bannerSummary"].lower()

    async def test_residential_complete(self, client, db_session):
        qid = str(uuid.uuid4())
        _seed_quote(db_session, qid, breakdown=_hugo_zimaro_breakdown())
        await db_session.commit()
        r = await client.get(f"/api/quotes/{qid}/calculation")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["quoteId"] == qid
        assert data["totals"]["ars"]["value"] == "$198.244,00"
        assert data["totals"]["usd"]["value"] == "USD 1.822"
        # Material + 2 labor (skip flete) + flete separado
        assert len(data["material"]["rows"]) == 1
        assert len(data["labor"]["rows"]) == 2
        assert data["flete"]["qty"] == "1 viaje"
