"""Schema API D-10 change_events, pencatatan kejadian perubahan (DIG-33, DIG-149).

Dipisah dari `schemas.py` supaya PR modul Data yang berjalan paralel tidak saling bentrok.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.data.enums import (
    EVENT_ID_PATTERN,
    TASK_ID_PATTERN,
    ChangeEventType,
    Decision,
    ResolutionMode,
    TaskStatus,
)
from app.modules.data.schemas import IsoDate, ProjectId, reject_nul

EventId = Annotated[str, StringConstraints(pattern=EVENT_ID_PATTERN)]
TaskId = Annotated[str, StringConstraints(pattern=TASK_ID_PATTERN)]
RequestedBy = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(reject_nul),
]
# Batas atas hanya penjaga nilai tidak masuk akal; dataset dosbim paling lama 5 hari.
ExtensionDays = Annotated[float, Field(ge=0, le=365, allow_inf_nan=False)]


class ChangeEventFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: ProjectId
    event_type: ChangeEventType
    event_date: IsoDate
    requested_by: RequestedBy | None = None
    decision: Decision | None = None
    resolution_mode: ResolutionMode | None = None
    affected_task_id: TaskId | None = None
    extension_days: ExtensionDays | None = None


class TaskEffect(BaseModel):
    """Efek samping ke task terdampak, disimpan bersama kejadiannya (DIG-150).

    Sengaja eksplisit: di dataset dosbim tidak ada pola tetap antara keputusan CR dan status
    task, jadi sistem tidak menebak. Pencatat yang memilih apa yang terjadi pada task.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["on_hold", "dropped"] | None = Field(
        default=None, description="Task ditunda (on_hold) atau dibatalkan (dropped)"
    )
    priority_rank: int | None = Field(default=None, ge=1, le=999, strict=True)


class ChangeEventCreate(ChangeEventFields):
    """Body POST. `event_id` boleh dikosongkan; server mengisi EVT-xxx berikutnya."""

    event_id: EventId | None = None
    task_effect: TaskEffect | None = None


class ChangeEventUpdate(BaseModel):
    """Body PATCH. Hanya kolom yang dikirim yang diubah; ID tidak bisa diubah."""

    model_config = ConfigDict(extra="forbid")

    project_id: ProjectId | None = None
    event_type: ChangeEventType | None = None
    event_date: IsoDate | None = None
    requested_by: RequestedBy | None = None
    decision: Decision | None = None
    resolution_mode: ResolutionMode | None = None
    affected_task_id: TaskId | None = None
    extension_days: ExtensionDays | None = None


class ChangeEventRead(BaseModel):
    event_id: str
    project_id: str
    project_name: str
    event_type: ChangeEventType
    event_date: date
    requested_by: str | None
    decision: Decision | None
    resolution_mode: ResolutionMode | None
    affected_task_id: str | None
    affected_task_name: str | None
    affected_task_status: TaskStatus | None = Field(description="Status task saat ini")
    affected_task_priority_rank: int | None = Field(description="Prioritas task saat ini")
    extension_days: float | None
