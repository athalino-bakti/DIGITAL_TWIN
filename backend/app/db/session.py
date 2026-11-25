from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def engine_options(settings: Settings) -> dict[str, Any]:
    """Pengaturan pool dan batas waktu koneksi PostgreSQL (DIG-210, docs/DATABASE.md)."""
    connect_args: dict[str, Any] = {
        "connect_timeout": 3,
        # Terlihat di pg_stat_activity, sehingga koneksi J&C dan tWinner mudah dibedakan.
        "application_name": settings.db_application_name,
    }
    limits = [
        ("statement_timeout", settings.db_statement_timeout_ms),
        ("idle_in_transaction_session_timeout", settings.db_idle_in_transaction_timeout_ms),
    ]
    options = " ".join(f"-c {name}={ms}" for name, ms in limits if ms > 0)
    if options:
        connect_args["options"] = options
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "connect_args": connect_args,
    }


engine = create_engine(get_settings().database_url, **engine_options(get_settings()))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
