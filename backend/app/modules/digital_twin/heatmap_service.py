"""Heatmap beban kerja per anggota per minggu (DIG-188), dari service RLI DIG-187."""

from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.modules.data.service import ONBOARDING_DAYS
from app.modules.digital_twin import rli_config as cfg
from app.modules.digital_twin.heatmap_schemas import (
    HeatmapCategory,
    HeatmapCell,
    HeatmapRow,
    HeatmapSummary,
    HeatmapWeek,
    WorkloadHeatmap,
)
from app.modules.digital_twin.rli import (
    FRIDAY,
    Inputs,
    Load,
    compute_cell,
    is_overloaded,
    load_holidays,
    load_inputs,
    monday_of,
    week_days,
)

WEEK = timedelta(weeks=1)
DEFAULT_WEEKS = 12
MAX_WEEKS = 26
WEEKS_BEFORE = 4  # bawaan `start`: Senin minggu berjalan dikurangi 4 minggu

CATEGORIES = [
    HeatmapCategory(code=code, label=label, min=low, max=high, overload=overload)
    for code, label, low, high, overload, _inclusive in cfg.CATEGORIES
]


def default_start(today: date) -> date:
    return monday_of(today) - WEEKS_BEFORE * WEEK


def works_on_project(loads: list[Load], project_id: str, first: date, last: date) -> bool:
    """Ada penugasan di proyek itu yang aktif sedikitnya satu hari dalam [first, last]."""
    for load in loads:
        if load.project_id != project_id:
            continue
        start = max([first, *(p[0] for p in load.periods)])
        end = min([last, *(p[1] for p in load.periods)])
        if start <= end:
            return True
    return False


def build_heatmap(
    db: Session,
    start: date,
    weeks: int,
    as_of: date,
    role_id: str | None = None,
    project_id: str | None = None,
    resource_id: str | None = None,
) -> WorkloadHeatmap:
    first = monday_of(start)
    mondays = [first + i * WEEK for i in range(weeks)]
    last = mondays[-1] + FRIDAY
    current = monday_of(as_of)
    inputs = load_inputs(
        db,
        min(first, current),
        max(last, current + FRIDAY),
        as_of,
        role_id=role_id,
        resource_id=resource_id,
    )
    members = [
        m
        for m in inputs.members
        if project_id is None
        or works_on_project(inputs.tasks.get(m.resource_id, []), project_id, first, last)
    ]

    rows = [
        HeatmapRow(
            resource_id=m.resource_id,
            resource_name=m.resource_name,
            primary_role_id=m.primary_role_id,
            capacity_reference=m.capacity_reference,
            is_onboarding=(as_of - m.join_date).days <= ONBOARDING_DAYS,
            cells=[HeatmapCell(**asdict(compute_cell(m, monday, inputs))) for monday in mondays],
        )
        for m in members
    ]
    joined = [m for m in members if m.join_date <= current + FRIDAY]
    return WorkloadHeatmap(
        as_of=as_of,
        formula_version=cfg.FORMULA_VERSION,
        provisional=cfg.PROVISIONAL,
        weeks=[week(monday, inputs) for monday in mondays],
        categories=CATEGORIES,
        summary=HeatmapSummary(
            week_start=current,
            overloaded=sum(is_overloaded(compute_cell(m, current, inputs)) for m in joined),
            resources=len(joined),
        ),
        rows=rows,
    )


def week(monday: date, inputs: Inputs) -> HeatmapWeek:
    friday = monday + FRIDAY
    return HeatmapWeek(
        week_start=monday,
        week_end=friday,
        working_days=len(week_days(monday, inputs.holidays)),
        holidays=sorted(day for day in inputs.holidays if monday <= day <= friday),
    )


def empty_heatmap(db: Session, start: date, weeks: int, as_of: date) -> WorkloadHeatmap:
    """Akun anggota tim yang belum tertaut ke data anggota: tanpa baris."""
    mondays = [monday_of(start) + i * WEEK for i in range(weeks)]
    inputs = Inputs([], holidays=load_holidays(db, mondays[0], mondays[-1] + FRIDAY))
    return WorkloadHeatmap(
        as_of=as_of,
        formula_version=cfg.FORMULA_VERSION,
        provisional=cfg.PROVISIONAL,
        weeks=[week(monday, inputs) for monday in mondays],
        categories=CATEGORIES,
        summary=HeatmapSummary(week_start=monday_of(as_of), overloaded=0, resources=0),
        rows=[],
    )
