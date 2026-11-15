from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth import security
from app.modules.auth.models import AppUser
from app.modules.auth.rbac_models import RolePermission, UserAppRole
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserRead


class InvalidCredentialsError(Exception):
    """Username atau password salah, atau akun nonaktif."""


def authenticate(db: Session, payload: LoginRequest) -> TokenResponse:
    user = db.scalar(select(AppUser).where(AppUser.username == payload.username))
    if user is None:
        security.burn_password_check(payload.password)
        raise InvalidCredentialsError
    if not security.verify_password(payload.password, user.password_hash):
        raise InvalidCredentialsError
    # Akun nonaktif mendapat pesan yang sama agar status akun tidak bocor ke orang lain.
    if not user.is_active:
        raise InvalidCredentialsError

    user.last_login_at = datetime.now(UTC)
    db.commit()

    minutes = get_settings().access_token_expire_minutes
    return TokenResponse(
        access_token=security.create_access_token(user.user_id, user.username, minutes),
        expires_in=minutes * 60,
        user=user_read(db, user),
    )


def get_user_roles(db: Session, user_id: int) -> list[str]:
    return list(
        db.scalars(
            select(UserAppRole.role_code)
            .where(UserAppRole.user_id == user_id)
            .order_by(UserAppRole.role_code)
        )
    )


def get_user_permissions(db: Session, user_id: int) -> set[str]:
    """Gabungan izin dari semua peran aplikasi pengguna."""
    return set(
        db.scalars(
            select(RolePermission.permission_code)
            .join(UserAppRole, UserAppRole.role_code == RolePermission.role_code)
            .where(UserAppRole.user_id == user_id)
            .distinct()
        )
    )


def user_read(db: Session, user: AppUser) -> UserRead:
    data = UserRead.model_validate(user)
    data.roles = get_user_roles(db, user.user_id)
    data.permissions = sorted(get_user_permissions(db, user.user_id))
    return data


def get_active_user(db: Session, user_id: int) -> AppUser | None:
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        return None
    return user
