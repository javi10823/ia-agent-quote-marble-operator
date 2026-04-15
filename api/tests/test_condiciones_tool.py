"""PR #24 — generación de PDF de Condiciones para edificios."""
import pytest
from sqlalchemy import update
from app.models.quote import Quote
from app.modules.agent.tools.condiciones_tool import (
    _build_data, generate_condiciones_pdf,
)


class _Q:
    """Stub Quote para _build_data (no requiere DB)."""
    def __init__(self, client, project):
        self.client_name = client
        self.project = project


def test_build_data_uses_default_plazo():
    q = _Q("DINALE S.A.", "Unidad Penitenciaria N°12")
    data = _build_data(q)
    assert "DINALE S.A." in data["header_line"]
    assert "Unidad Penitenciaria N°12" in data["header_line"]
    # Plazo default debe estar en algún ítem
    plazo_in_items = any("60" in i for i in data["items"])
    assert plazo_in_items
    # Items numerados, no vacíos
    assert len(data["items"]) >= 9


def test_build_data_with_plazo_override():
    q = _Q("DINALE", "Obra X")
    data = _build_data(q, plazo_override="4 meses desde toma de medidas")
    plazo_item = next((i for i in data["items"] if "4 meses" in i), None)
    assert plazo_item is not None
    # Y NO debe contener el default si hay override
    assert not any("60 DIAS" in i for i in data["items"])


@pytest.mark.asyncio
async def test_generate_condiciones_persists_record(client, db_session):
    resp = await client.post("/api/quotes")
    qid = resp.json()["id"]
    await db_session.execute(
        update(Quote).where(Quote.id == qid).values(
            client_name="DINALE S.A.",
            project="Ampliación Penitenciaria N°12",
            is_building=True,
        )
    )
    await db_session.commit()

    record = await generate_condiciones_pdf(db_session, qid)
    assert record["pdf_url"].startswith(f"/files/{qid}/")
    assert record["pdf_url"].endswith(".pdf")
    assert "plazo" in record

    # Persistido en DB
    from sqlalchemy import select
    db_session.expire_all()
    row = (await db_session.execute(
        select(Quote).where(Quote.id == qid)
    )).scalar_one()
    assert row.condiciones_pdf is not None
    assert row.condiciones_pdf["pdf_url"] == record["pdf_url"]


@pytest.mark.asyncio
async def test_quote_detail_exposes_condiciones_pdf(client, db_session):
    resp = await client.post("/api/quotes")
    qid = resp.json()["id"]
    await db_session.execute(
        update(Quote).where(Quote.id == qid).values(
            client_name="X",
            project="Y",
            is_building=True,
            condiciones_pdf={
                "pdf_url": "/files/x.pdf",
                "drive_url": "https://drive/x",
                "generated_at": "2026-04-15T10:00:00+00:00",
                "plazo": "60 DIAS HÁBILES",
            },
        )
    )
    await db_session.commit()

    detail = (await client.get(f"/api/quotes/{qid}")).json()
    assert "condiciones_pdf" in detail
    assert detail["condiciones_pdf"]["plazo"] == "60 DIAS HÁBILES"
