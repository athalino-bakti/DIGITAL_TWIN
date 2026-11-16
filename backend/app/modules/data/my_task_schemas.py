"""Schema API "task saya": blocker dan overrun oleh pelaksana task (DIG-34, DIG-153)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.data.enums import ChangeEventType, TaskPhase, TaskStatus
from app.modules.data.schemas import IsoDate


class MyTaskEvent(BaseModel):
    """Blocker atau overrun yang masih terbuka pada satu task."""

    event_id: str
    event_type: ChangeEventType
    event_date: date
    requested_by: str | None


class MyTaskRead(BaseModel):
    task_id: str
    task_name: str
    feature_name: str
    project_id: str
    project_name: str
    phase: TaskPhase
    status: TaskStatus
    priority_rank: int
    planned_start: date
    planned_finish: date
    actual_start: date | None
    role_in_task: str
    assigned_date: date
    is_past_plan: bool = Field(description="Belum selesai dan sudah lewat planned_finish")
    open_blocker: MyTaskEvent | None = Field(
        description="Blocker yang belum selesai; hanya ada selama task berstatus blocked"
    )
    open_overrun: MyTaskEvent | None = Field(description="Overrun yang belum ditandai selesai")


class MyTasks(BaseModel):
    resource_id: str | None = Field(description="Kosong bila akun belum dihubungkan ke anggota")
    resource_name: str | None
    as_of: date
    tasks: list[MyTaskRead]


class MyTaskEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["blocker", "overrun"]
    event_date: IsoDate | None = Field(default=None, description="Bawaan hari ini")


class MyTaskEventResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_date: IsoDate | None = Field(default=None, description="Bawaan hari ini")


class MyTaskEventResult(BaseModel):
    event_id: str
    event_type: ChangeEventType
    event_date: date
    resolved_date: date | None
    task_id: str
    task_status: TaskStatus = Field(description="Status task sesudah kejadian disimpan")
    task_status_changed: bool


class OverrunDetection(BaseModel):
    as_of: date
    dry_run: bool = Field(description="True: hanya menghitung, tidak ada yang disimpan")
    created_count: int = Field(description="Jumlah kejadian yang dibuat (atau akan dibuat)")
    task_ids: list[str] = Field(description="Task yang lewat rencana dan belum punya overrun")
    event_ids: list[str] = Field(description="Kosong pada dry run")
