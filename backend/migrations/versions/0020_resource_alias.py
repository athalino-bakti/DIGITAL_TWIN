"""resource_alias: alias identitas anggota antar tool

Jira: DIG-110 (story DIG-24). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2), tidak dibaca
tWinner dan tidak menambah kolom ke D-01 sampai D-11. Satu alias di satu sumber (project_plan,
trello, teamgit) menunjuk satu resource_id; satu anggota boleh punya banyak alias. Alias ikut
terhapus bersama anggotanya. Hak jc_app berlaku lewat default privileges (0014), jadi tanpa GRANT.

Revision ID: 0020
Revises: 0018
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_alias",
        sa.Column("alias_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("alias_key", sa.String(length=200), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("mapped_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source IN ('project_plan', 'trello', 'teamgit')",
            name=op.f("ck_resource_alias_source_valid"),
        ),
        sa.CheckConstraint(
            "source <> 'trello' OR alias_key ~ '^[0-9a-f]{24}$'",
            name=op.f("ck_resource_alias_trello_id_format"),
        ),
        sa.CheckConstraint("alias_key <> ''", name=op.f("ck_resource_alias_alias_key_not_empty")),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_resource_alias_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapped_by_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_resource_alias_mapped_by_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("alias_id", name=op.f("pk_resource_alias")),
        sa.UniqueConstraint("source", "alias_key", name=op.f("uq_resource_alias_source_alias_key")),
    )
    op.create_index(
        op.f("ix_resource_alias_resource_id"), "resource_alias", ["resource_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_resource_alias_resource_id"), table_name="resource_alias")
    op.drop_table("resource_alias")
