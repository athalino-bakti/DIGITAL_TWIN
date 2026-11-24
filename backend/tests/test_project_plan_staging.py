"""DIG-113: tabel staging_project_plan dan kolom import_job_id di staging_trello_action,
terhadap PostgreSQL sungguhan."""

import pytest
from sqlalchemy import text

from tests.conftest import REQUIRES_DB
from tests.test_support_tables import violated

pytestmark = REQUIRES_DB

ACTION_ID = "a" * 24
BOARD_ID = "b" * 24


@pytest.fixture
def clean_db(db):
    db.execute(text("TRUNCATE import_job, staging_project_plan, staging_trello_action CASCADE"))
    db.commit()
    return db


def new_job(db, source: str = "project_plan") -> int:
    job_id = db.scalar(
        text(
            "INSERT INTO import_job (source, trigger, status, finished_at) "
            "VALUES (:source, 'manual', 'succeeded', now()) RETURNING job_id"
        ),
        {"source": source},
    )
    db.commit()
    return job_id


def plan_row(job_id, row: int = 2, project_id: str = "PRJ-001") -> str:
    return (
        "INSERT INTO staging_project_plan (import_job_id, row_number, project_id, file_name, raw) "
        f"VALUES ({job_id}, {row}, '{project_id}', 'project_plan_PRJ-001.csv', '{{}}')"
    )


def test_rows_belong_to_one_job_and_row_number(clean_db):
    job = new_job(clean_db)
    clean_db.execute(text(plan_row(job, 2)))
    clean_db.execute(text(plan_row(job, 3)))
    clean_db.commit()
    assert violated(clean_db, plan_row(job, 2)) == "pk_staging_project_plan"
    # Berkas yang sama diunggah ulang menjadi batch baru.
    clean_db.execute(text(plan_row(new_job(clean_db), 2)))
    clean_db.commit()


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (plan_row(999999), "fk_staging_project_plan_import_job_id_import_job"),
        (plan_row("NULL"), None),  # NOT NULL, bukan constraint bernama
    ],
)
def test_rows_need_an_existing_job(clean_db, statement, constraint):
    assert violated(clean_db, statement) == constraint


def test_project_id_format_is_checked_but_not_a_foreign_key(clean_db):
    job = new_job(clean_db)
    assert (
        violated(clean_db, plan_row(job, project_id="PRJ-1"))
        == "ck_staging_project_plan_project_id_format"
    )
    # Proyek yang belum ada di D-01 tetap masuk staging; validator DIG-31 yang menangkapnya.
    clean_db.execute(text(plan_row(job, project_id="PRJ-999")))
    clean_db.commit()


def test_deleting_a_job_removes_its_plan_rows_but_keeps_trello_actions(clean_db):
    plan_job, trello_job = new_job(clean_db), new_job(clean_db, "trello")
    clean_db.execute(text(plan_row(plan_job)))
    clean_db.execute(
        text(
            "INSERT INTO staging_trello_action "
            "(action_id, action_type, action_date, board_id, raw, import_job_id) "
            f"VALUES ('{ACTION_ID}', 'createCard', now(), '{BOARD_ID}', '{{}}', {trello_job})"
        )
    )
    clean_db.commit()

    clean_db.execute(text("DELETE FROM import_job"))
    clean_db.commit()
    assert clean_db.scalar(text("SELECT count(*) FROM staging_project_plan")) == 0
    assert clean_db.execute(
        text("SELECT action_id, import_job_id FROM staging_trello_action")
    ).all() == [(ACTION_ID, None)]
