"""staging_trello_action dan trello_list_mapping: staging impor Trello

Jira: DIG-117. Tabel internal J&C (DATA_CONTRACT bagian 7.2), bukan final sources.
staging_trello_action menyimpan action Trello apa adanya dengan id action sebagai primary key,
sehingga impor ulang tidak menggandakan baris. trello_list_mapping memetakan list per papan
(berdasarkan id list) ke status dan phase task; keduanya boleh kosong sampai dipetakan.

Revision ID: 0010
Revises: 0006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TASK_STATUSES = "'not_started', 'in_progress', 'blocked', 'on_hold', 'in_qa', 'done', 'dropped'"
TASK_PHASES = (
    "'planning', 'uiux', 'dm_dev', 'be_dev', 'fe_dev', 'testing', 'bugfix', 'documentation'"
)


def upgrade() -> None:
    op.create_table(
        "staging_trello_action",
        sa.Column("action_id", sa.String(length=24), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("action_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("board_id", sa.String(length=24), nullable=False),
        sa.Column("card_id", sa.String(length=24), nullable=True),
        sa.Column("card_name", sa.Text(), nullable=True),
        sa.Column("list_before_id", sa.String(length=24), nullable=True),
        sa.Column("list_before_name", sa.Text(), nullable=True),
        sa.Column("list_after_id", sa.String(length=24), nullable=True),
        sa.Column("list_after_name", sa.Text(), nullable=True),
        sa.Column("member_creator_id", sa.String(length=24), nullable=True),
        sa.Column("member_creator_username", sa.String(length=100), nullable=True),
        sa.Column("member_creator_full_name", sa.String(length=200), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action_id ~ '^[0-9a-f]{24}$'",
            name=op.f("ck_staging_trello_action_action_id_format"),
        ),
        sa.PrimaryKeyConstraint("action_id", name=op.f("pk_staging_trello_action")),
    )
    op.create_index(
        "ix_staging_trello_action_card_id_action_date",
        "staging_trello_action",
        ["card_id", "action_date"],
    )
    op.create_table(
        "trello_list_mapping",
        sa.Column("board_id", sa.String(length=24), nullable=False),
        sa.Column("list_id", sa.String(length=24), nullable=False),
        sa.Column("list_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("phase", sa.String(length=20), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({TASK_STATUSES})", name=op.f("ck_trello_list_mapping_status_valid")
        ),
        sa.CheckConstraint(
            f"phase IN ({TASK_PHASES})", name=op.f("ck_trello_list_mapping_phase_valid")
        ),
        sa.PrimaryKeyConstraint("board_id", "list_id", name=op.f("pk_trello_list_mapping")),
    )


def downgrade() -> None:
    op.drop_table("trello_list_mapping")
    op.drop_table("staging_trello_action")  # index ikut terhapus bersama tabel
