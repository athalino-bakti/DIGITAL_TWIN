"""Schema API D-05 tasks: daftar dan pembaruan status task (DIG-36, DIG-161).

Dipisah dari `schemas.py` supaya PR modul Data yang berjalan paralel tidak saling bentrok.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.modules.data.enums import TaskPhase, TaskStatus
from app.modules.data.schemas import IsoDate


class TaskRead(BaseModel):
    task_id: str
    project_id: str
    project_name: str
    feature_name: str
    task_name: str
    required_role_id: str
    complexity_id: str
    priority_rank: int
    estimated_days: float
    phase: TaskPhase
    planned_start: date
    planned_finish: date
    actual_start: date | None
    actual_finish: date | None
    status: TaskStatus
    qa_reject_count: int
    dod_fulfilled: bool


class TaskStatusUpdate(BaseModel):
    """Body PATCH status task. Hanya kolom yang dikirim yang diubah.

    Kolom lain D-05 (jadwal rencana, estimasi, prioritas) berasal dari impor Project Plan,
    jadi tidak diubah lewat endpoint ini.
    """

    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    actual_start: IsoDate | None = None
    actual_finish: IsoDate | None = None
    dod_fulfilled: bool | None = Field(default=None, strict=True)
