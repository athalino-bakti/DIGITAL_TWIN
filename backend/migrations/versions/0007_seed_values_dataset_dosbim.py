"""Nilai seed complexity_levels dan capacity_reference mengikuti dataset dosbim

Jira: DIG-78. Rentang hari dan bobot complexity_levels pada revisi 0005 adalah asumsi
tim. Dataset dummy dosbim (puti_datasets.xlsx) memberi nilai acuan yang dipakai kedua
tim, jadi seed mengikuti nilai tersebut. Nama dan deskripsi peran tetap dari wawancara
Tim DEVTI PuTI. Downgrade mengembalikan nilai revisi 0005.

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

complexity_levels = sa.table(
    "complexity_levels",
    sa.column("complexity_id", sa.String),
    sa.column("min_days", sa.Double),
    sa.column("max_days", sa.Double),
    sa.column("load_weight", sa.Double),
)
roles = sa.table(
    "roles",
    sa.column("role_id", sa.String),
    sa.column("capacity_reference", sa.Double),
)

# (id, min_days, max_days, load_weight)
DOSBIM = [
    ("CX-VH", 8.0, 15.0, 1.5),
    ("CX-H", 5.0, 8.0, 1.2),
    ("CX-M", 3.0, 5.0, 0.9),
    ("CX-L", 1.0, 3.0, 0.6),
]
PREVIOUS = [
    ("CX-VH", 10.0, 20.0, 2.0),
    ("CX-H", 5.0, 10.0, 1.5),
    ("CX-M", 2.0, 5.0, 1.0),
    ("CX-L", 0.5, 2.0, 0.5),
]
# capacity_reference yang berbeda dari default 3.0 pada dataset dosbim.
CAPACITY = {"ROLE-TW": (2.5, 3.0)}


def _set_complexity(values: list[tuple[str, float, float, float]]) -> None:
    for complexity_id, min_days, max_days, load_weight in values:
        op.execute(
            complexity_levels.update()
            .where(complexity_levels.c.complexity_id == complexity_id)
            .values(min_days=min_days, max_days=max_days, load_weight=load_weight)
        )


def upgrade() -> None:
    _set_complexity(DOSBIM)
    for role_id, (new, _) in CAPACITY.items():
        op.execute(roles.update().where(roles.c.role_id == role_id).values(capacity_reference=new))


def downgrade() -> None:
    for role_id, (_, old) in CAPACITY.items():
        op.execute(roles.update().where(roles.c.role_id == role_id).values(capacity_reference=old))
    _set_complexity(PREVIOUS)
