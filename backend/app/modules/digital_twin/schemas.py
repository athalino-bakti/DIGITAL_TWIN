from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class BaselineCreateRequest(BaseModel):
    project_id: int
    name: str = "Baseline Otomatis"


class BaselineResponse(BaseModel):
    id: int
    project_id: int
    name: str
    status: str
    created_at: datetime


class TimelineItem(BaseModel):
    task_id: int
    task_name: str
    start_date: date
    end_date: date
    duration_days: int
    priority: int


class ResourceLoadItem(BaseModel):
    resource_id: int
    resource_name: str
    total_allocation_percent: float


class DependencyItem(BaseModel):
    predecessor_task_id: int
    predecessor_task_name: str
    successor_task_id: int
    successor_task_name: str
    kind: str
