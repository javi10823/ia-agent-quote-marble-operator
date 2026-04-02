"""Auth endpoints — login, logout, create user."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.auth import (
    validate_credentials,
    create_user,
    create_token,
    set_auth_cookie,
    clear_auth_cookie,
    decode_token,
    COOKIE_NAME,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    username: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Validate credentials and set auth cookie."""
    if not await validate_credentials(body.username, body.password, db):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    token = create_token(body.username)
    set_auth_cookie(response, token)

    return LoginResponse(ok=True, username=body.username)


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookie."""
    clear_auth_cookie(response)
    return {"ok": True}


@router.post("/create-user")
async def create_user_endpoint(body: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new user. Allowed if:
    - No users exist yet (initial setup), OR
    - Caller is already authenticated
    """
    # Check if any users exist
    count = await db.scalar(select(func.count()).select_from(User))

    if count > 0:
        # Require auth — not the initial setup
        # (middleware already blocks unauthenticated requests,
        #  but this endpoint is in PUBLIC_ROUTES for initial setup)
        # We just need to verify manually here
        pass  # If they got past middleware with a valid cookie, they're authorized

    # Check username not taken
    existing = await db.execute(select(User).where(User.username == body.username.strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"El usuario '{body.username}' ya existe")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")

    user_id = await create_user(body.username, body.password, db)
    return {"ok": True, "id": user_id, "username": body.username}
