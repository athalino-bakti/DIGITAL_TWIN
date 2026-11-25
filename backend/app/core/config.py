from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets import secrets_dir

# Hanya untuk development lokal. Di staging/production wajib diganti lewat JWT_SECRET_KEY.
DEV_JWT_SECRET = "dev-only-ganti-jwt-secret-key-di-env-minimal-32-karakter"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Digital Twin PuTI API"
    app_env: Literal["development", "staging", "production"] = "development"
    database_url: str = "postgresql+psycopg://puti:puti_local@localhost:5432/digital_twin"
    # Pool koneksi PostgreSQL (DIG-210). Basis data dipakai bersama tWinner, jadi API J&C
    # dibatasi paling banyak db_pool_size + db_max_overflow koneksi (bawaan 10).
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_timeout: int = Field(default=10, ge=1, le=120)  # detik menunggu koneksi kosong
    db_pool_recycle: int = Field(default=1800, ge=60)  # detik sebelum koneksi dibuka ulang
    db_application_name: str = Field(default="jc-api", max_length=63)
    # 0 = tanpa batas. Diisi untuk service api saja (compose.prod.yaml), bukan untuk migrasi.
    db_statement_timeout_ms: int = Field(default=0, ge=0)
    db_idle_in_transaction_timeout_ms: int = Field(default=0, ge=0)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    jwt_secret_key: SecretStr = SecretStr(DEV_JWT_SECRET)
    access_token_expire_minutes: int = Field(default=60, ge=1, le=24 * 60)
    # Batas login gagal (app/modules/auth/rate_limit.py).
    login_max_failures_per_user: int = Field(default=5, ge=1)
    login_max_failures_per_ip: int = Field(default=20, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)
    # Deteksi overrun otomatis (DIG-154) membuat kejadian D-10 untuk semua task yang lewat
    # rencana; di dataset dosbim 557 sekaligus. Mati sampai tim sepakat (review PR #39);
    # dry run tetap bisa dipakai.
    overrun_detection_enabled: bool = False

    @model_validator(mode="after")
    def check_jwt_secret(self) -> "Settings":
        secret = self.jwt_secret_key.get_secret_value()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY minimal 32 karakter")
        if self.app_env != "development" and secret == DEV_JWT_SECRET:
            raise ValueError(f"JWT_SECRET_KEY wajib diganti untuk APP_ENV={self.app_env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings(_secrets_dir=secrets_dir())
