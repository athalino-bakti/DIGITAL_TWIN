"""Endpoint pemetaan list Trello (DIG-120). Dipasang di router modul Data (berawalan /data).

Pemetaan adalah konfigurasi impor Trello, jadi izinnya import:run (Administrator Data), sama
dengan membentuk ulang event log yang memakai hasilnya.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data import trello_list_mapping as service
from app.modules.data.staging_models import TRELLO_ID_PATTERN
from app.modules.data.trello_list_mapping import TrelloListRead, TrelloListUpdate

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
TrelloIdPath = Annotated[str, Path(pattern=TRELLO_ID_PATTERN)]
IMPORT = [Depends(require_permission(Perm.IMPORT_RUN))]


@router.get(
    "/trello-lists",
    dependencies=IMPORT,
    response_model=list[TrelloListRead],
    summary="Daftar list Trello beserta pemetaan status dan phase",
)
def list_trello_lists(db: Db, unmapped_only: bool = False) -> list[TrelloListRead]:
    return service.list_mappings(db, unmapped_only)


@router.patch(
    "/trello-lists/{board_id}/{list_id}",
    dependencies=IMPORT,
    response_model=TrelloListRead,
    summary="Ubah status dan phase hasil pemetaan sebuah list Trello",
)
def update_trello_list(
    db: Db, board_id: TrelloIdPath, list_id: TrelloIdPath, payload: TrelloListUpdate
) -> TrelloListRead:
    # Diimpor di sini karena router.py mengimpor modul ini saat ia sendiri belum selesai dimuat.
    from app.modules.data.router import to_http

    try:
        return service.update_mapping(db, board_id, list_id, payload)
    except service.TrelloListNotFoundError as exc:
        raise to_http(exc) from exc
