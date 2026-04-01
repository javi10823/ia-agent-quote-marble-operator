import os
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

# Set test env vars BEFORE importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_FILE", "test-sa.json")
os.environ.setdefault("GOOGLE_DRIVE_FOLDER_ID", "test-folder-id")
os.environ.setdefault("SECRET_KEY", "test-secret-key-12345")
os.environ.setdefault("APP_ENV", "test")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from app.core.database import Base, get_db
from app.main import app
from app.models.quote import Quote, QuoteStatus


# ── Database fixtures ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """FastAPI test client with DB override."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Data fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_quote_data():
    """Standard quote data for Silestone Blanco Norte mesada."""
    return {
        "client_name": "Juan Carlos",
        "project": "Cocina",
        "date": "31.03.2026",
        "delivery_days": "30 dias",
        "material_name": "SILESTONE BLANCO NORTE",
        "material_m2": 1.30,
        "material_price_unit": 628,
        "material_currency": "USD",
        "discount_pct": 0,
        "sectors": [
            {
                "label": "COCINA",
                "pieces": ["2.00 X 0.60", "ZOCALO 2.00 X 0.05"],
            }
        ],
        "sinks": [],
        "mo_items": [
            {"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 65147},
            {"description": "Agujero anafe", "quantity": 1, "unit_price": 43097},
            {"description": "Colocacion", "quantity": 1.30, "unit_price": 60135},
            {"description": "Flete + toma medidas Rosario", "quantity": 1, "unit_price": 52000},
        ],
        "total_ars": 238420,
        "total_usd": 816,
    }


@pytest.fixture
def sample_multi_material_data(sample_quote_data):
    """Two materials: Silestone + Purastone."""
    purastone = sample_quote_data.copy()
    purastone["material_name"] = "PURASTONE BLANCO PALOMA"
    purastone["material_price_unit"] = 407
    purastone["total_usd"] = 529
    return [sample_quote_data, purastone]


@pytest_asyncio.fixture
async def created_quote(db_session):
    """A quote already in the DB."""
    quote = Quote(
        id=str(uuid.uuid4()),
        client_name="Test Client",
        project="Test Project",
        messages=[],
        status=QuoteStatus.DRAFT,
    )
    db_session.add(quote)
    await db_session.commit()
    return quote
