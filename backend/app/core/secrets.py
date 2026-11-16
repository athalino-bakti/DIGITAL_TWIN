"""Lokasi berkas rahasia untuk pengaturan aplikasi (DIG-125).

Selain lewat environment atau `.env`, setiap pengaturan bisa dibaca dari satu berkas per
rahasia di folder `SECRETS_DIR`, misalnya Docker/Compose secrets di `/run/secrets`. Nama
berkas = nama variabel dalam huruf kecil (`jwt_secret_key`, `trello_api_token`,
`teamgit_token`). Urutan prioritas pydantic-settings: argumen, environment, `.env`, lalu
berkas rahasia.
"""

import os
from pathlib import Path


def secrets_dir() -> Path | None:
    """Folder rahasia dari `SECRETS_DIR`, atau None bila tidak diisi atau foldernya tidak ada."""
    value = os.environ.get("SECRETS_DIR", "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() else None
