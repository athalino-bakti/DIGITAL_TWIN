"""Model final sources D-01 s.d. D-11 (Data Dictionary bersama J&C dan tWinner).

Nama tabel dan kolom mengikuti Data Dictionary apa adanya karena tWinner membaca
tabel yang sama. Tabel internal J&C (staging, alias, event log, kualitas data,
audit) tidak ditaruh di sini.
"""

from datetime import date
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    Double,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.data.enums import (
    ASSIGNMENT_ID_PATTERN,
    AVAILABILITY_ID_PATTERN,
    COMPLEXITY_ID_PATTERN,
    DEPENDENCY_ID_PATTERN,
    EVENT_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RESOURCE_ID_PATTERN,
    ROLE_ID_PATTERN,
    SECONDARY_ROLE_IDS_PATTERN,
    TASK_ID_PATTERN,
    WORKLOAD_ITEM_ID_PATTERN,
    AbsenceType,
    ChangeEventType,
    Decision,
    DependencyType,
    ProjectStatus,
    ResolutionMode,
    Seniority,
    Severity,
    TaskPhase,
    TaskStatus,
    WorkloadItemType,
)


def one_of(column: str, values: type[StrEnum]) -> str:
    """Ekspresi CHECK `kolom IN (...)` dari sebuah StrEnum."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"


def matches(column: str, pattern: str) -> str:
    """Ekspresi CHECK regex PostgreSQL untuk format ID."""
    return f"{column} ~ '{pattern}'"


class Project(Base):
    """D-01 projects"""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(matches("project_id", PROJECT_ID_PATTERN), name="project_id_format"),
        CheckConstraint(one_of("status", ProjectStatus), name="status_valid"),
        CheckConstraint("priority_rank >= 1", name="priority_rank_min"),
        CheckConstraint("target_launch_date >= start_date", name="target_after_start"),
        CheckConstraint("actual_launch_date >= start_date", name="actual_after_start"),
    )

    project_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(200))
    process_owner: Mapped[str] = mapped_column(String(200))
    priority_rank: Mapped[int]
    start_date: Mapped[date] = mapped_column(Date)
    target_launch_date: Mapped[date] = mapped_column(Date)
    actual_launch_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    dor_fulfilled: Mapped[bool] = mapped_column(server_default=false())


class Role(Base):
    """D-03 roles"""

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(matches("role_id", ROLE_ID_PATTERN), name="role_id_format"),
        CheckConstraint("capacity_reference > 0", name="capacity_reference_positive"),
    )

    role_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    role_name: Mapped[str] = mapped_column(String(100))
    capacity_reference: Mapped[float] = mapped_column(Double, server_default="3.0")
    description: Mapped[str | None] = mapped_column(Text)


class Resource(Base):
    """D-02 resources

    secondary_role_ids tetap string berpemisah titik koma sesuai Data Dictionary.
    PostgreSQL tidak bisa memasang FK pada isi string, jadi CHECK hanya menjaga
    formatnya. Keberadaan setiap role_id diperiksa di service (DIG-100).
    """

    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint(matches("resource_id", RESOURCE_ID_PATTERN), name="resource_id_format"),
        CheckConstraint(
            matches("secondary_role_ids", SECONDARY_ROLE_IDS_PATTERN),
            name="secondary_role_ids_format",
        ),
        CheckConstraint(one_of("seniority", Seniority), name="seniority_valid"),
    )

    resource_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    resource_name: Mapped[str] = mapped_column(String(200))
    primary_role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"), index=True)
    secondary_role_ids: Mapped[str | None] = mapped_column(String(200))
    cross_role_capable: Mapped[bool] = mapped_column(server_default=false())
    join_date: Mapped[date] = mapped_column(Date)
    seniority: Mapped[str] = mapped_column(String(10))


class ComplexityLevel(Base):
    """D-04 complexity_levels"""

    __tablename__ = "complexity_levels"
    __table_args__ = (
        CheckConstraint(
            matches("complexity_id", COMPLEXITY_ID_PATTERN), name="complexity_id_format"
        ),
        CheckConstraint("min_days >= 0", name="min_days_min"),
        CheckConstraint("max_days >= min_days", name="max_days_after_min"),
        CheckConstraint("load_weight >= 0", name="load_weight_min"),
    )

    complexity_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    complexity_name: Mapped[str] = mapped_column(String(50))
    min_days: Mapped[float] = mapped_column(Double)
    max_days: Mapped[float] = mapped_column(Double)
    load_weight: Mapped[float] = mapped_column(Double)


class Task(Base):
    """D-05 tasks"""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(matches("task_id", TASK_ID_PATTERN), name="task_id_format"),
        CheckConstraint(one_of("phase", TaskPhase), name="phase_valid"),
        CheckConstraint(one_of("status", TaskStatus), name="status_valid"),
        CheckConstraint("priority_rank >= 1", name="priority_rank_min"),
        CheckConstraint("estimated_days > 0", name="estimated_days_positive"),
        CheckConstraint("planned_finish >= planned_start", name="planned_finish_after_start"),
        CheckConstraint("actual_finish >= actual_start", name="actual_finish_after_start"),
        CheckConstraint(
            "actual_finish IS NULL OR actual_start IS NOT NULL", name="actual_finish_needs_start"
        ),
        CheckConstraint("qa_reject_count >= 0", name="qa_reject_count_min"),
    )

    task_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    feature_name: Mapped[str] = mapped_column(String(200))
    task_name: Mapped[str] = mapped_column(String(300))
    required_role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"), index=True)
    complexity_id: Mapped[str] = mapped_column(
        ForeignKey("complexity_levels.complexity_id"), index=True
    )
    priority_rank: Mapped[int]
    estimated_days: Mapped[float] = mapped_column(Double)
    phase: Mapped[str] = mapped_column(String(20))
    planned_start: Mapped[date] = mapped_column(Date)
    planned_finish: Mapped[date] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_finish: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), server_default=TaskStatus.NOT_STARTED.value)
    qa_reject_count: Mapped[int] = mapped_column(server_default="0")
    dod_fulfilled: Mapped[bool] = mapped_column(server_default=false())


class TaskDependency(Base):
    """D-06 task_dependencies

    propagation_factor 1.0 untuk hard; soft memakai nilai di bawah 1 (default 0.3
    menurut Data Dictionary, diisi oleh pemanggil karena bergantung pada tipe).
    """

    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint(
            matches("dependency_id", DEPENDENCY_ID_PATTERN), name="dependency_id_format"
        ),
        CheckConstraint(one_of("dependency_type", DependencyType), name="dependency_type_valid"),
        CheckConstraint(
            "propagation_factor > 0 AND propagation_factor <= 1", name="propagation_factor_range"
        ),
        CheckConstraint(
            "dependency_type <> 'hard' OR propagation_factor = 1.0", name="hard_propagation_full"
        ),
        CheckConstraint("task_id <> depends_on_task_id", name="no_self_dependency"),
        UniqueConstraint("task_id", "depends_on_task_id"),
    )

    dependency_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"), index=True)
    depends_on_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(10))
    propagation_factor: Mapped[float] = mapped_column(Double)


class Assignment(Base):
    """D-07 assignments

    role_in_task bisa berbeda dari primary_role_id resource (peran rangkap atau
    pengambilalihan lintas peran), sehingga ber-FK langsung ke roles.
    """

    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            matches("assignment_id", ASSIGNMENT_ID_PATTERN), name="assignment_id_format"
        ),
        CheckConstraint("released_date >= assigned_date", name="released_after_assigned"),
    )

    assignment_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), index=True)
    role_in_task: Mapped[str] = mapped_column(ForeignKey("roles.role_id"), index=True)
    assigned_date: Mapped[date] = mapped_column(Date)
    released_date: Mapped[date | None] = mapped_column(Date)
    is_takeover: Mapped[bool] = mapped_column(server_default=false())


class WorkloadItem(Base):
    """D-08 workload_items (beban non-proyek: operasional dan tiket)"""

    __tablename__ = "workload_items"
    __table_args__ = (
        CheckConstraint(matches("item_id", WORKLOAD_ITEM_ID_PATTERN), name="item_id_format"),
        CheckConstraint(one_of("item_type", WorkloadItemType), name="item_type_valid"),
        CheckConstraint(one_of("severity", Severity), name="severity_valid"),
        CheckConstraint("started_date >= received_date", name="started_after_received"),
        CheckConstraint("resolved_date >= received_date", name="resolved_after_received"),
        CheckConstraint("resolved_date >= started_date", name="resolved_after_started"),
    )

    item_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), index=True)
    item_type: Mapped[str] = mapped_column(String(20))
    related_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.project_id"), index=True
    )
    received_date: Mapped[date] = mapped_column(Date)
    started_date: Mapped[date | None] = mapped_column(Date)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    severity: Mapped[str | None] = mapped_column(String(10))
    is_hotfix: Mapped[bool] = mapped_column(server_default=false())


class Availability(Base):
    """D-09 availability (cuti dan rotasi; hari libur nasional ada di D-11)"""

    __tablename__ = "availability"
    __table_args__ = (
        CheckConstraint(
            matches("availability_id", AVAILABILITY_ID_PATTERN), name="availability_id_format"
        ),
        CheckConstraint(one_of("absence_type", AbsenceType), name="absence_type_valid"),
        CheckConstraint("date_end >= date_start", name="date_end_after_start"),
    )

    availability_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), index=True)
    date_start: Mapped[date] = mapped_column(Date)
    date_end: Mapped[date] = mapped_column(Date)
    absence_type: Mapped[str] = mapped_column(String(20))
    is_known_at_planning: Mapped[bool] = mapped_column(server_default=false())


class ChangeEvent(Base):
    """D-10 change_events

    decision, resolution_mode, affected_task_id, dan extension_days boleh kosong
    karena tidak semua event_type punya keputusan (misalnya blocker atau overrun).
    """

    __tablename__ = "change_events"
    __table_args__ = (
        CheckConstraint(matches("event_id", EVENT_ID_PATTERN), name="event_id_format"),
        CheckConstraint(one_of("event_type", ChangeEventType), name="event_type_valid"),
        CheckConstraint(one_of("decision", Decision), name="decision_valid"),
        CheckConstraint(one_of("resolution_mode", ResolutionMode), name="resolution_mode_valid"),
        CheckConstraint("extension_days > 0", name="extension_days_positive"),
    )

    event_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    event_date: Mapped[date] = mapped_column(Date)
    requested_by: Mapped[str | None] = mapped_column(String(100))
    decision: Mapped[str | None] = mapped_column(String(20))
    resolution_mode: Mapped[str | None] = mapped_column(String(20))
    affected_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.task_id"), index=True)
    extension_days: Mapped[float | None] = mapped_column(Double)


class Holiday(Base):
    """D-11 holidays"""

    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, primary_key=True)
    holiday_name: Mapped[str] = mapped_column(String(200))
