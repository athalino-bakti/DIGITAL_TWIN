"""RBAC: app_role, permission, role_permission, user_app_role

Jira: DIG-89. Peran aplikasi terpisah dari D-03 roles. Satu pengguna boleh punya banyak
peran (user_app_role), dan izinnya gabungan dari semua peran (role_permission).

Revision ID: 0015
Revises: 0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_role",
        sa.Column("role_code", sa.String(length=30), nullable=False),
        sa.Column("role_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.CheckConstraint(
            "role_code ~ '^[a-z][a-z_]{2,29}$'", name=op.f("ck_app_role_role_code_format")
        ),
        sa.PrimaryKeyConstraint("role_code", name=op.f("pk_app_role")),
    )
    op.create_table(
        "permission",
        sa.Column("permission_code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.CheckConstraint(
            "permission_code ~ '^[a-z][a-z_]*:[a-z][a-z_]*$'",
            name=op.f("ck_permission_permission_code_format"),
        ),
        sa.PrimaryKeyConstraint("permission_code", name=op.f("pk_permission")),
    )
    op.create_table(
        "role_permission",
        sa.Column("role_code", sa.String(length=30), nullable=False),
        sa.Column("permission_code", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permission.permission_code"],
            name=op.f("fk_role_permission_permission_code_permission"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["app_role.role_code"],
            name=op.f("fk_role_permission_role_code_app_role"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_code", "permission_code", name=op.f("pk_role_permission")),
    )
    op.create_table(
        "user_app_role",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_code", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["app_role.role_code"],
            name=op.f("fk_user_app_role_role_code_app_role"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_user_app_role_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_code", name=op.f("pk_user_app_role")),
    )


def downgrade() -> None:
    op.drop_table("user_app_role")
    op.drop_table("role_permission")
    op.drop_table("permission")
    op.drop_table("app_role")
