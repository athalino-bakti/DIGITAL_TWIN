"""DIG-193: GET /api/v1/data/final-sources.zip berisi 11 CSV sesuai Data Dictionary."""

import csv
import io
import zipfile
from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.db.base import Base
from synthetic import reference as ref
from synthetic.final_sources import write_final_sources
from synthetic.load import load
from synthetic.world import build_world
from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB

URL = "/api/v1/data/final-sources.zip"
SEED, AS_OF = 42, date(2026, 11, 6)


@pytest.fixture
def exported(client, db):
    load(db.connection(), SEED, AS_OF)
    db.commit()
    response = client.get(URL)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(response.content))


def read(archive, name) -> list[list[str]]:
    return list(csv.reader(io.StringIO(archive.read(f"{name}.csv").decode("utf-8"))))


def test_eleven_files_with_data_dictionary_headers(exported):
    assert sorted(exported.namelist()) == sorted(f"{name}.csv" for name in ref.HEADERS)
    for name, header in ref.HEADERS.items():
        assert read(exported, name)[0] == header, name


def test_row_counts_match_the_tables(db, exported):
    for name in ref.HEADERS:
        rows = db.scalar(select(func.count()).select_from(Base.metadata.tables[name]))
        assert len(read(exported, name)) - 1 == rows, name


def test_content_equals_the_generator_csv(exported, tmp_path):
    # Data yang sama dari generator (DIG-81): ekspor harus menghasilkan CSV yang identik.
    write_final_sources(build_world(SEED, AS_OF), tmp_path)
    for name in ref.HEADERS:
        expected = list(csv.reader((tmp_path / f"{name}.csv").open(encoding="utf-8")))
        assert sorted(read(exported, name)[1:]) == sorted(expected[1:]), name


def test_formula_like_text_is_exported_raw(client, db, exported):
    task_id = db.scalar(text("SELECT task_id FROM tasks ORDER BY task_id LIMIT 1"))
    db.execute(text("UPDATE tasks SET task_name = '=SUM(A1)' WHERE task_id = :t"), {"t": task_id})
    db.commit()
    archive = zipfile.ZipFile(io.BytesIO(client.get(URL).content))
    header, *rows = read(archive, "tasks")
    names = {row[0]: row[header.index("task_name")] for row in rows}
    # ZIP dibaca program tWinner: nilai mentah, tanpa awalan ' (DATA_CONTRACT bagian 4).
    assert names[task_id] == "=SUM(A1)"


def test_requires_data_quality_read(client, db):
    from tests.conftest import make_token

    token = make_token(db, "anggota", ["anggota_tim"])
    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
