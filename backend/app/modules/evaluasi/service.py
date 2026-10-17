from __future__ import annotations

from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.data.models import Assignment, Task
from app.modules.digital_twin.models import Baseline
from app.modules.evaluasi.models import EvaluationResult
from app.modules.evaluasi.schemas import EvaluationCreateRequest, EvaluationResponse
from app.modules.simulasi.models import SimulationResult, SimulationRun


def _to_response(item: EvaluationResult) -> EvaluationResponse:
    return EvaluationResponse.model_validate(item, from_attributes=True)


def create_evaluation(
    db: Session,
    background_tasks: BackgroundTasks,
    payload: EvaluationCreateRequest,
) -> EvaluationResponse:
    baseline = db.get(Baseline, payload.baseline_id)
    if baseline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Baseline tidak ditemukan"
        )

    run = db.get(SimulationRun, payload.run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run simulasi tidak ditemukan"
        )

    if run.baseline_id != baseline.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run simulasi tidak sesuai baseline",
        )

    report = EvaluationResult(
        baseline_id=baseline.id,
        run_id=run.id,
        status="queued",
        kpi={},
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    background_tasks.add_task(process_evaluation, report.id)
    return _to_response(report)


def process_evaluation(report_id: int) -> None:
    with SessionLocal() as db:
        report = db.get(EvaluationResult, report_id)
        if report is None:
            return

        baseline = db.get(Baseline, report.baseline_id)
        run = db.get(SimulationRun, report.run_id)
        if baseline is None or run is None:
            report.status = "failed"
            report.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        baseline_duration = (
            db.scalar(
                select(func.coalesce(func.sum(Task.duration_days), 0)).where(
                    Task.project_id == baseline.project_id
                )
            )
            or 0
        )

        simulation_metrics = db.scalars(
            select(SimulationResult).where(SimulationResult.run_id == run.id)
        ).all()
        metric_map = {item.metric_key: float(item.metric_value) for item in simulation_metrics}

        simulated_duration = metric_map.get("total_duration_days", float(baseline_duration))
        delay_days = simulated_duration - float(baseline_duration)

        avg_utilization = (
            db.scalar(
                select(func.coalesce(func.avg(Assignment.allocation_percent), 0))
                .join(Task, Task.id == Assignment.task_id)
                .where(Task.project_id == baseline.project_id)
            )
            or 0
        )

        overload_count = metric_map.get("overload_count", 0.0)
        ranking_score = max(0.0, 100.0 - max(0.0, delay_days) * 2.0 - overload_count * 5.0)

        report.status = "completed"
        report.kpi = {
            "baseline_duration_days": float(baseline_duration),
            "simulated_duration_days": simulated_duration,
            "delay_days": delay_days,
            "overload_count": overload_count,
            "avg_utilization_percent": float(avg_utilization),
        }
        report.ranking_score = ranking_score
        report.finished_at = datetime.now(timezone.utc)
        db.commit()


def get_evaluation(db: Session, evaluation_id: int) -> EvaluationResponse:
    report = db.get(EvaluationResult, evaluation_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hasil evaluasi tidak ditemukan",
        )
    return _to_response(report)
