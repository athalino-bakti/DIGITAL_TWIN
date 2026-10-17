from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class UploadSummary(BaseModel):
    id: int
    source_filename: str
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    created_at: datetime
    processed_at: datetime | None


class ValidationErrorItem(BaseModel):
    row_number: int
    message: str
    raw_data: str


class UploadDetail(UploadSummary):
    errors: list[ValidationErrorItem]


class ProjectItem(BaseModel):
    id: int
    name: str
    created_at: datetime


class ResourceItem(BaseModel):
    id: int
    name: str
    role: str
    capacity_hours_per_week: float


class TaskItem(BaseModel):
    id: int
    project_id: int
    name: str
    start_date: date
    end_date: date
    duration_days: int
    priority: int
    status: str
