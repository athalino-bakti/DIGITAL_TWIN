"""D-01 projects, D-03 roles, D-04 complexity_levels, D-11 holidays

Jira: DIG-74. Tabel master tanpa FK ke tabel lain, jadi dibuat paling awal.

Revision ID: 0001
Revises: -
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "complexity_levels",
        sa.Column("complexity_id", sa.String(length=20), nullable=False),
        sa.Column("complexity_name", sa.String(length=50), nullable=False),
        sa.Column("min_days", sa.Double(), nullable=False),
        sa.Column("max_days", sa.Double(), nullable=False),
        sa.Column("load_weight", sa.Double(), nullable=False),
        sa.CheckConstraint(
            "complexity_id ~ '^CX-[A-Z]+$'", name=op.f("ck_complexity_levels_complexity_id_format")
        ),
        sa.CheckConstraint("load_weight >= 0", name=op.f("ck_complexity_levels_load_weight_min")),
        sa.CheckConstraint(
            "max_days >= min_days", name=op.f("ck_complexity_levels_max_days_after_min")
        ),
        sa.CheckConstraint("min_days >= 0", name=op.f("ck_complexity_levels_min_days_min")),
        sa.PrimaryKeyConstraint("complexity_id", name=op.f("pk_complexity_levels")),
    )
    op.create_table(
        "holidays",
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("holiday_name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("holiday_date", name=op.f("pk_holidays")),
    )
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=20), nullable=False),
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("process_owner", sa.String(length=200), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("target_launch_date", sa.Date(), nullable=False),
        sa.Column("actual_launch_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dor_fulfilled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "project_id ~ '^PRJ-[0-9]{3}$'", name=op.f("ck_projects_project_id_format")
        ),
        sa.CheckConstraint(
            "status IN ('planning', 'development', 'testing', 'released', 'on_hold')",
            name=op.f("ck_projects_status_valid"),
        ),
        sa.CheckConstraint(
            "actual_launch_date >= start_date", name=op.f("ck_projects_actual_after_start")
        ),
        sa.CheckConstraint("priority_rank >= 1", name=op.f("ck_projects_priority_rank_min")),
        sa.CheckConstraint(
            "target_launch_date >= start_date", name=op.f("ck_projects_target_after_start")
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_projects")),
    )
    op.create_table(
        "roles",
        sa.Column("role_id", sa.String(length=20), nullable=False),
        sa.Column("role_name", sa.String(length=100), nullable=False),
        sa.Column("capacity_reference", sa.Double(), server_default="3.0", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint("role_id ~ '^ROLE-[A-Z]+$'", name=op.f("ck_roles_role_id_format")),
        sa.CheckConstraint(
            "capacity_reference > 0", name=op.f("ck_roles_capacity_reference_positive")
        ),
        sa.PrimaryKeyConstraint("role_id", name=op.f("pk_roles")),
    )


def downgrade() -> None:
    op.drop_table("roles")
    op.drop_table("projects")
    op.drop_table("holidays")
    op.drop_table("complexity_levels")
