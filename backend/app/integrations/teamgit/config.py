from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets import secrets_dir


class TeamGitSettings(BaseSettings):
    """Alamat dan token akses TeamGit (DIG-125), dibaca dari .env, environment, atau SECRETS_DIR.

    Dipakai konektor TeamGit (DIG-122) dan uji konektivitas (DIG-126). Token cukup berhak baca
    repository; lihat docs/SECRETS.md.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        env_prefix="TEAMGIT_",
        extra="ignore",
    )

    base_url: str | None = None
    token: SecretStr | None = None


@lru_cache
def get_teamgit_settings() -> TeamGitSettings:
    return TeamGitSettings(_secrets_dir=secrets_dir())
