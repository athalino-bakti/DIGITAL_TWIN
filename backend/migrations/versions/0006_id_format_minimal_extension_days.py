"""Format ID minimal digit dan extension_days boleh 0

Jira: DIG-15. Dataset dummy dosbim (puti_datasets.xlsx) memakai DEP-0001, ASG-00001,
AVL-0001, dan EVT-0001, serta extension_days 0.0 untuk event tanpa perpanjangan. Jumlah
digit pada contoh Data Dictionary kini menjadi jumlah digit minimal, sehingga format Data
Dictionary dan format dataset sama-sama valid. Downgrade gagal bila tabel sudah berisi ID
yang lebih panjang dari format lama atau extension_days bernilai 0.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabel, kolom, prefiks, digit minimal)
ID_FORMATS = [
    ("projects", "project_id", "PRJ", 3),
    ("resources", "resource_id", "RES", 3),
    ("tasks", "task_id", "TSK", 4),
    ("task_dependencies", "dependency_id", "DEP", 3),
    ("assignments", "assignment_id", "ASG", 4),
    ("workload_items", "item_id", "WLI", 4),
    ("availability", "availability_id", "AVL", 3),
    ("change_events", "event_id", "EVT", 3),
]


def _swap_id_checks(minimal: bool) -> None:
    for table, column, prefix, digits in ID_FORMATS:
        name = op.f(f"ck_{table}_{column}_format")
        quantifier = f"{{{digits},}}" if minimal else f"{{{digits}}}"
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} ~ '^{prefix}-[0-9]{quantifier}$'")


def upgrade() -> None:
    _swap_id_checks(minimal=True)
    op.drop_constraint(
        op.f("ck_change_events_extension_days_positive"), "change_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_change_events_extension_days_min"), "change_events", "extension_days >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_change_events_extension_days_min"), "change_events", type_="check")
    op.create_check_constraint(
        op.f("ck_change_events_extension_days_positive"), "change_events", "extension_days > 0"
    )
    _swap_id_checks(minimal=False)
