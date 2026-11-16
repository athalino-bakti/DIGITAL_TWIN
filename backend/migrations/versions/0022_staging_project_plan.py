"""staging_project_plan dan import_job_id di staging_trello_action

Jira: DIG-113 (story DIG-25). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2).
- `staging_project_plan`: baris Project Plan apa adanya (teks), satu batch per import_job.
  Menghapus job menghapus batch-nya (CASCADE).
- `staging_trello_action.import_job_id`: job yang pertama menyimpan action. Baris lama tetap
  NULL; menghapus job tidak menghapus action (SET NULL).

Revision ID: 0022
Revises: 0019
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLAN_TEXT_COLUMNS = (
    "task_code",
    "feature_name",
    "task_name",
    "role_label",
    "pic",
    "complexity_label",
    "priority",
    "estimated_days",
    "planned_start",
    "planned_finish",
    "actual_start",
    "actual_finish",
    "status_label",
    "depends_on",
    "notes",
)


def upgrade() -> None:
    op.create_table(
        "staging_project_plan",
        sa.Column("import_job_id", sa.BigInteger(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("sheet_name", sa.Text(), nullable=True),
        *(sa.Column(name, sa.Text(), nullable=True) for name in PLAN_TEXT_COLUMNS),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "project_id ~ '^PRJ-[0-9]{3,}$'",
            name=op.f("ck_staging_project_plan_project_id_format"),
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["import_job.job_id"],
            name=op.f("fk_staging_project_plan_import_job_id_import_job"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "import_job_id", "row_number", name=op.f("pk_staging_project_plan")
        ),
    )
    op.create_index(
        "ix_staging_project_plan_project_id_import_job_id",
        "staging_project_plan",
        ["project_id", "import_job_id"],
    )
    op.add_column(
        "staging_trello_action", sa.Column("import_job_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_staging_trello_action_import_job_id_import_job"),
        "staging_trello_action",
        "import_job",
        ["import_job_id"],
        ["job_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_staging_trello_action_import_job_id_import_job"),
        "staging_trello_action",
        type_="foreignkey",
    )
    op.drop_column("staging_trello_action", "import_job_id")
    op.drop_index(
        "ix_staging_project_plan_project_id_import_job_id", table_name="staging_project_plan"
    )
    op.drop_table("staging_project_plan")
