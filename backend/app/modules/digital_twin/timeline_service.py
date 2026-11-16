"""Data Gantt rencana vs aktual untuk tab Timeline (DIG-41, DIG-177).

Aturan keterlambatan (dites di DIG-180):
- Task selesai (done) terlambat bila `actual_finish` setelah `planned_finish`.
- Task yang belum selesai terlambat bila tanggal acuan (`as_of`, bawaan hari ini) sudah
  melewati `planned_finish`. Task dropped tidak pernah dihitung terlambat.
- `delay_days` menghitung hari kalender, `delay_working_days` hanya hari kerja (Senin sampai
  Jumat di luar D-11 holidays). Di dataset dosbim banyak `planned_finish` jatuh pada akhir
  pekan, jadi task bisa terlambat secara kalender dengan 0 hari kerja.
"""

from collections import defaultdict
from collections.abc import Collection
from datetime import date, timedelta
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.enums import TaskPhase, TaskStatus
from app.modules.data.models import Assignment, ChangeEvent, Holiday, Project, Resource, Task
from app.modules.data.workdays import count_working_days
from app.modules.digital_twin.timeline_schemas import (
    TimelineEvent,
    TimelineHoliday,
    TimelinePhase,
    TimelineProject,
    TimelineResponse,
    TimelineTask,
)

ONE_DAY = timedelta(days=1)
PHASE_ORDER = {phase: index for index, phase in enumerate(TaskPhase)}


class Delay(NamedTuple):
    is_late: bool
    days: int
    working_days: int


NOT_LATE = Delay(False, 0, 0)


def task_delay(
    status: TaskStatus | str,
    planned_finish: date,
    actual_finish: date | None,
    as_of: date,
    holidays: Collection[date] = (),
) -> Delay:
    """Keterlambatan satu task terhadap `planned_finish`, tanpa menyentuh basis data."""
    status = TaskStatus(status)
    if status == TaskStatus.DROPPED:
        return NOT_LATE
    # Task done tanpa actual_finish (data lama yang tidak lengkap) dinilai seperti belum selesai.
    reference = actual_finish if status == TaskStatus.DONE and actual_finish else as_of
    if reference <= planned_finish:
        return NOT_LATE
    return Delay(
        True,
        (reference - planned_finish).days,
        count_working_days(planned_finish + ONE_DAY, reference, holidays),
    )


def build_timeline(
    db: Session,
    as_of: date,
    project_id: str | None = None,
    resource_id: str | None = None,
) -> TimelineResponse:
    task_query = select(Task).order_by(Task.planned_start, Task.task_id)
    if project_id is not None:
        task_query = task_query.where(Task.project_id == project_id)
    if resource_id is not None:
        # Semua task yang pernah ditugaskan ke anggota ini, termasuk yang sudah dialihkan.
        assigned = select(Assignment.task_id).where(Assignment.resource_id == resource_id)
        task_query = task_query.where(Task.task_id.in_(assigned))
    tasks = list(db.scalars(task_query))
    task_ids = {task.task_id for task in tasks}

    holidays = list(db.scalars(select(Holiday).order_by(Holiday.holiday_date)))
    holiday_dates = {holiday.holiday_date for holiday in holidays}

    assignees: dict[str, list[str]] = defaultdict(list)
    if tasks:
        rows = db.execute(
            select(Assignment.task_id, Resource.resource_name)
            .join(Resource, Resource.resource_id == Assignment.resource_id)
            .where(Assignment.released_date.is_(None), Assignment.task_id.in_(task_ids))
            .order_by(Assignment.assigned_date, Assignment.assignment_id)
        )
        for task_id, name in rows:
            assignees[task_id].append(name)

    by_project: dict[str, dict[TaskPhase, list[TimelineTask]]] = defaultdict(
        lambda: defaultdict(list)
    )
    dates: list[date] = []
    for task in tasks:
        delay = task_delay(
            task.status, task.planned_finish, task.actual_finish, as_of, holiday_dates
        )
        by_project[task.project_id][TaskPhase(task.phase)].append(
            TimelineTask(
                task_id=task.task_id,
                task_name=task.task_name,
                feature_name=task.feature_name,
                required_role_id=task.required_role_id,
                status=task.status,
                planned_start=task.planned_start,
                planned_finish=task.planned_finish,
                actual_start=task.actual_start,
                actual_finish=task.actual_finish,
                is_late=delay.is_late,
                delay_days=delay.days,
                delay_working_days=delay.working_days,
                assignees=assignees.get(task.task_id, []),
            )
        )
        dates += [task.planned_start, task.planned_finish]
        dates += [d for d in (task.actual_start, task.actual_finish) if d is not None]

    project_query = select(Project).order_by(Project.priority_rank, Project.project_id)
    if project_id is not None:
        project_query = project_query.where(Project.project_id == project_id)
    projects = []
    for project in db.scalars(project_query):
        phases = by_project.get(project.project_id, {})
        if not phases and (resource_id is not None or project_id is None):
            continue  # proyek tanpa task yang cocok tidak ditampilkan
        items = [task for group in phases.values() for task in group]
        projects.append(
            TimelineProject(
                project_id=project.project_id,
                project_name=project.project_name,
                priority_rank=project.priority_rank,
                status=project.status,
                start_date=project.start_date,
                target_launch_date=project.target_launch_date,
                actual_launch_date=project.actual_launch_date,
                task_count=len(items),
                late_count=sum(task.is_late for task in items),
                phases=[
                    TimelinePhase(phase=phase, tasks=phases[phase])
                    for phase in sorted(phases, key=PHASE_ORDER.__getitem__)
                ],
            )
        )

    shown = {project.project_id for project in projects}
    events = []
    if shown:
        event_query = (
            select(ChangeEvent)
            .where(ChangeEvent.project_id.in_(shown))
            .order_by(ChangeEvent.event_date, ChangeEvent.event_id)
        )
        if resource_id is not None:
            event_query = event_query.where(ChangeEvent.affected_task_id.in_(task_ids))
        events = [
            TimelineEvent(
                event_id=event.event_id,
                project_id=event.project_id,
                event_type=event.event_type,
                event_date=event.event_date,
                affected_task_id=event.affected_task_id,
            )
            for event in db.scalars(event_query)
        ]

    start, end = (min(dates), max(dates)) if dates else (None, None)
    return TimelineResponse(
        as_of=as_of,
        range_start=start,
        range_end=end,
        projects=projects,
        events=events,
        holidays=[
            TimelineHoliday(holiday_date=h.holiday_date, holiday_name=h.holiday_name)
            for h in holidays
            if start is not None and start <= h.holiday_date <= end
        ],
    )
