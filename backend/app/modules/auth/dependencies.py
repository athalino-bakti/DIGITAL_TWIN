"""Dependency FastAPI untuk endpoint yang butuh login dan izin.

Wajib login saja:

    from app.modules.auth.dependencies import CurrentUser

    @router.get("/projects")
    def list_projects(user: CurrentUser, db: Db): ...

Wajib izin tertentu (RBAC, DIG-91):

    from app.modules.auth.dependencies import require_permission
    from app.modules.auth.permissions import Perm

    @router.post("/projects", dependencies=[Depends(require_permission(Perm.MASTER_DATA_WRITE))])
    def create_project(...): ...

Tanpa token atau token tidak sah: 401. Login tapi tidak punya izin: 403.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import security, service
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import Perm

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


FORBIDDEN = "Anda tidak punya izin untuk tindakan ini"


def require_permission(*required: Perm):
    """Dependency yang meloloskan user hanya bila ia punya SEMUA izin yang diminta.

    Izin dibaca ulang dari basis data di setiap request, sehingga perubahan peran langsung
    berlaku tanpa perlu login ulang.
    """
    if not required:
        raise ValueError("require_permission butuh minimal satu izin")
    needed = frozenset(Perm(code) for code in required)

    def dependency(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> AppUser:
        if not needed <= service.get_user_permissions(db, user.user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)
        return user

    # Dipakai tes untuk memastikan setiap endpoint data memasang izin.
    dependency.required_permissions = needed  # type: ignore[attr-defined]
    return dependency
