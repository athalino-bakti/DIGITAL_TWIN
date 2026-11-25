"""Schema API alias identitas anggota (DIG-111). Tabel internal J&C, bukan Data Dictionary."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.core.privacy import mask_email
from app.modules.data.enums import IdentitySource
from app.modules.data.schemas import ResourceId

AliasText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
AliasRef = Annotated[str, StringConstraints(pattern=r"^ref-[0-9a-f]{32}$")]


class ResourceAliasCreate(BaseModel):
    """Body POST. `alias` berisi id member untuk trello, email untuk teamgit, dan nama PIC
    untuk project_plan. Pencocokan memakai bentuk ternormalisasinya (`alias_key`).

    Saat memetakan identitas dari daftar belum terpetakan, kirim `alias_ref` dari daftar itu.
    Server mengambil nilai aslinya sendiri, karena email teamgit hanya dikirim tersamar
    (DIG-95); `alias` boleh berisi bentuk tersamar tersebut dan diabaikan."""

    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    source: IdentitySource
    alias: AliasText
    alias_ref: AliasRef | None = None
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

    @model_validator(mode="after")
    def hide_email(self) -> "ResourceAliasRead":
        """Email author commit tidak pernah dikirim apa adanya (DIG-95)."""
        if self.source is IdentitySource.TEAMGIT:
            self.alias = mask_email(self.alias)
            self.alias_key = mask_email(self.alias_key)
        return self


class UnmappedIdentity(BaseModel):
    """Identitas yang muncul di staging tetapi belum punya baris di resource_alias.

    Untuk teamgit, `alias` tersamar dan `alias_key` diganti `alias_ref` (DIG-95). Kirim
    `alias_ref` di POST /resource-aliases untuk memetakannya tanpa membuka emailnya.
    """

    source: IdentitySource
    alias_key: str
    alias_ref: str
    alias: str
    username: str | None
    display_name: str | None
    occurrences: int
    last_seen: datetime
