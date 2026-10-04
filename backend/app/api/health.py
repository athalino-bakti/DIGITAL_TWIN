from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(HealthResponse):
    database: Literal["connected"] = "connected"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness API tanpa memerlukan koneksi database."""
    return HealthResponse()


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
    """Readiness: uji koneksi PostgreSQL tanpa membuat tabel bisnis."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database belum tersedia",
        ) from exc
    return ReadinessResponse()
