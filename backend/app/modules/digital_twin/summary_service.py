"""Kartu ringkasan baseline (DIG-40, DIG-175).

Aturan, mengikuti AC DIG-40:
- Proyek aktif: status planning, development, atau testing.
- Proyek lewat target: proyek aktif yang proyeksi selesainya melewati target_launch_date.
  Proyeksi selesai = tanggal paling akhir dari task proyek itu yang tidak dropped: actual_finish
  untuk task done, planned_finish untuk task lain, atau tanggal acuan bila task itu belum ditutup
  dan sudah lewat planned_finish (task itu paling cepat selesai hari ini). Ini asumsi tim; belum
  memakai rambatan dependency (DIG-42) atau sisa durasi task.
- Resource overload: RLI > 1 pada minggu berjalan. Formula RLI belum final (DIG-186) dan
  service-nya belum ada (DIG-187), jadi kartu ini dikembalikan tanpa angka beserta alasannya.
- Resource multi-role: secondary_role_ids tidak kosong, atau sedang menjalankan role_in_task
  berbeda dari primary_role_id pada penugasan aktif task yang belum ditutup.

Dicek terhadap dataset dosbim: 9 proyek aktif, 22 dari 40 anggota multi-role (22 punya peran
rangkap; 19 juga sedang menjalankan peran lain, semuanya termasuk 22 itu).
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.enums import ProjectStatus, TaskStatus
from app.modules.data.models import Assignment, Project, Resource, Task
from app.modules.data.service import split_role_ids
from app.modules.digital_twin.summary_schemas import (
    ActiveProject,
    BaselineSummary,
    LateProject,
    LateProjectCard,
    MultiRoleCard,
    MultiRoleResource,
    PendingCard,
    ProjectCard,
)

ACTIVE = (ProjectStatus.PLANNING, ProjectStatus.DEVELOPMENT, ProjectStatus.TESTING)
CLOSED = (TaskStatus.DONE, TaskStatus.DROPPED)
RLI_PENDING = (
    "Menunggu perhitungan Resource Load Index (DIG-187); formula RLI belum final (DIG-186)."
)


def task_end(status: str, planned_finish: date, actual_finish: date | None, as_of: date) -> date:
    """Tanggal selesai satu task untuk proyeksi proyek."""
    if status == TaskStatus.DONE:
        return actual_finish or planned_finish
    return max(planned_finish, as_of)


def projected_finish(tasks: list[tuple[str, date, date | None]], as_of: date) -> date | None:
    """Proyeksi selesai proyek dari (status, planned_finish, actual_finish) task-tasknya."""
    ends = [
        task_end(status, planned, actual, as_of)
        for status, planned, actual in tasks
        if status != TaskStatus.DROPPED
    ]
    return max(ends, default=None)


def build_summary(db: Session, as_of: date) -> BaselineSummary:
    projects = list(
        db.scalars(
            select(Project)
            .where(Project.status.in_(ACTIVE))
            .order_by(Project.priority_rank, Project.project_id)
        )
    )
    active = [
        ActiveProject(
            project_id=p.project_id,
            project_name=p.project_name,
            status=p.status,
            priority_rank=p.priority_rank,
            target_launch_date=p.target_launch_date,
        )
        for p in projects
    ]

    tasks: dict[str, list[tuple[str, date, date | None]]] = defaultdict(list)
    for project_id, status, planned, actual in db.execute(
        select(Task.project_id, Task.status, Task.planned_finish, Task.actual_finish).where(
            Task.project_id.in_([p.project_id for p in projects])
        )
    ):
        tasks[project_id].append((status, planned, actual))

    late: list[LateProject] = []
    for project in active:
        rows = tasks.get(project.project_id, [])
        finish = projected_finish(rows, as_of)
        if finish is None or finish <= project.target_launch_date:
            continue
        open_rows = [r for r in rows if r[0] not in CLOSED]
        late.append(
            LateProject(
                **project.model_dump(),
                projected_finish=finish,
                days_late=(finish - project.target_launch_date).days,
                open_tasks=len(open_rows),
                late_open_tasks=sum(1 for _, planned, _ in open_rows if planned < as_of),
            )
        )
    late.sort(key=lambda p: (-p.days_late, p.priority_rank, p.project_id))

    other_roles: dict[str, set[str]] = defaultdict(set)
    for resource_id, role, primary in db.execute(
        select(Assignment.resource_id, Assignment.role_in_task, Resource.primary_role_id)
        .join(Task, Task.task_id == Assignment.task_id)
        .join(Resource, Resource.resource_id == Assignment.resource_id)
        .where(
            Task.status.notin_(CLOSED),
            Assignment.assigned_date <= as_of,
            (Assignment.released_date.is_(None)) | (Assignment.released_date >= as_of),
        )
    ):
        if role != primary:
            other_roles[resource_id].add(role)

    multi: list[MultiRoleResource] = []
    for resource in db.scalars(select(Resource).order_by(Resource.resource_id)):
        secondary = split_role_ids(resource.secondary_role_ids)
        others = sorted(other_roles.get(resource.resource_id, set()))
        if secondary or others:
            multi.append(
                MultiRoleResource(
                    resource_id=resource.resource_id,
                    resource_name=resource.resource_name,
                    primary_role_id=resource.primary_role_id,
                    secondary_role_ids=secondary,
                    other_active_roles=others,
                )
            )

    return BaselineSummary(
        as_of=as_of,
        active_projects=ProjectCard(count=len(active), items=active),
        late_projects=LateProjectCard(count=len(late), items=late),
        overloaded_resources=PendingCard(reason=RLI_PENDING),
        multi_role_resources=MultiRoleCard(count=len(multi), items=multi),
    )
