import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        from app.models import quote  # noqa - ensures models are registered
        await conn.run_sync(Base.metadata.create_all)

        # Migrate: expand varchar columns + add new columns
        for col_sql in [
            "ALTER TABLE quotes ALTER COLUMN client_name TYPE VARCHAR(500)",
            "ALTER TABLE quotes ALTER COLUMN project TYPE VARCHAR(500)",
            "ALTER TABLE quotes ALTER COLUMN material TYPE VARCHAR(500)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS parent_quote_id VARCHAR",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'operator'",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS drive_file_id VARCHAR(200)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS quote_breakdown JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS source_files JSON",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT TRUE",
        ]:
            try:
                await conn.execute(__import__("sqlalchemy").text(col_sql))
            except Exception as e:
                logger.debug(f"Migration skipped: {col_sql[:60]}... ({e})")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
