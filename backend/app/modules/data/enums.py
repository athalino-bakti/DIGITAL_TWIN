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


# Pola regex PostgreSQL untuk format ID pada Data Dictionary.
PROJECT_ID_PATTERN = "^PRJ-[0-9]{3}$"
RESOURCE_ID_PATTERN = "^RES-[0-9]{3}$"
TASK_ID_PATTERN = "^TSK-[0-9]{4}$"
DEPENDENCY_ID_PATTERN = "^DEP-[0-9]{3}$"
ROLE_ID_PATTERN = "^ROLE-[A-Z]+$"
COMPLEXITY_ID_PATTERN = "^CX-[A-Z]+$"
# secondary_role_ids: daftar role_id dipisah titik koma, contoh ROLE-DM;ROLE-FE.
SECONDARY_ROLE_IDS_PATTERN = "^ROLE-[A-Z]+(;ROLE-[A-Z]+)*$"
