"""Schema API alias identitas anggota (DIG-111). Tabel internal J&C, bukan Data Dictionary."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.modules.data.enums import IdentitySource
from app.modules.data.schemas import ResourceId

AliasText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ResourceAliasCreate(BaseModel):
    """Body POST. `alias` berisi id member untuk trello, email untuk teamgit, dan nama PIC
    untuk project_plan. Pencocokan memakai bentuk ternormalisasinya (`alias_key`)."""

    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    source: IdentitySource
    alias: AliasText
    username: Username | None = None
    display_name: AliasText | None = None


class ResourceAliasUpdate(BaseModel):
    """Body PATCH. Sumber dan alias tidak bisa diubah: hapus lalu buat alias baru."""

    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId | None = None
    username: Username | None = None
    display_name: AliasText | None = None


class ResourceAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alias_id: int
    resource_id: str
    source: IdentitySource
    alias: str
    alias_key: str
    username: str | None
    display_name: str | None
    mapped_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class UnmappedIdentity(BaseModel):
    """Identitas yang muncul di staging tetapi belum punya baris di resource_alias."""

    source: IdentitySource
    alias_key: str
    alias: str
    username: str | None
    display_name: str | None
    occurrences: int
    last_seen: datetime
