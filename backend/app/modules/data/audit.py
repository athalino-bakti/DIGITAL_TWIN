"""Penulisan dan pembacaan jejak audit `audit_log` (DIG-222).

`record_audit` dipanggil di dalam transaksi pengubah data (form, impor, ETL DIG-29) dan tidak
commit, supaya jejak dan perubahannya masuk atau gagal bersama.
"""

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import AppUser
from app.modules.data.audit_models import AUDIT_ACTIONS, AUDIT_SOURCES, SYSTEM_ACTOR, AuditLog


def to_json(value: Any) -> Any:
    """Nilai kolom ke bentuk JSON: tanggal ISO 8601, Decimal ke float, enum ke nilainya."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _clean(values: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return None if values is None else {k: to_json(v) for k, v in values.items()}


def record_audit(
    db: Session,
    *,
    action: str,
    entity: str,
    entity_id: str,
    source: str,
    actor: AppUser | None = None,
    import_job_id: int | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    note: str | None = None,
) -> AuditLog | None:
    """Tambah satu baris jejak audit. Tidak commit.

    Untuk `update`, hanya kolom yang nilainya berbeda yang disimpan; bila tidak ada yang berbeda,
    tidak ada baris yang ditulis dan hasilnya None.
    """
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"action tidak dikenal: {action}")
    if source not in AUDIT_SOURCES:
        raise ValueError(f"source tidak dikenal: {source}")
    old, new = _clean(before), _clean(after)
    if action == "update":
        old, new = old or {}, new or {}
        changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        if not changed:
            return None
        old = {k: old.get(k) for k in changed}
        new = {k: new.get(k) for k in changed}
    entry = AuditLog(
        actor_user_id=actor.user_id if actor else None,
        actor_label=actor.username if actor else SYSTEM_ACTOR,
        action=action,
        entity=entity,
        entity_id=entity_id,
        source=source,
        import_job_id=import_job_id,
        before=old,
        after=new,
        note=note,
    )
    db.add(entry)
    return entry


def list_audit(
    db: Session,
    entity: str | None = None,
    entity_id: str | None = None,
    import_job_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[int, list[AuditLog]]:
    """(jumlah total, satu halaman) jejak audit, terbaru dulu."""
    query = select(AuditLog)
    if entity:
        query = query.where(AuditLog.entity == entity)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if import_job_id:
        query = query.where(AuditLog.import_job_id == import_job_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(AuditLog.occurred_at.desc(), AuditLog.audit_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return total or 0, list(rows)
