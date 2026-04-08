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
    """Delete draft quotes older than 1 hour that lack client + material.
    Drafts with real data (client_name AND material set) are preserved."""
    if settings.APP_ENV == "test":
        return  # Skip cleanup in test environment

    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete
    from app.models.quote import Quote

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Quote).where(
                Quote.status == "draft",
                Quote.created_at < cutoff,
                # Only delete if missing client OR material (incomplete)
                (Quote.client_name == "") | (Quote.client_name.is_(None)) | (Quote.material.is_(None)),
                # Never delete web-originated quotes — they may be in progress
                (Quote.source != "web") | (Quote.source.is_(None)),
            )
        )
        if result.rowcount > 0:
            await db.commit()
            logging.info(f"Cleaned up {result.rowcount} empty draft(s)")
        else:
            await db.commit()
