"""Aturan staging Trello (DIG-143): kartu tanpa kode task atau kode beban non-proyek.

Kode task diambil dari awal nama kartu (`TSK-0001 | ...`, lihat event_log.task_id_from_card).
Kartu tanpa kode tidak bisa dikaitkan ke D-05 atau D-08, sehingga aksinya tidak masuk event log.
Staging Project Plan menyusul setelah DIG-25 masuk main.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.event_log import task_id_from_card
from app.modules.data.quality.engine import (
    PERINGATAN,
    Hit,
    Report,
    Rule,
    SourceRow,
    register,
    run_rules,
)
from app.modules.data.staging_models import StagingTrelloAction

TRELLO_CARDS = "trello_cards"
_WORKLOAD_CODE = re.compile(r"^WLI-[0-9]{4,}\b")


def _missing_code(rows, ctx):
    for row in rows:
        name = row.values.get("card_name", "")
        if not task_id_from_card(name) and not _WORKLOAD_CODE.match(name.strip()):
            yield Hit(row, "card_name", name, "Nama kartu tidak diawali kode TSK- atau WLI-")


register(
    Rule(
        "DQ-TRL-001",
        TRELLO_CARDS,
        "completeness",
        PERINGATAN,
        "Kartu Trello diawali kode task atau kode beban non-proyek",
        _missing_code,
    )
)


def read_trello_cards(db: Session) -> list[SourceRow]:
    """Satu baris per kartu di staging Trello, dengan nama kartu pada aksi terbarunya."""
    latest: dict[str, tuple] = {}
    statement = (
        select(
            StagingTrelloAction.card_id, StagingTrelloAction.card_name, StagingTrelloAction.board_id
        )
        .where(StagingTrelloAction.card_id.is_not(None), StagingTrelloAction.card_name.is_not(None))
        .order_by(StagingTrelloAction.action_date, StagingTrelloAction.action_id)
    )
    for card_id, name, board_id in db.execute(statement):
        latest[card_id] = (name, board_id)
    return [
        SourceRow(None, card_id, {"card_id": card_id, "card_name": name, "board_id": board_id})
        for card_id, (name, board_id) in sorted(latest.items())
    ]


def validate_trello(cards: list[SourceRow], source: str = "trello") -> Report:
    return run_rules({TRELLO_CARDS: cards}, source)
