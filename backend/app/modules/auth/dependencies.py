"""Dependency FastAPI untuk endpoint yang butuh login.

Contoh pemakaian di router modul lain:

    from app.modules.auth.dependencies import CurrentUser

    @router.get("/projects")
    def list_projects(user: CurrentUser, db: Db): ...

require_permission (DIG-91) nanti dibangun di atas get_current_user.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import security, service
from app.modules.auth.models import AppUser

bearer = HTTPBearer(auto_error=False, description="Token dari POST /api/v1/auth/login")

UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="Sesi tidak valid atau sudah berakhir, silakan login ulang",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> AppUser:
    if credentials is None:
        raise UNAUTHORIZED
    try:
        user_id = security.decode_access_token(credentials.credentials)
    except security.InvalidTokenError as exc:
        raise UNAUTHORIZED from exc
    user = service.get_active_user(db, user_id)
    if user is None:
        raise UNAUTHORIZED
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]
