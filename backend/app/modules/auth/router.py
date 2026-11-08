from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import service
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["Auth"])

Db = Annotated[Session, Depends(get_db)]
UNAUTHORIZED = {status.HTTP_401_UNAUTHORIZED: {"description": "Belum login atau token tidak sah"}}


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Username atau password salah"}},
    summary="Login dan dapatkan token akses",
)
def login(db: Db, payload: LoginRequest) -> TokenResponse:
    """Kirim token di header `Authorization: Bearer <access_token>` untuk request berikutnya."""
    try:
        return service.authenticate(db, payload)
    except service.InvalidCredentialsError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get("/me", response_model=UserRead, responses=UNAUTHORIZED, summary="User yang login")
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
