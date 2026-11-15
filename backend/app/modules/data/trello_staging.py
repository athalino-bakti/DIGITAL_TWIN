"""Simpan hasil parser Trello (DIG-118) ke tabel staging (DIG-117).

Fungsi di sini tidak melakukan commit; pemanggil (endpoint impor atau skrip) yang menentukan
batas transaksi.
"""

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.trello.parser import TrelloParseResult
from app.modules.data.staging_models import StagingTrelloAction, TrelloListMapping


@dataclass(frozen=True)
class TrelloSaveSummary:
    inserted: int
    already_present: int
    lists_seen: int


def save_trello_import(db: Session, result: TrelloParseResult) -> TrelloSaveSummary:
    """Tambahkan action baru ke staging dan daftarkan list papan ke trello_list_mapping.

    Action yang id-nya sudah ada (ekspor tumpang tindih atau impor ulang lewat API) tidak
    ditimpa: impor pertama yang menang. Untuk list, hanya nama yang diperbarui; status dan
    phase hasil pemetaan (DIG-120) tidak pernah diubah di sini.
    """
    inserted = 0
    if result.actions:
        statement = (
            insert(StagingTrelloAction)
            .on_conflict_do_nothing(index_elements=["action_id"])
            .returning(StagingTrelloAction.action_id)
        )
        inserted = len(db.execute(statement, result.actions).all())

    if result.lists:
        statement = insert(TrelloListMapping).values(
            [
                {"board_id": result.board_id, "list_id": list_id, "list_name": name}
                for list_id, name in result.lists
            ]
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["board_id", "list_id"],
                set_={"list_name": statement.excluded.list_name, "updated_at": func.now()},
                where=TrelloListMapping.list_name != statement.excluded.list_name,
            )
        )

    return TrelloSaveSummary(
        inserted=inserted,
        already_present=len(result.actions) - inserted,
        lists_seen=len(result.lists),
    )
