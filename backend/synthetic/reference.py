"""Data referensi dan aturan Data Dictionary yang dipakai generator.

Nilai enum, format ID, dan urutan kolom disalin dari Data Dictionary (D-01 s.d. D-11).
Setelah DIG-15 masuk main, daftar enum dapat diganti dengan app.modules.data.enums.
"""

import re
from datetime import date

# Urutan kolom CSV final sources persis seperti Data Dictionary.
HEADERS: dict[str, list[str]] = {
    "projects": [
        "project_id",
        "project_name",
        "process_owner",
        "priority_rank",
        "start_date",
        "target_launch_date",
        "actual_launch_date",
        "status",
        "dor_fulfilled",
    ],
    "resources": [
        "resource_id",
        "resource_name",
        "primary_role_id",
        "secondary_role_ids",
        "cross_role_capable",
        "join_date",
        "seniority",
    ],
    "roles": ["role_id", "role_name", "capacity_reference", "description"],
    "complexity_levels": [
        "complexity_id",
        "complexity_name",
        "min_days",
        "max_days",
        "load_weight",
    ],
    "tasks": [
        "task_id",
        "project_id",
        "feature_name",
        "task_name",
        "required_role_id",
        "complexity_id",
        "priority_rank",
        "estimated_days",
        "phase",
        "planned_start",
        "planned_finish",
        "actual_start",
        "actual_finish",
        "status",
        "qa_reject_count",
        "dod_fulfilled",
    ],
    "task_dependencies": [
        "dependency_id",
        "task_id",
        "depends_on_task_id",
        "dependency_type",
        "propagation_factor",
    ],
    "assignments": [
        "assignment_id",
        "task_id",
        "resource_id",
        "role_in_task",
        "assigned_date",
        "released_date",
        "is_takeover",
    ],
    "workload_items": [
        "item_id",
        "resource_id",
        "item_type",
        "related_project_id",
        "received_date",
        "started_date",
        "resolved_date",
        "severity",
        "is_hotfix",
    ],
    "availability": [
        "availability_id",
        "resource_id",
        "date_start",
        "date_end",
        "absence_type",
        "is_known_at_planning",
    ],
    "change_events": [
        "event_id",
        "project_id",
        "event_type",
        "event_date",
        "requested_by",
        "decision",
        "resolution_mode",
        "affected_task_id",
        "extension_days",
    ],
    "holidays": ["holiday_date", "holiday_name"],
}

# Kode tabel Data Dictionary untuk penamaan berkas dan dokumentasi.
TABLE_CODES = {
    "projects": "D-01",
    "resources": "D-02",
    "roles": "D-03",
    "complexity_levels": "D-04",
    "tasks": "D-05",
    "task_dependencies": "D-06",
    "assignments": "D-07",
    "workload_items": "D-08",
    "availability": "D-09",
    "change_events": "D-10",
    "holidays": "D-11",
}

ID_PATTERNS = {
    "project_id": re.compile(r"^PRJ-[0-9]{3}$"),
    "resource_id": re.compile(r"^RES-[0-9]{3}$"),
    "role_id": re.compile(r"^ROLE-[A-Z]+$"),
    "complexity_id": re.compile(r"^CX-[A-Z]+$"),
    "task_id": re.compile(r"^TSK-[0-9]{4}$"),
    "dependency_id": re.compile(r"^DEP-[0-9]{3}$"),
    "assignment_id": re.compile(r"^ASG-[0-9]{4}$"),
    "item_id": re.compile(r"^WLI-[0-9]{4}$"),
    "availability_id": re.compile(r"^AVL-[0-9]{3}$"),
    "event_id": re.compile(r"^EVT-[0-9]{3}$"),
}

ENUMS = {
    ("projects", "status"): ["planning", "development", "testing", "released", "on_hold"],
    ("resources", "seniority"): ["junior", "mid", "senior"],
    ("tasks", "phase"): [
        "planning",
        "uiux",
        "dm_dev",
        "be_dev",
        "fe_dev",
        "testing",
        "bugfix",
        "documentation",
    ],
    ("tasks", "status"): [
        "not_started",
        "in_progress",
        "blocked",
        "on_hold",
        "in_qa",
        "done",
        "dropped",
    ],
    ("task_dependencies", "dependency_type"): ["hard", "soft"],
    ("workload_items", "item_type"): ["operational", "ticket"],
    ("workload_items", "severity"): ["low", "medium", "high", "critical"],
    ("availability", "absence_type"): [
        "planned_leave",
        "sudden_leave",
        "maternity_leave",
        "rotation_out",
        "rotation_in",
    ],
    ("change_events", "event_type"): [
        "change_request",
        "priority_change",
        "blocker",
        "overrun",
        "hotfix",
    ],
    ("change_events", "decision"): ["accept_now", "defer_next", "reject"],
    ("change_events", "resolution_mode"): [
        "swap_task",
        "extend_duration",
        "scope_addition",
        "reshuffle",
    ],
}

