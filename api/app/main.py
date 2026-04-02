import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db, cleanup_empty_drafts
from app.core.static import mount_static_files
from app.core.auth import auth_middleware
from app.modules.agent.router import router as agent_router
from app.modules.catalog.router import router as catalog_router
from app.modules.quote_engine.router import router as quote_engine_router
from app.modules.auth.router import router as auth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await cleanup_empty_drafts()
    logger.info(f"CORS_ORIGINS: {settings.CORS_ORIGINS}")
    yield


app = FastAPI(
    title="D'Angelo Marble Operator API",
    description="Agente de presupuestos Valentina",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(auth_middleware)

app.include_router(auth_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(quote_engine_router, prefix="/api")
mount_static_files(app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "marble-operator-api"}
