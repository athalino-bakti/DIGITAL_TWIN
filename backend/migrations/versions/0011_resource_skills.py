"""resource_skills: tingkat penguasaan anggota per peran

Jira: DIG-220. Tabel pendukung J&C yang dibaca tWinner (docs/DATA_CONTRACT.md bagian 7.1),
dengan struktur bagian 7.3. Satu baris mewakili satu pasangan anggota dan peran.
proficiency_level: 1 = dasar, 2 = mandiri, 3 = mahir.

Keahlian ikut terhapus bersama anggotanya (ON DELETE CASCADE). Peran yang masih dipakai
tidak bisa dihapus (ON DELETE RESTRICT).

Revision ID: 0011
Revises: 0016
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
# Saat PR ini di-rebase setelah migrasi lain masuk ke main, ganti ke head terbaru.
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_skills",
        sa.Column("resource_id", sa.String(length=20), nullable=False),
        sa.Column("role_id", sa.String(length=20), nullable=False),
        sa.Column("proficiency_level", sa.SmallInteger(), nullable=False),
        sa.Column("assessed_date", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "proficiency_level BETWEEN 1 AND 3",
            name=op.f("ck_resource_skills_proficiency_level_range"),
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_resource_skills_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.role_id"],
            name=op.f("fk_resource_skills_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("resource_id", "role_id", name=op.f("pk_resource_skills")),
    )
    op.create_index(op.f("ix_resource_skills_role_id"), "resource_skills", ["role_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_resource_skills_role_id"), table_name="resource_skills")
    op.drop_table("resource_skills")
