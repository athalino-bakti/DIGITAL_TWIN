"""Alias identitas anggota antar tool dan daftar identitas belum terpetakan (DIG-111).

`alias_key` adalah satu-satunya aturan normalisasi. Endpoint, daftar belum terpetakan, dan
entity resolution ETL (DIG-131) semuanya memakainya, supaya identitas yang sama selalu
menghasilkan kunci yang sama.

Daftar belum terpetakan dihitung saat request dari staging. Tiap sumber punya satu pengumpul di
`COLLECTORS`; Project Plan (DIG-113) dan TeamGit (DIG-121) cukup menambah pengumpulnya sendiri
tanpa mengubah endpoint.
"""

import hmac
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.privacy import alias_ref, mask_email
from app.modules.data.enums import IdentitySource
from app.modules.data.event_log import _assigned_member
from app.modules.data.models import Resource
from app.modules.data.resource_alias_models import ResourceAlias
from app.modules.data.resource_alias_schemas import (
    ResourceAliasCreate,
    ResourceAliasRead,
    ResourceAliasUpdate,
    UnmappedIdentity,
)
from app.modules.data.service import (
    ConflictError,
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
)
from app.modules.data.staging_models import TRELLO_ID_PATTERN, StagingTrelloAction

_TRELLO_ID = re.compile(TRELLO_ID_PATTERN)
ASSIGNMENT_TYPES = ("addMemberToCard", "removeMemberFromCard")


class ResourceAliasNotFoundError(NotFoundError):
    label = "Alias identitas"


def alias_key(source: IdentitySource | str, value: str) -> str:
    """Bentuk ternormalisasi untuk pencocokan.

    - trello: id member huruf kecil; ValueError bila bukan 24 heksadesimal.
    - teamgit: email huruf kecil tanpa spasi di tepi.
    - project_plan: nama PIC casefold dengan spasi dirapikan. Varian seperti "Sari P." tetap
      berbeda dari "Sari Puspitasari" dan dipetakan manual; tidak ada pencocokan kabur.
    """
    source = IdentitySource(source)
    if source is IdentitySource.TRELLO:
        key = value.strip().lower()
        if not _TRELLO_ID.match(key):
            raise ValueError("Id member Trello harus 24 karakter heksadesimal")
        return key
    if source is IdentitySource.TEAMGIT:
        return value.strip().lower()
    return " ".join(value.split()).casefold()


# --- CRUD ------------------------------------------------------------------------------------


def list_aliases(
    db: Session, source: IdentitySource | None = None, resource_id: str | None = None
) -> list[ResourceAliasRead]:
    statement = select(ResourceAlias).order_by(ResourceAlias.source, ResourceAlias.alias_key)
    if source is not None:
        statement = statement.where(ResourceAlias.source == source)
    if resource_id is not None:
        statement = statement.where(ResourceAlias.resource_id == resource_id)
    return [ResourceAliasRead.model_validate(row) for row in db.scalars(statement)]


def get_alias(db: Session, alias_id: int) -> ResourceAlias:
    alias = db.get(ResourceAlias, alias_id)
    if alias is None:
        raise ResourceAliasNotFoundError(alias_id)
    return alias


def _ensure_resource(db: Session, resource_id: str) -> None:
    if db.get(Resource, resource_id) is None:
        raise DataValidationError(
            [
                FieldError(
                    "resource_id", f"Anggota {resource_id} tidak terdaftar", "resource_not_found"
                )
            ]
        )


def _ensure_alias_free(db: Session, source: str, key: str) -> None:
    owner = db.scalar(
        select(ResourceAlias.resource_id).where(
            ResourceAlias.source == source, ResourceAlias.alias_key == key
        )
    )
    if owner is not None:
        raise ConflictError(f"Alias {source} ini sudah dipetakan ke {owner}", field="alias")


def _resolve_ref(db: Session, source: IdentitySource, ref: str) -> str:
    """Nilai asli identitas belum terpetakan yang `alias_ref`-nya cocok (DIG-95)."""
    collect = COLLECTORS.get(source)
    for alias, _username, _display_name, _seen in collect(db) if collect else ():
        try:
            key = alias_key(source, alias)
        except ValueError:
            continue
        if hmac.compare_digest(alias_ref(source, key), ref):
            return alias
    raise DataValidationError(
        [FieldError("alias_ref", "Identitas tidak ditemukan atau sudah dipetakan", "alias_ref")]
    )


