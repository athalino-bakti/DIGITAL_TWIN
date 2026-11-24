"""Resource Load Index per anggota per minggu (DIG-187, story DIG-43).

RLI(r, w) = (beban_proyek + beban_non_proyek) / kapasitas, sesuai USULAN_FORMULA_RLI.md
bagian 2. Bagian murni (tanpa basis data) dites di tests/test_rli_rules.py; `load_inputs`
membaca D-02 sampai D-11 yang dibutuhkan. Bobot asumsi ada di `rli_config`.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.data.enums import WorkloadItemType
from app.modules.data.models import (
    Assignment,
    Availability,
    ComplexityLevel,
    Holiday,
    Resource,
    Role,
    Task,
    WorkloadItem,
)
from app.modules.data.workdays import count_working_days_in_periods, working_days_between
from app.modules.digital_twin import rli_config as cfg
from app.modules.digital_twin.summary_service import task_end

ONE_DAY = timedelta(days=1)
FRIDAY = timedelta(days=4)

Period = tuple[date, date]


@dataclass(frozen=True)
class Member:
    resource_id: str
    resource_name: str
    primary_role_id: str
    capacity_reference: float
    join_date: date


@dataclass(frozen=True)
class Load:
    """Satu penyumbang beban: penugasan D-07 (proyek) atau item D-08 (non-proyek)."""

    weight: float
    periods: tuple[Period, ...]  # jendela aktif; beban dihitung pada irisan semuanya
    project_id: str | None = None


@dataclass
class Inputs:
    members: list[Member]
    holidays: set[date] = field(default_factory=set)
    absences: dict[str, list[Period]] = field(default_factory=lambda: defaultdict(list))
    tasks: dict[str, list[Load]] = field(default_factory=lambda: defaultdict(list))
    items: dict[str, list[Load]] = field(default_factory=lambda: defaultdict(list))


@dataclass(frozen=True)
class Cell:
    week_start: date
    rli: float | None
    category: str
    project_load: float
    non_project_load: float
    capacity: float
    available_days: int
    onboarding_factor: float
    tasks: int
    workload_items: int


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_days(monday: date, holidays: set[date]) -> list[date]:
    """Hari kerja Senin sampai Jumat minggu itu, tanpa libur D-11."""
    return working_days_between(monday, monday + FRIDAY, holidays)


def task_window(
    status: str,
    planned_start: date,
    planned_finish: date,
    actual_start: date | None,
    actual_finish: date | None,
    as_of: date,
) -> Period:
    """Jendela task D-05: mulai aktual (atau rencana) sampai selesai aktual (atau rencana;
    task terbuka yang lewat rencana diperpanjang sampai `as_of`)."""
    start = actual_start or planned_start
    end = actual_finish or task_end(status, planned_finish, None, as_of)
    return start, max(start, end)


def item_weight(item_type: str, severity: str | None, is_hotfix: bool) -> float:
    """Bobot D-08 (asumsi A3)."""
    if item_type == WorkloadItemType.OPERATIONAL:
        return cfg.OPERATIONAL_WEIGHT
    if is_hotfix:
        return cfg.HOTFIX_WEIGHT
    return cfg.TICKET_WEIGHT.get(severity, cfg.TICKET_WEIGHT[None])


def onboarding_factor(join_date: date, monday: date) -> float:
    """Faktor onboarding (asumsi A5) dari masa kerja sampai Senin minggu itu."""
    tenure = (monday - join_date).days
    for upper, factor in cfg.ONBOARDING_STEPS:
        if tenure <= upper:
            return factor
    return 1.0


def category(rli: float | None) -> str:
    """Kategori heatmap dari RLI yang sudah dibulatkan; None berarti kapasitas 0."""
    if rli is None:
        return cfg.UNAVAILABLE
    for code, _label, _min, upper, _overload, inclusive in cfg.CATEGORIES:
        if upper is None or rli < upper or (inclusive and rli == upper):
            return code
    raise AssertionError("kategori tidak lengkap")  # pragma: no cover


def active_days(days: list[date], periods: tuple[Period, ...]) -> int:
    """Hari kerja minggu itu yang masuk semua jendela `periods`."""
    return sum(1 for day in days if all(start <= day <= end for start, end in periods))


def weighted(loads: list[Load], days: list[date]) -> tuple[float, int]:
    """(Σ bobot × hari_aktif / hari_kerja, jumlah penyumbang)."""
    total, count = 0.0, 0
    for load in loads:
        active = active_days(days, load.periods)
        if active:
            total += load.weight * active / len(days)
            count += 1
    return total, count


def compute_cell(member: Member, monday: date, inputs: Inputs) -> Cell:
    """RLI satu anggota pada minggu yang dimulai `monday`."""
    friday = monday + FRIDAY
    days = week_days(monday, inputs.holidays)
    factor = onboarding_factor(member.join_date, monday)
    if not days:
        # Minggu tanpa hari kerja tidak dihitung.
        return Cell(monday, None, cfg.UNAVAILABLE, 0.0, 0.0, 0.0, 0, factor, 0, 0)

    unavailable = list(inputs.absences.get(member.resource_id, ()))
    if member.join_date > monday:
        unavailable.append((monday, member.join_date - ONE_DAY))
    missing = count_working_days_in_periods(unavailable, inputs.holidays, within=(monday, friday))
    available = len(days) - missing

    project, tasks = weighted(inputs.tasks.get(member.resource_id, []), days)
    non_project, items = weighted(inputs.items.get(member.resource_id, []), days)
    capacity = member.capacity_reference * available / len(days) * factor
    rli = round((project + non_project) / capacity, cfg.RLI_DECIMALS) if capacity else None
    return Cell(
        week_start=monday,
        rli=rli,
        category=category(rli),
        project_load=round(project, cfg.RLI_DECIMALS),
        non_project_load=round(non_project, cfg.RLI_DECIMALS),
        capacity=round(capacity, cfg.RLI_DECIMALS),
        available_days=available,
        onboarding_factor=factor,
        tasks=tasks,
        workload_items=items,
    )


def task_load(assignment: Assignment, task: Task, load_weight: float, as_of: date) -> Load | None:
    """Beban satu penugasan D-07, aktif pada irisan masa penugasan dan jendela task.
    Task `dropped` dan `on_hold` tidak menambah beban (asumsi A1)."""
    if task.status in cfg.UNLOADED_TASK_STATUSES:
        return None
    window = task_window(
        task.status,
        task.planned_start,
        task.planned_finish,
        task.actual_start,
        task.actual_finish,
        as_of,
    )
    held = (assignment.assigned_date, assignment.released_date or date.max)
    return Load(load_weight, (held, window), task.project_id)


def item_load(item: WorkloadItem, as_of: date) -> Load | None:
    """Beban satu item D-08, aktif dari mulai (atau diterima) sampai selesai (atau `as_of`)."""
    start = item.started_date or item.received_date
    end = item.resolved_date or as_of
    if end < start:
        return None
    weight = item_weight(item.item_type, item.severity, item.is_hotfix)
    return Load(weight, ((start, end),), item.related_project_id)


def is_overloaded(cell: Cell) -> bool:
    return cell.rli is not None and cell.rli > cfg.OVERLOAD_THRESHOLD


# --- baca basis data -------------------------------------------------------------------


def load_inputs(
    db: Session,
    first: date,
    last: date,
    as_of: date,
    role_id: str | None = None,
    resource_id: str | None = None,
) -> Inputs:
    """Baca anggota yang sudah bergabung sebelum `last` beserta semua penyumbang bebannya
    dalam rentang [`first`, `last`]."""
    query = (
        select(Resource, Role.capacity_reference)
        .join(Role, Role.role_id == Resource.primary_role_id)
        .where(Resource.join_date <= last)
        .order_by(Resource.resource_id)
    )
    if role_id:
        query = query.where(Resource.primary_role_id == role_id)
    if resource_id:
        query = query.where(Resource.resource_id == resource_id)
    members = [
        Member(r.resource_id, r.resource_name, r.primary_role_id, capacity, r.join_date)
        for r, capacity in db.execute(query)
    ]
    inputs = Inputs(members)
    ids = [m.resource_id for m in members]
    if not ids:
        return inputs

    inputs.holidays = set(
        db.scalars(select(Holiday.holiday_date).where(Holiday.holiday_date.between(first, last)))
    )
    for row in db.execute(
        select(Availability.resource_id, Availability.date_start, Availability.date_end).where(
            Availability.resource_id.in_(ids),
            Availability.absence_type.in_(list(cfg.ABSENCE_TYPES)),
            Availability.date_start <= last,
            Availability.date_end >= first,
        )
    ):
        inputs.absences[row.resource_id].append((row.date_start, row.date_end))

    for row in db.execute(
        select(Assignment, Task, ComplexityLevel.load_weight)
        .join(Task, Task.task_id == Assignment.task_id)
        .join(ComplexityLevel, ComplexityLevel.complexity_id == Task.complexity_id)
        .where(
            Assignment.resource_id.in_(ids),
            Assignment.assigned_date <= last,
            or_(Assignment.released_date.is_(None), Assignment.released_date >= first),
        )
    ):
        assignment, task, load_weight = row
        load = task_load(assignment, task, load_weight, as_of)
        if load:
            inputs.tasks[assignment.resource_id].append(load)

    for item in db.scalars(
        select(WorkloadItem).where(
            WorkloadItem.resource_id.in_(ids),
            WorkloadItem.received_date <= last,
            or_(WorkloadItem.resolved_date.is_(None), WorkloadItem.resolved_date >= first),
        )
    ):
        load = item_load(item, as_of)
        if load:
            inputs.items[item.resource_id].append(load)
    return inputs
