"""event_log: event log untuk process mining

Jira: DIG-164 (story DIG-37). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2), diisi
ulang seluruhnya oleh service pembentukan event log. Satu task menjadi satu case, satu baris
sumber (action Trello atau kejadian D-10) menjadi satu event, dengan atribut XES concept:name,
time:timestamp, dan org:resource. resource_id boleh kosong sampai alias identitas (DIG-24) ada;
akun pelaku dari sumber disimpan di actor_source_id dan actor_name.

case_id tanpa foreign key karena kartu Trello bisa berisi task yang belum dimuat ke D-05.

Revision ID: 0018
Revises: 0012
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_log",
        sa.Column("event_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("case_id", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.String(length=20), nullable=True),
        sa.Column("activity", sa.String(length=100), nullable=False),
        sa.Column("activity_kind", sa.String(length=20), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resource_id", sa.String(length=20), nullable=True),
        sa.Column("actor_source_id", sa.String(length=50), nullable=True),
        sa.Column("actor_name", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=50), nullable=False),
        sa.CheckConstraint(
            "activity_kind IN ('created', 'status', 'archived', 'deleted', 'assignment', "
            "'change_event')",
            name=op.f("ck_event_log_activity_kind_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('trello', 'change_event')", name=op.f("ck_event_log_source_valid")
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_event_log_resource_id_resources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_event_log")),
        sa.UniqueConstraint("source", "source_ref", name=op.f("uq_event_log_source_source_ref")),
    )
    op.create_index("ix_event_log_case_id_event_time", "event_log", ["case_id", "event_time"])
    op.create_index("ix_event_log_project_id_event_time", "event_log", ["project_id", "event_time"])


def downgrade() -> None:
    op.drop_index("ix_event_log_project_id_event_time", table_name="event_log")
    op.drop_index("ix_event_log_case_id_event_time", table_name="event_log")
    op.drop_table("event_log")
