"""Tests de `GET /api/quotes/{quote_id}/pieces` · sub-PR despiece-real-wire.

Cobertura:
- Quote con dual_read_result · tramos + zócalos → serializa al shape Piece
- Quote sin dual_read_result → status="pending", lista vacía
- Quote con dual_read_result pero sectores vacíos → status="failed"
- Quote inexistente → 404
- Helper _serialize_dual_read_to_pieces · tests unitarios del mapeo
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.agent.router import _serialize_dual_read_to_pieces, _field_valor


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_quote(db_session, quote_id: str, breakdown: dict | None = None):
    """Inserta una quote draft con el breakdown dado (o None)."""
    from app.models.quote import Quote, QuoteStatus

    db_session.add(
        Quote(
            id=quote_id,
            client_name="Test Client",
            project="Cocina test",
            material="Silestone Blanco Norte",
            status=QuoteStatus.DRAFT,
            quote_breakdown=breakdown,
        )
    )


def _field(valor: float) -> dict:
    """FieldValue shape usado por dual_read_result."""
    return {"valor": valor, "opus": None, "sonnet": None, "status": "CONFIRMADO"}


# ── Tests del helper de serialización ───────────────────────────────────────


class TestFieldValor:
    def test_extracts_from_dict_shape(self):
        assert _field_valor({"valor": 2.5}) == 2.5

    def test_extracts_from_plain_number(self):
        assert _field_valor(1.5) == 1.5
        assert _field_valor(3) == 3.0

    def test_none_returns_none(self):
        assert _field_valor(None) is None

    def test_dict_without_valor_returns_none(self):
        assert _field_valor({"opus": 1.0}) is None

    def test_invalid_valor_returns_none(self):
        assert _field_valor({"valor": "abc"}) is None


class TestSerializeDualRead:
    def test_empty_dual_read(self):
        assert _serialize_dual_read_to_pieces({}) == []
        assert _serialize_dual_read_to_pieces(None) == []

    def test_single_mesada_no_zocalos(self):
        dr = {
            "sectores": [{
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Mesada principal",
                    "largo_m": _field(2.5),
                    "ancho_m": _field(0.6),
                    "quantity": 1,
                    "zocalos": [],
                }]
            }]
        }
        pieces = _serialize_dual_read_to_pieces(dr)
        assert len(pieces) == 1
        p = pieces[0]
        assert p["id"] == "t1"
        assert p["type"] == "encimera"
        assert p["label"] == "Mesada principal"
        assert p["width_mm"] == 2500.0
        assert p["depth_mm"] == 600.0
        assert p["quantity"] == 1
        assert p["origin"] == "IA"

    def test_mesada_manual_flag_maps_to_editado(self):
        dr = {
            "sectores": [{
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Mesada principal",
                    "largo_m": _field(2.5),
                    "ancho_m": _field(0.6),
                    "_manual": True,
                }]
            }]
        }
        pieces = _serialize_dual_read_to_pieces(dr)
        assert pieces[0]["origin"] == "EDITADO"

    def test_mesada_with_zocalos_emits_one_piece_per_zocalo(self):
        dr = {
            "sectores": [{
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Mesada principal",
                    "largo_m": _field(2.5),
                    "ancho_m": _field(0.6),
                    "zocalos": [
                        {"lado": "trasero", "ml": 2.5, "alto_m": 0.05, "quantity": 1},
                        {"lado": "lateral_izq", "ml": 0.6, "alto_m": 0.05, "quantity": 1},
                    ],
                }]
            }]
        }
        pieces = _serialize_dual_read_to_pieces(dr)
        # 1 mesada + 2 zócalos
        assert len(pieces) == 3
        assert pieces[0]["type"] == "encimera"
        assert pieces[1]["type"] == "zocalo"
        assert pieces[1]["label"] == "Zócalo trasero"
        assert pieces[1]["width_mm"] == 2500.0
        assert pieces[1]["depth_mm"] == 50.0
        assert pieces[2]["label"] == "Zócalo lateral_izq"

    def test_skips_tramos_without_required_dimensions(self):
        dr = {
            "sectores": [{
                "tramos": [
                    {"id": "t1", "descripcion": "Sin medidas"},  # falta largo/ancho
                    {
                        "id": "t2",
                        "descripcion": "Mesada válida",
                        "largo_m": _field(2.0),
                        "ancho_m": _field(0.6),
                    },
                ]
            }]
        }
        pieces = _serialize_dual_read_to_pieces(dr)
        assert len(pieces) == 1
        assert pieces[0]["id"] == "t2"

    def test_quantity_int_coerced(self):
        dr = {
            "sectores": [{
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Mesada",
                    "largo_m": _field(1.0),
                    "ancho_m": _field(0.6),
                    "quantity": "24",
                }]
            }]
        }
        pieces = _serialize_dual_read_to_pieces(dr)
        assert pieces[0]["quantity"] == 24

    def test_quantity_invalid_defaults_to_one(self):
        dr = {
            "sectores": [{
                "tramos": [{
                    "id": "t1",
                    "descripcion": "Mesada",
                    "largo_m": _field(1.0),
                    "ancho_m": _field(0.6),
                    "quantity": "abc",
                }]
            }]
        }
        pieces = _serialize_dual_read_to_pieces(dr)
        assert pieces[0]["quantity"] == 1


# ── Tests del endpoint REST ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestListPiecesEndpoint:
    async def test_404_quote_not_found(self, client):
        random_id = str(uuid.uuid4())
        r = await client.get(f"/api/quotes/{random_id}/pieces")
        assert r.status_code == 404
        assert r.json()["detail"] == "quote_not_found"

    async def test_pending_when_no_breakdown(self, client, db_session):
        qid = str(uuid.uuid4())
        _seed_quote(db_session, qid, breakdown=None)
        await db_session.commit()
        r = await client.get(f"/api/quotes/{qid}/pieces")
        assert r.status_code == 200
        data = r.json()
        assert data["pieces"] == []
        assert data["status"] == "pending"

    async def test_pending_when_breakdown_has_no_dual_read(self, client, db_session):
        qid = str(uuid.uuid4())
        _seed_quote(db_session, qid, breakdown={"other_key": "x"})
        await db_session.commit()
        r = await client.get(f"/api/quotes/{qid}/pieces")
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    async def test_failed_when_dual_read_has_no_valid_tramos(self, client, db_session):
        qid = str(uuid.uuid4())
        _seed_quote(db_session, qid, breakdown={"dual_read_result": {"sectores": []}})
        await db_session.commit()
        r = await client.get(f"/api/quotes/{qid}/pieces")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "failed"
        assert "no detectó piezas" in data["warnings"][0].lower()

    async def test_done_with_real_text_dispiece_shape(self, client, db_session):
        """Brief solo texto · `parsed_pieces_to_card()` produce este shape."""
        qid = str(uuid.uuid4())
        breakdown = {
            "dual_read_result": {
                "source": "TEXT",
                "sectores": [{
                    "id": "sector_1",
                    "tipo": "cocina",
                    "tramos": [
                        {
                            "id": "t1",
                            "descripcion": "Mesada principal",
                            "largo_m": _field(2.5),
                            "ancho_m": _field(0.6),
                            "quantity": 1,
                            "_manual": True,
                            "zocalos": [{
                                "lado": "trasero",
                                "ml": 2.5,
                                "alto_m": 0.05,
                                "quantity": 1,
                            }],
                        },
                        {
                            "id": "t2",
                            "descripcion": "Mesada isla",
                            "largo_m": _field(1.8),
                            "ancho_m": _field(0.9),
                            "quantity": 1,
                            "_manual": True,
                            "zocalos": [],
                        },
                    ],
                }],
            }
        }
        _seed_quote(db_session, qid, breakdown=breakdown)
        await db_session.commit()

        r = await client.get(f"/api/quotes/{qid}/pieces")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "done"
        # 2 mesadas + 1 zócalo
        assert len(data["pieces"]) == 3
        labels = [p["label"] for p in data["pieces"]]
        assert "Mesada principal" in labels
        assert "Mesada isla" in labels
        assert "Zócalo trasero" in labels
        # Origen EDITADO porque tramos tienen _manual=True
        mesadas = [p for p in data["pieces"] if p["type"] == "encimera"]
        assert all(p["origin"] == "EDITADO" for p in mesadas)
        # _manual flag NO se expone al frontend
        for p in data["pieces"]:
            assert "_manual" not in p
