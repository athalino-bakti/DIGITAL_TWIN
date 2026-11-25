"""Endpoint baca jejak audit (DIG-222). Dipasang di router modul Data (prefix /data).

Izin `data_quality:read`: jejak audit adalah karakteristik traceability laporan kualitas data
(Administrator Data dan System Analyst). Tidak ada endpoint tulis; baris ditulis lewat
`audit.record_audit` di dalam transaksi pengubah data.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.core.privacy import mask_emails_deep
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.audit import list_audit

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: int
    occurred_at: datetime
    actor_user_id: int | None
    actor_label: str
    action: str
    entity: str
    entity_id: str
    source: str
    import_job_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    note: str | None

    @field_validator("before", "after", "note", "entity_id")
    @classmethod
    def hide_email(cls, value: Any) -> Any:
        """Email (mis. alias teamgit) di isi audit tidak dikirim apa adanya (DIG-95)."""
        return mask_emails_deep(value)


class AuditPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditRead]


@router.get(
    "/audit-log",
    response_model=AuditPage,
    dependencies=[Depends(require_permission(Perm.DATA_QUALITY_READ))],
    summary="Jejak audit perubahan final sources, terbaru dulu",
)
def read_audit_log(
    db: Db,
    entity: Annotated[str | None, Query(max_length=50, examples=["tasks"])] = None,
    entity_id: Annotated[str | None, Query(max_length=100, examples=["TSK-0001"])] = None,
    import_job_id: Annotated[int | None, Query(ge=1)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    total, rows = list_audit(db, entity, entity_id, import_job_id, page, page_size)
    return AuditPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[AuditRead.model_validate(r) for r in rows],
    )
