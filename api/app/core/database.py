import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

_engine_kwargs = {
    "echo": settings.APP_ENV == "development",
    "pool_pre_ping": True,
}
# Pool config only for PostgreSQL (SQLite doesn't support it)
if "sqlite" not in settings.DATABASE_URL:
    _engine_kwargs.update(pool_size=5, max_overflow=10, pool_timeout=30, pool_recycle=600)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        from app.models import quote, user  # noqa - ensures models are registered
        await conn.run_sync(Base.metadata.create_all)

        # Migrations only needed for PostgreSQL (existing deploys)
        # SQLite creates tables fresh via create_all above
        if "sqlite" in settings.DATABASE_URL:
            return

        # Migrate: expand varchar columns + add parent_quote_id
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE quotes "
                "ALTER COLUMN client_name TYPE VARCHAR(500), "
                "ALTER COLUMN project TYPE VARCHAR(500), "
                "ALTER COLUMN material TYPE VARCHAR(500)"
            )
        )
        for col_sql in [
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS parent_quote_id VARCHAR",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'operator'",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS drive_file_id VARCHAR(200)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS quote_breakdown JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS source_files JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1 NOT NULL",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS notes TEXT",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS client_phone VARCHAR(100)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS client_email VARCHAR(200)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS localidad VARCHAR(200)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS colocacion BOOLEAN DEFAULT FALSE",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS pileta VARCHAR(50)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS anafe BOOLEAN DEFAULT FALSE",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS pieces JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(100)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS change_history JSON DEFAULT '[]'",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS sink_type JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS is_building BOOLEAN DEFAULT FALSE",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS quote_kind VARCHAR(30) DEFAULT 'standard'",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS comparison_group_id VARCHAR(200)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS drive_pdf_url VARCHAR(500)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS drive_excel_url VARCHAR(500)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS resumen_obra JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS email_draft JSON",
            # PR #24 — Condiciones de Contratación PDF para edificios.
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS condiciones_pdf JSON",
            # PR #19 — backfill is_building para quotes que tenían is_edificio=true
            # solo en el JSON breakdown. Idempotente (UPDATE WHERE).
            "UPDATE quotes SET is_building = TRUE "
            "WHERE (is_building IS NULL OR is_building = FALSE) "
            "AND quote_breakdown IS NOT NULL "
            "AND (quote_breakdown->>'is_edificio')::text = 'true'",
        ]:
            try:
                await conn.execute(__import__("sqlalchemy").text(col_sql))
            except Exception as e:
                err_lower = str(e).lower()
                if "already exists" in err_lower or "duplicate" in err_lower:
                    pass  # Idempotent — column already exists
                else:
                    logging.error(f"Migration FAILED: {col_sql[:60]}... → {e}")
                    raise

        # Create token_usage table for API cost tracking
        await conn.execute(
            __import__("sqlalchemy").text("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    id SERIAL PRIMARY KEY,
                    quote_id VARCHAR(200),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cache_read_tokens INTEGER DEFAULT 0,
                    cache_write_tokens INTEGER DEFAULT 0,
                    model VARCHAR(50) DEFAULT 'sonnet',
                    cost_usd FLOAT DEFAULT 0.0,
                    iterations INTEGER DEFAULT 1
                )
            """)
        )

        # Create catalogs table for persistent catalog storage
        await conn.execute(
            __import__("sqlalchemy").text("""
                CREATE TABLE IF NOT EXISTS catalogs (
                    name VARCHAR(100) PRIMARY KEY,
                    content JSON NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
        )

        # Create catalog_backups table for import safety
        await conn.execute(
            __import__("sqlalchemy").text("""
                CREATE TABLE IF NOT EXISTS catalog_backups (
                    id SERIAL PRIMARY KEY,
                    catalog_name VARCHAR(100) NOT NULL,
                    content JSON NOT NULL,
                    source_file VARCHAR(500),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    stats JSON
                )
            """)
        )

        # Add 'pending' value to quotestatus enum if not present
        try:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TYPE quotestatus ADD VALUE IF NOT EXISTS 'PENDING'"
                )
            )
        except Exception as e:
            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                logging.error(f"Migration FAILED: add PENDING to quotestatus → {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def cleanup_empty_drafts():
    """Delete draft quotes that are truly abandoned placeholders.

    "Abandoned" means: inactive for >1h AND nothing real attached —
    no client_name, no plano adjunto, no historial de chat. Un quote
    con cualquiera de esos es trabajo en curso y NO se toca.

    Causa raíz del bug que arregla esta función (ver regresión en
    tests/test_cleanup_drafts.py): antes borrábamos cualquier draft con
    `material IS NULL` más de 1h de antigüedad. Pero `material` se setea
    recién en Paso 2 (tras confirmar el despiece), así que durante todo
    el Paso 1 — brief, plano, Dual Read, revisar medidas — material
    queda NULL. Si el operador tardaba >1h (esperar a Opus, corregir,
    revisar con cliente) y otro tab disparaba `POST /quotes` (que lanza
    cleanup fire-and-forget), o Railway hacía cold-start, el quote se
    borraba en pleno flow y `[DUAL_READ_CONFIRMED]` volvía 404 → el
    frontend redirigía al listado perdiendo todo el trabajo.

    Fix:
    - Usar `updated_at` en vez de `created_at` — actividad reciente
      preserva la quote aunque sea vieja.
    - Sacar el check de `material IS NULL` — material null es estado
      normal en Paso 1.
    - Preservar cualquier quote con source_files (plano pegado) o con
      mensajes en el historial.
    """
    if settings.APP_ENV == "test":
        return  # Skip cleanup in test environment

    await _cleanup_empty_drafts_impl()


async def _cleanup_empty_drafts_impl():
    """Implementation sin el guard de APP_ENV=test para poder testear."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete, cast, String
    from app.models.quote import Quote

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Quote).where(
                Quote.status == "draft",
                # "Idle for >1h" — updated_at refleja la última edición,
                # not created_at. Un quote activo se actualiza en cada turno
                # de chat (messages, quote_breakdown, source_files), así que
                # nunca llega al cutoff mientras el operador esté laburando.
                Quote.updated_at < cutoff,
                # Empty placeholder: sin cliente asignado.
                (Quote.client_name == "") | (Quote.client_name.is_(None)),
                # Nunca borrar si hay plano adjunto (es trabajo real).
                # source_files arranca como NULL; al subir el primer plano
                # pasa a una lista con 1+ items.
                (Quote.source_files.is_(None)) | (cast(Quote.source_files, String).in_(("null", "[]"))),
                # Nunca borrar si hay historial de chat.
                # messages arranca como [] (default=list), pasa a >1 item
                # apenas Valentina responde.
                cast(Quote.messages, String).in_(("null", "[]")),
                # Never delete web-originated quotes — they may be in progress
                (Quote.source != "web") | (Quote.source.is_(None)),
            )
        )
        if result.rowcount > 0:
            await db.commit()
            logging.info(f"Cleaned up {result.rowcount} empty draft(s)")
        else:
            await db.commit()
