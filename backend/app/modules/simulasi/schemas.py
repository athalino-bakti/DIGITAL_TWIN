from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SimulationRunCreateRequest(BaseModel):
    baseline_id: int
    name: str = "Skenario simulasi"
    duration_multiplier: float = Field(default=1.0, gt=0)
    additional_allocation_percent: float = 0.0


class SimulationRunResponse(BaseModel):
    id: int
    baseline_id: int
    name: str
    status: str
    scenario: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SimulationMetricItem(BaseModel):
    metric_key: str
    metric_value: float
    details: dict[str, Any]
