"""Role jc_app dan schema twinner

Jira: DIG-223. Sesuai docs/DATA_CONTRACT.md bagian 4:
- Schema `twinner` milik tWinner untuk skenario dan hasil simulasinya; J&C tidak menulis
  ke schema ini, sehingga jc_app tidak diberi hak apa pun di sana.
- Role `jc_app` dipakai aplikasi J&C untuk baca-tulis data di schema `public`. Role ini
  tidak boleh mengubah struktur (CREATE/ALTER/DROP); struktur hanya berubah lewat migrasi.

jc_app dibuat NOLOGIN tanpa password karena kredensial tidak boleh ada di repository.
Admin basis data memberi login dan password di luar repository, lihat docs/DATABASE_ROLES.md.

Migrasi ini harus dijalankan role yang boleh membuat role (superuser atau CREATEROLE),
misalnya pemilik basis data di compose.yaml.

Revision ID: 0014
Revises: 0006
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DML = "SELECT, INSERT, UPDATE, DELETE"


def upgrade() -> None:
    # Role berlaku untuk seluruh cluster, jadi bisa sudah ada dari basis data lain.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jc_app') THEN
                CREATE ROLE jc_app NOLOGIN;
            END IF;
        END
        $$;
        """
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS twinner")
    op.execute("REVOKE ALL ON SCHEMA twinner FROM PUBLIC")

    # Hak sambung ke basis data saat ini, apa pun namanya (dev, test, staging).
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO jc_app', current_database());
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO jc_app")
    op.execute(f"GRANT {DML} ON ALL TABLES IN SCHEMA public TO jc_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO jc_app")
    # Riwayat migrasi hanya boleh diubah Alembic, bukan aplikasi.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM jc_app")

    # Tabel dan sequence dari migrasi berikutnya (dibuat role yang sama) ikut bisa dipakai.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {DML} ON TABLES TO jc_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO jc_app"
    )


def downgrade() -> None:
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE {DML} ON TABLES FROM jc_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM jc_app"
    )
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM jc_app")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM jc_app")
    op.execute("REVOKE ALL ON SCHEMA public FROM jc_app")
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE ALL ON DATABASE %I FROM jc_app', current_database());
        END
        $$;
        """
    )
    # Tanpa CASCADE: bila tWinner sudah punya tabel di schema ini, downgrade gagal dan
    # data tWinner tidak ikut terhapus.
    op.execute("DROP SCHEMA IF EXISTS twinner")
    # Role jc_app sengaja tidak di-drop: role berlaku untuk seluruh cluster dan bisa masih
    # punya hak di basis data lain (misalnya basis data dev dan test di server yang sama).
