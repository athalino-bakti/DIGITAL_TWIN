from __future__ import annotations

from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.data.models import Assignment, Dependency, Task
from app.modules.digital_twin.models import Baseline
from app.modules.simulasi.models import SimulationResult, SimulationRun
from app.modules.simulasi.schemas import (
    SimulationMetricItem,
    SimulationRunCreateRequest,
    SimulationRunResponse,
)


def _to_response(run: SimulationRun) -> SimulationRunResponse:
    return SimulationRunResponse.model_validate(run, from_attributes=True)


def create_simulation_run(
    db: Session,
    background_tasks: BackgroundTasks,
    payload: SimulationRunCreateRequest,
) -> SimulationRunResponse:
    baseline = db.get(Baseline, payload.baseline_id)
    if baseline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Baseline tidak ditemukan"
        )

    run = SimulationRun(
        baseline_id=payload.baseline_id,
        name=payload.name,
        status="queued",
        scenario={
            "duration_multiplier": payload.duration_multiplier,
            "additional_allocation_percent": payload.additional_allocation_percent,
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(process_simulation_run, run.id)
    return _to_response(run)


def process_simulation_run(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(SimulationRun, run_id)
        if run is None:
            return

        baseline = db.get(Baseline, run.baseline_id)
        if baseline is None:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.flush()

        duration_multiplier = float(run.scenario.get("duration_multiplier", 1.0))
        additional_allocation = float(run.scenario.get("additional_allocation_percent", 0.0))

        total_duration = (
            db.scalar(
                select(func.coalesce(func.sum(Task.duration_days), 0)).where(
                    Task.project_id == baseline.project_id
                )
            )
            or 0
        )

        resource_load_rows = db.execute(
            select(
                Assignment.resource_id, func.coalesce(func.sum(Assignment.allocation_percent), 0)
            )
            .join(Task, Task.id == Assignment.task_id)
            .where(Task.project_id == baseline.project_id)
            .group_by(Assignment.resource_id)
        ).all()

        overload_count = sum(
            1
            for _resource_id, load in resource_load_rows
            if float(load) + additional_allocation > 100
        )

        hard_dependency_count = (
            db.scalar(
                select(func.count(Dependency.id)).where(
                    Dependency.project_id == baseline.project_id,
                    Dependency.kind == "hard",
                )
            )
            or 0
        )

        adjusted_duration = float(total_duration) * duration_multiplier

        metrics = {
            "total_duration_days": adjusted_duration,
            "overload_count": float(overload_count),
            "hard_dependency_count": float(hard_dependency_count),
        }

        db.query(SimulationResult).filter(SimulationResult.run_id == run.id).delete()
        for key, value in metrics.items():
            db.add(
                SimulationResult(
                    run_id=run.id,
                    metric_key=key,
                    metric_value=float(value),
                    details={"source": "simulation_v1"},
                )
            )

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()


def get_simulation_run(db: Session, run_id: int) -> SimulationRunResponse:
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run simulasi tidak ditemukan"
        )
    return _to_response(run)


def get_simulation_results(db: Session, run_id: int) -> list[SimulationMetricItem]:
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run simulasi tidak ditemukan"
        )

    results = db.scalars(
        select(SimulationResult)
        .where(SimulationResult.run_id == run_id)
        .order_by(SimulationResult.metric_key.asc())
    ).all()
    return [SimulationMetricItem.model_validate(item, from_attributes=True) for item in results]
