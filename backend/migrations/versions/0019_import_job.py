"""import_job: catatan setiap job impor

Jira: DIG-128 (bersama DIG-113). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2).
Satu baris per job impor (Trello, Project Plan, TeamGit): pemicu, status, waktu, jumlah baris,
dan pesan error. Index unik parsial menjamin paling banyak satu job berjalan per sumber.

Revision ID: 0019
Revises: 0014
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_job",
        sa.Column("job_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_read", sa.Integer(), nullable=True),
        sa.Column("rows_written", sa.Integer(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "source IN ('trello', 'project_plan', 'teamgit')",
            name=op.f("ck_import_job_source_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'schedule')", name=op.f("ck_import_job_trigger_valid")
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name=op.f("ck_import_job_status_valid"),
        ),
        sa.CheckConstraint("attempts >= 1", name=op.f("ck_import_job_attempts_positive")),
        sa.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name=op.f("ck_import_job_finished_when_done"),
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_import_job")),
    )
    op.create_index("ix_import_job_source_started_at", "import_job", ["source", "started_at"])
    op.create_index(
        "uq_import_job_one_running_per_source",
        "import_job",
        ["source"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_import_job_one_running_per_source", table_name="import_job")
    op.drop_index("ix_import_job_source_started_at", table_name="import_job")
    op.drop_table("import_job")
