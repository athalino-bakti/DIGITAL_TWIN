"""Endpoint event log (DIG-165, story DIG-37).

Dipasang di router modul Data, sehingga path-nya berawalan /data. Izin mengikuti matriks RBAC:
membentuk ulang termasuk pengolahan data impor (import:run), sedangkan membaca event log mentah
sama dengan mengekspornya (event_log:export, FR-07). Process Map (DIG-38) memakai endpoint
sendiri dengan baseline:read.
"""

from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data import event_log as service
from app.modules.data.enums import PROJECT_ID_PATTERN, TASK_ID_PATTERN

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


class EventLogReportRead(BaseModel):
    events: int
    cases: int
    by_source: dict[str, int]
    by_kind: dict[str, int]
    cases_not_in_tasks: int
    events_without_resource: int
    skipped: dict[str, int]


class EventLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    case_id: str
    project_id: str | None
    activity: str
    activity_kind: str
    event_time: datetime
    resource_id: str | None
    actor_source_id: str | None
    actor_name: str | None
    source: str
    source_ref: str


@router.post(
    "/event-log/rebuild",
    response_model=EventLogReportRead,
    dependencies=[Depends(require_permission(Perm.IMPORT_RUN))],
    summary="Bentuk ulang event log dari staging Trello dan change_events",
)
def rebuild_event_log(db: Db) -> EventLogReportRead:
    """Isi event_log dihapus lalu dibentuk ulang seluruhnya; aman diulang."""
    return EventLogReportRead(**asdict(service.rebuild_event_log(db)))


@router.get(
    "/event-log",
    response_model=list[EventLogRead],
    dependencies=[Depends(require_permission(Perm.EVENT_LOG_EXPORT))],
    summary="Daftar event per case (task), bisa difilter proyek dan rentang tanggal",
)
def list_event_log(
    db: Db,
    project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    case_id: Annotated[str | None, Query(pattern=TASK_ID_PATTERN)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[EventLogRead]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["query", "date_to"],
                    "msg": "Tanggal akhir tidak boleh sebelum tanggal awal",
                    "type": "date_order",
                }
            ],
        )
    return [
        EventLogRead.model_validate(e)
        for e in service.list_event_log(db, project_id, case_id, date_from, date_to)
    ]
