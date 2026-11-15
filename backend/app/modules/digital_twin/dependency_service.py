"""Graf dependency, jalur kritis, dan dampak keterlambatan satu proyek (DIG-42, DIG-182)."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.enums import DependencyType, TaskStatus
from app.modules.data.models import Holiday, Project, Task, TaskDependency
from app.modules.data.service import DataValidationError, FieldError, NotFoundError
from app.modules.data.workdays import count_working_days
from app.modules.digital_twin.cpm import (
    EPSILON,
    CycleError,
    Edge,
    Schedule,
    critical_path,
    propagate_delay,
)
from app.modules.digital_twin.dependency_schemas import (
    DependencyEdge,
    DependencyFocus,
    DependencyGraph,
    DependencyNode,
)

ONE_DAY = timedelta(days=1)
FINISHED = (TaskStatus.DONE, TaskStatus.DROPPED)
NO_SCHEDULE = Schedule(0.0, 0.0, 0.0, 0.0)


class ProjectNotFoundError(NotFoundError):
    label = "Proyek"


def working_delay(task: Task, as_of: date, holidays: set[date]) -> int | None:
    """Hari kerja lewat planned_finish, atau None bila task tidak terlambat.

    Aturannya sama dengan Gantt (DIG-177): task done dinilai dari actual_finish, task lain
    dari tanggal acuan, dan task dropped tidak pernah terlambat.
    """
    if task.status == TaskStatus.DROPPED:
        return None
    done = task.status == TaskStatus.DONE and task.actual_finish is not None
    reference = task.actual_finish if done else as_of
    if reference <= task.planned_finish:
        return None
    return count_working_days(task.planned_finish + ONE_DAY, reference, holidays)


def build_dependency_graph(
    db: Session,
    project_id: str,
    as_of: date,
    focus_task_id: str | None = None,
    delay_days: float | None = None,
) -> DependencyGraph:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)
    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)))
    by_id = {task.task_id: task for task in tasks}
    if focus_task_id is not None and focus_task_id not in by_id:
        raise DataValidationError(
            [
                FieldError(
                    "task_id",
                    f"Task {focus_task_id} tidak ada di proyek {project_id}",
                    "task_not_in_project",
                )
            ]
        )

    rows = list(
        db.scalars(
            select(TaskDependency)
            .where(TaskDependency.task_id.in_(by_id), TaskDependency.depends_on_task_id.in_(by_id))
            .order_by(TaskDependency.dependency_id)
        )
    )
    edges = [
        Edge(
            row.depends_on_task_id,
            row.task_id,
            row.dependency_type == DependencyType.HARD,
            row.propagation_factor,
        )
        for row in rows
    ]
    holidays = set(db.scalars(select(Holiday.holiday_date)))
    delays = {task.task_id: working_delay(task, as_of, holidays) for task in tasks}

    cycle: list[str] = []
    try:
        schedules = critical_path({task.task_id: task.estimated_days for task in tasks}, edges)
    except CycleError as exc:
        schedules, cycle = {}, exc.task_ids

    impact: dict[str, float] = {}
    focus = None
    if focus_task_id is not None:
        delay = float(delays[focus_task_id] or 0) if delay_days is None else delay_days
        finished = {task.task_id for task in tasks if task.status in FINISHED}
        try:
            impact = propagate_delay(focus_task_id, delay, edges, finished)
        except CycleError as exc:
            cycle = sorted(set(cycle) | set(exc.task_ids))
        focus = DependencyFocus(task_id=focus_task_id, delay_days=delay, affected_count=len(impact))

    nodes = []
    for task in sorted(tasks, key=lambda t: (t.planned_start, t.task_id)):
        schedule = schedules.get(task.task_id, NO_SCHEDULE)
        nodes.append(
            DependencyNode(
                task_id=task.task_id,
                task_name=task.task_name,
                feature_name=task.feature_name,
                phase=task.phase,
                status=task.status,
                estimated_days=task.estimated_days,
                planned_start=task.planned_start,
                planned_finish=task.planned_finish,
                earliest_start=round(schedule.earliest_start, 2),
                earliest_finish=round(schedule.earliest_finish, 2),
                latest_start=round(schedule.latest_start, 2),
                latest_finish=round(schedule.latest_finish, 2),
                total_float=round(schedule.total_float, 2),
                is_critical=task.task_id in schedules and schedule.is_critical,
                is_late=delays[task.task_id] is not None,
                delay_working_days=delays[task.task_id] or 0,
                impact_days=round(impact[task.task_id], 2) if task.task_id in impact else None,
            )
        )

    def on_critical_path(edge: Edge) -> bool:
        before, after = schedules.get(edge.depends_on), schedules.get(edge.task_id)
        return (
            edge.hard
            and before is not None
            and after is not None
            and before.is_critical
            and after.is_critical
            and abs(before.earliest_finish - after.earliest_start) <= EPSILON
        )

    critical = sorted(
        (task_id for task_id, schedule in schedules.items() if schedule.is_critical),
        key=lambda task_id: (schedules[task_id].earliest_start, task_id),
    )
    return DependencyGraph(
        project_id=project.project_id,
        project_name=project.project_name,
        as_of=as_of,
        project_duration=round(
            max((s.earliest_finish for s in schedules.values()), default=0.0), 2
        ),
        critical_task_ids=critical,
        cycle_task_ids=cycle,
        focus=focus,
        nodes=nodes,
        edges=[
            DependencyEdge(
                dependency_id=row.dependency_id,
                depends_on_task_id=row.depends_on_task_id,
                task_id=row.task_id,
                dependency_type=row.dependency_type,
                propagation_factor=row.propagation_factor,
                is_critical=on_critical_path(edge),
            )
            for row, edge in zip(rows, edges, strict=True)
        ],
    )
