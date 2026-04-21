"""Auth endpoints — login, logout, create user."""

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.core.database import get_db
from app.core.auth import (
    validate_credentials,
    create_user,
    create_token,
    set_auth_cookie,
    clear_auth_cookie,
    decode_token,
    extract_token_from_request,
    COOKIE_NAME,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, v):
        return v.strip() if isinstance(v, str) else v


class LoginResponse(BaseModel):
    ok: bool
    username: str
    # JWT en el body — fallback para clientes donde la cookie cross-origin
    # no viaja (ej: iOS Safari con ITP bloqueando third-party cookies). El
    # cliente lo guarda en localStorage y lo manda como
    # `Authorization: Bearer <token>` en requests subsecuentes. En desktop
    # la cookie sigue funcionando y el header queda como redundancia
    # inofensiva (cookie tiene precedencia en el backend).
    token: str


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

    return LoginResponse(ok=True, username=body.username, token=token)


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookie."""
    clear_auth_cookie(response)
    return {"ok": True}


@router.post("/create-user")
async def create_user_endpoint(body: CreateUserRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a new user. Allowed if:
    - No users exist yet (initial setup), OR
    - Caller is already authenticated (valid JWT cookie)
    """
    # Check if any users exist
    count = await db.scalar(select(func.count()).select_from(User))

    if count > 0:
        # Not initial setup — require valid JWT (cookie o Authorization
        # header). Usamos el mismo helper que el middleware para mantener
        # una sola fuente de verdad sobre dónde puede venir el token.
        token = extract_token_from_request(request)
        if not token:
            raise HTTPException(status_code=401, detail="No autenticado")
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Sesión expirada")

    # Check username not taken
    existing = await db.execute(select(User).where(User.username == body.username.strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"El usuario '{body.username}' ya existe")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")

    user_id = await create_user(body.username, body.password, db)
    return {"ok": True, "id": user_id, "username": body.username}


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    """List all users (username + created_at, no passwords)."""
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "created_at": u.created_at.isoformat() if u.created_at else None} for u in users]


@router.delete("/users/{user_id}")
async def delete_user_endpoint(user_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a user by ID. Cannot delete the last user."""
    count = await db.scalar(select(func.count()).select_from(User))
    if count <= 1:
        raise HTTPException(status_code=400, detail="No se puede eliminar el ultimo usuario")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"ok": True}
