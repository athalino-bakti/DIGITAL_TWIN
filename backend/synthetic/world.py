"""Dunia simulasi Tim DEVTI: rencana, realisasi, dan kejadian sampai tanggal `as_of`.

Skenario mengikuti hasil wawancara dengan Tim DEVTI PuTI: breakdown task per peran,
peran rangkap, dependency hard/soft, cuti terencana dan mendadak, cuti hamil, rotasi,
anggota baru, change request, perubahan prioritas, blocker, overrun, dan hotfix.
Nama orang, proyek, dan unit adalah fiktif.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from synthetic import reference as ref
from synthetic.workcal import Absence, WorkCalendar


@dataclass
class Resource:
    resource_id: str
    resource_name: str
    primary_role_id: str
    secondary_role_ids: list[str]
    cross_role_capable: bool
    join_date: date
    seniority: str

    def can_do(self, role_id: str) -> bool:
        return role_id == self.primary_role_id or role_id in self.secondary_role_ids

    @property
    def aliases(self) -> dict[str, str]:
        """Identitas anggota di tiap tool; sengaja berbeda agar perlu entity resolution."""
        first, last = self.resource_name.split()[0], self.resource_name.split()[-1]
        return {
            "project_plan_pic": f"{first} {last[0]}.",
            "trello_fullname": self.resource_name,
            "trello_username": f"{first}{last[:4]}".lower(),
            "git_author": f"{first.lower()}{last[0].lower()}",
            "git_email": f"{first.lower()}.{last.lower()}@devti.example",
        }


@dataclass
class Project:
    project_id: str
    project_name: str
    process_owner: str
    priority_rank: int
    start_date: date
    dor_fulfilled: bool
    hold_date: date | None = None
    target_launch_date: date | None = None
    actual_launch_date: date | None = None
    status: str = "planning"


@dataclass
class Task:
    task_id: str
    project_id: str
    feature_name: str
    feature_key: str
    task_name: str
    required_role_id: str
    complexity_id: str
    priority_rank: int
    estimated_days: float
    phase: str
    interactive: bool
    min_start: date
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    status: str = "not_started"
    qa_reject_count: int = 0
    dod_fulfilled: bool = False
    dropped: bool = False
    planned_resource: str | None = None
    overrun_factor: float = 1.0
    extra_days: int = 0

    @property
    def planned_days(self) -> int:
        return max(1, math.ceil(self.estimated_days))


@dataclass
class Dependency:
    dependency_id: str
    task_id: str
    depends_on_task_id: str
    dependency_type: str
    propagation_factor: float


@dataclass
class Assignment:
    task_id: str
    resource_id: str
    role_in_task: str
    assigned_date: date
    released_date: date | None
    is_takeover: bool
    assignment_id: str = ""


@dataclass
class WorkloadItem:
    item_id: str
    resource_id: str
    item_type: str
    related_project_id: str | None
    received_date: date
    started_date: date | None
    resolved_date: date | None
    severity: str
    is_hotfix: bool
    title: str = ""


@dataclass
class ChangeEvent:
    project_id: str
    event_type: str
    event_date: date
    requested_by: str | None
    decision: str | None
    resolution_mode: str | None
    affected_task_id: str | None
    extension_days: float | None
    note: str = ""
    event_id: str = ""


@dataclass
class World:
    seed: int
    as_of: date
    calendar: WorkCalendar
    resources: list[Resource]
    projects: list[Project]
    tasks: list[Task]
    dependencies: list[Dependency]
    assignments: list[Assignment]
    workload_items: list[WorkloadItem]
    absences: list[Absence]
    events: list[ChangeEvent]
    scenario_notes: list[str] = field(default_factory=list)

    def task(self, task_id: str) -> Task:
        return self._task_index[task_id]

    def resource(self, resource_id: str) -> Resource:
        return self._resource_index[resource_id]

    def __post_init__(self) -> None:
        self._task_index = {t.task_id: t for t in self.tasks}
        self._resource_index = {r.resource_id: r for r in self.resources}


# --------------------------------------------------------------------------- skenario dasar

RESOURCES = [
    ("Hendra Wiratama", "ROLE-KAUR", [], False, date(2019, 3, 1), "senior"),
    ("Sari Puspitasari", "ROLE-SA", ["ROLE-FE"], True, date(2020, 7, 13), "senior"),
    ("Yoga Pratama", "ROLE-SA", ["ROLE-DM"], True, date(2022, 2, 7), "mid"),
    ("Nadia Kirana", "ROLE-TW", [], False, date(2023, 5, 2), "mid"),
    ("Fajar Nugroho", "ROLE-UIUX", ["ROLE-FE"], True, date(2021, 9, 6), "mid"),
    ("Intan Maharani", "ROLE-QA", [], False, date(2022, 8, 1), "mid"),
    ("Rizky Ramadhan", "ROLE-QA", [], False, date(2024, 1, 15), "junior"),
    ("Bayu Saputra", "ROLE-FE", [], True, date(2021, 4, 12), "senior"),
    ("Laras Ayuningtyas", "ROLE-FE", [], False, date(2025, 2, 3), "junior"),
    ("Galih Permana", "ROLE-BE", ["ROLE-DM"], True, date(2020, 11, 2), "senior"),
    ("Wulan Safitri", "ROLE-BE", [], False, date(2023, 10, 9), "mid"),
    ("Aditya Kusuma", "ROLE-DM", ["ROLE-BE"], True, date(2022, 6, 20), "mid"),
    ("Putri Anggraini", "ROLE-FE", [], False, date(2026, 10, 12), "junior"),
]

# (id, nama, unit pemilik proses, prioritas, mulai, DoR, [fitur: (nama, kompleksitas, interaktif)])
PROJECTS = [
    (
        "PRJ-001",
        "Aplikasi Pengajuan Cuti Pegawai",
        "Urusan Administrasi SDM",
        5,
        date(2026, 5, 4),
        True,
        [
            ("Pengajuan cuti", "CX-M", True),
            ("Persetujuan atasan", "CX-H", True),
            ("Rekap saldo cuti", "CX-M", False),
        ],
    ),
    (
        "PRJ-002",
        "Sistem Presensi Pegawai",
        "Urusan Kepegawaian",
        1,
        date(2026, 8, 24),
        True,
        [
            ("Presensi geolokasi", "CX-VH", True),
            ("Rekap kehadiran bulanan", "CX-H", False),
            ("Notifikasi keterlambatan", "CX-M", True),
            ("Integrasi data cuti", "CX-H", True),
        ],
    ),
    (
        "PRJ-003",
        "Portal Rekrutmen Dosen",
        "Urusan Pengembangan SDM",
        2,
        date(2026, 9, 7),
        True,
        [
            ("Pendaftaran pelamar", "CX-M", True),
            ("Seleksi berkas", "CX-H", True),
            ("Penjadwalan wawancara", "CX-M", True),
            ("Pengumuman hasil seleksi", "CX-M", False),
        ],
    ),
    (
        "PRJ-004",
        "Dashboard Kinerja Tendik",
        "Urusan Kinerja SDM",
        3,
        date(2026, 11, 2),
        False,
        [
            ("Indikator kinerja", "CX-H", False),
            ("Penilaian atasan", "CX-H", True),
            ("Laporan semester", "CX-M", False),
        ],
    ),
    (
        "PRJ-005",
        "Aplikasi Perjalanan Dinas",
        "Urusan Keuangan SDM",
        4,
        date(2026, 8, 17),
        True,
        [
            ("Pengajuan perjalanan dinas", "CX-H", True),
            ("Pertanggungjawaban biaya", "CX-H", True),
        ],
    ),
]

# Fitur tambahan dari change request scope_addition.
CR_SCOPE_FEATURE = ("PRJ-002", "Ekspor laporan presensi", "CX-M", False, date(2026, 9, 14))
HOLD_PROJECT, HOLD_DATE = "PRJ-005", date(2026, 10, 5)
BLOCKER_PROJECT = "PRJ-003"

# (indeks anggota, mulai, selesai, jenis, diketahui saat planning)
ABSENCES = [
    (5, date(2026, 9, 7), date(2026, 9, 11), "planned_leave", True),
    (1, date(2026, 10, 26), date(2026, 10, 28), "planned_leave", True),
    (11, date(2026, 8, 24), date(2026, 8, 26), "planned_leave", True),
    (7, date(2026, 9, 16), date(2026, 9, 18), "sudden_leave", False),
    (9, date(2026, 10, 13), date(2026, 10, 14), "sudden_leave", False),
    (8, date(2026, 8, 31), date(2026, 11, 27), "maternity_leave", True),
    (10, date(2026, 10, 5), date(2026, 12, 31), "rotation_out", False),
    (12, date(2026, 10, 12), date(2026, 12, 31), "rotation_in", False),
]


def _lower_complexity(complexity_id: str, steps: int) -> str:
    index = ref.COMPLEXITY_ORDER.index(complexity_id) + steps
    return ref.COMPLEXITY_ORDER[max(0, index)]


def _estimate(rng: random.Random, complexity_id: str) -> float:
    _, low, high, _ = ref.COMPLEXITY[complexity_id]
    return round(rng.uniform(low, high) * 2) / 2


# --------------------------------------------------------------------------- pembangun dunia


class _Builder:
    def __init__(self, seed: int, as_of: date):
        self.rng = random.Random(seed)
        self.seed = seed
        self.as_of = as_of
        self.cal = WorkCalendar(day for day, _ in ref.HOLIDAYS)
        self.resources: list[Resource] = []
        self.projects: dict[str, Project] = {}
        self.tasks: list[Task] = []
        self.deps: list[Dependency] = []
        self.assignments: list[Assignment] = []
        self.events: list[ChangeEvent] = []
        self.absences: list[Absence] = []
        self.notes: list[str] = []
        self.preds: dict[str, list[Dependency]] = {}

    # ---- master data

    def build_master(self) -> None:
        for index, (name, primary, secondary, cross, joined, seniority) in enumerate(RESOURCES):
            resource = Resource(
                f"RES-{index + 1:03d}", name, primary, secondary, cross, joined, seniority
            )
            self.resources.append(resource)
            self.cal.add_resource(resource.resource_id, joined)
        for index, start, end, absence_type, known in ABSENCES:
            absence = Absence(self.resources[index].resource_id, start, end, absence_type, known)
            self.absences.append(absence)
            self.cal.add_absence(absence)
        for pid, name, owner, rank, start, dor, _ in PROJECTS:
            hold = HOLD_DATE if pid == HOLD_PROJECT else None
            self.projects[pid] = Project(pid, name, owner, rank, start, dor, hold)

    # ---- breakdown fitur menjadi task per peran

    def build_tasks(self) -> None:
        features = []
        for pid, _, _, _, start, _, feature_specs in PROJECTS:
            for order, (fname, cx, interactive) in enumerate(feature_specs):
                features.append((pid, fname, cx, interactive, start, order + 1))
        pid, fname, cx, interactive, cr_date = CR_SCOPE_FEATURE
        features.append((pid, fname, cx, interactive, cr_date, 5))
        features.sort(key=lambda f: (f[4], f[0], f[5]))

        counter = 0
        for pid, fname, cx, interactive, min_start, priority in features:
            by_phase: dict[str, Task] = {}
            for phase, role, label, shift in ref.PHASES:
                counter += 1
                task_cx = _lower_complexity(cx, shift) if shift else cx
                task = Task(
                    task_id=f"TSK-{counter:04d}",
                    project_id=pid,
                    feature_name=fname,
                    feature_key=f"{pid}:{fname}",
                    task_name=f"{label} {fname.lower()}",
                    required_role_id=role,
                    complexity_id=task_cx,
                    priority_rank=priority,
                    estimated_days=_estimate(self.rng, task_cx),
                    phase=phase,
                    interactive=interactive,
                    min_start=min_start,
                )
                self.tasks.append(task)
                by_phase[phase] = task
            self._link_feature(by_phase, interactive)

    def _link_feature(self, t: dict[str, Task], interactive: bool) -> None:
        links = [
            ("uiux", "planning", "hard"),
            ("dm_dev", "planning", "hard"),
            ("be_dev", "dm_dev", "hard"),
            ("fe_dev", "uiux", "hard"),
            # FE boleh membuat dummy tampilan saat DM membuat basis data (soft);
            # fitur interaktif FE bergantung penuh pada BE (hard).
            ("fe_dev", "be_dev" if interactive else "dm_dev", "hard" if interactive else "soft"),
            ("testing", "fe_dev", "hard"),
            ("testing", "be_dev", "hard"),
            ("bugfix", "testing", "hard"),
            ("documentation", "testing", "soft"),
        ]
        for task_phase, pred_phase, dep_type in links:
            dep = Dependency(
                dependency_id=f"DEP-{len(self.deps) + 1:03d}",
                task_id=t[task_phase].task_id,
                depends_on_task_id=t[pred_phase].task_id,
                dependency_type=dep_type,
                propagation_factor=1.0 if dep_type == "hard" else ref.SOFT_PROPAGATION,
            )
            self.deps.append(dep)
            self.preds.setdefault(dep.task_id, []).append(dep)

    def _order(self) -> list[Task]:
        """Urutan topologis; urutan pembuatan task sudah menempatkan prasyarat lebih dulu."""
        return self.tasks

    # ---- jadwal rencana (hanya ketidakhadiran yang diketahui saat planning)

    def schedule_plan(self) -> None:
        tasks = {t.task_id: t for t in self.tasks}
        # Satu task aktif per anggota pada satu waktu; beban paralel datang dari D-08.
        slots = {r.resource_id: [date.min] for r in self.resources}
        load = {r.resource_id: 0 for r in self.resources}
        for task in self._order():
            project = self.projects[task.project_id]
            ready = max(task.min_start, project.start_date)
            for dep in self.preds.get(task.task_id, []):
                pred = tasks[dep.depends_on_task_id]
                if dep.dependency_type == "hard":
                    ready = max(ready, self.cal.next_workday(pred.planned_finish))
                else:
                    lag = math.ceil(dep.propagation_factor * pred.planned_days) + 1
                    ready = max(ready, self.cal.add_workdays(pred.planned_start, lag))
            best = None
            for resource in self.resources:
                if not resource.can_do(task.required_role_id):
                    continue
                for slot_index, free in enumerate(slots[resource.resource_id]):
                    start = self.cal.first_workday(max(ready, free), resource.resource_id)
                    rank = (
                        start,
                        0 if resource.primary_role_id == task.required_role_id else 1,
                        load[resource.resource_id],
                        resource.resource_id,
                    )
                    if best is None or rank < best[0]:
                        best = (rank, resource.resource_id, slot_index)
            _, rid, slot_index = best
            start = best[0][0]
            finish = self.cal.add_workdays(start, task.planned_days, rid)
            task.planned_start, task.planned_finish, task.planned_resource = start, finish, rid
            slots[rid][slot_index] = self.cal.next_workday(finish, rid)
            load[rid] += task.planned_days
        for project in self.projects.values():
            last = max(t.planned_finish for t in self.tasks if t.project_id == project.project_id)
            project.target_launch_date = self.cal.add_workdays(self.cal.next_workday(last), 3)

    # ---- kejadian yang mengubah rencana sebelum realisasi

    def plan_scenarios(self) -> dict[str, object]:
        by_key = {}
        for task in self.tasks:
            by_key.setdefault((task.project_id, task.feature_name, task.phase), task)
        # CR scope_addition: fitur ekspor laporan ditambahkan ke PRJ-002.
        pid, fname, _, _, cr_date = CR_SCOPE_FEATURE
        added = by_key[(pid, fname, "planning")]
        self.events.append(
            ChangeEvent(
                pid,
                "change_request",
                cr_date,
                "Pemilik proses",
                "accept_now",
                "scope_addition",
                added.task_id,
                None,
                "Pemilik proses meminta ekspor laporan presensi ke Excel",
            )
        )
        # CR swap_task: dokumentasi fitur terakhir PRJ-003 dibatalkan untuk fitur baru.
        dropped = by_key[("PRJ-003", "Penjadwalan wawancara", "documentation")]
        dropped.dropped = True
        self.events.append(
            ChangeEvent(
                "PRJ-003",
                "change_request",
                date(2026, 9, 21),
                "Kaur",
                "accept_now",
                "swap_task",
                dropped.task_id,
                None,
                "Dokumentasi penjadwalan wawancara ditukar dengan perbaikan alur seleksi",
            )
        )
        self.events.append(
            ChangeEvent(
                "PRJ-003",
                "change_request",
                date(2026, 10, 20),
                "Pemilik proses",
                "defer_next",
                None,
                None,
                None,
                "Permintaan integrasi kalender ditunda ke pengembangan berikutnya",
            )
        )
        self.events.append(
            ChangeEvent(
                "PRJ-002",
                "change_request",
                date(2026, 10, 26),
                "Asisten Manajer",
                "reject",
                None,
                None,
                None,
                "Permintaan presensi wajah ditolak karena di luar ruang lingkup",
            )
        )
        # Perubahan prioritas: PRJ-005 ditunda untuk mendahulukan PRJ-002.
        self.events.append(
            ChangeEvent(
                HOLD_PROJECT,
                "priority_change",
                HOLD_DATE,
                "Kaur",
                "accept_now",
                "reshuffle",
                None,
                None,
                "Perjalanan Dinas ditunda, kapasitas dialihkan ke Sistem Presensi",
            )
        )
        extend = by_key[("PRJ-002", "Presensi geolokasi", "be_dev")]
        extend.extra_days = 3
        blocker_resolved = by_key[("PRJ-002", "Rekap kehadiran bulanan", "dm_dev")]
        blocker_resolved.extra_days = 3
        return {"extend": extend, "blocker_resolved": blocker_resolved}

    # ---- realisasi sampai as_of

    def realize(self, scenario: dict[str, object]) -> None:
        tasks = {t.task_id: t for t in self.tasks}
        for task in self._order():
            planned = self._planned_assignment(task)
            self.assignments.append(planned)
            if task.dropped:
                task.status = "dropped"
                planned.released_date = max(planned.assigned_date, date(2026, 9, 21))
                continue
            project = self.projects[task.project_id]
            ready = task.planned_start
            startable = True
            for dep in self.preds.get(task.task_id, []):
                pred = tasks[dep.depends_on_task_id]
                if dep.dependency_type == "hard":
                    if pred.actual_finish is None or pred.status in ("blocked", "on_hold"):
                        startable = False
                        break
                    ready = max(ready, self.cal.next_workday(pred.actual_finish))
                else:
                    if pred.actual_start is None:
                        startable = False
                        break
                    lag = math.ceil(dep.propagation_factor * pred.planned_days) + 1
                    ready = max(ready, self.cal.add_workdays(pred.actual_start, lag))
            if not startable:
                task.status = "on_hold" if project.hold_date else "not_started"
                continue
            start = self.cal.add_workdays(ready, 1 + self.rng.choice([0, 0, 0, 1, 1, 2]))
            if project.hold_date and start >= project.hold_date:
                task.status = "on_hold"
                continue
            if start > self.as_of:
                continue
            overrun = self.rng.random() < 0.12
            task.overrun_factor = (
                self.rng.uniform(1.5, 2.0) if overrun else self.rng.uniform(0.8, 1.2)
            )
            duration = max(1, round(task.planned_days * task.overrun_factor)) + task.extra_days
            finish = self._work(task, planned, start, duration)
            task.actual_start = start
            if project.hold_date and finish >= project.hold_date:
                task.status = "on_hold"
                continue
            if finish <= self.as_of:
                task.actual_finish, task.status = finish, "done"
            else:
                task.status = "in_progress"
            self._record_overrun(task, duration)
        self._mark_blocked()
        self._record_scenario_events(scenario)

    def _mark_blocked(self) -> None:
        """Satu task pengembangan yang sedang berjalan menjadi blocked pada as_of."""
        running = [t for t in self.tasks if t.status == "in_progress"]
        running.sort(
            key=lambda t: (
                t.project_id != BLOCKER_PROJECT,
                t.phase not in ("be_dev", "fe_dev", "dm_dev"),
                t.task_id,
            )
        )
        if not running:
            return
        task = running[0]
        task.status = "blocked"
        when = max(task.actual_start, self.cal.previous_workday(self.as_of - timedelta(days=3)))
        self.events.append(
            ChangeEvent(
                task.project_id,
                "blocker",
                when,
                "System Analyst",
                None,
                None,
                task.task_id,
                None,
                "Menunggu akses server integrasi dari unit infrastruktur",
            )
        )

    def _planned_assignment(self, task: Task) -> Assignment:
        lead = self.rng.choice([1, 2, 3])
        assigned = task.planned_start - timedelta(days=lead)
        assigned = max(assigned, self.projects[task.project_id].start_date)
        return Assignment(
            task.task_id, task.planned_resource, task.required_role_id, assigned, None, False
        )

    def _work(self, task: Task, planned: Assignment, start: date, duration: int) -> date:
        """Hitung tanggal selesai; alihkan task bila pelaksana tiba-tiba tidak hadir."""
        rid = planned.resource_id
        finish = self.cal.add_workdays(start, duration, rid, "actual")
        absence = None
        for candidate in self.cal.absences.get(rid, []):
            if candidate.known_at_planning or candidate.absence_type == "rotation_in":
                continue
            if candidate.start <= finish and candidate.end >= start:
                absence = candidate
                break
        if absence is None:
            return finish
        handover = max(start, absence.start)
        handover = self.cal.first_workday(handover)
        done = (
            0
            if handover <= start
            else self.cal.count_workdays(start, handover - timedelta(days=1), rid, "actual")
        )
        remaining = max(1, duration - done) + 1
        new_rid = self._takeover_resource(task, rid, handover)
        planned.released_date = max(planned.assigned_date, handover - timedelta(days=1))
        self.assignments.append(
            Assignment(task.task_id, new_rid, task.required_role_id, handover, None, True)
        )
        self.notes.append(
            f"{task.task_id} dialihkan dari {rid} ke {new_rid} pada {handover.isoformat()} "
            f"({absence.absence_type})"
        )
        return self.cal.add_workdays(handover, remaining, new_rid, "actual")

    def _takeover_resource(self, task: Task, from_rid: str, day: date) -> str:
        def available(resource: Resource) -> bool:
            return resource.resource_id != from_rid and self.cal.is_workday(
                self.cal.first_workday(day), resource.resource_id, "actual"
            )

        same_role = [r for r in self.resources if r.can_do(task.required_role_id) and available(r)]
        if same_role:
            same_role.sort(
                key=lambda r: (r.primary_role_id != task.required_role_id, r.resource_id)
            )
            return same_role[0].resource_id
        cross = [r for r in self.resources if r.cross_role_capable and available(r)]
        return sorted(cross, key=lambda r: r.resource_id)[0].resource_id

    def _record_overrun(self, task: Task, duration: int) -> None:
        if task.overrun_factor < 1.5:
            return
        overdue_from = self.cal.next_workday(task.planned_finish)
        if overdue_from > self.as_of:
            return
        extension = duration - task.planned_days - task.extra_days
        if extension <= 0:
            return
        self.events.append(
            ChangeEvent(
                task.project_id,
                "overrun",
                overdue_from,
                "System Analyst",
                "accept_now",
                "extend_duration",
                task.task_id,
                float(extension),
                "Pengerjaan melewati estimasi dan diperpanjang",
            )
        )

    def _record_scenario_events(self, scenario: dict[str, object]) -> None:
        extend = scenario["extend"]
        if extend.actual_start is not None:
            self.events.append(
                ChangeEvent(
                    extend.project_id,
                    "change_request",
                    self.cal.add_workdays(extend.actual_start, 3),
                    "System Analyst",
                    "accept_now",
                    "extend_duration",
                    extend.task_id,
                    3.0,
                    "Validasi radius lokasi ditambahkan, durasi BE diperpanjang 3 hari",
                )
            )
        blocker = scenario["blocker_resolved"]
        if blocker.actual_start is not None:
            self.events.append(
                ChangeEvent(
                    blocker.project_id,
                    "blocker",
                    self.cal.add_workdays(blocker.actual_start, 2),
                    "System Analyst",
                    None,
                    None,
                    blocker.task_id,
                    None,
                    "Struktur tabel absensi lama berubah mendadak dari pemilik proses",
                )
            )

    # ---- status fitur dan proyek

    def finalize_status(self) -> None:
        features: dict[str, list[Task]] = {}
        for task in self.tasks:
            features.setdefault(task.feature_key, []).append(task)
        for feature_tasks in features.values():
            phase = {t.phase: t for t in feature_tasks}
            testing = phase["testing"]
            if testing.actual_start is not None:
                for dev_phase in ("fe_dev", "be_dev"):
                    dev = phase[dev_phase]
                    weights = [40, 35, 18, 7] if dev_phase == "fe_dev" else [60, 30, 10, 0]
                    dev.qa_reject_count = self.rng.choices([0, 1, 2, 3], weights)[0]
                    if testing.status == "in_progress" and dev.status == "done":
                        dev.status = "in_qa"
            if phase["bugfix"].status == "done":
                for task in feature_tasks:
                    if not task.dropped:
                        task.dod_fulfilled = True

        for project in self.projects.values():
            tasks = [t for t in self.tasks if t.project_id == project.project_id and not t.dropped]
            dev_done = all(
                t.status in ("done", "in_qa")
                for t in tasks
                if t.phase in ("dm_dev", "be_dev", "fe_dev")
            )
            started = [t for t in tasks if t.actual_start is not None]
            if project.hold_date:
                project.status = "on_hold"
            elif all(t.status == "done" for t in tasks):
                last = max(t.actual_finish for t in tasks)
                launch = self.cal.add_workdays(self.cal.next_workday(last), 2)
                if launch <= self.as_of:
                    project.status, project.actual_launch_date = "released", launch
                else:
                    project.status = "testing"
            elif not started or all(t.phase in ("planning", "uiux") for t in started):
                project.status = "planning"
            elif dev_done:
                project.status = "testing"
            else:
                project.status = "development"

    # ---- beban non-proyek: operasional dan tiket

    def build_workload(self) -> list[WorkloadItem]:
        items: list[WorkloadItem] = []
        workers = [r for r in self.resources if r.primary_role_id not in ("ROLE-KAUR", "ROLE-TW")]
        released = self.projects["PRJ-001"]
        week = date(2026, 7, 6)
        while week <= self.as_of:
            for _ in range(self.rng.randint(3, 6)):
                received = self.cal.add_workdays(week, self.rng.randint(1, 5))
                if received > self.as_of:
                    continue
                pool = [
                    r for r in workers if self.cal.is_workday(received, r.resource_id, "actual")
                ]
                if not pool:
                    continue
                resource = self.rng.choice(pool)
                ticket = self.rng.random() < 0.45
                if ticket:
                    severity = self.rng.choices(
                        ["low", "medium", "high", "critical"], [35, 35, 22, 8]
                    )[0]
                    delay = {
                        "critical": 0,
                        "high": self.rng.randint(0, 1),
                        "medium": self.rng.randint(1, 3),
                        "low": self.rng.randint(2, 5),
                    }
                    wait = delay[severity]
                else:
                    severity = self.rng.choice(["low", "medium"])
                    wait = self.rng.randint(0, 2)
                items.append(
                    self._workload(resource.resource_id, ticket, received, wait, severity, released)
                )
            week += timedelta(days=7)
        hotfix_day = date(2026, 9, 29)
        if released.actual_launch_date and released.actual_launch_date < hotfix_day <= self.as_of:
            hotfix = self._workload("RES-010", True, hotfix_day, 0, "critical", released)
            hotfix.related_project_id, hotfix.is_hotfix = "PRJ-001", True
            hotfix.title = "Hotfix: pengajuan cuti gagal tersimpan setelah pembaruan server"
            items.append(hotfix)
            self.events.append(
                ChangeEvent(
                    "PRJ-001",
                    "hotfix",
                    hotfix_day,
                    "Pemilik proses",
                    "accept_now",
                    None,
                    None,
                    None,
                    hotfix.title,
                )
            )
        items.sort(key=lambda i: (i.received_date, i.resource_id))
        for index, item in enumerate(items):
            item.item_id = f"WLI-{index + 1:04d}"
        return items

    def _workload(
        self, rid: str, ticket: bool, received: date, wait: int, severity: str, released: Project
    ) -> WorkloadItem:
        started = self.cal.add_workdays(received, 1 + wait, rid, "actual")
        span = self.rng.randint(0, 1) if severity == "critical" else self.rng.randint(0, 3)
        resolved = self.cal.add_workdays(started, 1 + span, rid, "actual")
        related = None
        if ticket and released.actual_launch_date and received >= released.actual_launch_date:
            related = "PRJ-001" if self.rng.random() < 0.5 else None
        title = ("Tiket: " if ticket else "Operasional: ") + self.rng.choice(
            [
                "reset akun pengguna",
                "laporan tidak muncul",
                "pemeliharaan basis data",
                "pembaruan sertifikat server",
                "permintaan data presensi",
                "perbaikan hak akses",
                "pencadangan server",
                "kendala unggah berkas",
            ]
        )
        return WorkloadItem(
            item_id="",
            resource_id=rid,
            item_type="ticket" if ticket else "operational",
            related_project_id=related,
            received_date=received,
            started_date=started if started <= self.as_of else None,
            resolved_date=resolved if resolved <= self.as_of else None,
            severity=severity,
            is_hotfix=False,
            title=title,
        )

    # ---- penomoran akhir

    def finalize_ids(self) -> None:
        self.assignments.sort(key=lambda a: (a.task_id, a.assigned_date, a.is_takeover))
        for index, assignment in enumerate(self.assignments):
            assignment.assignment_id = f"ASG-{index + 1:04d}"
        self.events.sort(key=lambda e: (e.event_date, e.project_id, e.event_type))
        for index, event in enumerate(self.events):
            event.event_id = f"EVT-{index + 1:03d}"


def build_world(seed: int = 42, as_of: date = date(2026, 11, 6)) -> World:
    """Bangun dunia simulasi yang deterministik untuk seed dan tanggal acuan yang sama."""
    builder = _Builder(seed, as_of)
    builder.build_master()
    builder.build_tasks()
    builder.schedule_plan()
    scenario = builder.plan_scenarios()
    builder.realize(scenario)
    builder.finalize_status()
    workload = builder.build_workload()
    builder.finalize_ids()
    return World(
        seed=seed,
        as_of=as_of,
        calendar=builder.cal,
        resources=builder.resources,
        projects=list(builder.projects.values()),
        tasks=builder.tasks,
        dependencies=builder.deps,
        assignments=builder.assignments,
        workload_items=workload,
        absences=builder.absences,
        events=builder.events,
        scenario_notes=builder.notes,
    )
