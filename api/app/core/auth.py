"""
Authentication module — JWT with httpOnly cookies.

Users stored in DB (table 'users'). Passwords hashed with HMAC-SHA256.
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 72  # 3 days
COOKIE_NAME = "auth_token"


# ── Rate Limiter (in-memory, no Redis) ─────────────────────────────────────

import time as _time

class InMemoryRateLimiter:
    """Simple sliding-window rate limiter. Thread-safe enough for single-process."""
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = _time.monotonic()
        hits = self._hits.get(key, [])
        # Prune old entries
        hits = [t for t in hits if now - t < self._window]
        if len(hits) >= self._max:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


_login_limiter = InMemoryRateLimiter(10, 60)   # 10 req/min per IP
_chat_limiter = InMemoryRateLimiter(20, 60)     # 20 req/min per IP

# Routes that don't require authentication
PUBLIC_ROUTES = {
    "/health",
    "/api/auth/login",
    "/api/auth/create-user",  # Protected internally (checks if users exist)
    "/api/v1/quote",  # Web API — uses its own API key
}

# Route prefixes that are public
PUBLIC_PREFIXES = (
    "/docs",
    "/openapi",
    "/redoc",
)


# ── Password Hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password with HMAC-SHA256 using SECRET_KEY as salt."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        password.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(hash_password(plain), hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_token(email: str) -> str:
    """Create a JWT token for the given email."""
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
    payload = {
        "sub": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ── Cookie Helpers ───────────────────────────────────────────────────────────

def set_auth_cookie(response: Response, token: str):
    """Set httpOnly secure cookie with JWT.

    SameSite: en dev usamos "lax" (mismo origen), en prod "none" porque
    el frontend (vercel.app) y el backend (railway.app) están en dominios
    distintos → la cookie NECESITA SameSite=None para viajar cross-origin.
    Requiere Secure=True (Chrome lo obliga), que ya tenemos en prod.

    Default de APP_ENV es "production" (ver config.py), así que aunque
    Railway no tenga la env var seteada, la cookie sale correcta.
    """
    is_prod = settings.APP_ENV != "development"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        max_age=TOKEN_EXPIRY_HOURS * 3600,
        path="/",
    )
    logger.info(
        f"Set auth cookie — APP_ENV={settings.APP_ENV!r}, "
        f"secure={is_prod}, samesite={'none' if is_prod else 'lax'}"
    )


def clear_auth_cookie(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ── User Validation ─────────────────────────────────────────────────────────

async def validate_credentials(username: str, password: str, db: AsyncSession) -> bool:
    """Validate credentials against users table in DB."""
    from app.models.user import User

    result = await db.execute(
        select(User).where(User.username == username.strip())
    )
    user = result.scalar_one_or_none()
    if not user:
        return False

    return verify_password(password, user.password_hash)


async def create_user(username: str, password: str, db: AsyncSession) -> str:
    """Create a new user in the DB. Returns user ID."""
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        username=username.strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    logger.info(f"Created user: {username}")
    return user.id


# ── Middleware ───────────────────────────────────────────────────────────────

async def auth_middleware(request: Request, call_next):
    """
    FastAPI middleware that checks JWT cookie on every request.
    Public routes are whitelisted.
    """
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"

    # Preflight CORS requests (OPTIONS) NO deben pasar por auth. El browser
    # las dispara antes del request real para chequear Access-Control-*
    # headers; si acá devolvemos 401 el browser nunca hace el request real
    # y la UI ve un error genérico de CORS en vez del 401 legítimo.
    if request.method == "OPTIONS":
        return await call_next(request)

    # Rate limiting on sensitive endpoints
    if path == "/api/auth/login" and not _login_limiter.is_allowed(client_ip):
        return JSONResponse(status_code=429, content={"detail": "Demasiados intentos. Esperá un minuto."})
    if "/chat" in path and path.startswith("/api/quotes/") and not _chat_limiter.is_allowed(client_ip):
        return JSONResponse(status_code=429, content={"detail": "Demasiadas solicitudes. Esperá un minuto."})

    # Allow public routes
    if path in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    # Check cookie
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        # Fallback: accept X-API-Key header (for web chatbot calling /api/quotes endpoints)
        api_key = request.headers.get("x-api-key")
        if api_key and settings.QUOTE_API_KEY and api_key == settings.QUOTE_API_KEY:
            request.state.user_email = "api-key"
            return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "No autenticado"})

    payload = decode_token(token)
    if not payload:
        return JSONResponse(status_code=401, content={"detail": "Sesión expirada"})

    # Attach user info to request state
    request.state.user_email = payload.get("sub")

    return await call_next(request)
