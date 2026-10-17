from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.evaluasi.schemas import EvaluationCreateRequest, EvaluationResponse
from app.modules.evaluasi.service import create_evaluation, get_evaluation

router = APIRouter(prefix="/evaluasi", tags=["Evaluasi"])


@router.post("/reports", response_model=EvaluationResponse, status_code=201)
def create_report(
    payload: EvaluationCreateRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> EvaluationResponse:
    return create_evaluation(db, background_tasks, payload)


@router.get("/reports/{evaluation_id}", response_model=EvaluationResponse)
def get_report(
    evaluation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> EvaluationResponse:
    return get_evaluation(db, evaluation_id)
