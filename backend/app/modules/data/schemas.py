"""Schema request dan response API modul Data."""

import re
from datetime import date
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.modules.data.enums import (
    PROJECT_ID_PATTERN,
    RESOURCE_ID_PATTERN,
    ROLE_ID_PATTERN,
    ProjectStatus,
    Seniority,
)

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_iso_date(value: Any) -> Any:
    """Terima tanggal hanya sebagai string `YYYY-MM-DD` (DATA_CONTRACT.md bagian 5).

    Tanpa ini Pydantic menerima unix timestamp dan string datetime, dan PostgreSQL
    menerima `01/12/2026` lalu menyimpannya sebagai 12 Januari.
    """
    if isinstance(value, date) or value is None:
        return value
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValueError("Tanggal harus berformat YYYY-MM-DD")
    return date.fromisoformat(value)


def reject_nul(value: str) -> str:
    """PostgreSQL tidak bisa menyimpan karakter NUL di kolom teks (psycopg menolaknya)."""
    if "\x00" in value:
        raise ValueError("Teks tidak boleh mengandung karakter NUL")
    return value


IsoDate = Annotated[date, BeforeValidator(parse_iso_date)]
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(reject_nul),
]
# Batas atas mengikuti kolom INTEGER PostgreSQL; di atasnya insert gagal dengan error 500.
PG_INTEGER_MAX = 2_147_483_647
PriorityRank = Annotated[int, Field(strict=True, ge=1, le=PG_INTEGER_MAX)]
ProjectId = Annotated[str, StringConstraints(pattern=PROJECT_ID_PATTERN)]


class ProjectFields(BaseModel):
    """Kolom D-01 yang boleh diisi pengguna (semua selain `project_id`)."""

    model_config = ConfigDict(extra="forbid")

    project_name: Name
    process_owner: Name
    priority_rank: PriorityRank
    start_date: IsoDate
    target_launch_date: IsoDate
    actual_launch_date: IsoDate | None = None
    status: ProjectStatus = ProjectStatus.PLANNING
    dor_fulfilled: bool = Field(default=False, strict=True)


class ProjectCreate(ProjectFields):
    """Body POST. `project_id` boleh dikosongkan; server mengisi PRJ-xxx berikutnya."""

    project_id: ProjectId | None = None


class ProjectUpdate(BaseModel):
    """Body PATCH. Hanya kolom yang dikirim yang diubah; `project_id` tidak bisa diubah."""

    model_config = ConfigDict(extra="forbid")

    project_name: Name | None = None
    process_owner: Name | None = None
    priority_rank: PriorityRank | None = None
    start_date: IsoDate | None = None
    target_launch_date: IsoDate | None = None
    actual_launch_date: IsoDate | None = None
    status: ProjectStatus | None = None
    dor_fulfilled: bool | None = Field(default=None, strict=True)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    project_name: str
    process_owner: str
    priority_rank: int
    start_date: date
    target_launch_date: date
    actual_launch_date: date | None
    status: ProjectStatus
    dor_fulfilled: bool
    is_active: bool = Field(description="Status planning, development, atau testing")
    is_overdue: bool = Field(
        description="Proyek aktif yang target launching-nya sudah lewat dari hari ini"
    )


# --- D-04 complexity_levels (DIG-22) ---

# Hari dan bobot boleh desimal (misalnya 0,5 hari), tidak negatif, dan harus angka
# biasa: string, boolean, NaN, dan tak hingga ditolak.
NonNegative = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class ComplexityUpdate(BaseModel):
    """Body PATCH. ID dan nama level tetap; yang diatur hanya rentang hari dan bobot."""

    model_config = ConfigDict(extra="forbid")

    min_days: NonNegative | None = None
    max_days: NonNegative | None = None
    load_weight: NonNegative | None = None


class ComplexityRead(BaseModel):
    complexity_id: str
    complexity_name: str
    min_days: float
    max_days: float
    load_weight: float
    task_count: int = Field(description="Jumlah task yang memakai level ini")


# --- D-02 resources dan D-03 roles (DIG-21) ---

RoleId = Annotated[str, StringConstraints(pattern=ROLE_ID_PATTERN)]
ResourceId = Annotated[str, StringConstraints(pattern=RESOURCE_ID_PATTERN)]
# Daftar role rangkap dikirim sebagai array (multi-select). Di basis data disimpan
# sebagai string berpemisah titik koma sesuai Data Dictionary, misalnya ROLE-DM;ROLE-FE.
RoleIdList = Annotated[list[RoleId], Field(max_length=8)]


class ResourceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_name: Name
    primary_role_id: RoleId
    secondary_role_ids: RoleIdList = Field(default_factory=list)
    cross_role_capable: bool = Field(default=False, strict=True)
    join_date: IsoDate
    seniority: Seniority


class ResourceCreate(ResourceFields):
    """Body POST. `resource_id` boleh dikosongkan; server mengisi RES-xxx berikutnya."""

    resource_id: ResourceId | None = None


class ResourceUpdate(BaseModel):
    """Body PATCH. Hanya kolom yang dikirim yang diubah; `resource_id` tidak bisa diubah."""

    model_config = ConfigDict(extra="forbid")

    resource_name: Name | None = None
    primary_role_id: RoleId | None = None
    secondary_role_ids: RoleIdList | None = None
    cross_role_capable: bool | None = Field(default=None, strict=True)
    join_date: IsoDate | None = None
    seniority: Seniority | None = None


class ResourceRead(BaseModel):
    resource_id: str
    resource_name: str
    primary_role_id: str
    secondary_role_ids: list[str]
    cross_role_capable: bool
    join_date: date
    seniority: Seniority
    tenure_days: int = Field(description="Lama bergabung dalam hari, dihitung dari join_date")
    is_onboarding: bool = Field(
        description="Bergabung kurang dari ONBOARDING_DAYS hari yang lalu (asumsi, lihat DIG-186)"
    )


Capacity = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class RoleUpdate(BaseModel):
    """Body PATCH. ID dan nama peran tetap; yang diatur kapasitas dan deskripsi."""

    model_config = ConfigDict(extra="forbid")

    capacity_reference: Capacity | None = None
    description: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=1000),
            AfterValidator(reject_nul),
        ]
        | None
    ) = None


class RoleRead(BaseModel):
    role_id: str
    role_name: str
    capacity_reference: float
    description: str | None
    resource_count: int = Field(description="Jumlah anggota dengan peran ini sebagai peran utama")
