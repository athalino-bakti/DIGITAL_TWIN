"""Schema API D-08 workload_items, beban non-proyek (DIG-30).

Dipisah dari `schemas.py` supaya PR modul Data yang berjalan paralel tidak saling bentrok.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.data.enums import WORKLOAD_ITEM_ID_PATTERN, Severity, WorkloadItemType
from app.modules.data.schemas import IsoDate, ProjectId, ResourceId

WorkloadItemId = Annotated[str, StringConstraints(pattern=WORKLOAD_ITEM_ID_PATTERN)]
WorkloadStatus = Literal["waiting", "in_progress", "resolved"]


class WorkloadItemFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    item_type: WorkloadItemType
    related_project_id: ProjectId | None = None
    received_date: IsoDate
    started_date: IsoDate | None = None
    resolved_date: IsoDate | None = None
    severity: Severity | None = None
    is_hotfix: bool = Field(default=False, strict=True)


class WorkloadItemCreate(WorkloadItemFields):
    """Body POST. `item_id` boleh dikosongkan; server mengisi WLI-xxxx berikutnya."""

    item_id: WorkloadItemId | None = None


class WorkloadItemUpdate(BaseModel):
    """Body PATCH. Hanya kolom yang dikirim yang diubah; ID tidak bisa diubah."""

    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId | None = None
    item_type: WorkloadItemType | None = None
    related_project_id: ProjectId | None = None
    received_date: IsoDate | None = None
    started_date: IsoDate | None = None
    resolved_date: IsoDate | None = None
    severity: Severity | None = None
    is_hotfix: bool | None = Field(default=None, strict=True)


class WorkloadItemRead(BaseModel):
    item_id: str
    resource_id: str
    resource_name: str
    item_type: WorkloadItemType
    related_project_id: str | None
    project_name: str | None
    received_date: date
    started_date: date | None
    resolved_date: date | None
    severity: Severity | None
    is_hotfix: bool
    status: WorkloadStatus = Field(
        description=(
            "waiting bila belum dimulai, in_progress bila sudah dimulai, resolved bila selesai"
        )
    )


# Batas berkas impor: 5 MB teks, kira-kira 50 ribu baris D-08.
MAX_IMPORT_CHARS = 5_000_000


class WorkloadImportRequest(BaseModel):
    """Isi berkas CSV D-08 (UTF-8, pemisah koma, baris pertama nama kolom Data Dictionary)."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_IMPORT_CHARS)
    dry_run: bool = Field(
        default=True, strict=True, description="true hanya memeriksa, tanpa menyimpan"
    )


class ImportRowError(BaseModel):
    row: int = Field(description="Nomor baris di berkas, baris judul kolom adalah baris 1")
    item_id: str | None
    field: str | None
    message: str


class WorkloadImportResult(BaseModel):
    dry_run: bool
    applied: bool = Field(description="true bila data benar-benar disimpan")
    total: int
    inserted: int
    updated: int
    error_count: int
    errors: list[ImportRowError] = Field(description="Paling banyak 500 kesalahan pertama")
