from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.digital_twin.schemas import (
    BaselineCreateRequest,
    BaselineResponse,
    DependencyItem,
    ResourceLoadItem,
    TimelineItem,
)
from app.modules.digital_twin.service import create_baseline, get_dependencies, get_resource_load, get_timeline

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])


@router.post("/baselines", response_model=BaselineResponse, status_code=201)
def create_digital_twin_baseline(
    payload: BaselineCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> BaselineResponse:
    return create_baseline(db, payload)


@router.get("/{baseline_id}/timeline", response_model=list[TimelineItem])
def get_digital_twin_timeline(
    baseline_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[TimelineItem]:
    return get_timeline(db, baseline_id)


@router.get("/{baseline_id}/resource-load", response_model=list[ResourceLoadItem])
def get_digital_twin_resource_load(
    baseline_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[ResourceLoadItem]:
    return get_resource_load(db, baseline_id)


@router.get("/{baseline_id}/dependencies", response_model=list[DependencyItem])
def get_digital_twin_dependencies(
    baseline_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[DependencyItem]:
    return get_dependencies(db, baseline_id)