def create_alias(db: Session, payload: ResourceAliasCreate, user_id: int) -> ResourceAliasRead:
    data = payload.model_dump(exclude={"alias_ref"})
    if payload.alias_ref is not None:
        data["alias"] = _resolve_ref(db, payload.source, payload.alias_ref)
    try:
        key = alias_key(payload.source, data["alias"])
    except ValueError as exc:
        raise DataValidationError([FieldError("alias", str(exc), "alias_format")]) from exc
    _ensure_resource(db, payload.resource_id)
    _ensure_alias_free(db, payload.source, key)
    alias = ResourceAlias(**data, alias_key=key, mapped_by_user_id=user_id)
    db.add(alias)
    commit(db)  # balapan dua permintaan pada alias yang sama tetap menjadi 409
    db.refresh(alias)
    return ResourceAliasRead.model_validate(alias)


def update_alias(
    db: Session, alias_id: int, payload: ResourceAliasUpdate, user_id: int
) -> ResourceAliasRead:
    alias = get_alias(db, alias_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("resource_id") is None:
        changes.pop("resource_id", None)  # resource_id wajib; null berarti tidak diubah
    else:
        _ensure_resource(db, changes["resource_id"])
    for column, value in changes.items():
        setattr(alias, column, value)
    alias.mapped_by_user_id = user_id
    alias.updated_at = func.now()
    commit(db)
    db.refresh(alias)
    return ResourceAliasRead.model_validate(alias)


def delete_alias(db: Session, alias_id: int) -> None:
    db.delete(get_alias(db, alias_id))
    commit(db)


# --- identitas belum terpetakan --------------------------------------------------------------

# (alias asli, username, nama tampilan, waktu terlihat) per kemunculan.
Sighting = tuple[str, str | None, str | None, datetime]


def trello_sightings(db: Session) -> Iterable[Sighting]:
    """Pelaku setiap action, serta anggota yang ditambah atau dilepas dari kartu.

    Akun yang hanya tercatat di `idMembers` kartu atau `members` papan tanpa pernah muncul di
    action tidak ikut, karena keduanya tidak disimpan di staging dan tidak menghasilkan event.
    """
    # ponytail: dihitung di Python dari seluruh staging; cukup untuk ratusan sampai ribuan
    # action. Pindahkan ke SQL (UNION pelaku dan JSONB raw) bila staging membesar.
    rows = db.execute(
        select(
            StagingTrelloAction.action_type,
            StagingTrelloAction.action_date,
            StagingTrelloAction.member_creator_id,
            StagingTrelloAction.member_creator_username,
            StagingTrelloAction.member_creator_full_name,
            StagingTrelloAction.raw,
        )
    )
    for action_type, seen, creator_id, username, full_name, raw in rows:
        if creator_id:
            yield creator_id, username, full_name, seen
        if action_type in ASSIGNMENT_TYPES:
            member_id, name = _assigned_member(raw or {})
            if member_id:
                yield member_id, None, name, seen


COLLECTORS: dict[IdentitySource, Callable[[Session], Iterable[Sighting]]] = {
    IdentitySource.TRELLO: trello_sightings,
}


def list_unmapped(db: Session, source: IdentitySource | None = None) -> list[UnmappedIdentity]:
    """Identitas di staging yang belum punya alias, urut kemunculan terbanyak."""
    result: list[UnmappedIdentity] = []
    for current, collect in COLLECTORS.items():
        if source is not None and current is not source:
            continue
        mapped = set(
            db.scalars(select(ResourceAlias.alias_key).where(ResourceAlias.source == current))
        )
        found: dict[str, dict[str, Any]] = {}
        for alias, username, display_name, seen in collect(db):
            try:
                key = alias_key(current, alias)
            except ValueError:
                continue  # id rusak sudah ditolak parser; jangan sampai menggagalkan daftar
            if key in mapped:
                continue
            item = found.setdefault(
                key,
                {"alias": alias, "username": None, "display_name": None, "n": 0, "last": seen},
            )
            item["n"] += 1
            item["last"] = max(item["last"], seen)
            item["username"] = item["username"] or username
            item["display_name"] = item["display_name"] or display_name
        hidden = current is IdentitySource.TEAMGIT  # email tidak dikirim apa adanya (DIG-95)
        result += [
            UnmappedIdentity(
                source=current,
                alias_key=alias_ref(current, key) if hidden else key,
                alias_ref=alias_ref(current, key),
                alias=mask_email(item["alias"]) if hidden else item["alias"],
                username=item["username"],
                display_name=item["display_name"],
                occurrences=item["n"],
                last_seen=item["last"],
            )
            for key, item in found.items()
        ]
    return sorted(result, key=lambda i: (-i.occurrences, i.source, i.alias_key))
