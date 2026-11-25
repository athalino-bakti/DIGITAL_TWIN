"""Normalisasi staging menjadi baris kandidat berbentuk tabel final (DIG-130, story DIG-29).

Fungsi di modul ini murni: masukannya baris staging yang sudah dibaca, keluarannya `SourceRow`
untuk `tasks`, `task_dependencies`, dan `assignments` dalam format teks kontrak (tanggal ISO,
desimal bertitik, enum Data Dictionary), sehingga aturan DIG-31 bisa dijalankan langsung di atasnya.

Nilai yang tidak dikenali tidak ditebak: kolomnya dikosongkan dan dicatat sebagai `Problem`, lalu
aturan kelengkapan DIG-31 yang menolak barisnya. Peta kolom: RANCANGAN_ETL_DIG-29.md.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.modules.data.enums import TaskPhase, TaskStatus
from app.modules.data.event_log import task_id_from_card
from app.modules.data.quality.dates import ISO, PLAN, parse_date
from app.modules.data.quality.engine import SourceRow

WIB = timezone(timedelta(hours=7))

# Label kolom Status Project Plan (templat PuTI, lihat synthetic/raw_sources.STATUS_LABEL).
# Nilai enum D-05 sendiri juga diterima, supaya berkas yang sudah memakai enum tidak ditolak.
STATUS_LABELS: dict[str, TaskStatus] = {
    "belum mulai": TaskStatus.NOT_STARTED,
    "dikerjakan": TaskStatus.IN_PROGRESS,
    "terblokir": TaskStatus.BLOCKED,
    "ditunda": TaskStatus.ON_HOLD,
    "qa": TaskStatus.IN_QA,
    "selesai": TaskStatus.DONE,
    "dibatalkan": TaskStatus.DROPPED,
    **{s.value: s for s in TaskStatus},
}

# Asumsi (keputusan Davi 24 Nov, RANCANGAN_ETL_DIG-29.md bagian 9): Project Plan tidak punya
# kolom phase, jadi task tanpa kartu Trello mendapat phase dari peran yang dibutuhkan. Fase
# bugfix tidak bisa dibedakan dari fe_dev lewat peran; task bugfix perlu kartu Trello.
PHASE_BY_ROLE: dict[str, TaskPhase] = {
    "ROLE-SA": TaskPhase.PLANNING,
    "ROLE-UIUX": TaskPhase.UIUX,
    "ROLE-DM": TaskPhase.DM_DEV,
    "ROLE-BE": TaskPhase.BE_DEV,
    "ROLE-FE": TaskPhase.FE_DEV,
    "ROLE-QA": TaskPhase.TESTING,
    "ROLE-TW": TaskPhase.DOCUMENTATION,
}

# Kolom Bergantung Pada berisi "TSK-0001 (hard); TSK-0002 (soft)" (templat PuTI). Tipe yang tidak
# ditulis dianggap hard (keputusan Davi 24 Nov).
DEFAULT_DEPENDENCY = "hard"
PROPAGATION = {"hard": "1.0", "soft": "0.3"}  # AC DIG-29: bila propagation_factor kosong

_SPLIT = re.compile(r"[;,]")
_DEPENDENCY = re.compile(r"^(?P<code>[^()\s]+)\s*(?:\((?P<type>[^()]*)\))?$")
_DECIMAL = re.compile(r"^[0-9]+([.,][0-9]+)?$")
_INTEGER = re.compile(r"^[0-9]+$")


@dataclass(frozen=True)
class Problem:
    """Nilai staging yang tidak bisa dinormalisasi. Dilaporkan, tidak ditebak."""

    source: str  # project_plan atau trello
    row: int | None  # nomor baris berkas Project Plan; None untuk Trello
    key: str | None  # task_id bila terbaca
    column: str
    value: str
    message: str


@dataclass(frozen=True)
class PlanRow:
    """Satu baris `staging_project_plan` (semua teks mentah)."""

    row_number: int
    project_id: str
    values: Mapping[str, str | None]
    imported_at: datetime
    file_name: str = ""


@dataclass(frozen=True)
class TrelloMove:
    """Satu aksi Trello yang menaruh kartu di sebuah list."""

    card_name: str | None
    board_id: str
    list_id: str
    at: datetime


@dataclass(frozen=True)
class CardState:
    """Posisi terakhir kartu menurut `trello_list_mapping`."""

    status: TaskStatus | None
    phase: TaskPhase | None
    at: datetime


@dataclass
class Candidates:
    tables: dict[str, list[SourceRow]] = field(
        default_factory=lambda: {"tasks": [], "task_dependencies": [], "assignments": []}
    )
    problems: list[Problem] = field(default_factory=list)


def _text(value: str | None) -> str:
    return (value or "").strip()


def normalize_date(value: str | None, xlsx: bool = False) -> tuple[str, str | None]:
    """(tanggal ISO atau "", pesan masalah atau None).

    Project Plan memakai dd/mm/yyyy (validator DIG-141). Hanya untuk berkas XLSX, ISO juga
    diterima karena unggahan menulis sel bertipe tanggal sebagai ISO (IMPORT_PIPELINE.md). ISO di
    berkas CSV tetap ditolak, sama dengan validator.
    """
    text = _text(value)
    if not text:
        return "", None
    parsed = parse_date(text, PLAN) or (parse_date(text, ISO) if xlsx else None)
    if parsed is None:
        expected = "dd/mm/yyyy atau YYYY-MM-DD" if xlsx else "dd/mm/yyyy"
        return "", f"Tanggal '{text}' tidak berformat {expected}"
    return parsed.isoformat(), None


def normalize_status(value: str | None) -> tuple[str, str | None]:
    text = _text(value)
    if not text:
        return "", None
    status = STATUS_LABELS.get(text.lower())
    if status is None:
        return "", f"Status '{text}' tidak dikenal"
    return status.value, None


def normalize_decimal(value: str | None) -> tuple[str, str | None]:
    """Angka dengan koma atau titik desimal menjadi teks bertitik ("2,5" menjadi "2.5")."""
    text = _text(value)
    if not text:
        return "", None
    if not _DECIMAL.fullmatch(text):
        return "", f"Angka '{text}' tidak valid"
    return text.replace(",", "."), None


def normalize_integer(value: str | None) -> tuple[str, str | None]:
    text = _text(value)
    if not text:
        return "", None
    if not _INTEGER.fullmatch(text):
        return "", f"Bilangan bulat '{text}' tidak valid"
    return str(int(text)), None


def lookup(value: str | None, by_label: Mapping[str, str], kind: str) -> tuple[str, str | None]:
    """ID referensi dari label (tanpa beda huruf besar/kecil) atau dari ID-nya sendiri."""
    text = _text(value)
    if not text:
        return "", None
    found = by_label.get(text.lower())
    if found is None:
        return "", f"{kind} '{text}' tidak dikenal"
    return found, None


def label_index(pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    """{label kecil: id} dari pasangan (id, nama), termasuk id itu sendiri sebagai label."""
    index: dict[str, str] = {}
    for ref_id, name in pairs:
        index[ref_id.lower()] = ref_id
        index[name.strip().lower()] = ref_id
    return index


def split_dependencies(value: str | None) -> list[tuple[str, str, str | None]]:
    """[(kode task, tipe, pesan masalah atau None)] dari kolom Bergantung Pada.

    Dipisah ';' atau ','; urutan dipertahankan dan kode ganda dibuang. Tipe tanpa tulisan menjadi
    hard; tipe yang bukan hard/soft dilaporkan dan dikosongkan agar ditolak validator.
    """
    found: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for part in _SPLIT.split(_text(value)):
        part = part.strip()
        if not part:
            continue
        match = _DEPENDENCY.fullmatch(part)
        if match is None:
            found.append((part, "", f"Dependensi '{part}' tidak terbaca"))
            continue
        code, kind = match["code"], (match["type"] or "").strip().lower() or DEFAULT_DEPENDENCY
        if code in seen:
            continue
        seen.add(code)
        problem = None if kind in PROPAGATION else f"Tipe dependensi '{kind}' tidak dikenal"
        found.append((code, kind if problem is None else "", problem))
    return found


def card_states(
    moves: Iterable[TrelloMove], mapping: Mapping[tuple[str, str], tuple[str | None, str | None]]
) -> dict[str, CardState]:
    """Posisi terakhir tiap task di Trello: {task_id: CardState}.

    `mapping` = {(board_id, list_id): (status, phase)} dari `trello_list_mapping`. Kartu tanpa
    kode task dilewati (sudah dilaporkan DQ-TRL-001). List yang belum dipetakan memberi status
    dan phase None, sehingga nilai Project Plan tetap dipakai.
    """
    states: dict[str, CardState] = {}
    for move in sorted(moves, key=lambda m: m.at):
        task_id = task_id_from_card(move.card_name)
        if task_id is None:
            continue
        status, phase = mapping.get((move.board_id, move.list_id), (None, None))
        states[task_id] = CardState(
            TaskStatus(status) if status else None, TaskPhase(phase) if phase else None, move.at
        )
    return states


def to_wib_date(value: datetime) -> date:
    return value.astimezone(WIB).date()


def build_candidates(
    plan: Iterable[PlanRow],
    cards: Mapping[str, CardState],
    roles: Mapping[str, str],
    complexities: Mapping[str, str],
) -> Candidates:
    """Baris kandidat `tasks`, `task_dependencies`, dan `assignments` dari satu batch Project Plan.

    `roles` dan `complexities` adalah hasil `label_index` dari D-03 dan D-04. Status: bila Project
    Plan dan Trello sama-sama punya nilai, yang terbaru menang (Trello memakai waktu aksi,
    Project Plan memakai waktu impor batch). Phase: Trello bila list-nya dipetakan, selain itu
    dari `PHASE_BY_ROLE`.
    """
    result = Candidates()
    for row in plan:
        raw = row.values
        task_id = _text(raw.get("task_code"))
        values: dict[str, str] = {
            "task_id": task_id,
            "project_id": row.project_id,
            "feature_name": _text(raw.get("feature_name")),
            "task_name": _text(raw.get("task_name")),
        }

        def report(column: str, value: str | None, message: str | None) -> None:
            if message:
                result.problems.append(
                    Problem("project_plan", row.row_number, task_id or None, column,
                            _text(value), message)
                )  # fmt: skip

        xlsx = row.file_name.lower().endswith(".xlsx")

        def read_date(value: str | None) -> tuple[str, str | None]:
            return normalize_date(value, xlsx)

        checks = [
            ("required_role_id", "role_label", lambda v: lookup(v, roles, "Peran")),
            (
                "complexity_id",
                "complexity_label",
                lambda v: lookup(v, complexities, "Kompleksitas"),
            ),
            ("priority_rank", "priority", normalize_integer),
            ("estimated_days", "estimated_days", normalize_decimal),
            ("planned_start", "planned_start", read_date),
            ("planned_finish", "planned_finish", read_date),
            ("actual_start", "actual_start", read_date),
            ("actual_finish", "actual_finish", read_date),
            ("status", "status_label", normalize_status),
        ]
        for column, staging_column, normalize in checks:
            value, message = normalize(raw.get(staging_column))
            values[column] = value
            report(column, raw.get(staging_column), message)

        card = cards.get(task_id)
        if card and card.status and (not values["status"] or card.at >= row.imported_at):
            values["status"] = card.status.value
        if card and card.phase:
            values["phase"] = card.phase.value
        else:
            phase = PHASE_BY_ROLE.get(values["required_role_id"])
            values["phase"] = phase.value if phase else ""
            if values["required_role_id"] and phase is None:
                report(
                    "phase", values["required_role_id"], "Phase tidak bisa diturunkan dari peran"
                )
        values["qa_reject_count"] = "0"  # diturunkan dari riwayat Trello di DIG-132
        values["dod_fulfilled"] = "false"  # tidak ada sumber; diisi lewat aplikasi
        result.tables["tasks"].append(SourceRow(row.row_number, task_id or None, values))

        for depends_on, kind, message in split_dependencies(raw.get("depends_on")):
            report("task_dependencies", depends_on, message)
            result.tables["task_dependencies"].append(
                SourceRow(
                    row.row_number,
                    None,  # dependency_id dibuat saat upsert (DIG-134)
                    {
                        "dependency_id": "",
                        "task_id": task_id,
                        "depends_on_task_id": depends_on,
                        "dependency_type": kind,
                        "propagation_factor": PROPAGATION.get(kind, ""),
                    },
                )
            )

        pic = _text(raw.get("pic"))
        if pic:
            # resource_id diisi entity resolution DIG-131; tanggal dan takeover di DIG-133.
            result.tables["assignments"].append(
                SourceRow(
                    row.row_number,
                    None,
                    {
                        "assignment_id": "",
                        "task_id": task_id,
                        "resource_id": "",
                        "role_in_task": values["required_role_id"],
                        "assigned_date": values["actual_start"] or values["planned_start"],
                        "released_date": "",
                        "is_takeover": "false",
                        "pic": pic,
                    },
                )
            )
    return result
