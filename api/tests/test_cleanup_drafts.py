"""Regresión: cleanup_empty_drafts NO debe borrar quotes en curso.

Bug histórico: el cleanup borraba cualquier draft con `material IS NULL`
y `created_at < hace 1h`. Pero durante todo el Paso 1 (brief + plano +
Dual Read + despiece) el `material` queda NULL — se setea recién en
Paso 2. Resultado: si el operador tardaba >1h, otro tab disparaba
`POST /quotes` (que lanza cleanup fire-and-forget), y el quote se
borraba en plena confirmación del despiece → frontend veía 404 →
redirect al listado → trabajo perdido.

Estos tests fijan el contrato nuevo:
- No borrar quotes con `source_files` (plano adjunto)
- No borrar quotes con `messages` (historial de chat)
- Usar `updated_at` en vez de `created_at` (actividad reciente = viva)
- material NULL ya no es señal de abandono
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.quote import Quote, QuoteStatus


# Los helpers necesitan AsyncSessionLocal apuntando al db de test, que
# el fixture `client` ya configura via conftest.py. Por eso dependemos
# de `client` aunque no lo usemos para HTTP — solo para el side-effect
# del binding de AsyncSessionLocal.


async def _insert_quote(db_session, **fields):
    q = Quote(
        id=str(uuid.uuid4()),
        client_name=fields.pop("client_name", ""),
        project=fields.pop("project", ""),
        messages=fields.pop("messages", []),
        status=fields.pop("status", QuoteStatus.DRAFT),
        **fields,
    )
    db_session.add(q)
    await db_session.commit()
    return q


async def _force_timestamps(db_session, quote_id: str, *, updated_at, created_at=None):
    """Setea timestamps manualmente — los defaults de SQLAlchemy ponen NOW,
    y no podemos bypassar func.now() salvo actualizando después del insert."""
    from sqlalchemy import update as sql_update
    values = {"updated_at": updated_at}
    if created_at is not None:
        values["created_at"] = created_at
    await db_session.execute(
        sql_update(Quote).where(Quote.id == quote_id).values(**values)
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_cleanup_preserves_draft_with_plano_attached(client, db_session):
    """Un draft con plano adjunto + material=None NO debe ser borrado,
    aunque lleve >1h. Este es el escenario del bug original."""
    from app.core.database import _cleanup_empty_drafts_impl

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    q = await _insert_quote(
        db_session,
        client_name="",  # Valentina todavía no extrajo
        material=None,  # Paso 2 no ejecutado
        source_files=[{"filename": "plano.pdf", "size": 12345}],  # ← plano adjunto
    )
    await _force_timestamps(db_session, q.id, updated_at=old, created_at=old)

    await _cleanup_empty_drafts_impl()

    # La quote debe seguir viva.
    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is not None, "Cleanup borró un draft con plano adjunto"


@pytest.mark.asyncio
async def test_cleanup_preserves_draft_with_chat_history(client, db_session):
    """Un draft con mensajes en el historial NO debe borrarse — es trabajo real."""
    from app.core.database import _cleanup_empty_drafts_impl

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    q = await _insert_quote(
        db_session,
        client_name="",
        material=None,
        messages=[
            {"role": "user", "content": "Cocina en L con isla"},
            {"role": "assistant", "content": "Dale, ¿me pasás el plano?"},
        ],
    )
    await _force_timestamps(db_session, q.id, updated_at=old, created_at=old)

    await _cleanup_empty_drafts_impl()

    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is not None, "Cleanup borró un draft con historial de chat"


@pytest.mark.asyncio
async def test_cleanup_preserves_draft_with_recent_activity(client, db_session):
    """Un draft con updated_at reciente NO debe borrarse, aunque sea viejo
    de created_at. Este es el fix del filtro created_at→updated_at."""
    from app.core.database import _cleanup_empty_drafts_impl

    old_created = datetime.now(timezone.utc) - timedelta(hours=5)
    recent_update = datetime.now(timezone.utc) - timedelta(minutes=2)
    q = await _insert_quote(db_session, client_name="")
    await _force_timestamps(
        db_session, q.id, created_at=old_created, updated_at=recent_update
    )

    await _cleanup_empty_drafts_impl()

    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is not None, "Cleanup borró un draft con actividad reciente"


@pytest.mark.asyncio
async def test_cleanup_deletes_truly_empty_placeholder(client, db_session):
    """El caso legítimo: un placeholder vacío (sin cliente, sin plano,
    sin mensajes) creado hace >1h. ESE sí debe borrarse."""
    from app.core.database import _cleanup_empty_drafts_impl

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    q = await _insert_quote(db_session, client_name="")
    await _force_timestamps(db_session, q.id, updated_at=old, created_at=old)

    await _cleanup_empty_drafts_impl()

    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is None, "Cleanup no borró un placeholder vacío"


@pytest.mark.asyncio
async def test_cleanup_preserves_draft_with_client_name(client, db_session):
    """Un draft con client_name seteado NO debe borrarse, aun sin plano."""
    from app.core.database import _cleanup_empty_drafts_impl

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    q = await _insert_quote(db_session, client_name="Juan Pérez")
    await _force_timestamps(db_session, q.id, updated_at=old, created_at=old)

    await _cleanup_empty_drafts_impl()

    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is not None, "Cleanup borró un draft con cliente asignado"


@pytest.mark.asyncio
async def test_cleanup_preserves_non_draft_status(client, db_session):
    """Quotes en pending/validated/sent nunca deben tocarse."""
    from app.core.database import _cleanup_empty_drafts_impl

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    q = await _insert_quote(db_session, client_name="", status=QuoteStatus.PENDING)
    await _force_timestamps(db_session, q.id, updated_at=old, created_at=old)

    await _cleanup_empty_drafts_impl()

    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is not None, "Cleanup borró un quote no-draft"


@pytest.mark.asyncio
async def test_cleanup_preserves_web_source_quotes(client, db_session):
    """Quotes con source='web' nunca se tocan — pueden estar en progreso."""
    from app.core.database import _cleanup_empty_drafts_impl

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    q = await _insert_quote(db_session, client_name="", source="web")
    await _force_timestamps(db_session, q.id, updated_at=old, created_at=old)

    await _cleanup_empty_drafts_impl()

    result = await db_session.execute(select(Quote).where(Quote.id == q.id))
    assert result.scalar_one_or_none() is not None, "Cleanup borró un quote source=web"
