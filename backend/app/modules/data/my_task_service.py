"""Blocker dan overrun oleh pelaksana task, plus deteksi overrun otomatis (DIG-34).

Yang sengaja TIDAK dijadikan aturan, karena dataset dosbim (`puti_datasets.xlsx`) tidak
mengikutinya dan aturan tebakan pernah menolak data baseline (hotfix D-08, DIG-30):

- Dari 87 kejadian blocker di dataset, hanya 2 yang task-nya berstatus blocked, dan dari 52
  task blocked hanya 2 yang punya kejadian blocker. Karena itu status task hanya diubah untuk
  blocker yang dicatat lewat modul ini, dan kejadian lama tidak dianggap "blocker aktif"
  kecuali task-nya memang sedang blocked.
- 31 dari 68 kejadian overrun bertanggal tidak sesudah `planned_finish` task-nya, jadi
  overrun manual tidak diwajibkan sudah lewat rencana.
- `requested_by` di dataset berisi jabatan (Kaur, System Analyst, ...), bukan pelaksana task.
  Kolomnya teks bebas, jadi di sini diisi nama anggota yang mencatat.

Status blocked di dataset selalu punya `actual_start` (aturan status DIG-161), sehingga
blocker pada task yang belum dimulai tetap tercatat tetapi statusnya tidak diubah.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import AppUser
from app.modules.data.change_event_detail_rules import check_detail_dates
from app.modules.data.change_event_service import next_event_id, validate_event
from app.modules.data.enums import ChangeEventType, TaskStatus
from app.modules.data.models import Assignment, ChangeEvent, Project, Resource, Task
from app.modules.data.my_task_schemas import (
    MyTaskEvent,
    MyTaskEventCreate,
    MyTaskEventResolve,
    MyTaskEventResult,
    MyTaskRead,
    MyTasks,
    OverrunDetection,
)
from app.modules.data.service import (
    ConflictError,
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
    holiday_dates,
    next_id,
)
from app.modules.data.support_models import ChangeEventDetail
from app.modules.data.workdays import next_working_day

ONE_DAY = timedelta(days=1)
CLOSED = frozenset({TaskStatus.DONE, TaskStatus.DROPPED})
# Status yang berarti task sedang dikerjakan, sehingga blocker menghentikannya.
BLOCKABLE = frozenset({TaskStatus.IN_PROGRESS, TaskStatus.IN_QA})
MEMBER_EVENTS = (ChangeEventType.BLOCKER, ChangeEventType.OVERRUN)
SYSTEM_REQUESTER = "Sistem"
EVENT_LABEL = {ChangeEventType.BLOCKER: "blocker", ChangeEventType.OVERRUN: "overrun"}


class TaskNotFoundError(NotFoundError):
    label = "Task"


class EventNotFoundError(NotFoundError):
    label = "Kejadian"


class NotTaskOwnerError(Exception):
    """Pengguna bukan pelaksana aktif task ini (403)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def is_active_assignment(assigned: date, released: date | None, on: date) -> bool:
    """Penugasan berlaku pada `on`: sudah ditugaskan dan belum dilepas."""
    return assigned <= on and (released is None or released >= on)


def status_after_blocker(status: TaskStatus) -> TaskStatus:
    """Task yang sedang dikerjakan menjadi blocked; status lain tidak disentuh."""
    return TaskStatus.BLOCKED if status in BLOCKABLE else status


def open_events(db: Session, task_ids: list[str]) -> dict[tuple[str, str], ChangeEvent]:
    """Blocker dan overrun yang belum punya `resolved_date`, terbaru per (task, jenis)."""
    if not task_ids:
        return {}
    rows = db.scalars(
        select(ChangeEvent)
        .outerjoin(ChangeEventDetail, ChangeEventDetail.event_id == ChangeEvent.event_id)
        .where(
            ChangeEvent.affected_task_id.in_(task_ids),
            ChangeEvent.event_type.in_(MEMBER_EVENTS),
            ChangeEventDetail.resolved_date.is_(None),
        )
        .order_by(ChangeEvent.event_date, ChangeEvent.event_id)
    )
    return {(event.affected_task_id, event.event_type): event for event in rows}


def open_blocker(status: TaskStatus, event: ChangeEvent | None) -> ChangeEvent | None:
    """Blocker dianggap masih aktif hanya selama task-nya berstatus blocked."""
    return event if status == TaskStatus.BLOCKED else None


def event_read(event: ChangeEvent | None) -> MyTaskEvent | None:
    if event is None:
        return None
    return MyTaskEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        event_date=event.event_date,
        requested_by=event.requested_by,
    )


