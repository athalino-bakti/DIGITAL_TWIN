"""Pemetaan list Trello ke status dan phase task (DIG-120), tabel internal J&C.

Baris `trello_list_mapping` dibuat oleh impor Trello (`trello_staging.save_trello_import`), jadi
endpoint di sini hanya membaca dan mengubah status/phase; list tidak dibuat atau dihapus manual.
Event log (DIG-37) memakai status hasil pemetaan ini untuk aktivitas "Pindah ke <status>", jadi
setelah pemetaan diubah event log perlu dibentuk ulang (`POST /data/event-log/rebuild`).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.data.enums import TaskPhase, TaskStatus
from app.modules.data.service import NotFoundError, commit
from app.modules.data.staging_models import StagingTrelloAction, TrelloListMapping


class TrelloListNotFoundError(NotFoundError):
    label = "List Trello"


class TrelloListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    board_id: str
    board_name: str | None
    list_id: str
    list_name: str
    status: TaskStatus | None
    phase: TaskPhase | None
    updated_at: datetime
    # Jumlah action staging yang menyentuh list ini (kartu masuk, keluar, atau dibuat di sana),
    # supaya admin tahu list mana yang paling berpengaruh ke event log.
    actions: int
    last_seen: datetime | None


class TrelloListUpdate(BaseModel):
    """Body PATCH. Kirim null untuk mengosongkan pemetaan; field yang tidak dikirim tetap."""

    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    phase: TaskPhase | None = None


def _usage(db: Session) -> dict[tuple[str, str], tuple[int, datetime]]:
    touched = or_(
        StagingTrelloAction.list_after_id == TrelloListMapping.list_id,
        StagingTrelloAction.list_before_id == TrelloListMapping.list_id,
    )
    rows = db.execute(
        select(
            TrelloListMapping.board_id,
            TrelloListMapping.list_id,
            func.count(StagingTrelloAction.action_id),
            func.max(StagingTrelloAction.action_date),
        )
        .join(
            StagingTrelloAction,
            (StagingTrelloAction.board_id == TrelloListMapping.board_id) & touched,
        )
        .group_by(TrelloListMapping.board_id, TrelloListMapping.list_id)
    )
    return {(board, list_id): (n, seen) for board, list_id, n, seen in rows}


def _board_names(db: Session) -> dict[str, str]:
    """Nama papan dari action terbaru yang membawanya (`data.board.name` di JSON Trello)."""
    name = StagingTrelloAction.raw[("data", "board", "name")].astext
    rows = db.execute(
        select(StagingTrelloAction.board_id, name)
        .where(name.is_not(None))
        .distinct(StagingTrelloAction.board_id)
        .order_by(StagingTrelloAction.board_id, StagingTrelloAction.action_date.desc())
    )
    return {board: board_name for board, board_name in rows}


def _read(row: TrelloListMapping, usage, boards) -> TrelloListRead:
    actions, seen = usage.get((row.board_id, row.list_id), (0, None))
    return TrelloListRead(
        board_id=row.board_id,
        board_name=boards.get(row.board_id),
        list_id=row.list_id,
        list_name=row.list_name,
        status=row.status,
        phase=row.phase,
        updated_at=row.updated_at,
        actions=actions,
        last_seen=seen,
    )


def list_mappings(db: Session, unmapped_only: bool = False) -> list[TrelloListRead]:
    statement = select(TrelloListMapping).order_by(
        TrelloListMapping.board_id, TrelloListMapping.list_name, TrelloListMapping.list_id
    )
    if unmapped_only:
        statement = statement.where(TrelloListMapping.status.is_(None))
    usage, boards = _usage(db), _board_names(db)
    return [_read(row, usage, boards) for row in db.scalars(statement)]


def update_mapping(
    db: Session, board_id: str, list_id: str, payload: TrelloListUpdate
) -> TrelloListRead:
    row = db.get(TrelloListMapping, (board_id, list_id))
    if row is None:
        raise TrelloListNotFoundError
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, None if value is None else str(value))
    if changes:
        row.updated_at = func.now()
    commit(db)
    db.refresh(row)
    return _read(row, _usage(db), _board_names(db))
