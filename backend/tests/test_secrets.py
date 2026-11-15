"""DIG-125: kredensial dibaca dari environment, .env, atau SECRETS_DIR, dan tidak ada di repo."""

import re
import subprocess
from pathlib import Path

import pytest

from app.core.config import DEV_JWT_SECRET, Settings
from app.core.secrets import secrets_dir
from app.integrations.teamgit.config import TeamGitSettings
from app.integrations.trello.config import TrelloSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"
SECRET_VARS = ("TRELLO_API_KEY", "TRELLO_API_TOKEN", "TEAMGIT_TOKEN")


@pytest.fixture
def secret_files(tmp_path, monkeypatch):
    """Folder rahasia ala Docker secrets, dipasang lewat SECRETS_DIR."""
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    for name in ("TRELLO_API_KEY", "TRELLO_API_TOKEN", "TEAMGIT_TOKEN", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    def write(name: str, value: str) -> None:
        (tmp_path / name).write_text(value + "\n", encoding="utf-8")

    return write


# --- SECRETS_DIR ----------------------------------------------------------------------


def test_secrets_dir_is_optional(monkeypatch, tmp_path):
    monkeypatch.delenv("SECRETS_DIR", raising=False)
    assert secrets_dir() is None
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path / "tidak-ada"))
    assert secrets_dir() is None
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    assert secrets_dir() == tmp_path


def test_credentials_are_read_from_secret_files(secret_files):
    secret_files("trello_api_key", "k" * 32)
    secret_files("trello_api_token", "token-dari-berkas")
    secret_files("teamgit_token", "teamgit-dari-berkas")

    trello = TrelloSettings(_env_file=None, _secrets_dir=secrets_dir())
    teamgit = TeamGitSettings(_env_file=None, _secrets_dir=secrets_dir())

    assert trello.api_key.get_secret_value() == "k" * 32
    assert trello.api_token.get_secret_value() == "token-dari-berkas"  # baris baru dibuang
    assert teamgit.token.get_secret_value() == "teamgit-dari-berkas"


def test_environment_wins_over_secret_file(secret_files, monkeypatch):
    secret_files("trello_api_token", "dari-berkas")
    monkeypatch.setenv("TRELLO_API_TOKEN", "dari-environment")

    settings = TrelloSettings(_env_file=None, _secrets_dir=secrets_dir())
    assert settings.api_token.get_secret_value() == "dari-environment"


def test_staging_accepts_jwt_secret_from_file(secret_files, monkeypatch):
    secret_files("jwt_secret_key", "s" * 48)
    monkeypatch.setenv("APP_ENV", "staging")

    settings = Settings(_env_file=None, _secrets_dir=secrets_dir())
    assert settings.jwt_secret_key.get_secret_value() == "s" * 48


def test_staging_still_rejects_default_jwt_secret(monkeypatch):
    monkeypatch.delenv("SECRETS_DIR", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY wajib diganti"):
        Settings(_env_file=None)


def test_secret_values_never_show_in_repr(secret_files):
    secret_files("trello_api_token", "token-rahasia-123")
    secret_files("teamgit_token", "teamgit-rahasia-456")
    text = repr(TrelloSettings(_env_file=None, _secrets_dir=secrets_dir())) + repr(
        TeamGitSettings(_env_file=None, _secrets_dir=secrets_dir())
    )
    assert "token-rahasia-123" not in text and "teamgit-rahasia-456" not in text


# --- repo bersih dari rahasia ---------------------------------------------------------

# Pola dirakit dari potongan supaya berkas tes ini sendiri tidak cocok.
SECRET_PATTERNS = {
    "token Trello": re.compile("ATTA" + r"[0-9a-fA-F]{64}"),
    "token GitLab": re.compile("glpat" + r"-[0-9A-Za-z_\-]{20,}"),
    "token GitHub": re.compile("gh[pousr]" + r"_[0-9A-Za-z]{36}"),
    "private key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "kunci Trello di variabel": re.compile(r"(?i)trello_api_key\s*[=:]\s*['\"]?[0-9a-f]{32}\b"),
}


def tracked_files() -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("bukan repository git")
    return [REPO_ROOT / name for name in output.decode().split("\0") if name]


def test_no_env_file_is_tracked():
    tracked = [p.relative_to(REPO_ROOT).as_posix() for p in tracked_files()]
    leaked = [
        p for p in tracked if re.search(r"(^|/)\.env(\.[^/]+)?$", p) and not p.endswith(".example")
    ]
    assert leaked == [], "berkas .env tidak boleh di-commit"


def test_tracked_files_contain_no_credentials():
    found = []
    for path in tracked_files():
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # berkas biner
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                found.append(f"{path.relative_to(REPO_ROOT)}: {label}")
    assert found == []


def test_env_example_leaves_secrets_empty():
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip()

    assert {name: values.get(name) for name in SECRET_VARS} == dict.fromkeys(SECRET_VARS, "")
    # Satu-satunya rahasia yang diisi adalah nilai development, yang ditolak di staging.
    assert values["JWT_SECRET_KEY"] == DEV_JWT_SECRET
