"""task_manual_change: jejak perubahan task dari aplikasi

Jira: DIG-162 (AC DIG-36). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2), tidak dibaca
tWinner. Satu baris per kolom task yang diubah lewat aplikasi, supaya impor berikutnya tidak
menimpanya tanpa konfirmasi.

Revision ID: 0020
Revises: 0019
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_manual_change",
        sa.Column("change_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("task_id", sa.String(length=20), nullable=False),
        sa.Column("field", sa.String(length=20), nullable=False),
        sa.Column("old_value", sa.String(length=50), nullable=True),
        sa.Column("new_value", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("ref", sa.String(length=20), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "field IN ('status', 'priority_rank', 'actual_start', 'actual_finish', "
            "'dod_fulfilled')",
            name=op.f("ck_task_manual_change_field_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('status_update', 'change_event', 'blocker')",
            name=op.f("ck_task_manual_change_source_valid"),
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ('kept', 'import_taken', 'caught_up')",
            name=op.f("ck_task_manual_change_resolution_valid"),
        ),
        sa.CheckConstraint(
            "(resolution IS NULL) = (resolved_at IS NULL)",
            name=op.f("ck_task_manual_change_resolved_together"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.task_id"],
            name=op.f("fk_task_manual_change_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["app_user.user_id"],
            name=op.f("fk_task_manual_change_changed_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("change_id", name=op.f("pk_task_manual_change")),
    )
    op.create_index(
        op.f("ix_task_manual_change_task_id"), "task_manual_change", ["task_id"], unique=False
    )
    op.create_index(
        "ix_task_manual_change_open",
        "task_manual_change",
        ["task_id", "field"],
        postgresql_where=sa.text("resolution IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_task_manual_change_open", table_name="task_manual_change")
    op.drop_index(op.f("ix_task_manual_change_task_id"), table_name="task_manual_change")
    op.drop_table("task_manual_change")
