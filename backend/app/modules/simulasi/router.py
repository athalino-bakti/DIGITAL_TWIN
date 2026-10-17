from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.simulasi.schemas import (
    SimulationMetricItem,
    SimulationRunCreateRequest,
    SimulationRunResponse,
)
from app.modules.simulasi.service import (
    create_simulation_run,
    get_simulation_results,
    get_simulation_run,
)

router = APIRouter(prefix="/simulasi", tags=["Simulasi"])


@router.post("/runs", response_model=SimulationRunResponse, status_code=201)
def create_run(
    payload: SimulationRunCreateRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> SimulationRunResponse:
    return create_simulation_run(db, background_tasks, payload)


@router.get("/runs/{run_id}", response_model=SimulationRunResponse)
def get_run(run_id: int, db: Annotated[Session, Depends(get_db)]) -> SimulationRunResponse:
    return get_simulation_run(db, run_id)


@router.get("/runs/{run_id}/results", response_model=list[SimulationMetricItem])
def get_run_results(
    run_id: int, db: Annotated[Session, Depends(get_db)]
) -> list[SimulationMetricItem]:
    return get_simulation_results(db, run_id)