def list_my_tasks(db: Session, user: AppUser, as_of: date) -> MyTasks:
    """Task yang masih ditugaskan ke pengguna dan belum selesai, paling mendesak lebih dulu."""
    if user.resource_id is None:
        return MyTasks(resource_id=None, resource_name=None, as_of=as_of, tasks=[])
    rows = db.execute(
        select(Task, Project.project_name, Assignment)
        .join(Assignment, Assignment.task_id == Task.task_id)
        .join(Project, Project.project_id == Task.project_id)
        .where(Assignment.resource_id == user.resource_id, Task.status.notin_(CLOSED))
        .order_by(Task.planned_finish, Task.task_id, Assignment.assigned_date.desc())
    ).all()
    current: dict[str, tuple[Task, str, Assignment]] = {}
    for task, project_name, assignment in rows:
        active = is_active_assignment(assignment.assigned_date, assignment.released_date, as_of)
        if active and task.task_id not in current:
            current[task.task_id] = (task, project_name, assignment)
    events = open_events(db, list(current))
    tasks = [
        MyTaskRead(
            task_id=task.task_id,
            task_name=task.task_name,
            feature_name=task.feature_name,
            project_id=task.project_id,
            project_name=project_name,
            phase=task.phase,
            status=task.status,
            priority_rank=task.priority_rank,
            planned_start=task.planned_start,
            planned_finish=task.planned_finish,
            actual_start=task.actual_start,
            role_in_task=assignment.role_in_task,
            assigned_date=assignment.assigned_date,
            is_past_plan=task.planned_finish < as_of,
            open_blocker=event_read(
                open_blocker(
                    TaskStatus(task.status), events.get((task.task_id, ChangeEventType.BLOCKER))
                )
            ),
            open_overrun=event_read(events.get((task.task_id, ChangeEventType.OVERRUN))),
        )
        for task, project_name, assignment in current.values()
    ]
    return MyTasks(
        resource_id=user.resource_id,
        resource_name=db.scalar(
            select(Resource.resource_name).where(Resource.resource_id == user.resource_id)
        ),
        as_of=as_of,
        tasks=tasks,
    )


def lock_own_task(db: Session, user: AppUser, task_id: str, on: date) -> Task:
    """Kunci task sampai commit dan pastikan pengguna pelaksana aktifnya pada tanggal `on`."""
    task = db.get(Task, task_id, with_for_update=True)
    if task is None:
        raise TaskNotFoundError(task_id)
    if user.resource_id is None:
        raise NotTaskOwnerError("Akun Anda belum dihubungkan ke data anggota tim")
    assignments = db.execute(
        select(Assignment.assigned_date, Assignment.released_date).where(
            Assignment.task_id == task_id, Assignment.resource_id == user.resource_id
        )
    ).all()
    if not any(is_active_assignment(assigned, released, on) for assigned, released in assignments):
        raise NotTaskOwnerError("Task ini tidak sedang ditugaskan kepada Anda")
    return task


def check_not_future(field: str, value: date, today: date) -> None:
    if value > today:
        raise DataValidationError(
            [FieldError(field, "Tidak boleh tanggal yang akan datang", "future_date")]
        )


def result(event: ChangeEvent, resolved: date | None, task: Task, before: str) -> MyTaskEventResult:
    return MyTaskEventResult(
        event_id=event.event_id,
        event_type=event.event_type,
        event_date=event.event_date,
        resolved_date=resolved,
        task_id=task.task_id,
        task_status=task.status,
        task_status_changed=task.status != before,
    )


def record_event(
    db: Session, user: AppUser, task_id: str, payload: MyTaskEventCreate, today: date
) -> MyTaskEventResult:
    event_date = payload.event_date or today
    check_not_future("event_date", event_date, today)
    task = lock_own_task(db, user, task_id, event_date)
    event_type = ChangeEventType(payload.event_type)
    status = TaskStatus(task.status)
    if status in CLOSED:
        state = "selesai" if status == TaskStatus.DONE else "dibatalkan"
        raise ConflictError(f"Task sudah {state}, {EVENT_LABEL[event_type]} tidak bisa dicatat")
    existing = open_events(db, [task_id]).get((task_id, event_type))
    if event_type == ChangeEventType.BLOCKER:
        existing = open_blocker(status, existing)
    if existing is not None:
        raise ConflictError(
            f"Task ini masih punya {EVENT_LABEL[event_type]} yang belum selesai "
            f"({existing.event_id}). Tandai selesai dulu sebelum mencatat yang baru."
        )
    values = {
        "event_id": next_event_id(db),
        "project_id": task.project_id,
        "event_type": event_type,
        "event_date": event_date,
        "requested_by": db.scalar(
            select(Resource.resource_name).where(Resource.resource_id == user.resource_id)
        ),
        "decision": None,
        "resolution_mode": None,
        "affected_task_id": task_id,
        "extension_days": None,
    }
    validate_event(db, values)
    event = ChangeEvent(**values)
    db.add(event)
    before = task.status
    if event_type == ChangeEventType.BLOCKER:
        # Kejadian dan status task tersimpan bersama, atau tidak sama sekali.
        task.status = status_after_blocker(status)
    commit(db)
    return result(event, None, task, before)


