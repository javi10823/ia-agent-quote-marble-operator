from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db
from app.core.static import mount_static_files
from app.modules.agent.router import router as agent_router
from app.modules.catalog.router import router as catalog_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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

app.include_router(agent_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
mount_static_files(app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "marble-operator-api"}
