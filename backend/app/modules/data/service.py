from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.models import Assignment, DataUpload, Dependency, Project, Resource, Task, ValidationError
from app.modules.data.schemas import (
    ProjectItem,
    ResourceItem,
    TaskItem,
    UploadDetail,
    UploadSummary,
    ValidationErrorItem,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
REQUIRED_COLUMNS = {
    "project_name",
    "task_name",
    "task_start_date",
    "task_end_date",
    "duration_days",
    "priority",
    "resource_name",
    "resource_role",
    "allocation_percent",
}


@dataclass
class ParsedRow:
    row_number: int
    project_name: str
    task_name: str
    task_start_date: datetime.date
    task_end_date: datetime.date
    duration_days: int
    priority: int
    resource_name: str
    resource_role: str
    allocation_percent: float
    predecessor_task: str | None
    dependency_kind: str


def _sanitize_text(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} tidak boleh kosong")
    if text[0] in {"=", "+", "-", "@"}:
        raise ValueError(f"{field_name} mengandung karakter berbahaya")
    return text


def _parse_csv(content: str) -> tuple[list[ParsedRow], list[tuple[int, str, str]]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("Header CSV tidak ditemukan")

    missing_columns = REQUIRED_COLUMNS.difference({column.strip() for column in reader.fieldnames})
    if missing_columns:
        raise ValueError(f"Kolom wajib belum lengkap: {', '.join(sorted(missing_columns))}")

    parsed_rows: list[ParsedRow] = []
    errors: list[tuple[int, str, str]] = []

    for row_number, row in enumerate(reader, start=2):
        raw_data = str(row)
        try:
            project_name = _sanitize_text(str(row.get("project_name", "")), "project_name")
            task_name = _sanitize_text(str(row.get("task_name", "")), "task_name")
            task_start_date = datetime.strptime(
                _sanitize_text(str(row.get("task_start_date", "")), "task_start_date"),
                "%Y-%m-%d",
            ).date()
            task_end_date = datetime.strptime(
                _sanitize_text(str(row.get("task_end_date", "")), "task_end_date"),
                "%Y-%m-%d",
            ).date()
            duration_days = int(str(row.get("duration_days", "")).strip())
            priority = int(str(row.get("priority", "")).strip())
            resource_name = _sanitize_text(str(row.get("resource_name", "")), "resource_name")
            resource_role = _sanitize_text(str(row.get("resource_role", "General")), "resource_role")
            allocation_percent = float(str(row.get("allocation_percent", "")).strip())

            predecessor_task_raw = str(row.get("predecessor_task", "")).strip()
            predecessor_task = predecessor_task_raw if predecessor_task_raw else None
            dependency_kind = str(row.get("dependency_kind", "hard")).strip().lower() or "hard"
            if dependency_kind not in {"hard", "soft"}:
                raise ValueError("dependency_kind harus hard atau soft")

            if duration_days <= 0:
                raise ValueError("duration_days harus lebih dari 0")
            if priority < 1 or priority > 5:
                raise ValueError("priority harus antara 1 sampai 5")
            if allocation_percent < 0 or allocation_percent > 100:
                raise ValueError("allocation_percent harus 0-100")
            if task_end_date < task_start_date:
                raise ValueError("task_end_date tidak boleh sebelum task_start_date")

            parsed_rows.append(
                ParsedRow(
                    row_number=row_number,
                    project_name=project_name,
                    task_name=task_name,
                    task_start_date=task_start_date,
                    task_end_date=task_end_date,
                    duration_days=duration_days,
                    priority=priority,
                    resource_name=resource_name,
                    resource_role=resource_role,
                    allocation_percent=allocation_percent,
                    predecessor_task=predecessor_task,
                    dependency_kind=dependency_kind,
                )
            )
        except ValueError as exc:
            errors.append((row_number, str(exc), raw_data))

    return parsed_rows, errors


def create_upload(db: Session, upload_file: UploadFile) -> UploadSummary:
    if not upload_file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nama file tidak tersedia")
    if not upload_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File harus berformat CSV")

    content_bytes = upload_file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Ukuran file melebihi 2MB")

    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File harus UTF-8") from exc

    upload = DataUpload(source_filename=upload_file.filename, status="processing")
    db.add(upload)
    db.flush()

    try:
        parsed_rows, errors = _parse_csv(content)
    except ValueError as exc:
        upload.status = "failed"
        upload.total_rows = 0
        upload.accepted_rows = 0
        upload.rejected_rows = 0
        upload.processed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    project_cache: dict[str, Project] = {}
    resource_cache: dict[str, Resource] = {}
    task_cache: dict[tuple[int, str], Task] = {}

    for row in parsed_rows:
        project = project_cache.get(row.project_name)
        if project is None:
            project = db.scalar(select(Project).where(Project.name == row.project_name))
            if project is None:
                project = Project(name=row.project_name, source_upload_id=upload.id)
                db.add(project)
                db.flush()
            project_cache[row.project_name] = project

        resource = resource_cache.get(row.resource_name)
        if resource is None:
            resource = db.scalar(select(Resource).where(Resource.name == row.resource_name))
            if resource is None:
                resource = Resource(name=row.resource_name, role=row.resource_role)
                db.add(resource)
                db.flush()
            resource_cache[row.resource_name] = resource

        task_key = (project.id, row.task_name)
        task = task_cache.get(task_key)
        if task is None:
            task = db.scalar(
                select(Task).where(Task.project_id == project.id, Task.name == row.task_name)
            )
            if task is None:
                task = Task(
                    project_id=project.id,
                    name=row.task_name,
                    start_date=row.task_start_date,
                    end_date=row.task_end_date,
                    duration_days=row.duration_days,
                    priority=row.priority,
                )
                db.add(task)
                db.flush()
            task_cache[task_key] = task

        assignment = db.scalar(
            select(Assignment).where(
                Assignment.task_id == task.id, Assignment.resource_id == resource.id
            )
        )
        if assignment is None:
            db.add(
                Assignment(
                    task_id=task.id,
                    resource_id=resource.id,
                    allocation_percent=row.allocation_percent,
                )
            )

    db.flush()

    for row in parsed_rows:
        if not row.predecessor_task:
            continue

        project = project_cache[row.project_name]
        predecessor = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.name == row.predecessor_task,
            )
        )
        successor = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.name == row.task_name,
            )
        )

        if predecessor is None or successor is None or predecessor.id == successor.id:
            errors.append((row.row_number, "Dependency task tidak valid", row.predecessor_task or ""))
            continue

        dependency = db.scalar(
            select(Dependency).where(
                Dependency.project_id == project.id,
                Dependency.predecessor_task_id == predecessor.id,
                Dependency.successor_task_id == successor.id,
            )
        )
        if dependency is None:
            db.add(
                Dependency(
                    project_id=project.id,
                    predecessor_task_id=predecessor.id,
                    successor_task_id=successor.id,
                    kind=row.dependency_kind,
                )
            )

    for row_number, message, raw_data in errors:
        db.add(
            ValidationError(
                upload_id=upload.id,
                row_number=row_number,
                message=message,
                raw_data=raw_data,
            )
        )

    upload.total_rows = len(parsed_rows) + len(errors)
    upload.accepted_rows = len(parsed_rows)
    upload.rejected_rows = len(errors)
    upload.status = "completed"
    upload.processed_at = datetime.now(timezone.utc)

    db.commit()
    logger.info(
        "upload_processed upload_id=%s total=%s accepted=%s rejected=%s",
        upload.id,
        upload.total_rows,
        upload.accepted_rows,
        upload.rejected_rows,
    )
    return UploadSummary.model_validate(upload, from_attributes=True)


def get_upload_detail(db: Session, upload_id: int) -> UploadDetail:
    upload = db.get(DataUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload tidak ditemukan")

    errors = db.scalars(
        select(ValidationError)
        .where(ValidationError.upload_id == upload_id)
        .order_by(ValidationError.row_number)
    ).all()
    return UploadDetail(
        **UploadSummary.model_validate(upload, from_attributes=True).model_dump(),
        errors=[ValidationErrorItem.model_validate(item, from_attributes=True) for item in errors],
    )


def list_projects(db: Session) -> list[ProjectItem]:
    projects = db.scalars(select(Project).order_by(Project.created_at.desc()).limit(100)).all()
    return [ProjectItem.model_validate(item, from_attributes=True) for item in projects]


def list_resources(db: Session) -> list[ResourceItem]:
    resources = db.scalars(select(Resource).order_by(Resource.name.asc()).limit(200)).all()
    return [ResourceItem.model_validate(item, from_attributes=True) for item in resources]


def list_tasks(db: Session) -> list[TaskItem]:
    tasks = db.scalars(select(Task).order_by(Task.id.desc()).limit(500)).all()
    return [TaskItem.model_validate(item, from_attributes=True) for item in tasks]
