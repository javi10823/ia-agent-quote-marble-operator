import logging
import asyncio
import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import init_db, cleanup_empty_drafts, get_db
# mount_static_files removed — files served via authenticated endpoint
from app.core.auth import auth_middleware
from app.core.request_context import request_context_middleware
from app.modules.agent.router import router as agent_router, files_router
from app.modules.observability.router import router as observability_router
from app.modules.catalog.router import router as catalog_router
from app.modules.quote_engine.router import router as quote_engine_router
from app.modules.auth.router import router as auth_router
from app.modules.usage.router import router as usage_router

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
                # Only send the stable cached block — no conditional content or examples
                from app.modules.agent.agent import _get_stable_text
                system = [{"type": "text", "text": _get_stable_text(), "cache_control": {"type": "ephemeral"}}]
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
        interval = int(os.environ.get("CACHE_KEEPALIVE_SECONDS", "240"))
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Seed catalogs to DB on first boot
    from app.core.catalog_dir import seed_catalogs_to_db
    from app.core.database import engine
    await seed_catalogs_to_db(engine)
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

# Orden CRÍTICO: Starlette aplica los middlewares en orden INVERSO al
# `add_middleware`. El último agregado es el OUTER (corre primero). Así
# que CORS tiene que ser el ÚLTIMO en agregarse para que envuelva a
# auth — si no, un 401 de auth sale SIN los headers CORS, el browser
# lo bloquea, y la UI ve un error genérico en vez del 401 real.
app.middleware("http")(auth_middleware)

# Request context middleware (corre DESPUÉS de auth porque está
# registrado ANTES — orden inverso). Asigna `request.state.request_id`
# (UUID4) y `request.state.session_id` (None por default; se setea
# explícitamente en handlers que ya tengan sesión modelada). El audit
# helper los lee de ahí.
app.middleware("http")(request_context_middleware)

# ProxyHeadersMiddleware — Railway termina TLS antes de llegar a uvicorn.
# Sin esto, cualquier redirect que FastAPI genere (ej. trailing-slash:
# /api/catalog → /api/catalog/) sale con `Location: http://...` porque
# uvicorn cree que la request llegó por HTTP. El browser bloquea ese
# redirect por Mixed Content desde la página https de Vercel.
# Con este middleware, uvicorn lee X-Forwarded-Proto y arma los
# redirects con scheme correcto (https).
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Regex se suma (OR) a allow_origins — cualquiera de las dos matchea.
    # Vacío por configuración → FastAPI lo ignora. Ver config.py para el
    # default (previews de Vercel del proyecto/team actual).
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # PR #389 — sliding session refresh: el middleware de auth emite un
    # nuevo JWT en cookie + `X-Refreshed-Token` cuando al token activo le
    # quedan <24h de vida. El header queda expuesto al JS del frontend
    # para que el fallback de localStorage (iOS Safari con ITP bloqueando
    # cookies cross-origin) también se actualice y la sesión deslice.
    expose_headers=["X-Refreshed-Token"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(usage_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(quote_engine_router, prefix="/api")
app.include_router(observability_router, prefix="/api")
# PR #398 — endpoint público de reglas de negocio v0 para el bot web.
from app.modules.business_rules.router import router as business_rules_router
app.include_router(business_rules_router, prefix="/api")
# Authenticated file serving (replaces unauthenticated StaticFiles mount)
app.include_router(files_router)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "marble-operator-api", "db": "connected"}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "service": "marble-operator-api", "db": "unreachable"},
        )
