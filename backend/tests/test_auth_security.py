"""DIG-88: hash password dan token akses, tanpa database."""

import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest

from app.core.config import DEV_JWT_SECRET, Settings, get_settings
from app.modules.auth import security


def test_hash_password_uses_owasp_scrypt_params_and_random_salt():
    first = security.hash_password("rahasia-123")
    second = security.hash_password("rahasia-123")

    assert first.startswith(f"scrypt${2**15}$8$3$")
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


# --- beban memori dan jumlah hash bersamaan ------------------------------------------


def test_scrypt_memory_per_hash_is_32_mib():
    # OWASP: N=2^15, r=8, p=3 setara N=2^17, r=8, p=1 dengan memori 4x lebih kecil.
    assert 128 * security.SCRYPT_N * security.SCRYPT_R == 32 * 1024 * 1024
    assert security.SCRYPT_P == 3


def test_old_parameter_hash_still_verifies_and_needs_rehash():
    salt = b"0123456789abcdef"
    digest = security._scrypt("rahasia-123", salt, 2**17, 8, 1, 32)
    old = f"scrypt${2**17}$8$1${security._b64encode(salt)}${security._b64encode(digest)}"

    assert security.verify_password("rahasia-123", old)
    assert security.needs_rehash(old)
    assert not security.needs_rehash(security.hash_password("rahasia-123"))
    assert security.needs_rehash("bukan-hash")


def test_concurrent_hashes_are_capped(monkeypatch):
    active = peak = 0
    lock = threading.Lock()
    real_scrypt = security.hashlib.scrypt

    def slow_scrypt(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return real_scrypt(*args, **{**kwargs, "n": 2**10})

    monkeypatch.setattr(security.hashlib, "scrypt", slow_scrypt)
    threads = [
        threading.Thread(target=security.hash_password, args=("rahasia",)) for _ in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == security.HASH_CONCURRENCY


def test_hash_waits_then_reports_busy(monkeypatch):
    monkeypatch.setattr(security, "_hash_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(security, "HASH_WAIT_SECONDS", 0.05)
    security._hash_slots.acquire()
    try:
        with pytest.raises(security.HashBusyError):
            security.hash_password("rahasia")
    finally:
        security._hash_slots.release()
    assert security.verify_password("rahasia", security.hash_password("rahasia"))


def test_dummy_hash_is_ready_when_module_loads():
    """Login pertama dengan username tak dikenal tidak boleh lebih lama karena membuat hash."""
    code = "from app.modules.auth import security; print(security._dummy_hash is not None)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
