"""Penanda perubahan manual pada task dan aturan konfliknya dengan impor (DIG-162).

Tiga jalur aplikasi mengubah kolom task: ubah status (DIG-161), efek CR (DIG-150), dan blocker
(DIG-153). Setiap perubahan dicatat di `task_manual_change` dalam transaksi yang sama lewat
`record_task_changes`. Impor berikutnya (upsert ETL DIG-134) memanggil `merge_task_import` per
task dengan perubahan yang masih terbuka (`open_changes`):

- kolom tanpa perubahan manual yang terbuka: impor menimpa seperti biasa;
- nilai impor sama dengan nilai sekarang: sumber sudah menyusul, perubahan ditutup `caught_up`;
- nilai impor berbeda: kolom itu tidak ditimpa dan dilaporkan sebagai konflik, untuk
  dikonfirmasi System Analyst (`kept` atau `import_taken`).

Usulan desain dan pertanyaan terbuka untuk DIG-134 ada di komentar Jira DIG-162.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.data.manual_change_models import TRACKED_FIELDS, TaskManualChange
from app.modules.data.models import Task


def to_text(value: Any) -> str | None:
    """Nilai kolom task sebagai teks yang bisa dibandingkan antara aplikasi dan impor."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def snapshot(task: Task) -> dict[str, str | None]:
    """Nilai kolom yang dilacak, diambil sebelum task diubah."""
    return {name: to_text(getattr(task, name)) for name in TRACKED_FIELDS}


def record_task_changes(
    db: Session,
    task: Task,
    before: Mapping[str, str | None],
    source: str,
    ref: str | None = None,
    changed_by: int | None = None,
) -> list[TaskManualChange]:
    """Catat setiap kolom yang nilainya berbeda dari `before`. Tidak commit."""
    rows = []
    for name in TRACKED_FIELDS:
        new = to_text(getattr(task, name))
        if new != before.get(name):
            row = TaskManualChange(
                task_id=task.task_id,
                field=name,
                old_value=before.get(name),
                new_value=new,
                source=source,
                ref=ref,
                changed_by=changed_by,
            )
            db.add(row)
            rows.append(row)
    return rows


def status_before(db: Session, task_id: str, source: str, ref: str) -> str | None:
    """Status task sebelum perubahan dari `source`/`ref`, misalnya sebelum satu blocker."""
    return db.scalar(
        select(TaskManualChange.old_value)
        .where(
            TaskManualChange.task_id == task_id,
            TaskManualChange.field == "status",
            TaskManualChange.source == source,
            TaskManualChange.ref == ref,
        )
        .order_by(TaskManualChange.change_id.desc())
        .limit(1)
    )


@dataclass(frozen=True)
class OpenChange:
    """Perubahan manual terakhir yang belum diselesaikan untuk satu kolom task."""

    field: str
    new_value: str | None
    change_ids: tuple[int, ...]
    changed_at: datetime
    changed_by: int | None
    source: str


def open_changes(db: Session, task_ids: Iterable[str]) -> dict[str, dict[str, OpenChange]]:
    """Per task, per kolom: perubahan manual terbuka (yang terbaru menentukan nilainya)."""
    ids = list(task_ids)
    if not ids:
        return {}
    rows = db.scalars(
        select(TaskManualChange)
        .where(TaskManualChange.task_id.in_(ids), TaskManualChange.resolution.is_(None))
        .order_by(TaskManualChange.change_id)
    )
    result: dict[str, dict[str, OpenChange]] = {}
    for row in rows:
        previous = result.setdefault(row.task_id, {}).get(row.field)
        result[row.task_id][row.field] = OpenChange(
            field=row.field,
            new_value=row.new_value,
            change_ids=(*(previous.change_ids if previous else ()), row.change_id),
            changed_at=row.changed_at,
            changed_by=row.changed_by,
            source=row.source,
        )
    return result


@dataclass(frozen=True)
class ImportConflict:
    """Kolom yang tidak ditimpa impor karena sudah diubah dari aplikasi."""

    field: str
    current: str | None
    incoming: str | None
    change: OpenChange


@dataclass
class MergeResult:
    updates: dict[str, Any] = field(default_factory=dict)
    conflicts: list[ImportConflict] = field(default_factory=list)
    caught_up: list[int] = field(default_factory=list)


def merge_task_import(
    current: Mapping[str, Any], incoming: Mapping[str, Any], pending: Mapping[str, OpenChange]
) -> MergeResult:
    """Tentukan kolom mana yang boleh ditimpa impor untuk satu task. Fungsi murni.

    `current` dan `incoming` berisi nilai kolom task (tipe Python apa pun yang bisa diubah
    `to_text`); `pending` adalah hasil `open_changes` untuk task tersebut.
    """
    result = MergeResult()
    for name, value in incoming.items():
        change = pending.get(name)
        if change is None:
            if to_text(value) != to_text(current.get(name)):
                result.updates[name] = value
        elif to_text(value) == to_text(current.get(name)):
            result.caught_up.extend(change.change_ids)
        else:
            result.conflicts.append(
                ImportConflict(name, to_text(current.get(name)), to_text(value), change)
            )
    return result


def settle(db: Session, change_ids: Iterable[int], resolution: str) -> int:
    """Tutup perubahan manual (`kept`, `import_taken`, atau `caught_up`). Tidak commit."""
    ids = list(change_ids)
    if not ids:
        return 0
    return db.execute(
        update(TaskManualChange)
        .where(TaskManualChange.change_id.in_(ids), TaskManualChange.resolution.is_(None))
        .values(resolution=resolution, resolved_at=func.now())
    ).rowcount
