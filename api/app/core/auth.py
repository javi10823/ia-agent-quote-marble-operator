"""
Authentication module — JWT with httpOnly cookies.

Single-user auth for operator access. Credentials stored in env vars.
Extensible to multi-user with DB table later.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response, HTTPException
from jose import jwt, JWTError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 72  # 3 days
COOKIE_NAME = "auth_token"

# Routes that don't require authentication
PUBLIC_ROUTES = {
    "/health",
    "/api/auth/login",
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
    """Set httpOnly secure cookie with JWT."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.APP_ENV != "development",  # HTTPS only in production
        samesite="lax",
        max_age=TOKEN_EXPIRY_HOURS * 3600,
        path="/",
    )


def clear_auth_cookie(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ── User Validation ─────────────────────────────────────────────────────────

def validate_credentials(email: str, password: str) -> bool:
    """
    Validate operator credentials.
    For MVP: single user from env vars (OPERATOR_EMAIL, OPERATOR_PASSWORD_HASH).
    Future: query users table in DB.
    """
    expected_email = getattr(settings, "OPERATOR_EMAIL", None)
    expected_hash = getattr(settings, "OPERATOR_PASSWORD_HASH", None)

    if not expected_email or not expected_hash:
        # Fallback: accept any login if env vars not set (dev mode)
        logger.warning("OPERATOR_EMAIL/OPERATOR_PASSWORD_HASH not set — auth disabled")
        return True

    if email.lower().strip() != expected_email.lower().strip():
        return False

    return verify_password(password, expected_hash)


# ── Middleware ───────────────────────────────────────────────────────────────

async def auth_middleware(request: Request, call_next):
    """
    FastAPI middleware that checks JWT cookie on every request.
    Public routes are whitelisted.
    """
    path = request.url.path

    # Allow public routes
    if path in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    # Allow static files (they go through Next.js rewrite anyway)
    if path.startswith("/files/"):
        # TODO: protect static files in Phase 2
        return await call_next(request)

    # Check cookie
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión expirada")

    # Attach user info to request state
    request.state.user_email = payload.get("sub")

    return await call_next(request)
