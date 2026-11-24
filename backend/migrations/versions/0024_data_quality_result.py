"""data_quality_result dan rejected_row: hasil pemeriksaan kualitas data per impor

Jira: DIG-145 (story DIG-32). Tabel internal J&C (docs/DATA_CONTRACT.md bagian 7.2), tidak
dibaca tWinner. Keduanya menempel ke import_job dan ikut terhapus bersama job-nya (CASCADE).

Revision ID: 0024
Revises: 0023
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, Sequence[str], None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHARACTERISTIC = "characteristic IN ('completeness', 'consistency', 'currentness', 'traceability')"
LEVEL = "level IN ('tolak', 'peringatan')"


def _job_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["job_id"],
        ["import_job.job_id"],
        name=op.f(f"fk_{table}_job_id_import_job"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "data_quality_result",
        sa.Column("result_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("rule_id", sa.String(length=20), nullable=False),
        sa.Column("table_name", sa.String(length=40), nullable=False),
        sa.Column("characteristic", sa.String(length=20), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("checked", sa.Integer(), nullable=False),
        sa.Column("violated", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            CHARACTERISTIC, name=op.f("ck_data_quality_result_characteristic_valid")
        ),
        sa.CheckConstraint(LEVEL, name=op.f("ck_data_quality_result_level_valid")),
        sa.CheckConstraint(
            "violated >= 0 AND violated <= checked",
            name=op.f("ck_data_quality_result_violated_range"),
        ),
        _job_fk("data_quality_result"),
        sa.PrimaryKeyConstraint("result_id", name=op.f("pk_data_quality_result")),
        sa.UniqueConstraint(
            "job_id",
            "source",
            "rule_id",
            name=op.f("uq_data_quality_result_job_id_source_rule_id"),
        ),
    )
    op.create_table(
        "rejected_row",
        sa.Column("rejected_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("table_name", sa.String(length=40), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("row_key", sa.Text(), nullable=True),
        sa.Column("rule_id", sa.String(length=20), nullable=False),
        sa.Column("characteristic", sa.String(length=20), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.CheckConstraint(CHARACTERISTIC, name=op.f("ck_rejected_row_characteristic_valid")),
        sa.CheckConstraint(LEVEL, name=op.f("ck_rejected_row_level_valid")),
        _job_fk("rejected_row"),
        sa.PrimaryKeyConstraint("rejected_id", name=op.f("pk_rejected_row")),
    )
    op.create_index("ix_rejected_row_job_id_level", "rejected_row", ["job_id", "level"])


def downgrade() -> None:
    op.drop_index("ix_rejected_row_job_id_level", table_name="rejected_row")
    op.drop_table("rejected_row")
    op.drop_table("data_quality_result")
