from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth import security
from app.modules.auth.models import AppUser
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
        user=UserRead.model_validate(user),
    )


def get_active_user(db: Session, user_id: int) -> AppUser | None:
    user = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        return None
    return user
