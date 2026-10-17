from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.data.schemas import (
    ProjectItem,
    ResourceItem,
    TaskItem,
    UploadDetail,
    UploadSummary,
)
from app.modules.data.service import (
    create_upload,
    get_upload_detail,
    list_projects,
    list_resources,
    list_tasks,
)

router = APIRouter(prefix="/data", tags=["Data"])


@router.post("/uploads", response_model=UploadSummary, status_code=201)
def upload_dataset(
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> UploadSummary:
    return create_upload(db, file)


@router.get("/uploads/{upload_id}", response_model=UploadDetail)
def get_upload(upload_id: int, db: Annotated[Session, Depends(get_db)]) -> UploadDetail:
    return get_upload_detail(db, upload_id)


@router.get("/master/projects", response_model=list[ProjectItem])
def get_projects(db: Annotated[Session, Depends(get_db)]) -> list[ProjectItem]:
    return list_projects(db)


@router.get("/master/resources", response_model=list[ResourceItem])
def get_resources(db: Annotated[Session, Depends(get_db)]) -> list[ResourceItem]:
    return list_resources(db)


@router.get("/master/tasks", response_model=list[TaskItem])
def get_tasks(db: Annotated[Session, Depends(get_db)]) -> list[TaskItem]:
    return list_tasks(db)
