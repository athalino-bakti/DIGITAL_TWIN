from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrelloSettings(BaseSettings):
    """Feature flag dan kredensial konektor Trello API, dibaca dari .env atau environment.

    Mati secara default; impor utama tetap memakai berkas ekspor JSON (DIG-118).
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        env_prefix="TRELLO_",
        extra="ignore",
    )

    api_enabled: bool = False
    api_key: SecretStr | None = None
    api_token: SecretStr | None = None
    api_base_url: str = "https://api.trello.com/1"


@lru_cache
def get_trello_settings() -> TrelloSettings:
    return TrelloSettings()
