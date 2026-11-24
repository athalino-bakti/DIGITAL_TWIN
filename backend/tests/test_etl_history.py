"""DIG-132: derivasi actual_start, actual_finish, dan qa_reject_count dari riwayat Trello."""

from datetime import UTC, datetime

from app.modules.data.etl.history import History, apply_history, derive_history
from app.modules.data.etl.normalize import Candidates, TrelloMove
from app.modules.data.quality.engine import SourceRow

BOARD = "b" * 24
MAPPING = {
    (BOARD, "TODO"): ("not_started", None),
    (BOARD, "DOING"): ("in_progress", "be_dev"),
    (BOARD, "BLOCK"): ("blocked", None),
    (BOARD, "QA"): ("in_qa", "testing"),
    (BOARD, "DONE"): ("done", None),
}


def move(list_id, day, hour=3, card="TSK-0001 | API cuti"):
    # 03.00 UTC = 10.00 WIB; 20.00 UTC = 03.00 WIB hari berikutnya.
    return TrelloMove(card, BOARD, list_id, datetime(2026, 11, day, hour, tzinfo=UTC))


def test_full_flow_with_one_qa_rejection():
    history = derive_history(
        [
            move("TODO", 2),
            move("DOING", 3),
            move("QA", 5),
            move("DOING", 6),  # dikembalikan dari QA
            move("QA", 7),
            move("DONE", 9),
        ],
        MAPPING,
    )
    assert history["TSK-0001"] == History("2026-11-03", "2026-11-09", 1)


def test_dates_use_wib():
    history = derive_history([move("DOING", 3, hour=20), move("DONE", 4, hour=20)], MAPPING)
    assert history["TSK-0001"] == History("2026-11-04", "2026-11-05", 0)


def test_card_moved_straight_to_qa_counts_as_started():
    assert derive_history([move("TODO", 2), move("QA", 4)], MAPPING)["TSK-0001"].actual_start == (
        "2026-11-04"
    )


def test_reopened_card_has_no_finish_and_later_done_wins():
    reopened = derive_history([move("DOING", 3), move("DONE", 4), move("DOING", 5)], MAPPING)
    assert reopened["TSK-0001"].actual_finish == ""
    done_again = derive_history(
        [move("DOING", 3), move("DONE", 4), move("DOING", 5), move("DONE", 8)], MAPPING
    )
    assert done_again["TSK-0001"].actual_finish == "2026-11-08"


def test_qa_to_blocked_counts_but_qa_to_done_or_todo_does_not():
    history = derive_history(
        [move("QA", 3), move("BLOCK", 4), move("QA", 5), move("TODO", 6), move("QA", 7)], MAPPING
    )
    assert history["TSK-0001"].qa_reject_count == 1


def test_unmapped_lists_and_cards_without_code_are_skipped():
    history = derive_history(
        [
            move("QA", 3),
            move("ARSIP", 4),  # belum dipetakan: dilewati
            move("DOING", 5),
            move("DOING", 5, card="Kartu tanpa kode"),
        ],
        MAPPING,
    )
    assert set(history) == {"TSK-0001"}
    assert history["TSK-0001"].qa_reject_count == 1


def test_not_started_card_has_no_dates():
    assert derive_history([move("TODO", 2)], MAPPING)["TSK-0001"] == History("", "", 0)


def task_row(task_id, **values):
    base = {"task_id": task_id, "actual_start": "", "actual_finish": "", "qa_reject_count": "0"}
    return SourceRow(2, task_id, base | values)


def test_apply_fills_only_empty_plan_dates_and_sets_reject_count():
    candidates = Candidates()
    candidates.tables["tasks"] = [
        task_row("TSK-0001", actual_start="2026-11-01"),  # Project Plan sudah mengisi
        task_row("TSK-0002"),  # tanpa kartu Trello
    ]
    applied = apply_history(candidates, {"TSK-0001": History("2026-11-03", "2026-11-09", 2)})
    first, second = (r.values for r in applied.tables["tasks"])
    assert (first["actual_start"], first["actual_finish"], first["qa_reject_count"]) == (
        "2026-11-01",
        "2026-11-09",
        "2",
    )
    assert (second["actual_start"], second["qa_reject_count"]) == ("", "0")
    assert candidates.tables["tasks"][0].values["actual_finish"] == ""  # masukan tidak diubah
