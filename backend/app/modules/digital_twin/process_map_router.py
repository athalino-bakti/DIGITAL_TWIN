"""Endpoint tab Process Map (DIG-169, story DIG-38).

Directly-follows graph dihitung saat request dari tabel event_log (DIG-37), jadi hasilnya selalu
mengikuti bangun ulang event log terakhir. Izin `baseline:read` (FR-08: System Analyst dan
Kaur/Asman). Router sendiri yang dipasang di `app/api/router.py`, supaya tidak bentrok dengan PR
lain yang mengisi `digital_twin/router.py`.
"""

from collections import defaultdict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.enums import PROJECT_ID_PATTERN
from app.modules.data.event_log import list_event_log
from app.modules.data.event_log_models import ACTIVITY_KINDS, EventLogEntry
from app.modules.digital_twin.process_map import Step, directly_follows, filter_by_frequency
from app.modules.digital_twin.process_map_schemas import (
    ActivityCount,
    HiddenCount,
    ProcessMapEdge,
    ProcessMapNode,
    ProcessMapResponse,
)

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])
Db = Annotated[Session, Depends(get_db)]
ActivityKind = Literal[ACTIVITY_KINDS]
# Alur status saja, sama dengan DFG utama laporan event log awal (DIG-167).
DEFAULT_KINDS = ["created", "status", "archived", "deleted"]


def build_process_map(
    db: Session,
    project_id: str | None,
    date_from: date | None,
    date_to: date | None,
    activity_kinds: list[str],
    min_frequency: int,
) -> ProcessMapResponse:
    kinds = set(activity_kinds)
    traces: dict[str, list[Step]] = defaultdict(list)
    for event in list_event_log(db, project_id, None, date_from, date_to):
        if event.activity_kind in kinds:
            traces[event.case_id].append(Step(event.activity, event.event_time))
    full = directly_follows(traces)
    shown, hidden = filter_by_frequency(full, min_frequency)
    return ProcessMapResponse(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        activity_kinds=sorted(kinds, key=ACTIVITY_KINDS.index),
        min_frequency=min_frequency,
        event_log_events=db.scalar(select(func.count()).select_from(EventLogEntry)),
        cases=shown.cases,
        events=shown.events,
        max_edge_frequency=shown.max_edge_frequency,
        nodes=[
            ProcessMapNode(
                id=n.activity,
                label=n.activity,
                frequency=n.frequency,
                cases=n.cases,
                start_cases=n.start_cases,
                end_cases=n.end_cases,
            )
            for n in shown.nodes
        ],
        edges=[
            ProcessMapEdge(
                source=e.source,
                target=e.target,
                frequency=e.frequency,
                cases=e.cases,
                mean_hours=e.mean_hours,
                median_hours=e.median_hours,
            )
            for e in shown.edges
        ],
        start_activities=_ends(shown.nodes, "start_cases"),
        end_activities=_ends(shown.nodes, "end_cases"),
        hidden=HiddenCount(
            edges=hidden.edges, nodes=hidden.nodes, edge_frequency=hidden.edge_frequency
        ),
    )


def _ends(nodes, field: str) -> list[ActivityCount]:
    counts = [(n.activity, getattr(n, field)) for n in nodes if getattr(n, field)]
    counts.sort(key=lambda item: (-item[1], item[0]))
    return [ActivityCount(activity=activity, cases=cases) for activity, cases in counts]


@router.get(
    "/process-map",
    response_model=ProcessMapResponse,
    dependencies=[Depends(require_permission(Perm.BASELINE_READ))],
    summary="Directly-follows graph dari event log (tab Process Map)",
)
def process_map(
    db: Db,
    project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    activity_kinds: Annotated[
        list[ActivityKind] | None,
        Query(
            description="Jenis aktivitas; bawaan alur status (created, status, archived, deleted)"
        ),
    ] = None,
    min_frequency: Annotated[
        int, Query(ge=1, description="Sembunyikan edge dengan frekuensi di bawah ini")
    ] = 1,
) -> ProcessMapResponse:
    """Rentang tanggal (WIB, inklusif) memotong trace: event di luar rentang tidak dihitung.
    Bila `event_log_events` = 0, event log belum dibentuk (POST /data/event-log/rebuild)."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "loc": ["query", "date_to"],
                    "msg": "Tanggal akhir tidak boleh sebelum tanggal awal",
                    "type": "date_order",
                }
            ],
        )
    return build_process_map(
        db, project_id, date_from, date_to, activity_kinds or DEFAULT_KINDS, min_frequency
    )
