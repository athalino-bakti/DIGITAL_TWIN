from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets import secrets_dir


class PipelineSettings(BaseSettings):
    """Pengaturan job impor (DIG-127 s.d. DIG-129), dari .env, environment, atau SECRETS_DIR."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Papan Trello yang diimpor job terjadwal, dipisah koma (shortLink atau id).
    trello_board_ids: str = ""
    # Percobaan per job: error sementara (jaringan, 429, 5xx) dicoba ulang dengan jeda
    # IMPORT_RETRY_DELAY_SECONDS, lalu dua kali lipat di percobaan berikutnya.
    import_max_attempts: int = Field(default=3, ge=1, le=10)
    import_retry_delay_seconds: float = Field(default=60.0, ge=0)
    # Job `running` yang lebih tua dari ini dianggap terhenti (proses mati) dan ditutup gagal.
    import_stale_minutes: int = Field(default=120, ge=1)

    log_format: Literal["text", "json"] = "text"
    log_level: str = "INFO"

    # Webhook untuk notifikasi kegagalan (Slack, Discord, Google Chat, Mattermost). Rahasia,
    # karena siapa pun yang tahu URL-nya bisa mengirim pesan ke kanal tim.
    notify_webhook_url: SecretStr | None = None
    notify_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def board_ids(self) -> list[str]:
        return [b.strip() for b in self.trello_board_ids.split(",") if b.strip()]


@lru_cache
def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings(_secrets_dir=secrets_dir())
