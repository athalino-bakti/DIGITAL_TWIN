"""Pengalihan task saat anggota tidak hadir (DIG-35).

- DIG-157: task yang terdampak oleh catatan ketidakhadiran (D-09). Pencatatan izin mendadak
  dan rotasi sendiri memakai endpoint /availability yang sudah ada (is_known_at_planning
  bawaan false).
- DIG-159: kandidat pengganti untuk sebuah task.
- DIG-158: pengalihan dalam satu transaksi: penugasan lama ditutup (released_date) dan
  penugasan baru dibuat dengan is_takeover = true.

Aturan kandidat mengikuti dataset dosbim (`puti_datasets.xlsx`): `role_in_task` selalu sama
dengan `required_role_id` task (1.380 dari 1.380 penugasan), dan ke-180 penugasan takeover
dijalankan anggota yang memegang peran itu sebagai peran utama (20), peran rangkap (20), atau
yang `cross_role_capable` (140). Data lama tidak diperiksa ulang di sini; aturan hanya berlaku
untuk pengalihan baru lewat endpoint ini.
"""

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.data.enums import TaskStatus
from app.modules.data.models import Assignment, Availability, Project, Resource, Task
from app.modules.data.service import (
    ABSENT_TYPES,
    AvailabilityNotFoundError,
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
    next_id,
    split_role_ids,
)
from app.modules.data.takeover_schemas import (
    AffectedTask,
    AssignmentRead,
    ReplacementCandidate,
    RoleMatch,
    TakeoverRequest,
    TakeoverResult,
)

CLOSED_TASK_STATUSES = (TaskStatus.DONE, TaskStatus.DROPPED)
MATCH_ORDER = {"primary": 0, "secondary": 1, "cross": 2}


class TaskNotFoundError(NotFoundError):
    label = "Task"


def get_task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


def role_match(resource: Resource, role_id: str) -> RoleMatch | None:
    if resource.primary_role_id == role_id:
        return "primary"
    if role_id in split_role_ids(resource.secondary_role_ids):
        return "secondary"
    if resource.cross_role_capable:
        return "cross"
    return None


def absent_on(db: Session, resource_id: str, day: date) -> Availability | None:
    query = select(Availability).where(
        Availability.resource_id == resource_id,
        Availability.absence_type.in_(ABSENT_TYPES),
        Availability.date_start <= day,
        Availability.date_end >= day,
    )
    return db.scalars(query.limit(1)).first()


def _assignment_read(assignment: Assignment, resource_name: str) -> AssignmentRead:
    return AssignmentRead(
        assignment_id=assignment.assignment_id,
        task_id=assignment.task_id,
        resource_id=assignment.resource_id,
        resource_name=resource_name,
        role_in_task=assignment.role_in_task,
        assigned_date=assignment.assigned_date,
        released_date=assignment.released_date,
        is_takeover=assignment.is_takeover,
    )


def list_task_assignments(db: Session, task_id: str) -> list[AssignmentRead]:
    """Riwayat penugasan sebuah task, urut tanggal ditugaskan."""
    get_task(db, task_id)
    query = (
        select(Assignment, Resource.resource_name)
        .join(Resource, Resource.resource_id == Assignment.resource_id)
        .where(Assignment.task_id == task_id)
        .order_by(Assignment.assigned_date, Assignment.assignment_id)
    )
    return [_assignment_read(a, name) for a, name in db.execute(query)]


def replacement_candidates(db: Session, task_id: str, on: date) -> list[ReplacementCandidate]:
    """Anggota yang bisa mengambil alih task pada tanggal `on`.

    Tidak termasuk: pelaksana aktif task itu, anggota yang tidak hadir pada tanggal itu, dan
    anggota yang belum bergabung. Urutan: peran utama, peran rangkap, lalu lintas peran;
    di dalamnya yang penugasan aktifnya paling sedikit lebih dulu.
    """
    task = get_task(db, task_id)
    active_on_task = set(
        db.scalars(
            select(Assignment.resource_id).where(
                Assignment.task_id == task_id, Assignment.released_date.is_(None)
            )
        )
    )
    absent = set(
        db.scalars(
            select(Availability.resource_id).where(
                Availability.absence_type.in_(ABSENT_TYPES),
                Availability.date_start <= on,
                Availability.date_end >= on,
            )
        )
    )
    load = dict(
        db.execute(
            select(Assignment.resource_id, func.count())
            .where(Assignment.released_date.is_(None))
            .group_by(Assignment.resource_id)
        ).all()
    )
    candidates = []
    for resource in db.scalars(select(Resource).where(Resource.join_date <= on)):
        if resource.resource_id in active_on_task or resource.resource_id in absent:
            continue
        match = role_match(resource, task.required_role_id)
        if match is None:
            continue
        candidates.append(
            ReplacementCandidate(
                resource_id=resource.resource_id,
                resource_name=resource.resource_name,
                primary_role_id=resource.primary_role_id,
                seniority=resource.seniority,
                match=match,
                active_assignments=load.get(resource.resource_id, 0),
            )
        )
    candidates.sort(key=lambda c: (MATCH_ORDER[c.match], c.active_assignments, c.resource_id))
    return candidates