# D-03 roles: ID dari Data Dictionary; nama dan deskripsi dari wawancara Tim DEVTI PuTI.
ROLES = [
    (
        "ROLE-KAUR",
        "Kepala Urusan / Asisten Manajer",
        "Mengawasi jalannya proyek dari sisi manajemen dan kebijakan organisasi.",
    ),
    (
        "ROLE-SA",
        "System Analyst",
        "Memimpin diskusi teknis, mematangkan proses bisnis, melakukan breakdown task, "
        "dan memimpin penentuan estimasi kompleksitas fitur bersama tim.",
    ),
    (
        "ROLE-TW",
        "Technical Writer",
        "Mendokumentasikan hasil requirement gathering dan dokumentasi teknis aplikasi.",
    ),
    (
        "ROLE-UIUX",
        "UI/UX Designer",
        "Merancang antarmuka dan pengalaman pengguna berdasarkan proses bisnis "
        "yang telah disepakati.",
    ),
    (
        "ROLE-QA",
        "Quality Assurance",
        "Menguji fitur yang selesai dikembangkan untuk memastikan produk bebas dari bug.",
    ),
    ("ROLE-FE", "Front-End Developer", "Mengembangkan sisi antarmuka dan tampilan fitur aplikasi."),
    (
        "ROLE-BE",
        "Back-End Developer",
        "Mengembangkan sisi server dan integrasi logika sistem untuk mendukung "
        "kebutuhan data Front-End.",
    ),
    (
        "ROLE-DM",
        "Data Manager",
        "Merancang, membuat, dan mengelola struktur basis data utama aplikasi.",
    ),
]
CAPACITY_REFERENCE = 3.0

# D-04 complexity_levels: rentang hari dan bobot adalah ASUMSI TIM (sama dengan seed DIG-78).
COMPLEXITY = {
    "CX-VH": ("Very High", 10.0, 20.0, 2.0),
    "CX-H": ("High", 5.0, 10.0, 1.5),
    "CX-M": ("Medium", 2.0, 5.0, 1.0),
    "CX-L": ("Low", 0.5, 2.0, 0.5),
}
COMPLEXITY_ORDER = ["CX-L", "CX-M", "CX-H", "CX-VH"]

# Fase task per fitur, sesuai siklus kerja hasil wawancara (breakdown per peran).
PHASES = [
    ("planning", "ROLE-SA", "Analisis kebutuhan dan breakdown task", -1),
    ("uiux", "ROLE-UIUX", "Rancangan antarmuka", -1),
    ("dm_dev", "ROLE-DM", "Rancangan dan pembuatan basis data", 0),
    ("be_dev", "ROLE-BE", "Pengembangan API", 0),
    ("fe_dev", "ROLE-FE", "Pengembangan antarmuka", 0),
    ("testing", "ROLE-QA", "Pengujian fitur", -1),
    ("bugfix", "ROLE-FE", "Perbaikan bug hasil pengujian", -2),
    ("documentation", "ROLE-TW", "Dokumentasi fitur", -2),
]

SOFT_PROPAGATION = 0.3

# D-11 holidays: libur nasional dan cuti bersama 2026 menurut SKB 3 Menteri
# (setneg.go.id, "Inilah SKB 3 Menteri Libur Nasional dan Cuti Bersama 2026").
HOLIDAYS: list[tuple[date, str]] = [
    (date(2026, 1, 1), "Tahun Baru 2026 Masehi"),
    (date(2026, 1, 16), "Isra Mikraj Nabi Muhammad SAW"),
    (date(2026, 2, 16), "Cuti Bersama Tahun Baru Imlek 2577 Kongzili"),
    (date(2026, 2, 17), "Tahun Baru Imlek 2577 Kongzili"),
    (date(2026, 3, 18), "Cuti Bersama Hari Suci Nyepi"),
    (date(2026, 3, 19), "Hari Suci Nyepi (Tahun Baru Saka 1948)"),
    (date(2026, 3, 20), "Cuti Bersama Idulfitri 1447 H"),
    (date(2026, 3, 21), "Idulfitri 1447 H"),
    (date(2026, 3, 22), "Idulfitri 1447 H"),
    (date(2026, 3, 23), "Cuti Bersama Idulfitri 1447 H"),
    (date(2026, 3, 24), "Cuti Bersama Idulfitri 1447 H"),
    (date(2026, 4, 3), "Wafat Yesus Kristus"),
    (date(2026, 4, 5), "Kebangkitan Yesus Kristus (Paskah)"),
    (date(2026, 5, 1), "Hari Buruh Internasional"),
    (date(2026, 5, 14), "Kenaikan Yesus Kristus"),
    (date(2026, 5, 15), "Cuti Bersama Kenaikan Yesus Kristus"),
    (date(2026, 5, 27), "Iduladha 1447 H"),
    (date(2026, 5, 28), "Cuti Bersama Iduladha 1447 H"),
    (date(2026, 5, 31), "Hari Raya Waisak 2570 BE"),
    (date(2026, 6, 1), "Hari Lahir Pancasila"),
    (date(2026, 6, 16), "1 Muharam Tahun Baru Islam 1448 H"),
    (date(2026, 8, 17), "Proklamasi Kemerdekaan"),
    (date(2026, 8, 25), "Maulid Nabi Muhammad SAW"),
    (date(2026, 12, 24), "Cuti Bersama Kelahiran Yesus Kristus"),
    (date(2026, 12, 25), "Kelahiran Yesus Kristus"),
    (date(2027, 1, 1), "Tahun Baru 2027 Masehi"),
]
