import io

from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.data.models import Dependency, Project, Resource, Task
from app.modules.data.service import create_upload
from app.modules.digital_twin.schemas import BaselineCreateRequest
from app.modules.digital_twin.service import create_baseline, get_timeline


CSV_CONTENT = """project_name,task_name,task_start_date,task_end_date,duration_days,priority,resource_name,resource_role,allocation_percent,predecessor_task,dependency_kind
Project A,Task 1,2026-01-01,2026-01-03,3,2,Alice,Engineer,50,,
Project A,Task 2,2026-01-04,2026-01-06,3,3,Bob,QA,60,Task 1,hard
"""


def make_db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)


def test_create_upload_persists_master_data():
    db = make_db_session()
    file = UploadFile(filename="dataset.csv", file=io.BytesIO(CSV_CONTENT.encode("utf-8")))

    summary = create_upload(db, file)

    assert summary.status == "completed"
    assert summary.accepted_rows == 2
    assert summary.rejected_rows == 0
    assert db.query(Project).count() == 1
    assert db.query(Task).count() == 2
    assert db.query(Resource).count() == 2
    assert db.query(Dependency).count() == 1


def test_create_baseline_and_timeline():
    db = make_db_session()
    file = UploadFile(filename="dataset.csv", file=io.BytesIO(CSV_CONTENT.encode("utf-8")))
    create_upload(db, file)
    project = db.query(Project).first()

    baseline = create_baseline(db, BaselineCreateRequest(project_id=project.id, name="Baseline test"))
    timeline = get_timeline(db, baseline.id)

    assert baseline.project_id == project.id
    assert len(timeline) == 2
    assert timeline[0].task_name == "Task 1"
