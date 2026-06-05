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
os.environ.setdefault("QUOTE_API_KEY", "")

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
        # Create non-ORM tables used by catalog system
        from sqlalchemy import text
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS catalogs (
                name VARCHAR(100) PRIMARY KEY,
                content JSON NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS catalog_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_name VARCHAR(100) NOT NULL,
                content JSON NOT NULL,
                source_file VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                stats JSON
            )
        """))
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
    """FastAPI test client with DB override + auth cookie."""
    from app.core.auth import create_token, COOKIE_NAME

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Override AsyncSessionLocal so catalog router (which bypasses get_db) uses test DB
    import app.core.database as _db_mod
    _original_session_local = _db_mod.AsyncSessionLocal
    _db_mod.AsyncSessionLocal = session_factory

    transport = ASGITransport(app=app)
    # Create a test JWT token so auth middleware doesn't block requests
    test_token = create_token("test@test.com")
    async with AsyncClient(transport=transport, base_url="http://test", cookies={COOKIE_NAME: test_token}) as ac:
        yield ac
    app.dependency_overrides.clear()
    _db_mod.AsyncSessionLocal = _original_session_local


@pytest_asyncio.fixture
async def client_no_auth(db_engine):
    """FastAPI test client WITHOUT auth cookie — for testing unauthenticated access."""
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


# ── Sprint 4 pdf-snapshot-tests · canon fixtures ─────────────────────────────
# Estructura replicada de los mocks canónicos del frontend
# (web/src/lib/mocks/canonicalQuote.ts) para alimentar snapshot tests de
# `_generate_pdf`. Los goldens generados NO certifican que las cifras
# matcheen el calculator real del backend · certifican que dado este fixture
# de inputs, el output del PDF es ESTABLE. Drift del calculator se valida
# en sub-PR paso-1-real futuro.

@pytest.fixture
def pres_2026_018_data():
    """PRES-2026-018 · Cueto-Heredia · Silestone Blanco Norte 20mm · canon.
    Datos replicados de CANONICAL_CALCULATION_018 del frontend mock."""
    return {
        "client_name": "Estudio Cueto-Heredia",
        "project": "cocina Belgrano",
        "date": "03.05.2026",
        "delivery_days": "3 semanas desde confirmación de medidas",
        "material_name": "SILESTONE BLANCO NORTE 20mm",
        "material_m2": 6.50,
        "material_price_unit": 249,
        "material_currency": "USD",
        "discount_pct": 5,
        "sectors": [
            {
                "label": "Cocina Belgrano",
                "pieces": [
                    "1.80 X 0.62 Mesada perimetral · brazo izq",
                    "1.50 X 0.62 Mesada perimetral · brazo derecho",
                    "1.10 X 0.62 Mesada perimetral · fondo",
                    "2.20 X 1.00 Isla central",
                    "7.05 X 0.05 Zocalo",
                ],
            }
        ],
        "sinks": [],
        "mo_items": [
            {"description": "Colocacion", "quantity": 6.50, "unit_price": 49698},
            {"description": "Pegado pileta empotrada", "quantity": 1, "unit_price": 53840},
            {"description": "Anafe (corte y cargas)", "quantity": 1, "unit_price": 35617},
            {"description": "Regrueso frontal", "quantity": 4.98, "unit_price": 13810},
            {"description": "Tomas (perforacion)", "quantity": 2, "unit_price": 6461},
            {"description": "Flete + toma medidas Belgrano CABA", "quantity": 1, "unit_price": 62920},
        ],
        "total_ars": 660890,
        "total_usd": 1538,
    }


@pytest.fixture
def pres_2026_017_data():
    """PRES-2026-017 · Pereyra · sin descuento arquitecta · canon.
    Datos replicados para verificar datasource isolation en snapshots."""
    return {
        "client_name": "Familia Pereyra",
        "project": "cocina Rosario",
        "date": "03.05.2026",
        "delivery_days": "4 semanas desde confirmación de medidas",
        "material_name": "SILESTONE BLANCO NORTE 20mm",
        "material_m2": 5.20,
        "material_price_unit": 249,
        "material_currency": "USD",
        "discount_pct": 0,
        "sectors": [
            {
                "label": "Cocina Rosario",
                "pieces": [
                    "2.40 X 0.62 Mesada principal",
                    "1.40 X 0.62 Mesada lateral",
                    "5.20 X 0.05 Zocalo",
                ],
            }
        ],
        "sinks": [],
        "mo_items": [
            {"description": "Colocacion", "quantity": 5.20, "unit_price": 49698},
            {"description": "Pegado pileta empotrada", "quantity": 1, "unit_price": 53840},
            {"description": "Flete + toma medidas Rosario", "quantity": 1, "unit_price": 18000},
        ],
        "total_ars": 330029,
        "total_usd": 1295,
    }


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
