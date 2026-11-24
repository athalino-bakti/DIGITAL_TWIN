"""rli_snapshot dan view resource_load_index untuk tWinner

Jira: DIG-192 (story DIG-44). Formula RLI tetap satu, di Python (`rli.py`, DIG-187); tabel
snapshot diisi `python -m app.modules.digital_twin.rli_snapshot`, dan tWinner membaca view
`resource_load_index` (docs/DATA_CONTRACT.md bagian 7.1). Hak SELECT untuk `twinner_reader`
diberikan di DIG-191 saat role itu dibuat. jc_app hanya membaca view.

Menyambung ke 0026 (#58), head main saat dibuat.

Revision ID: 0027
Revises: 0026
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, Sequence[str], None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rli_snapshot",
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("rli", sa.Numeric(8, 3), nullable=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("project_load", sa.Numeric(8, 3), nullable=False),
        sa.Column("non_project_load", sa.Numeric(8, 3), nullable=False),
        sa.Column("capacity", sa.Numeric(8, 3), nullable=False),
        sa.Column("available_days", sa.Integer(), nullable=False),
        sa.Column("onboarding_factor", sa.Numeric(4, 2), nullable=False),
        sa.Column("tasks", sa.Integer(), nullable=False),
        sa.Column("workload_items", sa.Integer(), nullable=False),
        sa.Column("formula_version", sa.String(length=30), nullable=False),
        sa.Column("provisional", sa.Boolean(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_rli_snapshot_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("resource_id", "week_start", name=op.f("pk_rli_snapshot")),
    )
    op.execute(
        "CREATE VIEW resource_load_index AS SELECT resource_id, week_start,"
        " week_start + 4 AS week_end, rli, category, project_load, non_project_load, capacity,"
        " available_days, onboarding_factor, tasks, workload_items, formula_version,"
        " provisional, as_of, computed_at FROM rli_snapshot"
    )
    # Default privileges 0014 memberi jc_app DML pada view juga; view ini hanya untuk dibaca.
    op.execute("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON resource_load_index FROM jc_app")


def downgrade() -> None:
    op.execute("DROP VIEW resource_load_index")
    op.drop_table("rli_snapshot")