def next_assignment_id(db: Session) -> str:
    return next_id(list(db.scalars(select(Assignment.assignment_id))), "ASG", width=4)


def take_over(db: Session, task_id: str, request: TakeoverRequest) -> TakeoverResult:
    task = get_task(db, task_id)
    day = request.takeover_date
    errors: list[FieldError] = []

    old = db.scalars(
        select(Assignment)
        .where(
            Assignment.task_id == task_id,
            Assignment.resource_id == request.from_resource_id,
            Assignment.released_date.is_(None),
        )
        .order_by(Assignment.assigned_date.desc())
        .limit(1)
    ).first()
    if old is None:
        errors.append(
            FieldError(
                "from_resource_id",
                f"{request.from_resource_id} tidak sedang ditugaskan di task {task_id}",
                "no_active_assignment",
            )
        )
    elif day < old.assigned_date:
        errors.append(
            FieldError(
                "takeover_date",
                f"Tidak boleh sebelum penugasan lama dimulai ({old.assigned_date.isoformat()})",
                "before_assigned",
            )
        )

    new_owner = db.get(Resource, request.to_resource_id)
    if request.to_resource_id == request.from_resource_id:
        errors.append(FieldError("to_resource_id", "Pengganti harus anggota lain", "same_resource"))
    elif new_owner is None:
        errors.append(
            FieldError(
                "to_resource_id",
                f"Anggota {request.to_resource_id} tidak terdaftar",
                "resource_not_found",
            )
        )
    else:
        already = db.scalar(
            select(Assignment.assignment_id).where(
                Assignment.task_id == task_id,
                Assignment.resource_id == new_owner.resource_id,
                Assignment.released_date.is_(None),
            )
        )
        clash = absent_on(db, new_owner.resource_id, day)
        if already is not None:
            message, kind = "Anggota ini sudah ditugaskan di task ini", "already_assigned"
        elif role_match(new_owner, task.required_role_id) is None:
            message = f"Tidak memegang peran {task.required_role_id} dan tidak bisa lintas peran"
            kind = "role_mismatch"
        elif clash is not None:
            message = (
                f"Tidak hadir pada tanggal itu ({clash.availability_id}, "
                f"{clash.date_start.isoformat()} s.d. {clash.date_end.isoformat()})"
            )
            kind = "resource_absent"
        elif new_owner.join_date > day:
            message = f"Baru bergabung {new_owner.join_date.isoformat()}"
            kind = "not_joined"
        else:
            message = None
        if message is not None:
            errors.append(FieldError("to_resource_id", message, kind))

    if errors:
        raise DataValidationError(errors)

    old.released_date = day
    created = Assignment(
        assignment_id=next_assignment_id(db),
        task_id=task_id,
        resource_id=new_owner.resource_id,
        role_in_task=task.required_role_id,
        assigned_date=day,
        is_takeover=True,
    )
    db.add(created)
    commit(db)  # penutupan dan penugasan baru tersimpan bersama, atau tidak sama sekali
    old_name = db.scalar(
        select(Resource.resource_name).where(Resource.resource_id == old.resource_id)
    )
    return TakeoverResult(
        released=_assignment_read(old, old_name or ""),
        created=_assignment_read(created, new_owner.resource_name),
    )


def affected_tasks(db: Session, availability_id: str) -> list[AffectedTask]:
    """Task yang sedang dipegang anggota selama periode ketidakhadirannya.

    Task terdampak: penugasannya aktif dalam periode itu, statusnya belum done/dropped, dan
    jadwal task (planned_start sampai actual_finish atau planned_finish) bersinggungan dengan
    periode. Catatan rotation_in berarti anggota hadir, jadi hasilnya kosong.
    """
    item = db.get(Availability, availability_id)
    if item is None:
        raise AvailabilityNotFoundError(availability_id)
    if item.absence_type not in ABSENT_TYPES:
        return []
    finish = func.coalesce(Task.actual_finish, Task.planned_finish)
    query = (
        select(Task, Project.project_name, Assignment.assignment_id)
        .join(Assignment, Assignment.task_id == Task.task_id)
        .join(Project, Project.project_id == Task.project_id)
        .where(
            Assignment.resource_id == item.resource_id,
            Assignment.assigned_date <= item.date_end,
            or_(Assignment.released_date.is_(None), Assignment.released_date >= item.date_start),
            Task.status.not_in(CLOSED_TASK_STATUSES),
            Task.planned_start <= item.date_end,
            finish >= item.date_start,
        )
        .order_by(Task.planned_start, Task.task_id)
    )
    return [
        AffectedTask(
            task_id=task.task_id,
            task_name=task.task_name,
            project_id=task.project_id,
            project_name=project_name,
            status=task.status,
            required_role_id=task.required_role_id,
            planned_start=task.planned_start,
            planned_finish=task.planned_finish,
            assignment_id=assignment_id,
        )
        for task, project_name, assignment_id in db.execute(query)
    ]
