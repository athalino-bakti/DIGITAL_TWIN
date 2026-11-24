"""audit_log: jejak audit perubahan final sources

Jira: DIG-222 (story DIG-32). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2 dan 8), tidak
dibaca tWinner. Append-only bagi aplikasi: role jc_app hanya SELECT dan INSERT.

Nomor 0026 karena 0024 (#53) dan 0025 (#57) masih terbuka. Sementara menyambung ke 0023; sambung
ulang `down_revision` ke head main setiap kali #53 atau #57 merge.

Revision ID: 0026
Revises: 0023
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, Sequence[str], None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("audit_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_label", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("import_job_id", sa.BigInteger(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "action IN ('insert', 'update', 'delete', 'import', 'export')",
            name=op.f("ck_audit_log_action_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('form', 'project_plan', 'trello', 'teamgit', 'etl', 'sistem')",
            name=op.f("ck_audit_log_source_valid"),
        ),
        sa.CheckConstraint(
            "(action <> 'insert' OR before IS NULL)"
            " AND (action <> 'delete' OR after IS NULL)"
            " AND (action <> 'update' OR (before IS NOT NULL AND after IS NOT NULL))",
            name=op.f("ck_audit_log_values_match_action"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_audit_log_actor_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["import_job.job_id"],
            name=op.f("fk_audit_log_import_job_id_import_job"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("audit_id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_entity", "audit_log", ["entity", "entity_id", "occurred_at"], unique=False
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"], unique=False)
    op.create_index("ix_audit_log_import_job_id", "audit_log", ["import_job_id"], unique=False)
    # Default privileges dari 0014 memberi jc_app DML penuh; jejak audit tidak boleh diubah.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM jc_app")


def downgrade() -> None:
    op.drop_index("ix_audit_log_import_job_id", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
