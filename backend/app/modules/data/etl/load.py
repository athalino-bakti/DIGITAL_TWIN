"""ETL staging ke D-05, D-06, D-07: validasi kandidat dan upsert idempoten (DIG-134, story DIG-29).

Alur per proyek (RANCANGAN_ETL_DIG-29.md bagian 3):
1. Baca batch Project Plan dari job `project_plan` sukses terakhir proyek itu, semua aksi Trello,
   `trello_list_mapping`, D-03, D-04, dan `resource_alias`.
2. Normalisasi (DIG-130), identitas (DIG-131), riwayat Trello (DIG-132), assignment (DIG-133).
3. Beri ID: pasangan dependensi dan assignment yang sudah ada memakai ID lamanya, sisanya ID baru.
4. Validasi dengan aturan DIG-31 yang sama, atas kandidat ditambah tabel rujukan dari basis data.
   Baris dengan temuan `tolak` tidak dimuat; `peringatan` tetap dimuat.
5. Upsert. Kolom task yang masih punya perubahan manual terbuka (`task_manual_change`, DIG-162)
   tidak ditimpa dan dilaporkan sebagai konflik; yang sudah sama ditutup `caught_up`. Setiap insert
   dan update dicatat `record_audit(source="etl", import_job_id=job)`.

Idempoten: menjalankan ulang pada data yang sama tidak menulis apa pun, karena ID lama dipakai
ulang dan `record_audit` melewati update tanpa beda. Baris final yang hilang dari Project Plan
tidak dihapus (penghapusan butuh keputusan manusia). Tidak commit.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.modules.data.quality.rules  # noqa: F401  (mendaftarkan aturan DIG-31)
from app.modules.auth.models import AppUser
from app.modules.data.audit import record_audit
from app.modules.data.etl.assignments import ADD, REMOVE, MemberEvent, merge_assignments
from app.modules.data.etl.history import apply_history, derive_history
from app.modules.data.etl.identity import load_alias_index, resolve_plan_assignments
from app.modules.data.etl.normalize import (
    Candidates,
    PlanRow,
    Problem,
    TrelloMove,
    build_candidates,
    card_states,
    label_index,
)
from app.modules.data.import_job_models import ImportJob
from app.modules.data.manual_change import merge_task_import, open_changes, settle
from app.modules.data.models import Assignment, ComplexityLevel, Role, Task, TaskDependency
from app.modules.data.quality.engine import (
    RULES,
    TOLAK,
    Context,
    Finding,
    RuleSummary,
    SourceRow,
)
from app.modules.data.quality.engine import Report as QualityReport
from app.modules.data.quality.rules import EXISTING_TASKS
from app.modules.data.quality.sources import read_database
from app.modules.data.quality.store import save_report
from app.modules.data.service import next_id
from app.modules.data.staging_models import (
    StagingProjectPlan,
    StagingTrelloAction,
    TrelloListMapping,
)

LOADED = ("tasks", "task_dependencies", "assignments")
SOURCE = "project_plan"
PLAN_COLUMNS = (
    "task_code", "feature_name", "task_name", "role_label", "pic", "complexity_label",
    "priority", "estimated_days", "planned_start", "planned_finish", "actual_start",
    "actual_finish", "status_label", "depends_on", "notes",
)  # fmt: skip
DATES = {"planned_start", "planned_finish", "actual_start", "actual_finish", "assigned_date",
         "released_date"}  # fmt: skip
INTEGERS = {"priority_rank", "qa_reject_count"}
FLOATS = {"estimated_days", "propagation_factor"}
BOOLEANS = {"dod_fulfilled", "is_takeover"}
SAMPLE = 50  # jumlah masalah dan temuan yang disimpan per job, supaya details tetap kecil


@dataclass
class EtlReport:
    project_id: str
    job_id: int | None
    plan_rows: int = 0
    inserted: Counter = field(default_factory=Counter)
    updated: Counter = field(default_factory=Counter)
    unchanged: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)
    skipped_parent: Counter = field(default_factory=Counter)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    problems: list[dict[str, Any]] = field(default_factory=list)
    findings: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["problems"] = data["problems"][:SAMPLE]
        data["problem_count"] = len(self.problems)
        for key in ("inserted", "updated", "unchanged", "rejected", "skipped_parent", "findings"):
            data[key] = dict(getattr(self, key))
        return data


# --- baca staging ---------------------------------------------------------------------------


def latest_plan_job(db: Session, project_id: str) -> int | None:
    return db.scalar(
        select(ImportJob.job_id)
        .join(StagingProjectPlan, StagingProjectPlan.import_job_id == ImportJob.job_id)
        .where(StagingProjectPlan.project_id == project_id, ImportJob.status == "succeeded")
        .order_by(ImportJob.job_id.desc())
        .limit(1)
    )


def plan_projects(db: Session) -> list[str]:
    return sorted(set(db.scalars(select(StagingProjectPlan.project_id))))


def read_plan(db: Session, job_id: int) -> list[PlanRow]:
    rows = db.scalars(
        select(StagingProjectPlan)
        .where(StagingProjectPlan.import_job_id == job_id)
        .order_by(StagingProjectPlan.row_number)
    )
    return [
        PlanRow(
            r.row_number,
            r.project_id,
            {c: getattr(r, c) for c in PLAN_COLUMNS},
            r.imported_at,
            r.file_name,
        )
        for r in rows
    ]


def read_trello(db: Session) -> tuple[list[TrelloMove], list[MemberEvent]]:
    moves, members = [], []
    for action in db.scalars(select(StagingTrelloAction).order_by(StagingTrelloAction.action_date)):
        if action.list_after_id:
            moves.append(
                TrelloMove(
                    action.card_name, action.board_id, action.list_after_id, action.action_date
                )
            )
        if action.action_type in (ADD, REMOVE):
            data = action.raw.get("data") or {}
            member = action.raw.get("member") or data.get("member") or {}
            members.append(
                MemberEvent(
                    action.card_name,
                    action.action_type,
                    data.get("idMember") or member.get("id"),
                    member.get("username") or member.get("fullName") or member.get("name"),
                    action.action_date,
                )
            )
    return moves, members


def read_mapping(db: Session) -> dict[tuple[str, str], tuple[str | None, str | None]]:
    return {
        (m.board_id, m.list_id): (m.status, m.phase) for m in db.scalars(select(TrelloListMapping))
    }


def build(db: Session, plan: list[PlanRow]) -> Candidates:
    moves, members = read_trello(db)
    mapping = read_mapping(db)
    roles = label_index(db.execute(select(Role.role_id, Role.role_name)).tuples())
    levels = label_index(
        db.execute(select(ComplexityLevel.complexity_id, ComplexityLevel.complexity_name)).tuples()
    )
    aliases = load_alias_index(db)
    candidates = build_candidates(plan, card_states(moves, mapping), roles, levels)
    candidates = resolve_plan_assignments(candidates, aliases)
    candidates = apply_history(candidates, derive_history(moves, mapping))
    return merge_assignments(candidates, members, aliases)


# --- ID dan validasi ------------------------------------------------------------------------


def assign_ids(db: Session, candidates: Candidates) -> Candidates:
    """Isi `dependency_id` dan `assignment_id`: ID lama untuk baris yang sama, sisanya ID baru."""
    db.flush()  # SessionLocal tanpa autoflush: baris proyek sebelumnya harus terlihat di sini
    deps = {
        (d.task_id, d.depends_on_task_id): d.dependency_id
        for d in db.scalars(select(TaskDependency))
    }
    used_deps = list(deps.values())
    assignments = {
        (a.task_id, a.resource_id, a.assigned_date.isoformat()): a.assignment_id
        for a in db.scalars(select(Assignment))
    }
    used_asg = list(assignments.values())

    dep_rows = []
    for row in candidates.tables["task_dependencies"]:
        key = (row.values["task_id"], row.values["depends_on_task_id"])
        dep_id = deps.get(key)
        if dep_id is None:
            dep_id = deps[key] = next_id(used_deps, "DEP")
            used_deps.append(dep_id)
        dep_rows.append(SourceRow(row.number, dep_id, {**row.values, "dependency_id": dep_id}))

    asg_rows = []
    for row in candidates.tables["assignments"]:
        values = dict(row.values)
        values.pop("pic", None)
        asg_id = ""
        if values["resource_id"] and values["assigned_date"]:
            key = (values["task_id"], values["resource_id"], values["assigned_date"])
            asg_id = assignments.get(key) or ""
            if not asg_id:
                asg_id = assignments[key] = next_id(used_asg, "ASG", width=4)
                used_asg.append(asg_id)
        values["assignment_id"] = asg_id
        asg_rows.append(SourceRow(row.number, asg_id or None, values))

    tables = {**candidates.tables, "task_dependencies": dep_rows, "assignments": asg_rows}
    return Candidates(tables=tables, problems=list(candidates.problems))


def validate(
    db: Session, candidates: Candidates, report: EtlReport
) -> tuple[set[int], QualityReport]:
    """(id() baris kandidat bertemuan `tolak`, laporan kualitas berbentuk `run_rules`).

    Aturan DIG-31 dipanggil per baris, bukan lewat `run_rules`, karena `Finding` tidak membawa
    identitas baris (assignment dari Trello tidak punya nomor baris maupun kunci).
    Task yang sudah ada ikut di konteks (`EXISTING_TASKS`) supaya DQ-TSK-014 bisa menolak
    `task_id` milik proyek lain sebelum upsert.
    """
    database = read_database(db)
    tables = {**database, **candidates.tables, EXISTING_TASKS: database["tasks"]}
    context = Context(tables)
    rejected: set[int] = set()
    quality = QualityReport(SOURCE)
    for rule in RULES.values():
        if rule.check is None or rule.table not in LOADED:
            continue
        rows = tables[rule.table]
        hits = list(rule.check(rows, context))
        for hit in hits:
            report.findings[f"{rule.rule_id}:{rule.level}"] += 1
            if rule.level == TOLAK:
                rejected.add(id(hit.row))
            quality.findings.append(
                Finding(rule.rule_id, rule.characteristic, rule.level, SOURCE, rule.table,
                        hit.row.number, hit.row.key, hit.column, hit.value, hit.message)
            )  # fmt: skip
        quality.summaries.append(
            RuleSummary(rule.rule_id, SOURCE, rule.table, rule.characteristic, rule.level,
                        rule.text, checked=len(rows), violated=len({id(h.row) for h in hits}))
        )  # fmt: skip
    return rejected, quality


# --- upsert ---------------------------------------------------------------------------------


def typed(values: dict[str, str], columns: Iterable[str]) -> dict[str, Any]:
    """Teks kontrak ke tipe Python kolom model."""
    result: dict[str, Any] = {}
    for column in columns:
        text = values.get(column, "")
        if column in DATES:
            result[column] = date.fromisoformat(text) if text else None
        elif column in INTEGERS:
            result[column] = int(text) if text else None
        elif column in FLOATS:
            result[column] = float(text) if text else None
        elif column in BOOLEANS:
            result[column] = text == "true"
        else:
            result[column] = text or None
    return result


TASK_COLUMNS = [c.name for c in Task.__table__.columns if c.name != "task_id"]
DEP_COLUMNS = [c.name for c in TaskDependency.__table__.columns if c.name != "dependency_id"]
ASG_COLUMNS = [c.name for c in Assignment.__table__.columns if c.name != "assignment_id"]


def _audit(db, action, entity, entity_id, job_id, before=None, after=None):
    record_audit(
        db, action=action, entity=entity, entity_id=entity_id, source="etl",
        import_job_id=job_id, before=before, after=after,
    )  # fmt: skip


def upsert_tasks(db, rows, job_id, report, actor: AppUser | None = None) -> None:
    pending = open_changes(db, [r.values["task_id"] for r in rows])
    caught_up: list[int] = []
    for row in rows:
        task_id = row.values["task_id"]
        incoming = typed(row.values, TASK_COLUMNS)
        task = db.get(Task, task_id)
        if task is None:
            db.add(Task(task_id=task_id, **incoming))
            _audit(db, "insert", "tasks", task_id, job_id, after=incoming)
            report.inserted["tasks"] += 1
            continue
        incoming.pop("dod_fulfilled")  # tidak ada sumber; nilai dari aplikasi dipertahankan
        incoming.pop("project_id")  # ETL tidak memindahkan task; beda proyek ditolak DQ-TSK-014
        current = {c: getattr(task, c) for c in incoming}
        merge = merge_task_import(current, incoming, pending.get(task_id, {}))
        caught_up.extend(merge.caught_up)
        for conflict in merge.conflicts:
            report.conflicts.append(
                {"task_id": task_id, "field": conflict.field, "current": conflict.current,
                 "incoming": conflict.incoming}
            )  # fmt: skip
        if not merge.updates:
            report.unchanged["tasks"] += 1
            continue
        before = {c: current[c] for c in merge.updates}
        for column, value in merge.updates.items():
            setattr(task, column, value)
        _audit(db, "update", "tasks", task_id, job_id, before=before, after=merge.updates)
        report.updated["tasks"] += 1
    if caught_up:
        settle(db, caught_up, "caught_up")


def _upsert_simple(db, model, key_column, columns, entity, rows, job_id, report) -> None:
    db.flush()
    # Baris dengan ID sama (misalnya baris Project Plan ganda) cukup dimuat sekali.
    unique = list({row.values[key_column]: row for row in rows}.values())
    for row in unique:
        key = row.values[key_column]
        incoming = typed(row.values, columns)
        existing = db.get(model, key)
        if existing is None:
            db.add(model(**{key_column: key}, **incoming))
            _audit(db, "insert", entity, key, job_id, after=incoming)
            report.inserted[entity] += 1
            continue
        before = {c: getattr(existing, c) for c in columns}
        changed = {c: v for c, v in incoming.items() if before[c] != v}
        if not changed:
            report.unchanged[entity] += 1
            continue
        for column, value in changed.items():
            setattr(existing, column, value)
        _audit(db, "update", entity, key, job_id, before={c: before[c] for c in changed},
               after=changed)  # fmt: skip
        report.updated[entity] += 1


def run_project(db: Session, project_id: str) -> EtlReport:
    """Jalankan ETL satu proyek dari batch Project Plan sukses terakhirnya. Tidak commit."""
    job_id = latest_plan_job(db, project_id)
    report = EtlReport(project_id, job_id)
    if job_id is None:
        return report
    plan = read_plan(db, job_id)
    report.plan_rows = len(plan)
    candidates = assign_ids(db, build(db, plan))
    report.problems = [asdict(p) for p in candidates.problems]
    rejected, quality = validate(db, candidates, report)
    # Hasil validasi tampil di laporan kualitas (DIG-146) untuk job batch ini.
    save_report(db, job_id, quality)

    accepted: dict[str, list[SourceRow]] = {}
    for table in LOADED:
        keep = [r for r in candidates.tables[table] if id(r) not in rejected]
        report.rejected[table] = len(candidates.tables[table]) - len(keep)
        accepted[table] = keep

    upsert_tasks(db, accepted["tasks"], job_id, report)
    db.flush()
    # Hanya task proyek ini: dependensi dan assignment yang menunjuk task proyek lain (termasuk
    # baris yang ditolak DQ-TSK-014) dilewati, bukan ditempelkan ke task milik proyek lain.
    present = set(db.scalars(select(Task.task_id).where(Task.project_id == project_id)))
    deps = [
        r for r in accepted["task_dependencies"]
        if r.values["task_id"] in present and r.values["depends_on_task_id"] in present
    ]  # fmt: skip
    asgs = [r for r in accepted["assignments"] if r.values["task_id"] in present]
    report.skipped_parent["task_dependencies"] = len(accepted["task_dependencies"]) - len(deps)
    report.skipped_parent["assignments"] = len(accepted["assignments"]) - len(asgs)
    _upsert_simple(db, TaskDependency, "dependency_id", DEP_COLUMNS, "task_dependencies", deps,
                   job_id, report)  # fmt: skip
    _upsert_simple(db, Assignment, "assignment_id", ASG_COLUMNS, "assignments", asgs, job_id,
                   report)  # fmt: skip

    job = db.get(ImportJob, job_id)
    job.details = {**(job.details or {}), "etl": report.as_dict()}
    db.flush()
    return report


def run(db: Session, project_id: str | None = None) -> list[EtlReport]:
    projects = [project_id] if project_id else plan_projects(db)
    return [run_project(db, p) for p in projects]


__all__ = ["EtlReport", "Problem", "run", "run_project"]
