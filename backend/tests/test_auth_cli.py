"""DIG-84: CLI pembuat akun harus bisa jalan sendiri, di luar aplikasi FastAPI."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_create_user_cli_resolves_resource_foreign_key():
    # Proses terpisah supaya model lain yang dimuat pytest tidak ikut menolong.
    code = (
        "import app.modules.auth.create_user\n"
        "from app.modules.auth.models import AppUser\n"
        "print([fk.column.table.name for fk in AppUser.__table__.foreign_keys])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "resources" in result.stdout
