from alembic import context

import app.modules.auth.models  # noqa: F401  (mendaftarkan app_user ke metadata)
import app.modules.data.models  # noqa: F401  (mendaftarkan D-01 s.d. D-11 ke metadata)
from app.db.base import Base
from app.db.session import engine

# Import model milik modul di sini sebelum autogenerate saat model sudah tersedia.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tes migrasi mengirim koneksi sendiri lewat config.attributes agar tidak
    # menyentuh database development dari DATABASE_URL.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run_with_connection(connection)
        return

    with engine.connect() as connection:
        _run_with_connection(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
