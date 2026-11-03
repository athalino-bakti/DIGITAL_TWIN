"""Penulis 11 CSV final sources sesuai Data Dictionary (DIG-81)."""

import csv
from datetime import date
from pathlib import Path

from synthetic import reference as ref
from synthetic.world import World


def format_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:g}" if value != int(value) else f"{value:.1f}"
    return str(value)


def final_source_rows(world: World) -> dict[str, list[dict[str, object]]]:
    """Baris setiap tabel D-01 s.d. D-11 sebagai dict dengan kunci kolom Data Dictionary."""
    as_of = world.as_of
    rows: dict[str, list[dict[str, object]]] = {}
    rows["projects"] = [
        {
            "project_id": p.project_id,
            "project_name": p.project_name,
            "process_owner": p.process_owner,
            "priority_rank": p.priority_rank,
            "start_date": p.start_date,
            "target_launch_date": p.target_launch_date,
            "actual_launch_date": p.actual_launch_date,
            "status": p.status,
            "dor_fulfilled": p.dor_fulfilled,
        }
        for p in world.projects
    ]
    rows["resources"] = [
        {
            "resource_id": r.resource_id,
            "resource_name": r.resource_name,
            "primary_role_id": r.primary_role_id,
            "secondary_role_ids": ";".join(r.secondary_role_ids) or None,
            "cross_role_capable": r.cross_role_capable,
            "join_date": r.join_date,
            "seniority": r.seniority,
        }
        for r in world.resources
    ]
    rows["roles"] = [
        {
            "role_id": role_id,
            "role_name": name,
            "capacity_reference": ref.CAPACITY_REFERENCE,
            "description": description,
        }
        for role_id, name, description in ref.ROLES
    ]
    rows["complexity_levels"] = [
        {
            "complexity_id": cx,
            "complexity_name": name,
            "min_days": low,
            "max_days": high,
            "load_weight": weight,
        }
        for cx, (name, low, high, weight) in ref.COMPLEXITY.items()
    ]
    rows["tasks"] = [
        {
            "task_id": t.task_id,
            "project_id": t.project_id,
            "feature_name": t.feature_name,
            "task_name": t.task_name,
            "required_role_id": t.required_role_id,
            "complexity_id": t.complexity_id,
            "priority_rank": t.priority_rank,
            "estimated_days": t.estimated_days,
            "phase": t.phase,
            "planned_start": t.planned_start,
            "planned_finish": t.planned_finish,
            "actual_start": t.actual_start,
            "actual_finish": t.actual_finish,
            "status": t.status,
            "qa_reject_count": t.qa_reject_count,
            "dod_fulfilled": t.dod_fulfilled,
        }
        for t in world.tasks
    ]
    rows["task_dependencies"] = [
        {
            "dependency_id": d.dependency_id,
            "task_id": d.task_id,
            "depends_on_task_id": d.depends_on_task_id,
            "dependency_type": d.dependency_type,
            "propagation_factor": d.propagation_factor,
        }
        for d in world.dependencies
    ]
    rows["assignments"] = [
        {
            "assignment_id": a.assignment_id,
            "task_id": a.task_id,
            "resource_id": a.resource_id,
            "role_in_task": a.role_in_task,
            "assigned_date": a.assigned_date,
            "released_date": a.released_date,
            "is_takeover": a.is_takeover,
        }
        for a in world.assignments
        if a.assigned_date <= as_of
    ]
    rows["workload_items"] = [
        {
            "item_id": w.item_id,
            "resource_id": w.resource_id,
            "item_type": w.item_type,
            "related_project_id": w.related_project_id,
            "received_date": w.received_date,
            "started_date": w.started_date,
            "resolved_date": w.resolved_date,
            "severity": w.severity,
            "is_hotfix": w.is_hotfix,
        }
        for w in world.workload_items
    ]
    absences = sorted(world.absences, key=lambda a: (a.start, a.resource_id))
    rows["availability"] = [
        {
            "availability_id": f"AVL-{index + 1:03d}",
            "resource_id": a.resource_id,
            "date_start": a.start,
            "date_end": a.end,
            "absence_type": a.absence_type,
            "is_known_at_planning": a.known_at_planning,
        }
        for index, a in enumerate(absences)
        if a.start <= as_of
    ]
    rows["change_events"] = [
        {
            "event_id": e.event_id,
            "project_id": e.project_id,
            "event_type": e.event_type,
            "event_date": e.event_date,
            "requested_by": e.requested_by,
            "decision": e.decision,
            "resolution_mode": e.resolution_mode,
            "affected_task_id": e.affected_task_id,
            "extension_days": e.extension_days,
        }
        for e in world.events
        if e.event_date <= as_of
    ]
    rows["holidays"] = [{"holiday_date": day, "holiday_name": name} for day, name in ref.HOLIDAYS]
    return rows


def write_csv(path: Path, table: str, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(ref.HEADERS[table])
        for row in rows:
            writer.writerow([format_value(row[column]) for column in ref.HEADERS[table]])


def write_final_sources(world: World, out_dir: Path) -> dict[str, int]:
    """Tulis `<tabel>.csv` untuk D-01 s.d. D-11; kembalikan jumlah baris per tabel."""
    counts = {}
    for table, rows in final_source_rows(world).items():
        write_csv(out_dir / f"{table}.csv", table, rows)
        counts[table] = len(rows)
    return counts
