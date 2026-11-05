"""Logika bisnis modul Data.

Constraint di basis data (format ID, enum, urutan tanggal) tetap menjadi pagar
terakhir. Service memeriksa aturan yang sama lebih dulu supaya pengguna
mendapat pesan per kolom, ditambah aturan DIG-20 yang tidak ada di skema D-01.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.data.enums import ACTIVE_PROJECT_STATUSES, ProjectStatus
from app.modules.data.models import ACTIVE_PRIORITY_INDEX, Project
from app.modules.data.schemas import ProjectCreate, ProjectRead, ProjectUpdate

ACTIVE_STATUSES = frozenset(ACTIVE_PROJECT_STATUSES)
NOT_NULL_FIELDS = frozenset(
    {
        "project_name",
        "process_owner",
        "priority_rank",
        "start_date",
        "target_launch_date",
        "status",
        "dor_fulfilled",
    }
)


class FieldError:
    def __init__(self, field: str, message: str, error_type: str) -> None:
        self.field = field
        self.message = message
        self.error_type = error_type

    def as_detail(self) -> dict:
        # Bentuknya sama dengan error validasi bawaan FastAPI agar frontend
        # cukup punya satu cara untuk menampilkan pesan per kolom.
        return {"loc": ["body", self.field], "msg": self.message, "type": self.error_type}


class ProjectValidationError(Exception):
    """Aturan isi data dilanggar (HTTP 422)."""

    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__(errors)
        self.errors = errors


class ProjectConflictError(Exception):
    """Bentrok dengan data lain (HTTP 409)."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class ProjectNotFoundError(Exception):
    """Proyek tidak ada (HTTP 404)."""


def is_active(status: str) -> bool:
    return status in ACTIVE_STATUSES


def to_read(project: Project, today: date | None = None) -> ProjectRead:
    today = today or date.today()
    active = is_active(project.status)
    return ProjectRead.model_validate(
        {
            **{c.key: getattr(project, c.key) for c in Project.__table__.columns},
            "is_active": active,
            "is_overdue": active and project.target_launch_date < today,
        }
    )


def check_project_rules(values: dict) -> list[FieldError]:
    """Aturan yang hanya melibatkan kolom proyek itu sendiri."""
    errors: list[FieldError] = []
    start = values["start_date"]
    status = values["status"]
    actual = values.get("actual_launch_date")

    if values["target_launch_date"] < start:
        errors.append(
            FieldError(
                "target_launch_date",
                "Target launching tidak boleh lebih awal dari tanggal mulai",
                "date_order",
            )
        )
    if status != ProjectStatus.RELEASED and actual is not None:
        errors.append(
            FieldError(
                "actual_launch_date",
                "Tanggal launching aktual harus kosong selama status belum released",
                "actual_launch_not_released",
            )
        )
    if status == ProjectStatus.RELEASED and actual is None:
        errors.append(
            FieldError(
                "actual_launch_date",
                "Tanggal launching aktual wajib diisi bila status released",
                "actual_launch_required",
            )
        )
    if actual is not None and actual < start:
        errors.append(
            FieldError(
                "actual_launch_date",
                "Tanggal launching aktual tidak boleh lebih awal dari tanggal mulai",
                "date_order",
            )
        )
    return errors


def ensure_unique_active_priority(db: Session, values: dict, exclude_id: str | None) -> None:
    if not is_active(values["status"]):
        return
    query = select(Project.project_id, Project.project_name).where(
        Project.priority_rank == values["priority_rank"],
        Project.status.in_(ACTIVE_STATUSES),
    )
    if exclude_id is not None:
        query = query.where(Project.project_id != exclude_id)
    clash = db.execute(query.limit(1)).first()
    if clash is not None:
        raise ProjectConflictError(
            f"Prioritas {values['priority_rank']} sudah dipakai proyek aktif "
            f"{clash.project_id} ({clash.project_name})",
            field="priority_rank",
        )


def next_project_id(db: Session) -> str:
    highest = db.scalar(select(func.max(Project.project_id)))
    number = int(highest.removeprefix("PRJ-")) + 1 if highest else 1
    if number > 999:
        raise ProjectConflictError("Nomor proyek sudah mencapai PRJ-999", field="project_id")
    return f"PRJ-{number:03d}"


def list_projects(
    db: Session, status: list[ProjectStatus] | None = None, active_only: bool = False
) -> list[ProjectRead]:
    query = select(Project).order_by(Project.priority_rank, Project.project_id)
    if active_only:
        query = query.where(Project.status.in_(ACTIVE_STATUSES))
    if status:
        query = query.where(Project.status.in_(status))
    today = date.today()
    return [to_read(project, today) for project in db.scalars(query)]


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)
    return project


def create_project(db: Session, payload: ProjectCreate) -> ProjectRead:
    values = payload.model_dump()
    errors = check_project_rules(values)
    if errors:
        raise ProjectValidationError(errors)

    if values["project_id"] is None:
        values["project_id"] = next_project_id(db)
    elif db.get(Project, values["project_id"]) is not None:
        raise ProjectConflictError(
            f"ID {values['project_id']} sudah dipakai proyek lain", field="project_id"
        )
    ensure_unique_active_priority(db, values, exclude_id=None)

    project = Project(**values)
    db.add(project)
    commit(db)
    return to_read(project)


def update_project(db: Session, project_id: str, payload: ProjectUpdate) -> ProjectRead:
    project = get_project(db, project_id)
    changes = payload.model_dump(exclude_unset=True)

    errors = [
        FieldError(field, "Kolom ini wajib diisi", "missing")
        for field, value in changes.items()
        if value is None and field in NOT_NULL_FIELDS
    ]
    if errors:
        raise ProjectValidationError(errors)

    values = {c.key: getattr(project, c.key) for c in Project.__table__.columns} | changes
    errors = check_project_rules(values)
    if errors:
        raise ProjectValidationError(errors)
    ensure_unique_active_priority(db, values, exclude_id=project_id)

    for field, value in changes.items():
        setattr(project, field, value)
    commit(db)
    return to_read(project)


def delete_project(db: Session, project_id: str) -> None:
    project = get_project(db, project_id)
    db.delete(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProjectConflictError(
            f"Proyek {project_id} masih dipakai task, beban non-proyek, atau change event, "
            "sehingga tidak bisa dihapus. Ubah statusnya menjadi on_hold bila proyek dihentikan."
        ) from exc


def commit(db: Session) -> None:
    """Commit dan terjemahkan pelanggaran constraint yang lolos pemeriksaan service.

    Pemeriksaan service dan constraint DB seharusnya sama. Bila tetap terjadi
    (misalnya dua permintaan bersamaan), pengguna mendapat 409, bukan 500.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == ACTIVE_PRIORITY_INDEX:
            raise ProjectConflictError(
                "Prioritas ini baru saja dipakai proyek aktif lain. "
                "Muat ulang daftar proyek lalu pilih prioritas lain.",
                field="priority_rank",
            ) from exc
        raise ProjectConflictError(
            "Data proyek ditolak basis data karena bentrok dengan data lain. "
            "Muat ulang daftar proyek lalu coba lagi."
        ) from exc
