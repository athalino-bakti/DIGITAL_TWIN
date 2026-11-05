"""Prioritas unik di antara proyek aktif D-01 projects

Jira: DIG-97 (review PR #7). Aturan DIG-20 "priority_rank unik di antara proyek
aktif" sebelumnya hanya dicek di service, sehingga dua permintaan bersamaan dengan
prioritas yang sama bisa sama-sama lolos. Partial unique index menutup celah itu.
Kolom D-01 tidak berubah.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "uq_projects_active_priority"
ACTIVE = "status IN ('planning', 'development', 'testing')"


def upgrade() -> None:
    op.create_index(
        INDEX, "projects", ["priority_rank"], unique=True, postgresql_where=sa.text(ACTIVE)
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="projects")
