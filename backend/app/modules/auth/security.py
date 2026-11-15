"""Hash password (scrypt) dan token akses (JWT HS256).

scrypt memakai hashlib bawaan Python dengan salah satu parameter minimum rekomendasi OWASP
(N=2^15, r=8, p=3). Kekuatannya setara N=2^17, r=8, p=1, tetapi memorinya 32 MiB per hash,
bukan 128 MiB. Parameter dan salt ikut disimpan di dalam hash, jadi hash lama dengan parameter
lain tetap bisa diverifikasi dan diperbarui saat pengguna berhasil login (`needs_rehash`).

Jumlah hash yang dihitung bersamaan dibatasi `HASH_CONCURRENCY`, sehingga pemakaian memori
untuk hash paling banyak HASH_CONCURRENCY x 32 MiB walaupun banyak login datang sekaligus.
Request yang tidak kebagian slot dalam `HASH_WAIT_SECONDS` mendapat `HashBusyError`.
"""

import base64
import hashlib
import hmac
import os
import threading
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3
SCRYPT_DKLEN = 32
SALT_BYTES = 16
JWT_ALGORITHM = "HS256"
TOKEN_TYPE = "access"
HASH_CONCURRENCY = 4
HASH_WAIT_SECONDS = 10.0

_hash_slots = threading.BoundedSemaphore(HASH_CONCURRENCY)


class HashBusyError(Exception):
    """Semua slot hash sedang dipakai lebih lama dari HASH_WAIT_SECONDS."""


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    if not _hash_slots.acquire(timeout=HASH_WAIT_SECONDS):
        raise HashBusyError
    try:
        # maxmem harus di atas 128*n*r byte; default hashlib (32 MiB) pas-pasan untuk N=2^15
        # dan terlalu kecil untuk hash lama N=2^17.
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=dklen,
            maxmem=256 * 1024 * 1024,
        )
    finally:
        _hash_slots.release()


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored_hash.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = _scrypt(password, salt, int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored_hash: str) -> bool:
    """True bila hash disimpan dengan parameter scrypt yang berbeda dari sekarang."""
    parts = stored_hash.split("$")
    return len(parts) != 6 or parts[1:4] != [str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)]


def burn_password_check(password: str) -> None:
    """Hitung hash palsu saat username tidak ada.

    Waktu respons login jadi setara antara username salah dan password salah, sehingga
    penyerang tidak bisa menebak username yang terdaftar dari lamanya respons.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("akun-tidak-ada")
    verify_password(password, _dummy_hash)


# Dibuat saat modul dimuat, supaya login pertama dengan username tidak dikenal tidak lebih
# lama dari yang lain. Tes boleh mengosongkannya; burn_password_check akan membuat ulang.
_dummy_hash: str | None = hash_password("akun-tidak-ada")


def create_access_token(user_id: int, username: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = settings.access_token_expire_minutes if expires_minutes is None else expires_minutes
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "username": username,
        "type": TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, settings.jwt_secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)


class InvalidTokenError(Exception):
    """Token tidak sah, rusak, atau kedaluwarsa."""


def decode_access_token(token: str) -> int:
    """Kembalikan user_id dari token akses yang sah."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        if claims.get("type") != TOKEN_TYPE:
            raise InvalidTokenError("Jenis token salah")
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc
