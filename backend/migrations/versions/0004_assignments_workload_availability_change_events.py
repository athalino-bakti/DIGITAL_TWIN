"""D-07 assignments, D-08 workload_items, D-09 availability, D-10 change_events

Jira: DIG-77. Tabel transaksi yang bergantung pada tasks, resources, dan projects.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("assignment_id", sa.String(length=20), nullable=False),
        sa.Column("task_id", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("role_in_task", sa.String(length=20), nullable=False),
        sa.Column("assigned_date", sa.Date(), nullable=False),
        sa.Column("released_date", sa.Date(), nullable=True),
        sa.Column("is_takeover", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "assignment_id ~ '^ASG-[0-9]{4}$'", name=op.f("ck_assignments_assignment_id_format")
        ),
        sa.CheckConstraint(
            "released_date >= assigned_date", name=op.f("ck_assignments_released_after_assigned")
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_assignments_resource_id_resources"),
        ),
        sa.ForeignKeyConstraint(
            ["role_in_task"], ["roles.role_id"], name=op.f("fk_assignments_role_in_task_roles")
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.task_id"], name=op.f("fk_assignments_task_id_tasks")
        ),
        sa.PrimaryKeyConstraint("assignment_id", name=op.f("pk_assignments")),
    )
    op.create_index(
        op.f("ix_assignments_resource_id"), "assignments", ["resource_id"], unique=False
    )
    op.create_index(
        op.f("ix_assignments_role_in_task"), "assignments", ["role_in_task"], unique=False
    )
    op.create_index(op.f("ix_assignments_task_id"), "assignments", ["task_id"], unique=False)
    op.create_table(
        "availability",
        sa.Column("availability_id", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("date_start", sa.Date(), nullable=False),
        sa.Column("date_end", sa.Date(), nullable=False),
        sa.Column("absence_type", sa.String(length=20), nullable=False),
        sa.Column(
            "is_known_at_planning", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint(
            "absence_type IN ('planned_leave', 'sudden_leave', 'maternity_leave', "
            "'rotation_out', 'rotation_in')",
            name=op.f("ck_availability_absence_type_valid"),
        ),
        sa.CheckConstraint(
            "availability_id ~ '^AVL-[0-9]{3}$'",
            name=op.f("ck_availability_availability_id_format"),
        ),
        sa.CheckConstraint(
            "date_end >= date_start", name=op.f("ck_availability_date_end_after_start")
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_availability_resource_id_resources"),
        ),
        sa.PrimaryKeyConstraint("availability_id", name=op.f("pk_availability")),
    )
    op.create_index(
        op.f("ix_availability_resource_id"), "availability", ["resource_id"], unique=False
    )
    op.create_table(
        "change_events",
        sa.Column("event_id", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("requested_by", sa.String(length=100), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("resolution_mode", sa.String(length=20), nullable=True),
        sa.Column("affected_task_id", sa.String(length=20), nullable=True),
        sa.Column("extension_days", sa.Double(), nullable=True),
        sa.CheckConstraint(
            "decision IN ('accept_now', 'defer_next', 'reject')",
            name=op.f("ck_change_events_decision_valid"),
        ),
        sa.CheckConstraint(
            "event_id ~ '^EVT-[0-9]{3}$'", name=op.f("ck_change_events_event_id_format")
        ),
        sa.CheckConstraint(
            "event_type IN ('change_request', 'priority_change', 'blocker', 'overrun', 'hotfix')",
            name=op.f("ck_change_events_event_type_valid"),
        ),
        sa.CheckConstraint(
            "resolution_mode IN ('swap_task', 'extend_duration', 'scope_addition', 'reshuffle')",
            name=op.f("ck_change_events_resolution_mode_valid"),
        ),
        sa.CheckConstraint(
            "extension_days > 0", name=op.f("ck_change_events_extension_days_positive")
        ),
        sa.ForeignKeyConstraint(
            ["affected_task_id"],
            ["tasks.task_id"],
            name=op.f("fk_change_events_affected_task_id_tasks"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name=op.f("fk_change_events_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_change_events")),
    )
    op.create_index(
        op.f("ix_change_events_affected_task_id"),
        "change_events",
        ["affected_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_change_events_project_id"), "change_events", ["project_id"], unique=False
    )
    op.create_table(
        "workload_items",
        sa.Column("item_id", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("related_project_id", sa.String(length=20), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("started_date", sa.Date(), nullable=True),
        sa.Column("resolved_date", sa.Date(), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=True),
        sa.Column("is_hotfix", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "item_id ~ '^WLI-[0-9]{4}$'", name=op.f("ck_workload_items_item_id_format")
        ),
        sa.CheckConstraint(
            "item_type IN ('operational', 'ticket')", name=op.f("ck_workload_items_item_type_valid")
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name=op.f("ck_workload_items_severity_valid"),
        ),
        sa.CheckConstraint(
            "resolved_date >= received_date", name=op.f("ck_workload_items_resolved_after_received")
        ),
        sa.CheckConstraint(
            "resolved_date >= started_date", name=op.f("ck_workload_items_resolved_after_started")
        ),
        sa.CheckConstraint(
            "started_date >= received_date", name=op.f("ck_workload_items_started_after_received")
        ),
        sa.ForeignKeyConstraint(
            ["related_project_id"],
            ["projects.project_id"],
            name=op.f("fk_workload_items_related_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_workload_items_resource_id_resources"),
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_workload_items")),
    )
    op.create_index(
        op.f("ix_workload_items_related_project_id"),
        "workload_items",
        ["related_project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workload_items_resource_id"), "workload_items", ["resource_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workload_items_resource_id"), table_name="workload_items")
    op.drop_index(op.f("ix_workload_items_related_project_id"), table_name="workload_items")
    op.drop_table("workload_items")
    op.drop_index(op.f("ix_change_events_project_id"), table_name="change_events")
    op.drop_index(op.f("ix_change_events_affected_task_id"), table_name="change_events")
    op.drop_table("change_events")
    op.drop_index(op.f("ix_availability_resource_id"), table_name="availability")
    op.drop_table("availability")
    op.drop_index(op.f("ix_assignments_task_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_role_in_task"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_resource_id"), table_name="assignments")
    op.drop_table("assignments")