def resolve_event(
    db: Session,
    user: AppUser,
    task_id: str,
    event_id: str,
    payload: MyTaskEventResolve,
    today: date,
) -> MyTaskEventResult:
    resolved_date = payload.resolved_date or today
    check_not_future("resolved_date", resolved_date, today)
    task = lock_own_task(db, user, task_id, resolved_date)
    event = db.get(ChangeEvent, event_id)
    if event is None or event.affected_task_id != task_id or event.event_type not in MEMBER_EVENTS:
        raise EventNotFoundError(event_id)
    detail = db.get(ChangeEventDetail, event_id)
    if detail is not None and detail.resolved_date is not None:
        raise ConflictError(
            f"Kejadian {event_id} sudah ditandai selesai pada {detail.resolved_date.isoformat()}"
        )
    errors = check_detail_dates(
        event.event_date, detail.approved_date if detail else None, resolved_date
    )
    errors = [error for error in errors if error.field == "resolved_date"]
    if errors:
        raise DataValidationError(errors)
    if detail is None:
        db.add(ChangeEventDetail(event_id=event_id, resolved_date=resolved_date))
    else:
        detail.resolved_date = resolved_date
    before = task.status
    if event.event_type == ChangeEventType.BLOCKER and task.status == TaskStatus.BLOCKED:
        db.flush()
        if open_events(db, [task_id]).get((task_id, ChangeEventType.BLOCKER)) is None:
            # Status sebelum blocker tidak tersimpan di mana pun (belum ada audit_log), jadi
            # task kembali ke in_progress. Task blocked selalu punya actual_start.
            task.status = TaskStatus.IN_PROGRESS
    commit(db)
    return result(event, resolved_date, task, before)


def detect_overruns(db: Session, as_of: date, dry_run: bool = False) -> OverrunDetection:
    """Buat kejadian overrun untuk task yang lewat `planned_finish` dan belum punya (DIG-154).

    Aman dijalankan berulang: task yang sudah punya kejadian overrun dilewati, begitu juga
    task done dan dropped. Tanggal kejadian = hari kerja pertama sesudah `planned_finish`,
    yaitu hari task itu mulai melewati rencana.

    `dry_run` hanya menghitung. Pakai itu dulu pada data lama: di dataset dosbim perintah ini
    membuat 500 lebih kejadian sekaligus, lebih banyak dari seluruh isi D-10 sebelumnya.
    """
    has_overrun = select(ChangeEvent.event_id).where(
        ChangeEvent.affected_task_id == Task.task_id,
        ChangeEvent.event_type == ChangeEventType.OVERRUN,
    )
    rows = db.execute(
        select(Task.task_id, Task.project_id, Task.planned_finish, Project.start_date)
        .join(Project, Project.project_id == Task.project_id)
        .where(
            Task.status.notin_(CLOSED),
            Task.planned_finish < as_of,
            ~has_overrun.exists(),
        )
        .order_by(Task.planned_finish, Task.task_id)
        .with_for_update(of=Task)
    ).all()
    task_ids = [row.task_id for row in rows]
    if dry_run:
        db.rollback()  # lepaskan kunci baris
        return OverrunDetection(
            as_of=as_of, dry_run=True, created_count=len(rows), task_ids=task_ids, event_ids=[]
        )
    holidays = holiday_dates(db)
    ids = list(db.scalars(select(ChangeEvent.event_id)))
    created: list[str] = []
    for task_id, project_id, planned_finish, project_start in rows:
        started = min(next_working_day(planned_finish + ONE_DAY, holidays), as_of)
        event_id = next_id(ids, "EVT")
        ids.append(event_id)
        db.add(
            ChangeEvent(
                event_id=event_id,
                project_id=project_id,
                event_type=ChangeEventType.OVERRUN,
                event_date=max(started, project_start),
                requested_by=SYSTEM_REQUESTER,
                affected_task_id=task_id,
            )
        )
        created.append(event_id)
    commit(db)
    return OverrunDetection(
        as_of=as_of, dry_run=False, created_count=len(created), task_ids=task_ids, event_ids=created
    )
