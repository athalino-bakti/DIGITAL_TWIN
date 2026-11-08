from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    jwt_secret_key: SecretStr = SecretStr(DEV_JWT_SECRET)
    access_token_expire_minutes: int = Field(default=60, ge=1, le=24 * 60)

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
    return Settings()
