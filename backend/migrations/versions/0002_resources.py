"""D-02 resources

Jira: DIG-75. primary_role_id ber-FK ke roles; secondary_role_ids string berpemisah
titik koma dengan CHECK format.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("resource_name", sa.String(length=200), nullable=False),
        sa.Column("primary_role_id", sa.String(length=20), nullable=False),
        sa.Column("secondary_role_ids", sa.String(length=200), nullable=True),
        sa.Column(
            "cross_role_capable", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("join_date", sa.Date(), nullable=False),
        sa.Column("seniority", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "resource_id ~ '^RES-[0-9]{3}$'", name=op.f("ck_resources_resource_id_format")
        ),
        sa.CheckConstraint(
            "secondary_role_ids ~ '^ROLE-[A-Z]+(;ROLE-[A-Z]+)*$'",
            name=op.f("ck_resources_secondary_role_ids_format"),
        ),
        sa.CheckConstraint(
            "seniority IN ('junior', 'mid', 'senior')", name=op.f("ck_resources_seniority_valid")
        ),
        sa.ForeignKeyConstraint(
            ["primary_role_id"], ["roles.role_id"], name=op.f("fk_resources_primary_role_id_roles")
        ),
        sa.PrimaryKeyConstraint("resource_id", name=op.f("pk_resources")),
    )
    op.create_index(
        op.f("ix_resources_primary_role_id"), "resources", ["primary_role_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_resources_primary_role_id"), table_name="resources")
    op.drop_table("resources")
