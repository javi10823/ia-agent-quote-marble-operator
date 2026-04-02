"""Auth endpoints — login, logout, current user."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.core.auth import (
    validate_credentials,
    create_token,
    set_auth_cookie,
    clear_auth_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    email: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response):
    """Validate credentials and set auth cookie."""
    if not validate_credentials(body.email, body.password):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    token = create_token(body.email)
    set_auth_cookie(response, token)

    return LoginResponse(ok=True, email=body.email)


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookie."""
    clear_auth_cookie(response)
    return {"ok": True}
