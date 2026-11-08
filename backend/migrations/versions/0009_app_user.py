"""app_user: akun pengguna aplikasi

Jira: DIG-84. Tabel internal J&C untuk login. resource_id opsional dan unik, ber-FK ke
resources dengan ON DELETE SET NULL agar menghapus anggota tidak menghapus akunnya.

Revision ID: 0009
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("user_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "username ~ '^[a-z0-9._-]{3,50}$'", name=op.f("ck_app_user_username_format")
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_app_user_resource_id_resources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("resource_id", name=op.f("uq_app_user_resource_id")),
        sa.UniqueConstraint("username", name=op.f("uq_app_user_username")),
    )


def downgrade() -> None:
    op.drop_table("app_user")
