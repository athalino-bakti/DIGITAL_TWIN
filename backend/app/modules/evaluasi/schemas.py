from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EvaluationCreateRequest(BaseModel):
    baseline_id: int
    run_id: int


class EvaluationResponse(BaseModel):
    id: int
    baseline_id: int
    run_id: int
    status: str
    kpi: dict[str, Any]
    ranking_score: float
    created_at: datetime
    finished_at: datetime | None
