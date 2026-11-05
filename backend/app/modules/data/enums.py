"""Nilai enum dan format ID sesuai Data Dictionary D-01 s.d. D-11.

Enum disimpan sebagai VARCHAR dengan CHECK constraint, bukan tipe ENUM PostgreSQL.
Dengan begitu nilai baru cukup ditambah lewat migrasi biasa dan downgrade tidak
perlu DROP TYPE. Kelas di sini dipakai model, schema Pydantic, dan validator agar
daftar nilai hanya ditulis di satu tempat.
"""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """D-01 projects.status"""

    PLANNING = "planning"
    DEVELOPMENT = "development"
    TESTING = "testing"
    RELEASED = "released"
    ON_HOLD = "on_hold"


# "Proyek aktif" pada DIG-20: masih dikerjakan. released sudah selesai dan on_hold
# sedang ditunda, sehingga keduanya tidak memegang nomor prioritas.
ACTIVE_PROJECT_STATUSES = (ProjectStatus.PLANNING, ProjectStatus.DEVELOPMENT, ProjectStatus.TESTING)


class Seniority(StrEnum):
    """D-02 resources.seniority"""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class TaskPhase(StrEnum):
    """D-05 tasks.phase"""

    PLANNING = "planning"
    UIUX = "uiux"
    DM_DEV = "dm_dev"
    BE_DEV = "be_dev"
    FE_DEV = "fe_dev"
    TESTING = "testing"
    BUGFIX = "bugfix"
    DOCUMENTATION = "documentation"


class TaskStatus(StrEnum):
    """D-05 tasks.status"""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    ON_HOLD = "on_hold"
    IN_QA = "in_qa"
    DONE = "done"
    DROPPED = "dropped"


class DependencyType(StrEnum):
    """D-06 task_dependencies.dependency_type

    hard: blokir total (BE menunggu DM). soft: pengerjaan parsial (FE membuat dummy).
    """

    HARD = "hard"
    SOFT = "soft"


class WorkloadItemType(StrEnum):
    """D-08 workload_items.item_type"""

    OPERATIONAL = "operational"
    TICKET = "ticket"


class Severity(StrEnum):
    """D-08 workload_items.severity"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AbsenceType(StrEnum):
    """D-09 availability.absence_type"""

    PLANNED_LEAVE = "planned_leave"
    SUDDEN_LEAVE = "sudden_leave"
    MATERNITY_LEAVE = "maternity_leave"
    ROTATION_OUT = "rotation_out"
    ROTATION_IN = "rotation_in"


class ChangeEventType(StrEnum):
    """D-10 change_events.event_type"""

    CHANGE_REQUEST = "change_request"
    PRIORITY_CHANGE = "priority_change"
    BLOCKER = "blocker"
    OVERRUN = "overrun"
    HOTFIX = "hotfix"


class Decision(StrEnum):
    """D-10 change_events.decision"""

    ACCEPT_NOW = "accept_now"
    DEFER_NEXT = "defer_next"
    REJECT = "reject"


class ResolutionMode(StrEnum):
    """D-10 change_events.resolution_mode"""

    SWAP_TASK = "swap_task"
    EXTEND_DURATION = "extend_duration"
    SCOPE_ADDITION = "scope_addition"
    RESHUFFLE = "reshuffle"


# Pola regex PostgreSQL untuk format ID pada Data Dictionary.
PROJECT_ID_PATTERN = "^PRJ-[0-9]{3}$"
RESOURCE_ID_PATTERN = "^RES-[0-9]{3}$"
TASK_ID_PATTERN = "^TSK-[0-9]{4}$"
DEPENDENCY_ID_PATTERN = "^DEP-[0-9]{3}$"
ASSIGNMENT_ID_PATTERN = "^ASG-[0-9]{4}$"
WORKLOAD_ITEM_ID_PATTERN = "^WLI-[0-9]{4}$"
AVAILABILITY_ID_PATTERN = "^AVL-[0-9]{3}$"
EVENT_ID_PATTERN = "^EVT-[0-9]{3}$"
ROLE_ID_PATTERN = "^ROLE-[A-Z]+$"
COMPLEXITY_ID_PATTERN = "^CX-[A-Z]+$"
# secondary_role_ids: daftar role_id dipisah titik koma, contoh ROLE-DM;ROLE-FE.
SECONDARY_ROLE_IDS_PATTERN = "^ROLE-[A-Z]+(;ROLE-[A-Z]+)*$"
