"""Endpoint alias identitas anggota antar tool (DIG-111), tabel internal J&C resource_alias.

Router ini dipasang di router modul Data, sehingga path-nya berawalan /data. Semua endpoint
memakai izin Administrator Data (master_data:write), karena alias memuat username dan email
anggota; master_data:read juga dipegang Anggota Tim sehingga terlalu luas.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import Perm

# Diimpor sebagai modul karena router.py mengimpor modul ini saat ia sendiri belum selesai dimuat.
from app.modules.data import resource_alias_service as service
from app.modules.data import router as data_routes
from app.modules.data.enums import RESOURCE_ID_PATTERN, IdentitySource
from app.modules.data.resource_alias_schemas import (
    ResourceAliasCreate,
    ResourceAliasRead,
    ResourceAliasUpdate,
    UnmappedIdentity,
)
from app.modules.data.service import ConflictError, DataValidationError

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Editor = Annotated[AppUser, Depends(require_permission(Perm.MASTER_DATA_WRITE))]
AliasIdPath = Annotated[int, Path(ge=1)]
CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Alias sudah dipetakan ke anggota lain"}}
ALIAS_READ = [Depends(require_permission(Perm.MASTER_DATA_WRITE))]


@router.get(
    "/resource-aliases",
    dependencies=ALIAS_READ,
    response_model=list[ResourceAliasRead],
    summary="Daftar alias identitas anggota",
)
def list_resource_aliases(
    db: Db,
    source: IdentitySource | None = None,
    resource_id: Annotated[str | None, Query(pattern=RESOURCE_ID_PATTERN)] = None,
) -> list[ResourceAliasRead]:
    return service.list_aliases(db, source, resource_id)


@router.get(
    "/resource-aliases/unmapped",
    dependencies=ALIAS_READ,
    response_model=list[UnmappedIdentity],
    summary="Identitas di staging yang belum dipetakan ke anggota",
)
def list_unmapped_identities(
    db: Db, source: IdentitySource | None = None
) -> list[UnmappedIdentity]:
    """Dihitung saat request dari staging, urut kemunculan terbanyak. Saat ini sumbernya hanya
    action Trello (pelaku dan anggota yang ditambah atau dilepas)."""
    return service.list_unmapped(db, source)


@router.post(
    "/resource-aliases",
    response_model=ResourceAliasRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Petakan identitas ke anggota",
)
def create_resource_alias(db: Db, user: Editor, payload: ResourceAliasCreate) -> ResourceAliasRead:
    try:
        return service.create_alias(db, payload, user.user_id)
    except (DataValidationError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc


@router.patch(
    "/resource-aliases/{alias_id}",
    response_model=ResourceAliasRead,
    responses=CONFLICT,
    summary="Ubah anggota atau keterangan sebuah alias",
)
def update_resource_alias(
    db: Db, user: Editor, alias_id: AliasIdPath, payload: ResourceAliasUpdate
) -> ResourceAliasRead:
    try:
        return service.update_alias(db, alias_id, payload, user.user_id)
    except (service.ResourceAliasNotFoundError, DataValidationError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc


@router.delete(
    "/resource-aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus alias; identitasnya kembali ke daftar belum terpetakan",
)
def delete_resource_alias(db: Db, user: Editor, alias_id: AliasIdPath) -> Response:
    try:
        service.delete_alias(db, alias_id)
    except (service.ResourceAliasNotFoundError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
