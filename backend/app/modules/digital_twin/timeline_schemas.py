"""Schema API Gantt rencana vs aktual, tab Timeline (DIG-41, DIG-177)."""

from datetime import date

from pydantic import BaseModel, Field

from app.modules.data.enums import ChangeEventType, ProjectStatus, TaskPhase, TaskStatus


class TimelineTask(BaseModel):
    task_id: str
    task_name: str
    feature_name: str
    required_role_id: str
    status: TaskStatus
    planned_start: date
    planned_finish: date
    actual_start: date | None
    actual_finish: date | None
    is_late: bool = Field(
        description="Selesai setelah planned_finish, atau belum selesai lewat itu"
    )
    delay_days: int = Field(
        description="Hari kalender lewat planned_finish, 0 bila tidak terlambat"
    )
    delay_working_days: int = Field(description="Hari kerja lewat planned_finish (tanpa libur)")
    assignees: list[str] = Field(description="Nama pelaksana aktif (released_date kosong)")


class TimelinePhase(BaseModel):
    phase: TaskPhase
    tasks: list[TimelineTask]


class TimelineProject(BaseModel):
    project_id: str
    project_name: str
    priority_rank: int
    status: ProjectStatus
    start_date: date
    target_launch_date: date
    actual_launch_date: date | None
    task_count: int
    late_count: int
    phases: list[TimelinePhase]


class TimelineEvent(BaseModel):
    event_id: str
    project_id: str
    event_type: ChangeEventType
    event_date: date
    affected_task_id: str | None


class TimelineHoliday(BaseModel):
    holiday_date: date
    holiday_name: str


class TimelineResponse(BaseModel):
    as_of: date = Field(description="Tanggal acuan untuk task yang belum selesai")
    range_start: date | None = Field(description="Tanggal paling awal di antara semua batang")
    range_end: date | None
    projects: list[TimelineProject]
    events: list[TimelineEvent]
    holidays: list[TimelineHoliday]
