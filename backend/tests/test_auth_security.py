"""DIG-88: hash password dan token akses, tanpa database."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import DEV_JWT_SECRET, Settings, get_settings
from app.modules.auth import security


def test_hash_password_uses_owasp_scrypt_params_and_random_salt():
    first = security.hash_password("rahasia-123")
    second = security.hash_password("rahasia-123")

    assert first.startswith(f"scrypt${2**17}$8$1$")
    assert first != second, "salt harus acak sehingga hash password sama tetap berbeda"
    assert "rahasia-123" not in first


def test_verify_password_accepts_correct_and_rejects_wrong():
    stored = security.hash_password("rahasia-123")

    assert security.verify_password("rahasia-123", stored)
    assert not security.verify_password("rahasia-124", stored)
    assert not security.verify_password("", stored)


@pytest.mark.parametrize(
    "stored",
    ["", "plaintext", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA", "scrypt$16384$8$1$!!$!!"],
)
def test_verify_password_rejects_malformed_hash(stored):
    assert security.verify_password("apa-saja", stored) is False


def test_access_token_round_trip():
    token = security.create_access_token(7, "bagas")
    assert security.decode_access_token(token) == 7


def test_expired_token_is_rejected():
    token = security.create_access_token(7, "bagas", expires_minutes=-1)
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token)


def test_token_signed_with_other_secret_is_rejected():
    claims = {"sub": "7", "type": "access", "iat": datetime.now(UTC)}
    claims["exp"] = claims["iat"] + timedelta(minutes=5)
    forged = jwt.encode(claims, "kunci-lain-yang-juga-panjang-32-karakter!", algorithm="HS256")
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(forged)


def test_unsigned_alg_none_token_is_rejected():
    claims = {"sub": "7", "type": "access", "iat": datetime.now(UTC)}
    claims["exp"] = claims["iat"] + timedelta(minutes=5)
    unsigned = jwt.encode(claims, key=None, algorithm="none")
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(unsigned)


def test_token_without_exp_or_wrong_type_is_rejected():
    secret = get_settings().jwt_secret_key.get_secret_value()
    no_exp = jwt.encode({"sub": "7", "type": "access", "iat": datetime.now(UTC)}, secret)
    now = datetime.now(UTC)
    refresh = jwt.encode(
        {"sub": "7", "type": "refresh", "iat": now, "exp": now + timedelta(minutes=5)}, secret
    )
    for token in (no_exp, refresh, "bukan.token.jwt"):
        with pytest.raises(security.InvalidTokenError):
            security.decode_access_token(token)


def test_settings_refuse_default_secret_outside_development():
    with pytest.raises(ValueError, match="wajib diganti"):
        Settings(app_env="production", jwt_secret_key=DEV_JWT_SECRET)
    with pytest.raises(ValueError, match="minimal 32"):
        Settings(jwt_secret_key="pendek")
    Settings(app_env="production", jwt_secret_key="x" * 48)
