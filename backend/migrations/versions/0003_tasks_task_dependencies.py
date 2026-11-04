"""D-05 tasks dan D-06 task_dependencies

Jira: DIG-76. tasks ber-FK ke projects, roles, dan complexity_levels; task_dependencies
menghubungkan dua task dan menolak self-dependency serta pasangan ganda. Deteksi siklus
tidak bisa lewat CHECK dan dikerjakan di validator (DIG-142).

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.String(length=20), nullable=False),
        sa.Column("feature_name", sa.String(length=200), nullable=False),
        sa.Column("task_name", sa.String(length=300), nullable=False),
        sa.Column("required_role_id", sa.String(length=20), nullable=False),
        sa.Column("complexity_id", sa.String(length=20), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False),
        sa.Column("estimated_days", sa.Double(), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("planned_start", sa.Date(), nullable=False),
        sa.Column("planned_finish", sa.Date(), nullable=False),
        sa.Column("actual_start", sa.Date(), nullable=True),
        sa.Column("actual_finish", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="not_started", nullable=False),
        sa.Column("qa_reject_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dod_fulfilled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "phase IN ('planning', 'uiux', 'dm_dev', 'be_dev', 'fe_dev', "
            "'testing', 'bugfix', 'documentation')",
            name=op.f("ck_tasks_phase_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'blocked', 'on_hold', "
            "'in_qa', 'done', 'dropped')",
            name=op.f("ck_tasks_status_valid"),
        ),
        sa.CheckConstraint("task_id ~ '^TSK-[0-9]{4}$'", name=op.f("ck_tasks_task_id_format")),
        sa.CheckConstraint(
            "actual_finish >= actual_start", name=op.f("ck_tasks_actual_finish_after_start")
        ),
        sa.CheckConstraint(
            "actual_finish IS NULL OR actual_start IS NOT NULL",
            name=op.f("ck_tasks_actual_finish_needs_start"),
        ),
        sa.CheckConstraint("estimated_days > 0", name=op.f("ck_tasks_estimated_days_positive")),
        sa.CheckConstraint(
            "planned_finish >= planned_start", name=op.f("ck_tasks_planned_finish_after_start")
        ),
        sa.CheckConstraint("priority_rank >= 1", name=op.f("ck_tasks_priority_rank_min")),
        sa.CheckConstraint("qa_reject_count >= 0", name=op.f("ck_tasks_qa_reject_count_min")),
        sa.ForeignKeyConstraint(
            ["complexity_id"],
            ["complexity_levels.complexity_id"],
            name=op.f("fk_tasks_complexity_id_complexity_levels"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], name=op.f("fk_tasks_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["required_role_id"], ["roles.role_id"], name=op.f("fk_tasks_required_role_id_roles")
        ),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_complexity_id"), "tasks", ["complexity_id"], unique=False)
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_tasks_required_role_id"), "tasks", ["required_role_id"], unique=False)
    op.create_table(
        "task_dependencies",
        sa.Column("dependency_id", sa.String(length=20), nullable=False),
        sa.Column("task_id", sa.String(length=20), nullable=False),
        sa.Column("depends_on_task_id", sa.String(length=20), nullable=False),
        sa.Column("dependency_type", sa.String(length=10), nullable=False),
        sa.Column("propagation_factor", sa.Double(), nullable=False),
        sa.CheckConstraint(
            "dependency_id ~ '^DEP-[0-9]{3}$'",
            name=op.f("ck_task_dependencies_dependency_id_format"),
        ),
        sa.CheckConstraint(
            "dependency_type <> 'hard' OR propagation_factor = 1.0",
            name=op.f("ck_task_dependencies_hard_propagation_full"),
        ),
        sa.CheckConstraint(
            "dependency_type IN ('hard', 'soft')",
            name=op.f("ck_task_dependencies_dependency_type_valid"),
        ),
        sa.CheckConstraint(
            "propagation_factor > 0 AND propagation_factor <= 1",
            name=op.f("ck_task_dependencies_propagation_factor_range"),
        ),
        sa.CheckConstraint(
            "task_id <> depends_on_task_id", name=op.f("ck_task_dependencies_no_self_dependency")
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id"],
            ["tasks.task_id"],
            name=op.f("fk_task_dependencies_depends_on_task_id_tasks"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.task_id"], name=op.f("fk_task_dependencies_task_id_tasks")
        ),
        sa.PrimaryKeyConstraint("dependency_id", name=op.f("pk_task_dependencies")),
        sa.UniqueConstraint(
            "task_id",
            "depends_on_task_id",
            name=op.f("uq_task_dependencies_task_id_depends_on_task_id"),
        ),
    )
    op.create_index(
        op.f("ix_task_dependencies_depends_on_task_id"),
        "task_dependencies",
        ["depends_on_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_dependencies_task_id"), "task_dependencies", ["task_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_dependencies_task_id"), table_name="task_dependencies")
    op.drop_index(op.f("ix_task_dependencies_depends_on_task_id"), table_name="task_dependencies")
    op.drop_table("task_dependencies")
    op.drop_index(op.f("ix_tasks_required_role_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_complexity_id"), table_name="tasks")
    op.drop_table("tasks")
