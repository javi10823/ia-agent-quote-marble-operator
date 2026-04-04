import logging
import asyncio
import time
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


# ── PROMPT CACHE KEEP-ALIVE ─────────────────────────────────────────────────
# Anthropic prompt cache has a 5-min TTL. A minimal ping every 4 min keeps
# the ~19,500 token stable block cached, paying 10% instead of 125% (write).
# Only pings if there was real activity in the last 10 minutes — avoids
# wasting tokens when nobody is using the system.

_last_chat_activity: float = 0.0  # epoch timestamp of last real chat request
ACTIVITY_WINDOW = 600  # 10 minutes — only keep cache alive if active within this window


def touch_chat_activity():
    """Mark that a real chat request happened. Called from agent router."""
    global _last_chat_activity
    _last_chat_activity = time.time()


async def _cache_keepalive_loop():
    """Ping Anthropic API every 4 min — only if there was recent chat activity."""
    import anthropic
    from app.modules.agent.agent import build_system_prompt

    if not settings.ANTHROPIC_API_KEY:
        return

    client = anthropic.AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        default_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )

    await asyncio.sleep(60)  # Wait 1 min after startup before first ping

    while True:
        try:
            if time.time() - _last_chat_activity < ACTIVITY_WINDOW:
                system = build_system_prompt()  # Stable block only
                await client.messages.create(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=1,
                    system=system,
                    messages=[{"role": "user", "content": "ping"}],
                )
                logger.info("Cache keep-alive ping sent")
            else:
                logger.debug("Cache keep-alive skipped — no recent activity")
        except Exception as e:
            logger.warning(f"Cache keep-alive failed: {e}")
        await asyncio.sleep(240)  # 4 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await cleanup_empty_drafts()
    logger.info(f"CORS_ORIGINS: {settings.CORS_ORIGINS}")
    # Start cache keep-alive background task
    keepalive_task = asyncio.create_task(_cache_keepalive_loop())
    yield
    keepalive_task.cancel()


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
