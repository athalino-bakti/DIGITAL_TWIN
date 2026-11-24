"""Schema kartu ringkasan baseline di halaman Digital Twin (DIG-40, DIG-175)."""

from datetime import date

from pydantic import BaseModel, Field

from app.modules.data.enums import ProjectStatus


class ActiveProject(BaseModel):
    project_id: str
    project_name: str
    status: ProjectStatus
    priority_rank: int
    target_launch_date: date


class LateProject(ActiveProject):
    projected_finish: date = Field(description="Proyeksi selesai, lihat aturan di endpoint")
    days_late: int = Field(description="Hari kalender dari target_launch_date ke proyeksi")
    open_tasks: int
    late_open_tasks: int = Field(description="Task belum ditutup yang sudah lewat planned_finish")


class MultiRoleResource(BaseModel):
    resource_id: str
    resource_name: str
    primary_role_id: str
    secondary_role_ids: list[str]
    other_active_roles: list[str] = Field(
        description=(
            "role_in_task berbeda dari peran utama pada penugasan aktif task yang belum ditutup"
        )
    )


class ProjectCard(BaseModel):
    count: int
    items: list[ActiveProject]


class LateProjectCard(BaseModel):
    count: int
    items: list[LateProject]


class MultiRoleCard(BaseModel):
    count: int
    items: list[MultiRoleResource]


class PendingCard(BaseModel):
    """Kartu yang datanya belum bisa dihitung."""

    count: None = None
    reason: str


class BaselineSummary(BaseModel):
    as_of: date
    active_projects: ProjectCard
    late_projects: LateProjectCard
    overloaded_resources: PendingCard
    multi_role_resources: MultiRoleCard
