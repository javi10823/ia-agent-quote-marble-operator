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
    _engine_kwargs.update(pool_size=5, max_overflow=10, pool_timeout=30)

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
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS notes TEXT",
        ]:
            try:
                await conn.execute(__import__("sqlalchemy").text(col_sql))
            except Exception as e:
                if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                    logging.warning(f"Migration: {col_sql[:60]}... → {e}")


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
            )
        )
        if result.rowcount > 0:
            await db.commit()
            logging.info(f"Cleaned up {result.rowcount} empty draft(s)")
        else:
            await db.commit()
