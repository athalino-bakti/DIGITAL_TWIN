from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from app.modules.data.models import Assignment, Dependency, Project, Resource, Task
from app.modules.digital_twin.models import Baseline
from app.modules.digital_twin.schemas import (
    BaselineCreateRequest,
    BaselineResponse,
    DependencyItem,
    ResourceLoadItem,
    TimelineItem,
)


def create_baseline(db: Session, payload: BaselineCreateRequest) -> BaselineResponse:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project tidak ditemukan")

    task_exists = db.scalar(select(Task.id).where(Task.project_id == payload.project_id).limit(1))
    if task_exists is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project belum memiliki task untuk baseline",
        )

    baseline = Baseline(project_id=payload.project_id, name=payload.name, status="ready")
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return BaselineResponse.model_validate(baseline, from_attributes=True)


def get_timeline(db: Session, baseline_id: int) -> list[TimelineItem]:
    baseline = db.get(Baseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Baseline tidak ditemukan")

    tasks = db.scalars(
        select(Task)
        .where(Task.project_id == baseline.project_id)
        .order_by(Task.start_date.asc(), Task.id.asc())
    ).all()
    return [
        TimelineItem(
            task_id=item.id,
            task_name=item.name,
            start_date=item.start_date,
            end_date=item.end_date,
            duration_days=item.duration_days,
            priority=item.priority,
        )
        for item in tasks
    ]


def get_resource_load(db: Session, baseline_id: int) -> list[ResourceLoadItem]:
    baseline = db.get(Baseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Baseline tidak ditemukan")

    rows = db.execute(
        select(
            Resource.id,
            Resource.name,
            Assignment.allocation_percent,
        )
        .join(Assignment, Assignment.resource_id == Resource.id)
        .join(Task, Task.id == Assignment.task_id)
        .where(Task.project_id == baseline.project_id)
    ).all()

    grouped: dict[int, ResourceLoadItem] = {}
    for resource_id, resource_name, allocation in rows:
        entry = grouped.get(resource_id)
        if entry is None:
            entry = ResourceLoadItem(
                resource_id=resource_id,
                resource_name=resource_name,
                total_allocation_percent=0,
            )
            grouped[resource_id] = entry
        entry.total_allocation_percent += allocation
    return sorted(grouped.values(), key=lambda item: item.resource_name)


def get_dependencies(db: Session, baseline_id: int) -> list[DependencyItem]:
    baseline = db.get(Baseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Baseline tidak ditemukan")

    predecessor_task = aliased(Task)
    successor_task = aliased(Task)
    rows = db.execute(
        select(
            Dependency.predecessor_task_id,
            predecessor_task.name,
            Dependency.successor_task_id,
            successor_task.name,
            Dependency.kind,
        )
        .join(predecessor_task, predecessor_task.id == Dependency.predecessor_task_id)
        .join(successor_task, successor_task.id == Dependency.successor_task_id)
        .where(Dependency.project_id == baseline.project_id)
    ).all()

    return [
        DependencyItem(
            predecessor_task_id=predecessor_id,
            predecessor_task_name=predecessor_name,
            successor_task_id=successor_id,
            successor_task_name=successor_name,
            kind=kind,
        )
        for predecessor_id, predecessor_name, successor_id, successor_name, kind in rows
    ]
