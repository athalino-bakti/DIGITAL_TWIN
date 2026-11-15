from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import security, service
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.rate_limit import get_login_limiter
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["Auth"])

Db = Annotated[Session, Depends(get_db)]
UNAUTHORIZED = {status.HTTP_401_UNAUTHORIZED: {"description": "Belum login atau token tidak sah"}}


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Username atau password salah"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Terlalu banyak percobaan gagal"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Server sedang sibuk"},
    },
    summary="Login dan dapatkan token akses",
)
def login(db: Db, payload: LoginRequest, request: Request) -> TokenResponse:
    """Kirim token di header `Authorization: Bearer <access_token>` untuk request berikutnya."""
    limiter = get_login_limiter()
    ip = request.client.host if request.client else "unknown"
    wait = limiter.retry_after(payload.username, ip)
    if wait is not None:
        minutes = max(1, -(-wait // 60))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Terlalu banyak percobaan login. Coba lagi dalam {minutes} menit.",
            headers={"Retry-After": str(wait)},
        )
    try:
        response = service.authenticate(db, payload)
    except service.InvalidCredentialsError as exc:
        limiter.record_failure(payload.username, ip)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except security.HashBusyError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server sedang sibuk, coba login lagi sebentar lagi",
            headers={"Retry-After": "5"},
        ) from exc
    limiter.record_success(payload.username)
    return response


@router.get("/me", response_model=UserRead, responses=UNAUTHORIZED, summary="User yang login")
def me(db: Db, user: CurrentUser) -> UserRead:
    """Data user beserta peran dan izinnya, dipakai frontend untuk menampilkan menu."""
    return service.user_read(db, user)
