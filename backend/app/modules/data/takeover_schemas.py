"""Schema API pengalihan task saat anggota tidak hadir (DIG-35: DIG-157, DIG-158, DIG-159).

Dipisah dari `schemas.py` supaya PR modul Data yang berjalan paralel tidak saling bentrok.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.data.enums import TaskStatus
from app.modules.data.schemas import IsoDate, ResourceId

RoleMatch = Literal["primary", "secondary", "cross"]


class AssignmentRead(BaseModel):
    assignment_id: str
    task_id: str
    resource_id: str
    resource_name: str
    role_in_task: str
    assigned_date: date
    released_date: date | None
    is_takeover: bool


class ReplacementCandidate(BaseModel):
    resource_id: str
    resource_name: str
    primary_role_id: str
    seniority: str
    match: RoleMatch = Field(
        description=(
            "primary: peran utama sama dengan peran task; secondary: peran rangkap; "
            "cross: tidak memegang peran itu tetapi cross_role_capable"
        )
    )
    active_assignments: int = Field(description="Penugasan yang belum dilepas (released_date)")


class TakeoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_resource_id: ResourceId
    to_resource_id: ResourceId
    takeover_date: IsoDate


class TakeoverResult(BaseModel):
    released: AssignmentRead = Field(description="Penugasan lama yang ditutup")
    created: AssignmentRead = Field(description="Penugasan baru dengan is_takeover = true")


class AffectedTask(BaseModel):
    task_id: str
    task_name: str
    project_id: str
    project_name: str
    status: TaskStatus
    required_role_id: str
    planned_start: date
    planned_finish: date
    assignment_id: str
