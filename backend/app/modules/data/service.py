"""Logika bisnis modul Data.

Constraint di basis data (format ID, enum, urutan tanggal) tetap menjadi pagar
terakhir. Service memeriksa aturan yang sama lebih dulu supaya pengguna
mendapat pesan per kolom, ditambah aturan DIG-20 yang tidak ada di skema D-01.
"""

import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.data.enums import ACTIVE_PROJECT_STATUSES, ProjectStatus
from app.modules.data.models import (
    ACTIVE_PRIORITY_INDEX,
    ComplexityLevel,
    Project,
    Resource,
    Role,
    Task,
)
from app.modules.data.schemas import (
    ComplexityRead,
    ComplexityUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    RoleRead,
    RoleUpdate,
)

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


class DataValidationError(Exception):
    """Aturan isi data dilanggar (HTTP 422)."""

    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__(errors)
        self.errors = errors


class ConflictError(Exception):
    """Bentrok dengan data lain (HTTP 409)."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class NotFoundError(Exception):
    """Data tidak ada (HTTP 404). `label` dipakai untuk pesan error."""

    label = "Data"


class ProjectNotFoundError(NotFoundError):
    label = "Proyek"


class ComplexityNotFoundError(NotFoundError):
    label = "Level kompleksitas"


class ResourceNotFoundError(NotFoundError):
    label = "Anggota"


class RoleNotFoundError(NotFoundError):
    label = "Peran"


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
        raise ConflictError(
            f"Prioritas {values['priority_rank']} sudah dipakai proyek aktif "
            f"{clash.project_id} ({clash.project_name})",
            field="priority_rank",
        )


def next_project_id(db: Session) -> str:
    highest = db.scalar(select(func.max(Project.project_id)))
    number = int(highest.removeprefix("PRJ-")) + 1 if highest else 1
    if number > 999:
        raise ConflictError("Nomor proyek sudah mencapai PRJ-999", field="project_id")
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
        raise DataValidationError(errors)

    if values["project_id"] is None:
        values["project_id"] = next_project_id(db)
    elif db.get(Project, values["project_id"]) is not None:
        raise ConflictError(
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
        raise DataValidationError(errors)

    values = {c.key: getattr(project, c.key) for c in Project.__table__.columns} | changes
    errors = check_project_rules(values)
    if errors:
        raise DataValidationError(errors)
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
        raise ConflictError(
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
            raise ConflictError(
                "Prioritas ini baru saja dipakai proyek aktif lain. "
                "Muat ulang daftar proyek lalu pilih prioritas lain.",
                field="priority_rank",
            ) from exc
        raise ConflictError(
            "Data ditolak basis data karena bentrok dengan data lain. "
            "Muat ulang halaman lalu coba lagi."
        ) from exc


# --- D-04 complexity_levels (DIG-22) ---

# Urutan tampilan dari level tersulit. Level lain (bila kelak ditambah) menyusul urut ID.
COMPLEXITY_ORDER = {"CX-VH": 0, "CX-H": 1, "CX-M": 2, "CX-L": 3}


def list_complexity_levels(db: Session) -> list[ComplexityRead]:
    task_counts = dict(
        db.execute(select(Task.complexity_id, func.count()).group_by(Task.complexity_id)).all()
    )
    levels = sorted(
        db.scalars(select(ComplexityLevel)),
        key=lambda level: (COMPLEXITY_ORDER.get(level.complexity_id, 99), level.complexity_id),
    )
    return [complexity_read(level, task_counts.get(level.complexity_id, 0)) for level in levels]


def complexity_read(level: ComplexityLevel, task_count: int) -> ComplexityRead:
    return ComplexityRead(
        complexity_id=level.complexity_id,
        complexity_name=level.complexity_name,
        min_days=level.min_days,
        max_days=level.max_days,
        load_weight=level.load_weight,
        task_count=task_count,
    )


def update_complexity_level(
    db: Session, complexity_id: str, payload: ComplexityUpdate
) -> ComplexityRead:
    level = db.get(ComplexityLevel, complexity_id)
    if level is None:
        raise ComplexityNotFoundError(complexity_id)
    changes = payload.model_dump(exclude_unset=True)

    errors = [
        FieldError(field, "Kolom ini wajib diisi", "missing")
        for field, value in changes.items()
        if value is None
    ]
    if errors:
        raise DataValidationError(errors)

    min_days = changes.get("min_days", level.min_days)
    max_days = changes.get("max_days", level.max_days)
    if min_days > max_days:
        # Pesan ditempel pada kolom yang sedang diubah agar mudah ditemukan di form.
        field = "min_days" if "min_days" in changes and "max_days" not in changes else "max_days"
        raise DataValidationError(
            [
                FieldError(
                    field,
                    "Hari minimum tidak boleh lebih besar dari hari maksimum",
                    "min_after_max",
                )
            ]
        )

    for field, value in changes.items():
        setattr(level, field, value)
    commit(db)
    task_count = db.scalar(
        select(func.count()).select_from(Task).where(Task.complexity_id == complexity_id)
    )
    return complexity_read(level, task_count or 0)


# --- D-02 resources dan D-03 roles (DIG-21) ---

# Asumsi tim sampai formula onboarding difinalkan bersama tWinner (DIG-186):
# anggota yang bergabung kurang dari 90 hari dianggap masih masa onboarding.
ONBOARDING_DAYS = 90
RESOURCE_NOT_NULL = frozenset(
    {"resource_name", "primary_role_id", "cross_role_capable", "join_date", "seniority"}
)


def split_role_ids(value: str | None) -> list[str]:
    return [role_id for role_id in (value or "").split(";") if role_id]


def join_role_ids(role_ids: list[str]) -> str | None:
    """Simpan sebagai ROLE-A;ROLE-B (tanpa spasi), atau NULL bila kosong."""
    return ";".join(role_ids) or None


def resource_read(resource: Resource, today: date | None = None) -> ResourceRead:
    today = today or date.today()
    tenure = (today - resource.join_date).days
    return ResourceRead(
        resource_id=resource.resource_id,
        resource_name=resource.resource_name,
        primary_role_id=resource.primary_role_id,
        secondary_role_ids=split_role_ids(resource.secondary_role_ids),
        cross_role_capable=resource.cross_role_capable,
        join_date=resource.join_date,
        seniority=resource.seniority,
        tenure_days=tenure,
        is_onboarding=0 <= tenure < ONBOARDING_DAYS,
    )


def check_resource_roles(db: Session, primary: str, secondary: list[str]) -> list[FieldError]:
    """Validasi FK peran: role utama dan setiap role rangkap harus ada di D-03."""
    known = set(db.scalars(select(Role.role_id)))
    errors: list[FieldError] = []
    if primary not in known:
        errors.append(
            FieldError("primary_role_id", f"Peran {primary} tidak terdaftar", "role_not_found")
        )
    unknown = [role_id for role_id in secondary if role_id not in known]
    if unknown:
        errors.append(
            FieldError(
                "secondary_role_ids",
                f"Peran {', '.join(unknown)} tidak terdaftar",
                "role_not_found",
            )
        )
    elif primary in secondary:
        errors.append(
            FieldError(
                "secondary_role_ids",
                f"{primary} sudah menjadi peran utama, tidak perlu dipilih sebagai peran rangkap",
                "duplicate_primary_role",
            )
        )
    elif len(set(secondary)) != len(secondary):
        errors.append(
            FieldError("secondary_role_ids", "Peran rangkap tidak boleh ganda", "duplicate_role")
        )
    return errors


def next_id(existing: list[str], prefix: str, width: int = 3) -> str:
    """ID berikutnya setelah angka terbesar, dihitung sebagai angka.

    Format ID boleh lebih dari `width` digit (PRJ-1000), sehingga urutan teks
    keliru: "RES-1000" < "RES-999".
    """
    pattern = re.compile(rf"{re.escape(prefix)}-(\d+)")
    numbers = [int(m.group(1)) for value in existing if (m := pattern.fullmatch(value))]
    return f"{prefix}-{max(numbers, default=0) + 1:0{width}d}"


def next_resource_id(db: Session) -> str:
    return next_id(list(db.scalars(select(Resource.resource_id))), "RES")


def list_resources(db: Session) -> list[ResourceRead]:
    today = date.today()
    resources = db.scalars(select(Resource).order_by(Resource.resource_id))
    return sorted(
        (resource_read(resource, today) for resource in resources),
        key=lambda r: int(r.resource_id.removeprefix("RES-")),
    )


def get_resource(db: Session, resource_id: str) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise ResourceNotFoundError(resource_id)
    return resource


def create_resource(db: Session, payload: ResourceCreate) -> ResourceRead:
    values = payload.model_dump()
    errors = check_resource_roles(db, values["primary_role_id"], values["secondary_role_ids"])
    if errors:
        raise DataValidationError(errors)
    if values["resource_id"] is None:
        values["resource_id"] = next_resource_id(db)
    elif db.get(Resource, values["resource_id"]) is not None:
        raise ConflictError(
            f"ID {values['resource_id']} sudah dipakai anggota lain", field="resource_id"
        )
    values["secondary_role_ids"] = join_role_ids(values["secondary_role_ids"])
    resource = Resource(**values)
    db.add(resource)
    commit(db)
    return resource_read(resource)


def update_resource(db: Session, resource_id: str, payload: ResourceUpdate) -> ResourceRead:
    resource = get_resource(db, resource_id)
    changes = payload.model_dump(exclude_unset=True)
    errors = [
        FieldError(field, "Kolom ini wajib diisi", "missing")
        for field, value in changes.items()
        if value is None and field in RESOURCE_NOT_NULL
    ]
    if errors:
        raise DataValidationError(errors)

    if "secondary_role_ids" in changes:
        changes["secondary_role_ids"] = changes["secondary_role_ids"] or []
    primary = changes.get("primary_role_id", resource.primary_role_id)
    secondary = changes.get("secondary_role_ids", split_role_ids(resource.secondary_role_ids))
    if "primary_role_id" in changes or "secondary_role_ids" in changes:
        errors = check_resource_roles(db, primary, secondary)
        if errors:
            raise DataValidationError(errors)

    if "secondary_role_ids" in changes:
        changes["secondary_role_ids"] = join_role_ids(changes["secondary_role_ids"])
    for field, value in changes.items():
        setattr(resource, field, value)
    commit(db)
    return resource_read(resource)


def delete_resource(db: Session, resource_id: str) -> None:
    resource = get_resource(db, resource_id)
    db.delete(resource)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Anggota {resource_id} masih tercatat di assignment, beban non-proyek, "
            "atau ketersediaan, sehingga tidak bisa dihapus."
        ) from exc


def list_roles(db: Session) -> list[RoleRead]:
    counts = dict(
        db.execute(
            select(Resource.primary_role_id, func.count()).group_by(Resource.primary_role_id)
        ).all()
    )
    return [
        role_read(role, counts.get(role.role_id, 0))
        for role in db.scalars(select(Role).order_by(Role.role_id))
    ]


def role_read(role: Role, resource_count: int) -> RoleRead:
    return RoleRead(
        role_id=role.role_id,
        role_name=role.role_name,
        capacity_reference=role.capacity_reference,
        description=role.description,
        resource_count=resource_count,
    )


def update_role(db: Session, role_id: str, payload: RoleUpdate) -> RoleRead:
    role = db.get(Role, role_id)
    if role is None:
        raise RoleNotFoundError(role_id)
    changes = payload.model_dump(exclude_unset=True)
    if "capacity_reference" in changes and changes["capacity_reference"] is None:
        raise DataValidationError(
            [FieldError("capacity_reference", "Kolom ini wajib diisi", "missing")]
        )
    if "description" in changes:
        # Deskripsi kosong disimpan sebagai NULL.
        changes["description"] = changes["description"] or None
    for field, value in changes.items():
        setattr(role, field, value)
    commit(db)
    count = db.scalar(
        select(func.count()).select_from(Resource).where(Resource.primary_role_id == role_id)
    )
    return role_read(role, count or 0)
