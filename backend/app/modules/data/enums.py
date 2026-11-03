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


# Pola regex PostgreSQL untuk format ID pada Data Dictionary.
PROJECT_ID_PATTERN = "^PRJ-[0-9]{3}$"
RESOURCE_ID_PATTERN = "^RES-[0-9]{3}$"
ROLE_ID_PATTERN = "^ROLE-[A-Z]+$"
COMPLEXITY_ID_PATTERN = "^CX-[A-Z]+$"
# secondary_role_ids: daftar role_id dipisah titik koma, contoh ROLE-DM;ROLE-FE.
SECONDARY_ROLE_IDS_PATTERN = "^ROLE-[A-Z]+(;ROLE-[A-Z]+)*$"
